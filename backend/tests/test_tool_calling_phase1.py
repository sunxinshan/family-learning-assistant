import json
import uuid
from collections.abc import Iterable
from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.core.config import Settings
from app.core.database import Database
from app.main import create_app
from app.modules.agent.prompt_registry import PromptRegistry
from app.modules.conversation.models import ConversationMessage


class FakeToolLLM:
    """按脚本返回工具调用，用于确定性验证 Tool Calling 闭环。"""

    def __init__(self) -> None:
        self.tool_calls: list[dict] = []
        self.text = ""
        self.usage = {"prompt_tokens": 7, "completion_tokens": 3, "total_tokens": 10}
        self.fail_if_called = False
        self.seen_tools: list[dict] = []
        self.seen_messages: list[dict] = []
        self.classify_calls: list[tuple[str, list[dict]]] = []

    def classify_intent(
        self, text: str, history: list[dict[str, str]] | None = None
    ) -> dict:
        self.classify_calls.append((text, list(history or [])))
        return {"route": "task_create", "source": "fake", "usage": self.usage}

    def chat_with_tools(self, messages: list[dict], tools: list[dict], **_kwargs) -> dict:
        if self.fail_if_called:
            raise AssertionError("chat_with_tools should not be called")
        self.seen_messages = messages
        self.seen_tools = tools
        return {
            "text": self.text,
            "tool_calls": self.tool_calls,
            "source": "fake",
            "usage": self.usage,
        }

    def generate_guidance(self, system: str, user_input: str) -> dict:
        return {"text": "兜底", "source": "fake", "usage": self.usage}

    def analyze_headers(self, headers: list[str], samples: list[list[str]]) -> dict:
        raise AssertionError("analyze_headers should not be called")


def auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def register(client: TestClient, prefix: str = "Tool") -> str:
    nickname = f"{prefix}{uuid.uuid4().hex[:8]}"
    response = client.post(
        "/api/v1/auth/register", json={"nickname": nickname, "password": "demo123"}
    )
    assert response.status_code == 201, response.text
    return response.json()["access_token"]


def create_library(client: TestClient, token: str, name: str = "Tool Library") -> dict:
    response = client.post(
        "/api/v1/vocabularies",
        headers=auth(token),
        json={
            "subject": "english",
            "name": name,
            "description": "",
            "tags": ["tool"],
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
    return response.json()


def parse_sse(text: str) -> list[dict]:
    events = []
    for block in text.strip().split("\n\n"):
        data = next((line[6:] for line in block.splitlines() if line.startswith("data: ")), None)
        if data:
            events.append(json.loads(data))
    return events


def find_event(events: Iterable[dict], event_type: str) -> dict:
    return next(event for event in events if event["type"] == event_type)


def start_run(client: TestClient, token: str, message: str) -> list[dict]:
    response = client.post(
        "/api/v1/agent/runs/stream",
        headers=auth(token),
        json={"message": message},
    )
    assert response.status_code == 200, response.text
    return parse_sse(response.text)


def _app(settings: Settings, llm: FakeToolLLM, enabled: bool = True):
    return create_app(
        settings.model_copy(update={"agent_tool_calling_enabled": enabled}),
        llm=llm,
    )


def test_task_create_tool_calling_end_to_end(settings: Settings) -> None:
    fake = FakeToolLLM()
    app = _app(settings, fake)
    with TestClient(app) as client:
        token = register(client)
        library = create_library(client, token)
        fake.tool_calls = [
            {
                "id": "call_1",
                "name": "task_create_preview",
                "arguments": {
                    "name": "Tool 任务",
                    "library_id": library["id"],
                    "selection_mode": "prefix",
                    "prefix_count": 2,
                    "task_mode": "long_term",
                    "words_per_group": 5,
                    "dictation_mode": "offline",
                    "repeat_count": 3,
                },
                "raw_arguments": "{}",
            }
        ]

        events = start_run(client, token, "帮我用这个库建一个长期任务，前两个词")

        assert [tool["function"]["name"] for tool in fake.seen_tools] == [
            "task_create_preview"
        ]
        assert "user_id" not in fake.seen_tools[0]["function"]["parameters"]["properties"]
        assert fake.seen_messages[1]["content"] == "帮我用这个库建一个长期任务，前两个词"

        status = find_event(events, "tool_status")["data"]
        assert status["tool"] == "task.create_preview"
        assert status["status"] == "success"

        confirmation = find_event(events, "confirmation_required")["data"]
        draft = confirmation["payload"]["taskDraft"]
        assert draft["name"] == "Tool 任务"
        assert draft["mode"] == "long_term"
        assert draft["selectedEntryIds"] == [entry["id"] for entry in library["entries"][:2]]
        assert draft["wordsPerGroup"] == 2
        assert draft["dictation"]["mode"] == "offline"
        assert draft["dictation"]["repeatCount"] == 3

        database = Database(settings)
        with database.session() as session:
            messages = session.scalars(
                select(ConversationMessage)
                .where(ConversationMessage.tool_call_id == "call_1")
                .order_by(ConversationMessage.sequence_no)
            ).all()
            assert [message.message_type for message in messages] == ["tool_call", "tool_result"]
            assert messages[0].run_id == confirmation["id"]
        conversation = client.get("/api/v1/conversations/current", headers=auth(token)).json()
        execution = next(
            message for message in conversation["messages"] if message.get("kind") == "execution"
        )
        assert execution["execution"]["status"] == "success"
        assert execution["execution"]["tool"] == "task.create_preview"

        confirmed = client.post(
            f"/api/v1/agent/actions/{confirmation['id']}/confirm",
            headers=auth(token),
            json={
                "draftVersion": confirmation["draftVersion"],
                "configHash": confirmation["configHash"],
            },
        )
        assert confirmed.status_code == 200, confirmed.text
        confirmed_events = parse_sse(confirmed.text)
        assert "已创建" in find_event(confirmed_events, "message")["data"]["content"]
        tasks = client.get("/api/v1/tasks", headers=auth(token)).json()
        assert any(task["name"] == "Tool 任务" for task in tasks)


def test_tool_calling_business_error_does_not_create_preview(settings: Settings) -> None:
    fake = FakeToolLLM()
    app = _app(settings, fake)
    with TestClient(app) as client:
        token = register(client, "ToolErr")
        create_library(client, token)
        fake.tool_calls = [
            {
                "id": "call_bad",
                "name": "task_create_preview",
                "arguments": {"name": "坏任务", "library_id": "missing-library"},
                "raw_arguments": "{}",
            }
        ]
        events = start_run(client, token, "用不存在的词库建任务")
        assert "confirmation_required" not in {event["type"] for event in events}
        message = find_event(events, "message")["data"]["content"]
        assert "没能生成任务预览" in message
        status = find_event(events, "tool_status")["data"]
        assert status["status"] == "error"


def test_tool_calling_allows_clarifying_text_without_tool_call(settings: Settings) -> None:
    fake = FakeToolLLM()
    fake.text = "请问你想用哪个词库？"
    app = _app(settings, fake)
    with TestClient(app) as client:
        token = register(client, "ToolAsk")
        create_library(client, token)
        events = start_run(client, token, "建个任务")
        assert "confirmation_required" not in {event["type"] for event in events}
        assert find_event(events, "message")["data"]["content"] == "请问你想用哪个词库？"


def test_tool_calling_disabled_keeps_legacy_flow(settings: Settings) -> None:
    fake = FakeToolLLM()
    fake.fail_if_called = True
    app = _app(settings, fake, enabled=False)
    with TestClient(app) as client:
        assert app.state.agent_runtime.tool_workflow is None
        token = register(client, "ToolOff")
        library = create_library(client, token)
        events = start_run(client, token, f"创建任务，选择「{library['name']}」的所有单词")
        confirmation = find_event(events, "confirmation_required")["data"]
        draft = confirmation["payload"]["taskDraft"]
        assert len(draft["selectedEntryIds"]) == 3


def test_task_create_tool_prompt_only_needs_libraries() -> None:
    prompt = PromptRegistry(Path("app/modules/agent/prompts")).get("task_create_tools")
    assert prompt.variables == ("libraries",)


def test_tool_calling_uses_history_for_follow_up(settings: Settings) -> None:
    fake = FakeToolLLM()
    app = _app(settings, fake)
    with TestClient(app) as client:
        token = register(client, "ToolFollow")
        library = create_library(client, token)

        fake.text = "请问你想用哪个词库？"
        first = start_run(client, token, "创建任务")
        assert "confirmation_required" not in {event["type"] for event in first}
        assert find_event(first, "message")["data"]["content"] == "请问你想用哪个词库？"

        fake.text = ""
        fake.tool_calls = [
            {
                "id": "call_follow",
                "name": "task_create_preview",
                "arguments": {"name": "追问任务", "library_id": library["id"]},
                "raw_arguments": "{}",
            }
        ]
        second = start_run(client, token, f"用「{library['name']}」")

        history = fake.classify_calls[1][1]
        assert {"role": "user", "content": "创建任务"} in history
        assert {"role": "assistant", "content": "请问你想用哪个词库？"} in history
        messages = fake.seen_messages
        assert messages[-1] == {"role": "user", "content": f"用「{library['name']}」"}
        assert {"role": "assistant", "content": "请问你想用哪个词库？"} in messages
        confirmation = find_event(second, "confirmation_required")["data"]
        assert confirmation["payload"]["taskDraft"]["selectedEntryIds"] == [
            entry["id"] for entry in library["entries"]
        ]


def test_library_candidates_cap_per_subject_and_keep_mentioned() -> None:
    from datetime import UTC, datetime, timedelta
    from types import SimpleNamespace

    from app.modules.agent.tool_workflow import TaskCreateToolWorkflow

    now = datetime.now(UTC)

    def library(name: str, subject: str, owner: str, minutes: int, index: int):
        return SimpleNamespace(
            id=f"{subject}-{index}",
            name=name,
            subject=subject,
            owner_user_id=owner,
            updated_at=now - timedelta(minutes=minutes),
            entries=[object()],
        )

    libraries = [
        library("个人英语A", "english", "user-1", 50, 1),
        library("个人英语B", "english", "user-1", 40, 2),
        library("公共英语C", "english", "other", 1, 3),
        library("公共英语D", "english", "other", 2, 4),
        library("点名英语E", "english", "other", 100, 5),
        library("个人语文A", "chinese", "user-1", 10, 6),
        library("个人语文B", "chinese", "user-1", 20, 7),
        library("个人语文C", "chinese", "user-1", 30, 8),
        library("个人语文D", "chinese", "user-1", 40, 9),
    ]
    selected, counts = TaskCreateToolWorkflow._select_library_candidates(
        libraries, "用点名英语E创建任务", "user-1"
    )
    english = [item.name for item in selected if item.subject == "english"]
    chinese = [item.name for item in selected if item.subject == "chinese"]
    assert counts == {"english": 5, "chinese": 4}
    assert len(english) == 3
    assert len(chinese) == 3
    assert "点名英语E" in english
    assert "个人英语A" in english
    assert english[0] == "点名英语E"
    assert chinese == ["个人语文A", "个人语文B", "个人语文C"]


def test_new_run_does_not_inherit_previous_task_links(client: TestClient) -> None:
    token = register(client, "LinkReset")
    library = create_library(client, token, "Link Reset Library")
    events = start_run(client, token, f"创建任务，选择「{library['name']}」的所有单词")
    confirmation = find_event(events, "confirmation_required")["data"]
    confirmed = client.post(
        f"/api/v1/agent/actions/{confirmation['id']}/confirm",
        headers=auth(token),
        json={
            "draftVersion": confirmation["draftVersion"],
            "configHash": confirmation["configHash"],
        },
    )
    assert confirmed.status_code == 200, confirmed.text
    created = find_event(parse_sse(confirmed.text), "message")["data"]
    assert created["links"][0]["label"] == "打开任务"

    follow_up = start_run(client, token, "你好")
    message = find_event(follow_up, "message")["data"]
    assert not message.get("links")
