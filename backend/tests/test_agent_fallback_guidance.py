import json
from collections.abc import Iterable
from pathlib import Path

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import SecretStr

from app.core.exceptions import AppError
from app.modules.agent.guidance import FALLBACK_GUIDANCE_TEXT, FallbackGuidanceService
from app.modules.agent.llm import OpenAICompatibleAdapter
from app.modules.agent.prompt_registry import PromptRegistry


def login(client: TestClient, nickname: str = "Alice", password: str = "demo123") -> str:
    response = client.post("/api/v1/auth/login", json={"nickname": nickname, "password": password})
    assert response.status_code == 200, response.text
    return response.json()["access_token"]


def auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def parse_sse(text: str) -> list[dict]:
    events = []
    for block in text.strip().split("\n\n"):
        data = next((line[6:] for line in block.splitlines() if line.startswith("data: ")), None)
        if data:
            events.append(json.loads(data))
    return events


def start_run(client: TestClient, token: str, message: str) -> list[dict]:
    response = client.post(
        "/api/v1/agent/runs/stream",
        headers=auth(token),
        json={"message": message},
    )
    assert response.status_code == 200, response.text
    return parse_sse(response.text)


def find_event(events: Iterable[dict], event_type: str) -> dict:
    return next(event for event in events if event["type"] == event_type)


class RecordingLLM:
    def __init__(self, text: str = "引导文本", error: AppError | None = None) -> None:
        self.text = text
        self.error = error
        self.calls: list[tuple[str, str]] = []

    def generate_guidance(self, system: str, user_input: str) -> dict:
        self.calls.append((system, user_input))
        if self.error:
            raise self.error
        return {"text": self.text, "source": "llm", "usage": {"total_tokens": 6}}


@pytest.fixture
def guide_dir(tmp_path):
    prompts = tmp_path / "prompts"
    prompts.mkdir()
    (prompts / "capability_guide.md").write_text("# 能力\n\n- 创建听写任务\n", encoding="utf-8")
    (prompts / "fallback_guidance.txt").write_text(
        "规则\n{capability_guide}\n", encoding="utf-8"
    )
    return prompts


def test_guide_is_real_and_has_no_template_placeholders() -> None:
    guide = PromptRegistry(Path("app/modules/agent/prompts")).get_document("capability_guide")
    assert "当前可用能力" in guide.content
    assert "创建听写任务" in guide.content
    assert "根据教材或课本内容自动生成听写任务" in guide.content
    assert "{能力名称}" not in guide.content
    assert "{capability_guide}" not in guide.content
    assert len(guide.content_hash) == 64
    prompt = PromptRegistry(Path("app/modules/agent/prompts")).get("fallback_guidance")
    assert prompt.variables == ("capability_guide",)


def test_guidance_prompt_assembles_guide_and_user_input(guide_dir) -> None:
    llm = RecordingLLM()
    service = FallbackGuidanceService(llm, guide_dir)
    result = service.respond("我想把任务改成每组 10 个")
    assert result.source == "llm"
    assert result.text == "引导文本"
    assert len(llm.calls) == 1
    system, user_input = llm.calls[0]
    assert "创建听写任务" in system
    assert "{capability_guide}" not in system
    assert user_input == "我想把任务改成每组 10 个"
    assert result.guide_version


def test_guidance_falls_back_when_guide_missing(tmp_path) -> None:
    service = FallbackGuidanceService(RecordingLLM(), tmp_path)
    result = service.respond("随便说点什么")
    assert result.source == "fallback"
    assert result.failure_reason == "guide_unavailable"
    assert result.text == FALLBACK_GUIDANCE_TEXT


def test_guidance_falls_back_when_llm_fails(guide_dir) -> None:
    llm = RecordingLLM(error=AppError("llm_timeout", "超时", status_code=504))
    result = FallbackGuidanceService(llm, guide_dir).respond("你好")
    assert result.source == "fallback"
    assert result.failure_reason == "llm_timeout"
    assert result.text == FALLBACK_GUIDANCE_TEXT


def test_unrecognized_intent_returns_input_aware_guidance(client: TestClient) -> None:
    token = login(client)
    first = start_run(client, token, "今天天气怎么样")
    second = start_run(client, token, "帮我订一张去北京的机票")

    first_message = find_event(first, "message")["data"]["content"]
    second_message = find_event(second, "message")["data"]["content"]
    assert "天气" in first_message
    assert "机票" in second_message
    assert first_message != second_message
    assert "我可以帮你创建和管理学习任务" not in first_message
    assert "confirmation_required" not in {event["type"] for event in first}
    assert not first_message.startswith("已整理")


def test_fallback_does_not_write_business_data(client: TestClient) -> None:
    token = login(client)
    before = client.get("/api/v1/tasks", headers=auth(token)).json()
    events = start_run(client, token, "今天适合学习吗")
    assert "confirmation_required" not in {event["type"] for event in events}
    assert find_event(events, "done")
    after = client.get("/api/v1/tasks", headers=auth(token)).json()
    assert len(after) == len(before)


def test_unsupported_capability_is_declined(client: TestClient) -> None:
    token = login(client)
    events = start_run(client, token, "你能根据课本自动听写吗")
    message = find_event(events, "message")["data"]["content"]
    assert "不支持" in message


def test_fallback_receives_real_guide_and_original_input(
    client: TestClient, app: FastAPI
) -> None:
    token = login(client)
    recorder = RecordingLLM("我目前可以帮你创建听写任务。你可以说：「用词库创建听写任务」。")
    app.state.agent_runtime.guidance.llm = recorder
    events = start_run(client, token, "随便聊两句")
    message = find_event(events, "message")["data"]["content"]
    assert message == recorder.text
    system, user_input = recorder.calls[0]
    assert "当前可用能力" in system
    assert user_input == "随便聊两句"


def test_fallback_llm_failure_keeps_conversation_alive(
    client: TestClient, app: FastAPI
) -> None:
    token = login(client)
    app.state.agent_runtime.guidance.llm = RecordingLLM(
        error=AppError("llm_unavailable", "LLM 服务暂时不可用", status_code=503)
    )
    events = start_run(client, token, "嗯……")
    message = find_event(events, "message")["data"]["content"]
    assert message == FALLBACK_GUIDANCE_TEXT
    assert find_event(events, "done")
    assert "error" not in {event["type"] for event in events}


def test_user_can_retry_after_guidance(client: TestClient) -> None:
    token = login(client)
    start_run(client, token, "今天天气怎么样")
    library = client.post(
        "/api/v1/vocabularies",
        headers=auth(token),
        json={
            "subject": "english",
            "name": "Retry Library",
            "description": "",
            "tags": [],
            "entries": [
                {
                    "word": "retry",
                    "phonetic": "",
                    "partOfSpeech": "n.",
                    "meanings": ["重试"],
                    "example": "",
                    "exampleTranslation": "",
                }
            ],
        },
    ).json()
    events = start_run(client, token, f"创建任务，选择「{library['name']}」的所有单词")
    assert find_event(events, "confirmation_required")


def test_openai_adapter_generates_plain_text_guidance(settings, tmp_path) -> None:
    settings = settings.model_copy(update={"llm_api_key": SecretStr("test-key")})
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured.update(json.loads(request.content))
        return httpx.Response(
            200,
            json={
                "choices": [{"message": {"content": "你可以先创建词库。"}}],
                "usage": {"prompt_tokens": 20, "completion_tokens": 8, "total_tokens": 28},
            },
            request=request,
        )

    adapter = OpenAICompatibleAdapter(
        settings, client=httpx.Client(transport=httpx.MockTransport(handler)), backoff_seconds=0
    )
    result = adapter.generate_guidance("系统指令", "我想听写")
    assert result["text"] == "你可以先创建词库。"
    assert result["source"] == "llm"
    assert result["usage"]["total_tokens"] == 28
    assert "response_format" not in captured
    assert captured["temperature"] != 0
    assert captured["messages"][1]["content"] == "我想听写"
