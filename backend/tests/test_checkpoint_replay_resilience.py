"""checkpoint 调试重放的韧性测试：AC-7（不拖垮在线服务）与可观测性。

T03 覆盖隔离性 / 零写入 / 可重复 / 三条拒绝路径，T06 覆盖 HTTP 契约。
本文件补四处空白（见 `.specs/checkpoint-replay/TEST.md` 第 1 轮）：

- 超时守卫：重放超出 60s 预算必须尽快返回 504，不能让管理端请求挂死。
- 执行锁隔离：重放不取 `_execution_lock`，真实用户执行期间也能跑。
- 注入形状的 checkpoint_id：走参数化查询，落到 404 而不是 500。
- 日志可追溯：带 source/replay thread 与 prompt_version，且不含回答正文。
"""

import logging
import threading
import time

import pymysql
import pytest
from fastapi.testclient import TestClient
from test_checkpoint_replay_unit import (
    FakeLLM,
    _history,
    _replayable_checkpoint,
    _start_run,
)

import app.modules.agent.runtime as runtime_module
from app.core.exceptions import AppError
from app.infrastructure.checkpoint import CheckpointerManager
from app.main import create_app


class SlowLLM(FakeLLM):
    """在 respond 节点故意拖延的假 LLM，用来触发重放超时。"""

    def __init__(self, delay: float = 0.5) -> None:
        super().__init__()
        self.delay = delay

    def generate_guidance(self, system: str, user_input: str) -> dict:
        time.sleep(self.delay)
        return super().generate_guidance(system, user_input)


@pytest.fixture
def chat_runtime(settings):
    """跑完一条 chat run，返回 (runtime, 可重放的 checkpoint_id)。"""
    fake = FakeLLM()
    app = create_app(settings, llm=fake)
    with TestClient(app) as client:
        nickname = f"Resilience{int(time.time() * 1000) % 100000}"
        token_response = client.post(
            "/api/v1/auth/register", json={"nickname": nickname, "password": "demo123"}
        )
        assert token_response.status_code == 201, token_response.text
        token = token_response.json()["access_token"]
        _, thread_id = _start_run(client, token, "你好，随便聊聊")
        runtime = app.state.agent_runtime
        checkpoint_id = _replayable_checkpoint(_history(runtime, thread_id))
        yield runtime, thread_id, checkpoint_id


def test_replay_returns_504_when_the_graph_exceeds_its_budget(
    chat_runtime, monkeypatch, caplog
) -> None:
    """AC-7：超过重放预算 → 504 replay_timeout，且原 thread 不受影响。

    预算用 monkeypatch 压到 0.1s，把 respond 节点拖到 0.5s。
    """
    runtime, thread_id, checkpoint_id = chat_runtime
    monkeypatch.setattr(runtime_module, "_REPLAY_TIMEOUT_SECONDS", 0.1)
    # respond 节点走的是 runtime.guidance（构造时已绑定原 llm），两处都要换。
    slow = SlowLLM(delay=0.5)
    runtime.llm = slow
    runtime.guidance.llm = slow

    history_before = len(_history(runtime, thread_id))
    caplog.set_level(logging.WARNING, logger="app.agent")

    with pytest.raises(AppError) as exc:
        runtime.replay_from_checkpoint(thread_id, checkpoint_id)

    assert exc.value.code == "replay_timeout"
    assert exc.value.status_code == 504

    # 原 thread 零污染（AC-2 在超时路径上同样成立）。
    assert len(_history(runtime, thread_id)) == history_before

    # 超时日志必须留下 replay_thread，否则后台线程无法被清理（ADR 风险表）。
    timeout_logs = [r for r in caplog.records if r.levelno == logging.WARNING]
    assert any("replay timeout" in r.getMessage() for r in timeout_logs)
    assert any("replay_thread=" in r.getMessage() for r in timeout_logs)

    # 被 shutdown(wait=False) 丢下的线程还在跑，等它自然结束再退出本用例，
    # 避免它在下一个用例的临时库上继续写。
    time.sleep(0.7)


def test_replay_does_not_wait_for_the_execution_lock(chat_runtime) -> None:
    """AC-7：`_execution_lock` 被真实执行持有时，重放仍能完成，不排队。

    这就是「不拖垮在线服务」的结构性保证：若实现去抢锁，本用例会超时失败。
    """
    runtime, thread_id, checkpoint_id = chat_runtime
    lock_held = runtime._execution_lock.acquire(timeout=0)
    assert lock_held, "测试自身应能拿到执行锁"

    outcome: dict[str, object] = {}

    def run_replay() -> None:
        try:
            outcome["result"] = runtime.replay_from_checkpoint(thread_id, checkpoint_id)
        except BaseException as exc:  # noqa: BLE001 - 原样记录交给主线程断言
            outcome["error"] = exc

    try:
        worker = threading.Thread(target=run_replay, daemon=True)
        worker.start()
        worker.join(timeout=15)
        assert not worker.is_alive(), "重放阻塞在 `_execution_lock` 上，说明抢锁了"
    finally:
        runtime._execution_lock.release()

    assert "error" not in outcome, f"重放抛错：{outcome.get('error')!r}"
    assert outcome["result"]["replay"]["thread_id"].startswith("replay-")


def test_replay_rejects_injection_shaped_checkpoint_id(chat_runtime) -> None:
    """A03 边界：checkpoint_id 带 SQL 片段 → 404，不是 500、不泄漏栈。"""
    runtime, thread_id, _ = chat_runtime

    for payload in ("' OR 1=1 --", "x' UNION SELECT 1 --", "%00", "a" * 512):
        with pytest.raises(AppError) as exc:
            runtime.replay_from_checkpoint(thread_id, payload)

        assert exc.value.code == "checkpoint_not_found", payload[:20]
        assert exc.value.status_code == 404
        assert "Traceback" not in exc.value.message


def test_replay_log_is_traceable_and_carries_no_response_text(chat_runtime, caplog) -> None:
    """可观测性：一条 INFO 日志含四个可反查字段，且不打回答正文（PII）。"""
    runtime, thread_id, checkpoint_id = chat_runtime
    caplog.set_level(logging.INFO, logger="app.agent")

    result = runtime.replay_from_checkpoint(thread_id, checkpoint_id)

    records = [r for r in caplog.records if r.levelno == logging.INFO]
    replay_logs = [r.getMessage() for r in records if "checkpoint replay" in r.getMessage()]
    assert replay_logs, "重放成功必须留一条 INFO 日志"

    message = replay_logs[-1]
    for field in (
        f"source_thread={thread_id}",
        f"source_checkpoint={checkpoint_id}",
        f"replay_thread={result['replay']['thread_id']}",
        "prompt_version=",
        "duration_ms=",
    ):
        assert field in message, f"日志缺字段 {field}"

    # LM 的回答会把用户原文复述出来，绝不能进日志。
    assert result["replay"]["response"] not in message


class _PingRecorder:
    """记录 ping 的 reconnect 参数，用来证明「放弃后没有再重连」。"""

    def __init__(self) -> None:
        self.calls: list[bool] = []

    def ping(self, reconnect: bool = False) -> None:
        self.calls.append(reconnect)


class _SaverWithConn:
    def __init__(self, conn: _PingRecorder) -> None:
        self.conn = conn


class _ExplodingGraph:
    """把「请求线程超时置位」模拟在写 checkpoint 的那一刻，再抛连接级异常。"""

    def __init__(self, abandoned: threading.Event | None = None) -> None:
        self.abandoned = abandoned
        self.calls = 0

    def invoke(self, *args, **kwargs):  # noqa: ANN002, ANN003 - 只要抛就行
        self.calls += 1
        if self.abandoned is not None:
            self.abandoned.set()
        raise pymysql.err.InterfaceError(0, "")


def test_replay_worker_does_not_reconnect_after_abandon() -> None:
    """超时放弃后，孤儿线程遇到 InterfaceError 不许 ping(reconnect=True)。

    原实现走 `_with_checkpoint_retry`，会重连 → 被请求线程关掉的连接被「复活」，
    再无人关闭，每次超时泄漏一条（REVIEW M-1 / AC-7 反向）。
    """
    abandoned = threading.Event()
    conn = _PingRecorder()
    graph = _ExplodingGraph(abandoned)

    with pytest.raises(runtime_module._ReplayAbandoned):
        runtime_module._invoke_replay_graph(
            graph, _SaverWithConn(conn), "replay-abandoned", abandoned
        )

    assert graph.calls == 1, "放弃后不该重试图调用"
    assert conn.calls == [True], f"只应有前置探活那一次 ping，实际 {conn.calls}"


def test_replay_worker_still_retries_when_not_abandoned() -> None:
    """没被放弃时（真实用户在跑）连接级异常仍要重连重试一次，别把正常路径改坏。"""
    abandoned = threading.Event()
    conn = _PingRecorder()
    graph = _ExplodingGraph()

    with pytest.raises(pymysql.err.InterfaceError):
        runtime_module._invoke_replay_graph(graph, _SaverWithConn(conn), "replay-normal", abandoned)

    assert graph.calls == 2, "非放弃态应重试一次"
    assert conn.calls == [True, True]


def test_timeout_hands_connection_to_orphan_thread(chat_runtime, monkeypatch) -> None:
    """超时后连接归属：孤儿线程还在跑就不许关，它结束后必须关（T-FIX-04）。"""
    runtime, thread_id, checkpoint_id = chat_runtime
    created: list[CheckpointerManager] = []

    class _SpyManager(CheckpointerManager):
        def __init__(self, settings) -> None:
            super().__init__(settings)
            created.append(self)

    monkeypatch.setattr(runtime_module, "CheckpointerManager", _SpyManager)
    monkeypatch.setattr(runtime_module, "_REPLAY_TIMEOUT_SECONDS", 0.1)
    monkeypatch.setattr(runtime_module, "_REPLAY_DRAIN_SECONDS", 0.2)
    release = threading.Event()

    def _stuck_invoke(graph, saver, replay_thread, abandoned):
        """模拟卡住的 worker：不看取消标志，就是不结束。"""
        release.wait(timeout=10)
        return {}

    monkeypatch.setattr(runtime_module, "_invoke_replay_graph", _stuck_invoke)

    with pytest.raises(AppError) as exc:
        runtime.replay_from_checkpoint(thread_id, checkpoint_id)
    assert exc.value.code == "replay_timeout"

    manager = created[-1]
    # 关键断言：worker 还在跑，请求线程不能关连接 —— 否则 worker 的写会触发重连复活。
    assert manager._closed is False, "超时后请求线程提前关了仍在使用的连接"
    assert runtime_module._ABANDONED_REPLAY_THREADS, "被放弃的重放应进登记表"

    release.set()
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline and not manager._closed:
        time.sleep(0.02)

    assert manager._closed is True, "孤儿线程结束后必须自己关连接，否则就是连接泄漏"
    assert not runtime_module._ABANDONED_REPLAY_THREADS, "登记表要被清理干净"
