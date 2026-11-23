"""checkpoint 调试重放的行为单测：隔离性 / 零写入 / 只跑剩余节点 / 拒绝路径。

对应 `.specs/checkpoint-replay/REQUIREMENT.md` 的 AC-2 / AC-3 / AC-5 与 AC-4。
所有用例走真实 sqlite checkpointer（临时目录），不用 MemorySaver —— 否则"行数不变"没有意义。
假 LLM 只实现 `LLMAdapter` 协议，不触网。
"""

import json
import uuid
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.core.config import Settings
from app.core.exceptions import AppError
from app.main import create_app
from app.modules.agent.models import AgentRun, AgentRunEvent
from app.modules.agent.runtime import AgentRuntime
from app.modules.content.models import ContentExtraction
from app.modules.conversation.models import ConversationMessage
from app.modules.material.models import Material
from app.modules.task.models import LearningTask


class FakeLLM:
    """可控假 LLM：记录 classify 调用次数，guidance 返回可区分的文本。"""

    def __init__(self, route: str = "chat") -> None:
        self.route = route
        self.classify_calls: list[str] = []
        self.guidance_calls = 0
        self.usage = {"prompt_tokens": 5, "completion_tokens": 2, "total_tokens": 7}

    def classify_intent(self, text: str, history: list[dict[str, str]] | None = None) -> dict:
        self.classify_calls.append(text)
        return {"route": self.route, "source": "fake", "usage": self.usage}

    def chat_with_tools(self, messages: list[dict], tools: list[dict], **_kwargs) -> dict:
        raise AssertionError("chat_with_tools should not be called in replay tests")

    def generate_guidance(self, system: str, user_input: str) -> dict:
        self.guidance_calls += 1
        return {
            "text": f"guidance#{self.guidance_calls}",
            "source": "fake",
            "usage": self.usage,
        }

    def analyze_headers(self, headers: list[str], samples: list[list[str]]) -> dict:
        raise AssertionError("analyze_headers should not be called in replay tests")


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _register(client: TestClient, prefix: str = "Replay") -> str:
    nickname = f"{prefix}{uuid.uuid4().hex[:8]}"
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


def _start_run(client: TestClient, token: str, message: str) -> tuple[str, str]:
    """跑一次真实 run，等 SSE 结束，返回 (run_id, thread_id)。"""
    response = client.post(
        "/api/v1/agent/runs/stream",
        headers=_auth(token),
        json={"message": message},
    )
    assert response.status_code == 200, response.text
    events = _parse_sse(response.text)
    assert events, "SSE 没有任何事件"
    run_id = events[0]["run_id"]
    with client.app.state.database.session() as session:  # type: ignore[attr-defined]
        run = session.get(AgentRun, run_id)
        assert run is not None
        return run_id, run.thread_id


def _create_library(client: TestClient, token: str, name: str) -> None:
    response = client.post(
        "/api/v1/vocabularies",
        headers=_auth(token),
        json={
            "subject": "english",
            "name": name,
            "description": "",
            "tags": [],
            "entries": [
                {
                    "word": word,
                    "phonetic": f"/{word}/",
                    "partOfSpeech": "n.",
                    "meanings": [word],
                    "example": "",
                    "exampleTranslation": "",
                }
                for word in ("alpha", "beta", "gamma")
            ],
        },
    )
    assert response.status_code == 201, response.text


def _history(runtime: AgentRuntime, thread_id: str) -> list:
    return list(runtime.graph.get_state_history({"configurable": {"thread_id": thread_id}}))


def _replayable_checkpoint(history: list) -> str:
    """选一个非终点、无 interrupt、且有父快照的 checkpoint（chat 流程里是 next=respond 那条）。"""
    for snapshot in history:
        if (
            snapshot.next
            and snapshot.parent_config
            and not any(task.interrupts for task in snapshot.tasks)
        ):
            return snapshot.config["configurable"]["checkpoint_id"]
    raise AssertionError("没有找到可重放的 checkpoint")


def _business_counts(runtime: AgentRuntime) -> dict[str, object]:
    """业务表指纹：计数 + 材料状态。

    只看计数不够 —— ``ContentService.extract`` 的副作用之一是
    ``material.status = "parsed"``，行数不变但状态变了（REVIEW C-1）。
    """
    with runtime.database.session() as session:
        return {
            "conversation_messages": session.scalar(
                select(func.count()).select_from(ConversationMessage)
            ),
            "agent_runs": session.scalar(select(func.count()).select_from(AgentRun)),
            "agent_run_events": session.scalar(select(func.count()).select_from(AgentRunEvent)),
            "tasks": session.scalar(select(func.count()).select_from(LearningTask)),
            "content_extractions": session.scalar(
                select(func.count()).select_from(ContentExtraction)
            ),
            "materials": tuple(
                session.execute(select(Material.id, Material.status).order_by(Material.id)).all()
            ),
        }


def _snapshot_with_next(history: list, node: str, route: str | None = None) -> str:
    """取 ``next == (node,)`` 的快照 id，可按 state 里的 route 再筛一层。"""
    for snapshot in history:
        if snapshot.next != (node,):
            continue
        if route is not None and snapshot.values.get("route") != route:
            continue
        return snapshot.config["configurable"]["checkpoint_id"]
    raise AssertionError(f"没有找到 next={node} route={route} 的 checkpoint")


@pytest.fixture
def chat_setup(settings: Settings) -> Iterator[tuple[TestClient, AgentRuntime, FakeLLM, str, str]]:
    """一条完成的 chat run：返回 client / runtime / fake / run_id / thread_id。"""
    fake = FakeLLM()
    app = create_app(settings, llm=fake)
    with TestClient(app) as client:
        token = _register(client)
        run_id, thread_id = _start_run(client, token, "你好，随便聊聊")
        yield client, app.state.agent_runtime, fake, run_id, thread_id


def test_replay_does_not_pollute_source_thread(
    chat_setup: tuple[TestClient, AgentRuntime, FakeLLM, str, str],
) -> None:
    """AC-2：重放前后，原 thread 的历史长度 / values / next 逐项不变。"""
    _, runtime, _, _, thread_id = chat_setup
    config = {"configurable": {"thread_id": thread_id}}

    history_before = _history(runtime, thread_id)
    state_before = runtime.graph.get_state(config)
    checkpoint_id = _replayable_checkpoint(history_before)

    runtime.replay_from_checkpoint(thread_id, checkpoint_id)

    # 行数用 graph.get_state_history 长度交叉验证（SQLite 层无法轻易读到 checkpointer 私有连接）。
    history_after = _history(runtime, thread_id)
    state_after = runtime.graph.get_state(config)

    assert len(history_after) == len(history_before)
    assert state_after.values == state_before.values
    assert state_after.next == state_before.next


def test_replay_writes_no_business_rows(
    chat_setup: tuple[TestClient, AgentRuntime, FakeLLM, str, str],
) -> None:
    """AC-3：重放不新增 conversation_messages / agent_runs / agent_run_events / tasks。"""
    _, runtime, _, _, thread_id = chat_setup
    checkpoint_id = _replayable_checkpoint(_history(runtime, thread_id))

    before = _business_counts(runtime)
    runtime.replay_from_checkpoint(thread_id, checkpoint_id)
    after = _business_counts(runtime)

    assert after == before


def test_replay_is_repeatable_and_keeps_previous_replay_thread(
    chat_setup: tuple[TestClient, AgentRuntime, FakeLLM, str, str],
) -> None:
    """AC-5：同一 (thread, checkpoint) 连跑两次都成功，互不影响。"""
    _, runtime, _, _, thread_id = chat_setup
    checkpoint_id = _replayable_checkpoint(_history(runtime, thread_id))

    first = runtime.replay_from_checkpoint(thread_id, checkpoint_id)
    second = runtime.replay_from_checkpoint(thread_id, checkpoint_id)

    assert first["replay"]["thread_id"] != second["replay"]["thread_id"]
    assert first["replay"]["response"] and second["replay"]["response"]

    first_replay = runtime.graph.get_state(
        {"configurable": {"thread_id": first["replay"]["thread_id"]}}
    )
    assert first_replay.values, "第一次重放的 thread 应仍然存在"
    assert first_replay.next == ()


def test_replay_runs_only_remaining_nodes(
    chat_setup: tuple[TestClient, AgentRuntime, FakeLLM, str, str],
) -> None:
    """核心断言：as_node 锚定后只跑剩余节点，classify 不会被二次执行。"""
    _, runtime, fake, _, thread_id = chat_setup
    checkpoint_id = _replayable_checkpoint(_history(runtime, thread_id))

    classify_before = len(fake.classify_calls)
    guidance_before = fake.guidance_calls

    result = runtime.replay_from_checkpoint(thread_id, checkpoint_id)

    # 锚点错误时这里会 +1（classify 重跑），是我们最想抓住的失败模式。
    assert len(fake.classify_calls) == classify_before
    # respond 确实执行了：guidance 被再调一次，且返回里带回了新文本。
    assert fake.guidance_calls == guidance_before + 1
    assert result["source"]["next"] == ["respond"]
    assert result["replay"]["response"]
    assert result["diff"]["response_changed"] is True


def test_replay_rejects_unknown_checkpoint(
    chat_setup: tuple[TestClient, AgentRuntime, FakeLLM, str, str],
) -> None:
    """AC-4：checkpoint_id 不存在 → checkpoint_not_found 404。"""
    _, runtime, _, _, thread_id = chat_setup

    with pytest.raises(AppError) as exc:
        runtime.replay_from_checkpoint(thread_id, f"does-not-exist-{uuid.uuid4().hex}")

    assert exc.value.code == "checkpoint_not_found"
    assert exc.value.status_code == 404


def test_replay_rejects_terminal_checkpoint(
    chat_setup: tuple[TestClient, AgentRuntime, FakeLLM, str, str],
) -> None:
    """AC-4：next 为空的终态 checkpoint → checkpoint_terminal 409。"""
    _, runtime, _, _, thread_id = chat_setup
    terminal = _history(runtime, thread_id)[0]
    assert terminal.next == ()

    with pytest.raises(AppError) as exc:
        runtime.replay_from_checkpoint(thread_id, terminal.config["configurable"]["checkpoint_id"])

    assert exc.value.code == "checkpoint_terminal"
    assert exc.value.status_code == 409


def test_replay_rejects_interrupted_checkpoint(settings: Settings) -> None:
    """AC-4：interrupt 挂起的 checkpoint → checkpoint_interrupted 409。"""
    fake = FakeLLM(route="task_create")
    app = create_app(settings, llm=fake)
    with TestClient(app) as client:
        runtime = app.state.agent_runtime
        token = _register(client, "ReplayInterrupt")
        _create_library(client, token, "中断词库")
        _, thread_id = _start_run(client, token, "用中断词库创建任务")

        history = _history(runtime, thread_id)
        interrupted = next(
            (snap for snap in history if any(task.interrupts for task in snap.tasks)), None
        )
        assert interrupted is not None, "task_create 应产生 wait 节点的 interrupt checkpoint"
        assert interrupted.next

        with pytest.raises(AppError) as exc:
            runtime.replay_from_checkpoint(
                thread_id, interrupted.config["configurable"]["checkpoint_id"]
            )

        assert exc.value.code == "checkpoint_interrupted"
        assert exc.value.status_code == 409


def test_replay_rejects_entry_checkpoint_without_parent(settings: Settings) -> None:
    """AC-4 补充：没有父快照（入口）的 checkpoint → checkpoint_terminal 409。

    真实 run 的 input checkpoint 的 values 为空，会先命中 `not src.values` 的 404 分支；
    这里用真实 checkpointer 在新 thread 上 `update_state` 写一个 parent_config 为空、
    values 非空的快照，专门覆盖 `not src.parent_config` 这条守卫。
    """
    fake = FakeLLM()
    app = create_app(settings, llm=fake)
    with TestClient(app):
        runtime = app.state.agent_runtime
        thread_id = f"entry-{uuid.uuid4()}"
        runtime.graph.update_state(
            {"configurable": {"thread_id": thread_id}},
            {"text": "seed", "route": "chat"},
            as_node="classify",
        )
        entry = _history(runtime, thread_id)[0]
        assert entry.parent_config is None
        assert entry.next

        with pytest.raises(AppError) as exc:
            runtime.replay_from_checkpoint(thread_id, entry.config["configurable"]["checkpoint_id"])

        assert exc.value.code == "checkpoint_terminal"
        assert exc.value.status_code == 409


def test_replay_writes_nothing_on_task_create_route(settings: Settings) -> None:
    """AC-3 跨路由：task_create（tool_calling 关闭，走 prepare）重放也不许写业务表。

    之前 AC-3 只在 chat 路由上验过，而 chat 的 respond 本来就不写库，
    等于用一条不会失败的用例证明「无副作用」（REVIEW C-1）。
    这里挑 next=('prepare',) 的快照：重放会真的再跑一次 prepare，才验得到副作用。
    """
    fake = FakeLLM(route="task_create")
    app = create_app(settings, llm=fake)
    with TestClient(app) as client:
        runtime = app.state.agent_runtime
        token = _register(client, "ReplayTaskCreate")
        _create_library(client, token, "任务词库")
        _, thread_id = _start_run(client, token, "用任务词库创建听写任务")

        checkpoint_id = _snapshot_with_next(
            _history(runtime, thread_id), "prepare", route="task_create"
        )
        before = _business_counts(runtime)

        result = runtime.replay_from_checkpoint(thread_id, checkpoint_id)

        assert _business_counts(runtime) == before, "重放 prepare 写了业务表"
        # task_create 的终点是 wait（等人工确认）：200 但没跑完，必须标出来（T-FIX-05）。
        assert result["replay"]["interrupted"] is True
        assert result["replay"]["pending_action"] is not None


def test_replay_rejects_vocabulary_import_route(settings: Settings) -> None:
    """AC-3：vocabulary_import 的 prepare 会解析文件并落库，重放必须 409（T-FIX-02 remedy ①）。"""
    fake = FakeLLM(route="vocabulary_import")
    app = create_app(settings, llm=fake)
    with TestClient(app) as client:
        runtime = app.state.agent_runtime
        token = _register(client, "ReplayImport")
        _, thread_id = _start_run(client, token, "导入这个单词表文件")

        checkpoint_id = _snapshot_with_next(
            _history(runtime, thread_id), "prepare", route="vocabulary_import"
        )
        before = _business_counts(runtime)

        with pytest.raises(AppError) as exc:
            runtime.replay_from_checkpoint(thread_id, checkpoint_id)

        assert exc.value.code == "replay_unsupported_route"
        assert exc.value.status_code == 409
        assert "content_extractions" in exc.value.message
        assert _business_counts(runtime) == before, "被拒绝的重放不该有任何写入"


def test_replay_marks_chat_route_as_not_interrupted(
    chat_setup: tuple[TestClient, AgentRuntime, FakeLLM, str, str],
) -> None:
    """chat 路由跑到 END，interrupted 必须是 False（否则前端会一直提示「未完成」）。"""
    _, runtime, _, _, thread_id = chat_setup
    checkpoint_id = _replayable_checkpoint(_history(runtime, thread_id))

    result = runtime.replay_from_checkpoint(thread_id, checkpoint_id)

    assert result["replay"]["interrupted"] is False
