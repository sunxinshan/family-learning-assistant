"""CheckpointRepository 的方言与降级契约（T-FIX-03 / T-FIX-06）。

前四轮测试只在 sqlite 上跑过，于是「管理端 SQL 写死 sqlite 方言」这个缺陷
在生产 MySQL 下必然 404（`writes` vs `checkpoint_writes`）。本文件用**假的
SQLAlchemy 引擎**抓真实 SQL 文本，把两套方言都钉住，不需要连 MySQL。

另覆盖「库不可用」与「不存在」必须分成 503 / 404 —— REVIEW C-2 的核心诉求。
"""

from __future__ import annotations

from typing import Any

import pytest

from app.core.config import Settings
from app.core.exceptions import AppError
from app.modules.admin.checkpoint_repository import CheckpointRepository


class _FakeResult:
    def __init__(self, rows: list[dict[str, Any]], scalar: Any = None) -> None:
        self._rows = rows
        self._scalar = scalar

    def mappings(self) -> _FakeResult:
        return self

    def first(self) -> dict[str, Any] | None:
        return self._rows[0] if self._rows else None

    def all(self) -> list[dict[str, Any]]:
        return list(self._rows)

    def scalar_one(self) -> Any:
        return self._scalar

    def __iter__(self):
        return iter([tuple(row.values()) for row in self._rows])


class _FakeConnection:
    def __init__(self, recorder: list[str], results: list[_FakeResult]) -> None:
        self.recorder = recorder
        self.results = results

    def __enter__(self) -> _FakeConnection:
        return self

    def __exit__(self, *exc_info: object) -> bool:
        return False

    def execute(self, statement: Any, params: Any = None) -> _FakeResult:
        self.recorder.append(" ".join(str(statement).split()))
        return self.results.pop(0) if self.results else _FakeResult([], scalar=0)


class _FakeEngine:
    def __init__(self, recorder: list[str], results: list[_FakeResult]) -> None:
        self.recorder = recorder
        self.results = results

    def connect(self) -> _FakeConnection:
        return _FakeConnection(self.recorder, self.results)


def _mysql_repo(
    monkeypatch: pytest.MonkeyPatch, results: list[_FakeResult]
) -> tuple[CheckpointRepository, list[str]]:
    settings = Settings(
        _env_file=None,
        environment="test",
        checkpoint_backend="mysql",
        checkpoint_url="mysql://fla:pw@127.0.0.1:3306/familylearning_checkpoints?charset=utf8mb4",
    )
    repo = CheckpointRepository(settings)
    recorder: list[str] = []
    monkeypatch.setattr(repo, "_engine", lambda url: _FakeEngine(recorder, results))
    return repo, recorder


def test_mysql_url_is_rewritten_to_pymysql_driver() -> None:
    """生产配置写的是 ``mysql://``；交给 SQLAlchemy 前必须补 +pymysql。"""
    settings = Settings(
        _env_file=None,
        environment="test",
        checkpoint_backend="mysql",
        checkpoint_url="mysql://fla:pw@127.0.0.1:3306/db?charset=utf8mb4",
    )
    url = CheckpointRepository(settings)._url()
    assert url is not None
    assert url.startswith("mysql+pymysql://")
    # 改驱动名不能把密码抹成 ***（render_as_string 默认会）。
    assert ":pw@" in url


def test_mysql_url_with_driver_already_present_is_untouched() -> None:
    settings = Settings(
        _env_file=None,
        environment="test",
        checkpoint_backend="mysql",
        checkpoint_url="mysql+pymysql://fla:pw@127.0.0.1:3306/db",
    )
    assert CheckpointRepository(settings)._url() == "mysql+pymysql://fla:pw@127.0.0.1:3306/db"


@pytest.mark.parametrize(
    ("backend", "table", "value_column"),
    [
        ("sqlite", "writes", "value"),
        ("mysql", "checkpoint_writes", "`blob`"),
    ],
)
def test_writes_query_follows_backend_dialect(backend: str, table: str, value_column: str) -> None:
    settings = (
        Settings(
            _env_file=None,
            environment="test",
            checkpoint_backend="mysql",
            checkpoint_url="mysql://fla:pw@127.0.0.1:3306/db",
        )
        if backend == "mysql"
        else Settings(_env_file=None, environment="test", checkpoint_backend="sqlite")
    )
    repo = CheckpointRepository(settings)

    assert repo._writes_table() == table
    query = repo._writes_query()
    assert f"from {table}" in query
    assert f"{value_column} as value" in query


def test_get_reads_checkpoint_writes_on_mysql(monkeypatch: pytest.MonkeyPatch) -> None:
    """MySQL 后端下详情页必须查 ``checkpoint_writes(blob)``，否则每条都 404。"""
    row = {
        "thread_id": "t-1",
        "checkpoint_ns": "",
        "checkpoint_id": "cp-1",
        "parent_checkpoint_id": None,
        "type": None,
        "checkpoint": None,
        "metadata": None,
        "size_bytes": 0,
    }
    repo, recorder = _mysql_repo(monkeypatch, [_FakeResult([row]), _FakeResult([], scalar=0)])

    detail = repo.get("t-1", "cp-1")

    assert detail is not None
    assert detail["writes"] == []
    writes_sql = next(sql for sql in recorder if "writes" in sql)
    assert "checkpoint_writes" in writes_sql
    assert "`blob` as value" in writes_sql


def test_routing_target_reads_checkpoint_writes_on_mysql(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """保留的诊断方法必须与 get() 用同一套方言（T-FIX-06：不可只修一半）。"""
    repo, recorder = _mysql_repo(monkeypatch, [_FakeResult([{"channel": "branch:to:respond"}])])

    assert repo.routing_target("t-1", "cp-1") == "respond"
    assert "checkpoint_writes" in recorder[0]
    assert " from writes " not in recorder[0]


def test_get_returns_none_only_when_record_absent(monkeypatch: pytest.MonkeyPatch) -> None:
    repo, _ = _mysql_repo(monkeypatch, [_FakeResult([])])
    assert repo.get("t-1", "nope") is None


def test_get_raises_503_when_sqlite_store_missing(tmp_path) -> None:
    """sqlite 文件不存在 → 503，不是 404（更不是 500）。"""
    settings = Settings(
        _env_file=None,
        environment="test",
        checkpoint_backend="sqlite",
        checkpoint_sqlite_path=str(tmp_path / "absent" / "checkpoints.db"),
    )
    with pytest.raises(AppError) as exc:
        CheckpointRepository(settings).get("t-1", "cp-1")

    assert exc.value.code == "checkpoint_store_unavailable"
    assert exc.value.status_code == 503


def test_get_maps_missing_driver_to_503(monkeypatch: pytest.MonkeyPatch) -> None:
    """驱动缺失是 ModuleNotFoundError，不是 SQLAlchemyError —— 也必须折成 503。"""
    settings = Settings(
        _env_file=None,
        environment="test",
        checkpoint_backend="mysql",
        checkpoint_url="mysql://fla:pw@127.0.0.1:3306/db",
    )
    repo = CheckpointRepository(settings)

    def _boom(url: str):
        raise ModuleNotFoundError("No module named 'MySQLdb'")

    monkeypatch.setattr(repo, "_engine", _boom)

    with pytest.raises(AppError) as exc:
        repo.get("t-1", "cp-1")
    assert exc.value.code == "checkpoint_store_unavailable"
    assert exc.value.status_code == 503
