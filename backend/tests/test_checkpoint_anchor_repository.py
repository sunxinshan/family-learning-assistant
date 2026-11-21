"""CheckpointRepository.routing_target / count_thread 的行为验证。

用真 SqliteSaver（落文件，不用 MemorySaver）跑一遍 a → b 的图，然后直接读
writes / checkpoints 表交叉验证，避免测试只反映 repository 自己的实现。
"""

from __future__ import annotations

import logging
import sqlite3
from collections.abc import Iterator
from pathlib import Path
from typing import TypedDict

import pytest
from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from app.core.config import Settings
from app.modules.admin.checkpoint_repository import CheckpointRepository

THREAD_ID = "thread-t01-anchor"


class _State(TypedDict):
    text: str


class _FanOutState(TypedDict, total=False):
    left: str
    right: str


def _node(name: str):  # noqa: ANN202 - 只是个测试用闭包工厂
    def run(state: _State) -> _State:
        return {"text": f"{state.get('text', '')}{name}"}

    return run


def _linear_graph(saver: SqliteSaver) -> CompiledStateGraph:
    """a → b → END 的直线图。"""
    builder = StateGraph(_State)
    builder.add_node("a", _node("a"))
    builder.add_node("b", _node("b"))
    builder.add_edge(START, "a")
    builder.add_edge("a", "b")
    builder.add_edge("b", END)
    return builder.compile(checkpointer=saver)


def _fan_out_graph(saver: SqliteSaver) -> CompiledStateGraph:
    """START 同时扇出到 b、c，用于制造同一条 checkpoint 上多个 branch:to 写入。"""
    builder = StateGraph(_FanOutState)
    builder.add_node("b", lambda state: {"left": "b"})
    builder.add_node("c", lambda state: {"right": "c"})
    builder.add_edge(START, "b")
    builder.add_edge(START, "c")
    builder.add_edge("b", END)
    builder.add_edge("c", END)
    return builder.compile(checkpointer=saver)


@pytest.fixture
def checkpoint_conn(settings: Settings) -> Iterator[sqlite3.Connection]:
    """真实落文件的 SqliteSaver 连接，并建好 checkpoints / writes 表。"""
    conn = sqlite3.connect(Path(settings.checkpoint_sqlite_path), check_same_thread=False)
    SqliteSaver(conn).setup()
    try:
        yield conn
    finally:
        conn.close()


def _graph_config() -> dict[str, dict[str, str]]:
    return {"configurable": {"thread_id": THREAD_ID}}


def _history(graph: CompiledStateGraph) -> list:
    return list(graph.get_state_history(_graph_config()))


def _snapshot_by_id(snapshots: list, checkpoint_id: str):
    return next(s for s in snapshots if s.config["configurable"]["checkpoint_id"] == checkpoint_id)


def _parent_of(snapshot) -> str:
    return snapshot.parent_config["configurable"]["checkpoint_id"]


def test_routing_target_returns_branch_target_of_parent_checkpoint(
    settings: Settings, checkpoint_conn: sqlite3.Connection
) -> None:
    graph = _linear_graph(SqliteSaver(checkpoint_conn))
    graph.invoke({"text": ""}, _graph_config())
    checkpoint_conn.commit()

    snapshots = _history(graph)
    # next == ("b",) 的那条快照：a 已跑完、b 还没开始，记它的 parent 作为入参。
    mid = next(s for s in snapshots if s.next == ("b",))
    mid_id = mid.config["configurable"]["checkpoint_id"]
    parent_id = _parent_of(mid)
    assert mid_id != parent_id

    repo = CheckpointRepository(settings)

    # 实测结论：branch:to:<node> 写在该任务所基于的 checkpoint 上，指向任务执行完后的
    # 路由目标。所以 routing_target(parent_id) 得到的是 mid 之后的待执行节点 "b"，
    # 而不是产出 mid 的节点 "a"。
    assert repo.routing_target(THREAD_ID, parent_id) == "b"

    # 想拿到「产出 mid 的那个节点」（= "a"），按同样的偏移再上溯一层 parent 的 parent。
    grandparent_id = _parent_of(_snapshot_by_id(snapshots, parent_id))
    assert repo.routing_target(THREAD_ID, grandparent_id) == "a"


def test_routing_target_returns_none_without_branch_writes(
    settings: Settings, checkpoint_conn: sqlite3.Connection
) -> None:
    graph = _linear_graph(SqliteSaver(checkpoint_conn))
    graph.invoke({"text": ""}, _graph_config())
    checkpoint_conn.commit()

    snapshots = _history(graph)
    # 终点快照没有 branch:to 写入（b → END 不再路由）。
    terminal = next(s for s in snapshots if s.next == ())
    terminal_id = terminal.config["configurable"]["checkpoint_id"]
    branch_writes = checkpoint_conn.execute(
        "select count(*) from writes where thread_id = ? and checkpoint_id = ? "
        "and channel like 'branch:to:%'",
        (THREAD_ID, terminal_id),
    ).fetchone()[0]
    assert branch_writes == 0

    repo = CheckpointRepository(settings)
    assert repo.routing_target(THREAD_ID, terminal_id) is None


def test_routing_target_returns_none_and_warns_on_multiple_branch_writes(
    settings: Settings,
    checkpoint_conn: sqlite3.Connection,
    caplog: pytest.LogCaptureFixture,
) -> None:
    graph = _fan_out_graph(SqliteSaver(checkpoint_conn))
    graph.invoke({"text": ""}, _graph_config())
    checkpoint_conn.commit()

    snapshots = _history(graph)
    # 入口 checkpoint（source=input）上的 __start__ 任务扇出两条边，两条 branch:to
    # 都落在同一条 checkpoint 的 writes 里。
    entry = next(s for s in snapshots if s.metadata.get("source") == "input")
    entry_id = entry.config["configurable"]["checkpoint_id"]
    channels = [
        row[0]
        for row in checkpoint_conn.execute(
            "select channel from writes where thread_id = ? and checkpoint_id = ? "
            "and channel like 'branch:to:%'",
            (THREAD_ID, entry_id),
        )
    ]
    assert sorted(channels) == ["branch:to:b", "branch:to:c"]

    repo = CheckpointRepository(settings)
    with caplog.at_level(logging.WARNING, logger="app.modules.admin.checkpoint_repository"):
        assert repo.routing_target(THREAD_ID, entry_id) is None
    assert "multiple branch writes" in caplog.text


def test_count_thread_matches_checkpoints_table(
    settings: Settings, checkpoint_conn: sqlite3.Connection
) -> None:
    graph = _linear_graph(SqliteSaver(checkpoint_conn))
    graph.invoke({"text": ""}, _graph_config())
    checkpoint_conn.commit()

    expected = checkpoint_conn.execute(
        "select count(*) from checkpoints where thread_id = ?", (THREAD_ID,)
    ).fetchone()[0]
    assert expected > 0

    repo = CheckpointRepository(settings)
    assert repo.count_thread(THREAD_ID) == expected


def test_count_thread_returns_zero_for_unknown_thread(
    settings: Settings, checkpoint_conn: sqlite3.Connection
) -> None:
    graph = _linear_graph(SqliteSaver(checkpoint_conn))
    graph.invoke({"text": ""}, _graph_config())
    checkpoint_conn.commit()

    repo = CheckpointRepository(settings)
    assert repo.count_thread("no-such-thread") == 0


def test_missing_database_file_degrades_silently(tmp_path: Path) -> None:
    missing_settings = Settings(
        _env_file=None,
        environment="test",
        checkpoint_backend="sqlite",
        checkpoint_sqlite_path=str(tmp_path / "no-such-dir" / "missing.db"),
    )
    assert not Path(missing_settings.checkpoint_sqlite_path).exists()

    repo = CheckpointRepository(missing_settings)
    assert repo.routing_target(THREAD_ID, "any-checkpoint") is None
    assert repo.count_thread(THREAD_ID) == 0
