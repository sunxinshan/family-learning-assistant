"""Checkpointer 长连接失效后的自愈。

背景：`PyMySQLSaver.from_conn_string` 只在进程启动时开一条 pymysql 连接并一直复用，
没有探活也没有回收。MySQL 的 `wait_timeout`（生产为 28800 秒）会把空闲连接踢掉，
但客户端对象仍然在进程里，下一次 checkpoint 读写就抛 `InterfaceError(0, '')`，
最终被兜成「执行失败，请稍后重试」。

生产实例：2026-11-19 07:50 与 2026-11-20 05:57 两次失败，服务自 11-17 15:57 未重启。
"""

import pymysql
import pytest

from app.modules.agent.runtime import _with_checkpoint_retry


class FakeConnection:
    """只有 ping 行为的最小连接替身。"""

    def __init__(self) -> None:
        self.pings: list[bool] = []
        self.closed = False

    def ping(self, reconnect: bool = False) -> None:
        self.pings.append(reconnect)
        if self.closed and reconnect:
            self.closed = False
            return
        if self.closed:
            raise pymysql.err.InterfaceError(0, "")


class FakeSaver:
    def __init__(self, conn: FakeConnection | None = None) -> None:
        if conn is not None:
            self.conn = conn


def test_retries_once_after_connection_dropped() -> None:
    """连接被 MySQL 掐断时，探活重连并把这次调用再执行一遍。"""
    conn = FakeConnection()
    saver = FakeSaver(conn)
    calls: list[str] = []

    def operation() -> str:
        calls.append("call")
        if len(calls) == 1:
            conn.closed = True
            raise pymysql.err.InterfaceError(0, "")
        return "ok"

    assert _with_checkpoint_retry(saver, operation) == "ok"
    assert calls == ["call", "call"], "应当重试且只重试一次"
    assert True in conn.pings, "重试前必须调用 ping(reconnect=True)"


def test_pings_before_calling_so_idle_connection_is_revived() -> None:
    """即使第一次调用没抛错，也要先探活——空闲过久的连接在 execute 时才炸。"""
    conn = FakeConnection()
    saver = FakeSaver(conn)
    conn.closed = True  # 模拟已被 wait_timeout 踢掉的连接
    seen: list[bool] = []

    def operation() -> str:
        seen.append(conn.closed)
        return "ok"

    assert _with_checkpoint_retry(saver, operation) == "ok"
    assert seen == [False], "调用时连接应已被重新建立"
    assert conn.pings == [True]


def test_backend_without_connection_attribute_is_untouched() -> None:
    """SQLite 后端（SqliteSaver）没有 .conn.ping，行为必须完全不变。"""
    saver = FakeSaver()
    calls: list[int] = []

    def operation() -> int:
        calls.append(1)
        return 42

    assert _with_checkpoint_retry(saver, operation) == 42
    assert calls == [1]


def test_non_connection_errors_are_not_retried() -> None:
    """业务异常原样抛出，不能被重试掩盖。"""
    saver = FakeSaver(FakeConnection())
    calls: list[int] = []

    def operation() -> None:
        calls.append(1)
        raise ValueError("boom")

    with pytest.raises(ValueError):
        _with_checkpoint_retry(saver, operation)
    assert calls == [1]
