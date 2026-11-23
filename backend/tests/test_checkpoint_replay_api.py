"""重放端点的 HTTP 契约测试（只通过 HTTP 断言）。

覆盖 `.specs/checkpoint-replay/REQUIREMENT.md`：
- AC-1：正向重放 200，响应三段齐全、camelCase 键、版本一致、耗时/写入行数合理；
- AC-2：HTTP 视角下重放不改变原 thread 的 checkpoint 总数；
- AC-4：不存在的 checkpoint → 404，终态 checkpoint → 409；
- AC-6：非管理员 403 / 未登录 401；checkpoint 库不可用时降级为 404 或 503，绝不 500。

真实 sqlite checkpointer（临时目录），假 LLM 只实现 LLMAdapter 协议，不触网。
"""

import json
import uuid
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app
from app.modules.agent.models import AgentRun


class FakeLLM:
    """chat 路由的假 LLM：classify 固定返回 chat，guidance 生成可区分的文本。"""

    def __init__(self) -> None:
        self.guidance_calls = 0
        self.usage = {"prompt_tokens": 5, "completion_tokens": 2, "total_tokens": 7}

    def classify_intent(self, text: str, history: list[dict[str, str]] | None = None) -> dict:
        return {"route": "chat", "source": "fake", "usage": self.usage}

    def chat_with_tools(self, *args, **kwargs) -> dict:
        raise AssertionError("chat_with_tools should not be called in replay API tests")

    def generate_guidance(self, system: str, user_input: str) -> dict:
        self.guidance_calls += 1
        return {
            "text": f"guidance#{self.guidance_calls}",
            "source": "fake",
            "usage": self.usage,
        }

    def analyze_headers(self, headers: list[str], samples: list[list[str]]) -> dict:
        raise AssertionError("analyze_headers should not be called in replay API tests")


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _login(client: TestClient, nickname: str, password: str) -> str:
    response = client.post("/api/v1/auth/login", json={"nickname": nickname, "password": password})
    assert response.status_code == 200, response.text
    return response.json()["access_token"]


def _register(client: TestClient) -> str:
    nickname = f"ReplayApi{uuid.uuid4().hex[:8]}"
    response = client.post(
        "/api/v1/auth/register", json={"nickname": nickname, "password": "demo123"}
    )
    assert response.status_code == 201, response.text
    return response.json()["access_token"]


def _parse_sse(text: str) -> list[dict]:
    events = []
    for block in text.strip().split("\n\n"):
        data = next((line[6:] for line in block.splitlines() if line.startswith("data: ")), None)
        if data:
            events.append(json.loads(data))
    return events


def _start_chat_run(client: TestClient, token: str) -> str:
    """跑一次真实 chat run，等 SSE 结束，返回 thread_id。"""
    response = client.post(
        "/api/v1/agent/runs/stream",
        headers=_auth(token),
        json={"message": "你好，随便聊聊"},
    )
    assert response.status_code == 200, response.text
    events = _parse_sse(response.text)
    assert events, "SSE 没有任何事件"
    with client.app.state.database.session() as session:  # type: ignore[attr-defined]
        run = session.get(AgentRun, events[0]["run_id"])
        assert run is not None
        return run.thread_id


def _history(client: TestClient, thread_id: str) -> list:
    runtime = client.app.state.agent_runtime  # type: ignore[attr-defined]
    return list(runtime.graph.get_state_history({"configurable": {"thread_id": thread_id}}))


def _replay_anchor(history: list) -> str:
    """chat 流程里 step=1 / next=('respond',) 的那条快照，是可重放锚点。"""
    for snapshot in history:
        if snapshot.metadata.get("step") == 1 and snapshot.next == ("respond",):
            return snapshot.config["configurable"]["checkpoint_id"]
    raise AssertionError(f"没有找到 step=1 且 next=respond 的 checkpoint，共 {len(history)} 条")


def _terminal_checkpoint(history: list) -> str:
    for snapshot in history:
        if snapshot.next == ():
            return snapshot.config["configurable"]["checkpoint_id"]
    raise AssertionError("没有找到终态 checkpoint")


def _replay_url(thread_id: str, checkpoint_id: str) -> str:
    return f"/api/v1/admin/checkpoints/{thread_id}/{checkpoint_id}/replay"


@pytest.fixture
def replay_api(settings: Settings) -> Iterator[dict]:
    """一个 app 内：先跑真实 run，再拿 admin token，供各用例重放。"""
    app = create_app(settings, llm=FakeLLM())
    with TestClient(app) as client:
        user_token = _register(client)
        thread_id = _start_chat_run(client, user_token)
        admin_token = _login(client, "admin", "admin213")
        checkpoint_id = _replay_anchor(_history(client, thread_id))
        yield {
            "client": client,
            "settings": settings,
            "thread_id": thread_id,
            "checkpoint_id": checkpoint_id,
            "admin_token": admin_token,
            "user_token": user_token,
        }


def test_replay_returns_200_with_camel_case_contract(replay_api: dict) -> None:
    """AC-1：200，source/replay/diff 三段齐全，camelCase 键，版本一致。"""
    client = replay_api["client"]
    response = client.post(
        _replay_url(replay_api["thread_id"], replay_api["checkpoint_id"]),
        headers=_auth(replay_api["admin_token"]),
    )
    assert response.status_code == 200, response.text
    body = response.json()

    assert set(body) == {"source", "replay", "diff"}
    assert body["source"]["next"] == ["respond"]
    assert body["source"]["threadId"] == replay_api["thread_id"]
    assert body["source"]["checkpointId"] == replay_api["checkpoint_id"]

    # 同一份 prompt 版本，两侧都应给出且相等。
    assert body["source"]["promptVersion"]
    assert body["replay"]["promptVersion"]
    assert body["replay"]["promptVersion"] == body["source"]["promptVersion"]

    replay = body["replay"]
    assert isinstance(replay["durationMs"], int)
    assert replay["durationMs"] > 0
    assert replay["checkpointRowsAdded"] >= 1
    assert replay["response"]
    assert replay["model"]
    # chat 跑到 END：200 且真的跑完了（T-FIX-05 的负例）。
    assert replay["interrupted"] is False

    # 前端契约：一律 camelCase，不能混入 snake_case。
    assert "promptVersion" in replay
    assert "prompt_version" not in replay
    assert "durationMs" in replay
    assert "duration_ms" not in replay
    assert "checkpointRowsAdded" in replay
    assert "checkpoint_rows_added" not in replay

    assert isinstance(body["diff"]["responseChanged"], bool)
    assert set(body["diff"]) == {"routeChanged", "responseChanged", "pendingActionChanged"}


def test_replay_rejects_unknown_checkpoint_with_404(replay_api: dict) -> None:
    """AC-4：不存在的 checkpoint_id → 404 checkpoint_not_found。"""
    client = replay_api["client"]
    response = client.post(
        _replay_url(replay_api["thread_id"], f"does-not-exist-{uuid.uuid4().hex}"),
        headers=_auth(replay_api["admin_token"]),
    )
    assert response.status_code == 404, response.text
    assert response.json()["error"]["code"] == "checkpoint_not_found"


def test_replay_rejects_terminal_checkpoint_with_409(replay_api: dict) -> None:
    """AC-4：next 为空的终态 checkpoint → 409 checkpoint_terminal。"""
    client = replay_api["client"]
    terminal_id = _terminal_checkpoint(_history(client, replay_api["thread_id"]))
    response = client.post(
        _replay_url(replay_api["thread_id"], terminal_id),
        headers=_auth(replay_api["admin_token"]),
    )
    assert response.status_code == 409, response.text
    assert response.json()["error"]["code"] == "checkpoint_terminal"


def test_replay_requires_admin(replay_api: dict) -> None:
    """AC-6：普通用户 403，未登录 401。"""
    client = replay_api["client"]
    url = _replay_url(replay_api["thread_id"], replay_api["checkpoint_id"])

    forbidden = client.post(url, headers=_auth(replay_api["user_token"]))
    assert forbidden.status_code == 403, forbidden.text
    assert forbidden.json()["error"]["code"] == "forbidden"

    anonymous = client.post(url)
    assert anonymous.status_code == 401, anonymous.text


def test_replay_degrades_when_checkpoint_store_missing(replay_api: dict, tmp_path: Path) -> None:
    """AC-6：checkpoint 库不可用 → 503 checkpoint_store_unavailable，绝不 404/500。

    「库读不了」和「记录不存在」必须是两个码：前者返回 404 会让管理员以为数据丢了（REVIEW C-2）。

    注意 app 启动时会把 checkpoint 库建出来（saver.setup()），所以不能靠换路径让「库不存在」；
    这里在启动后把管理端看到的库地址改成不存在的路径，才是真正的「库掉线」。
    """
    degraded_app = create_app(replay_api["settings"], llm=FakeLLM())
    with TestClient(degraded_app) as degraded_client:
        degraded_app.state.settings = replay_api["settings"].model_copy(
            update={"checkpoint_sqlite_path": str(tmp_path / "absent-store" / "checkpoints.db")}
        )
        response = degraded_client.post(
            _replay_url(replay_api["thread_id"], replay_api["checkpoint_id"]),
            headers=_auth(replay_api["admin_token"]),
        )

    assert response.status_code == 503, response.text
    assert response.json()["error"]["code"] == "checkpoint_store_unavailable"
    assert "Traceback" not in response.text


def test_replay_failure_is_audited(replay_api: dict) -> None:
    """T-FIX-03：失败的重放也要在 admin 操作日志里留痕（带结果码）。

    请求异常会让 `get_session` 回滚，所以失败日志必须自己 commit —— 本用例
    换一个新的 HTTP 请求去查，正是为了证明它真的落库了。
    """
    client = replay_api["client"]
    admin = _auth(replay_api["admin_token"])
    terminal_id = _terminal_checkpoint(_history(client, replay_api["thread_id"]))

    response = client.post(_replay_url(replay_api["thread_id"], terminal_id), headers=admin)
    assert response.status_code == 409, response.text

    logs = client.get("/api/v1/admin/logs", headers=admin)
    assert logs.status_code == 200, logs.text
    entries = [item for item in logs.json() if item["targetId"] == terminal_id]
    assert entries, "失败的重放没有留痕"

    failed = [item for item in entries if item["result"] == "failure"]
    assert failed, f"应有 result=failure 的日志，实际 {entries}"
    assert failed[0]["action"] == "重放 checkpoint 失败"


def test_replay_keeps_thread_checkpoint_total_unchanged(replay_api: dict) -> None:
    """AC-2：重放前后同一 thread 的 checkpoint 总数不变。"""
    client = replay_api["client"]
    admin = _auth(replay_api["admin_token"])
    list_url = f"/api/v1/admin/checkpoints?thread_id={replay_api['thread_id']}"

    before = client.get(list_url, headers=admin)
    assert before.status_code == 200, before.text
    total_before = before.json()["total"]
    assert total_before >= 1

    replay = client.post(
        _replay_url(replay_api["thread_id"], replay_api["checkpoint_id"]),
        headers=admin,
    )
    assert replay.status_code == 200, replay.text

    after = client.get(list_url, headers=admin)
    assert after.status_code == 200, after.text
    assert after.json()["total"] == total_before
