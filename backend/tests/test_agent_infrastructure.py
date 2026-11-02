import json

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import SecretStr

from app.core.exceptions import AppError
from app.modules.agent.llm import OpenAICompatibleAdapter
from app.modules.agent.prompt_registry import PromptRegistry
from app.modules.agent.tools import ToolRegistry


def login(client: TestClient, nickname: str = "Alice", password: str = "demo123") -> str:
    response = client.post("/api/v1/auth/login", json={"nickname": nickname, "password": password})
    assert response.status_code == 200, response.text
    return response.json()["access_token"]


def auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _completion(content: str = '{"route":"chat"}') -> dict:
    return {
        "choices": [{"message": {"content": content}}],
        "usage": {"prompt_tokens": 11, "completion_tokens": 7, "total_tokens": 18},
    }


def test_openai_adapter_retries_rate_limit_and_records_usage(settings) -> None:
    settings = settings.model_copy(update={"llm_api_key": SecretStr("test-key")})
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        if calls == 1:
            return httpx.Response(429, json={"error": "rate limited"}, request=request)
        return httpx.Response(200, json=_completion('{"route":"learning"}'), request=request)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    adapter = OpenAICompatibleAdapter(settings, client=client, backoff_seconds=0)
    result = adapter.classify_intent("查看学习记录")
    assert result["route"] == "learning"
    assert result["usage"]["total_tokens"] == 18
    assert calls == 2


def test_openai_adapter_maps_timeout_and_server_errors(settings) -> None:
    settings = settings.model_copy(update={"llm_api_key": SecretStr("test-key")})

    def timeout_handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("timed out", request=request)

    timeout_adapter = OpenAICompatibleAdapter(
        settings,
        client=httpx.Client(transport=httpx.MockTransport(timeout_handler)),
        backoff_seconds=0,
        max_attempts=2,
    )
    with pytest.raises(AppError) as timeout:
        timeout_adapter.classify_intent("hello")
    assert timeout.value.code == "llm_timeout"
    assert timeout.value.status_code == 504

    def unavailable_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, request=request)

    unavailable_adapter = OpenAICompatibleAdapter(
        settings,
        client=httpx.Client(transport=httpx.MockTransport(unavailable_handler)),
        backoff_seconds=0,
        max_attempts=2,
    )
    with pytest.raises(AppError) as unavailable:
        unavailable_adapter.classify_intent("hello")
    assert unavailable.value.code == "llm_unavailable"


def test_prompt_registry_version_hash_and_variable_validation(tmp_path) -> None:
    (tmp_path / "demo.txt").write_text("Hello {name}, subject={subject}", encoding="utf-8")
    prompt = PromptRegistry(tmp_path).get("demo")
    assert prompt.variables == ("name", "subject")
    assert len(prompt.content_hash) == 64
    assert prompt.render({"name": "Alice", "subject": "English"}) == "Hello Alice, subject=English"
    with pytest.raises(AppError) as missing:
        prompt.render({"name": "Alice"})
    assert missing.value.code == "prompt_missing_variables"
    with pytest.raises(AppError) as missing_prompt:
        PromptRegistry(tmp_path).get("../../etc/passwd")
    assert missing_prompt.value.code == "invalid_prompt_id"


def test_tool_registry_permission_filtering(client: TestClient, app: FastAPI) -> None:
    registry = ToolRegistry(app.state.agent_runtime.business)
    user_tools = registry.available("user")
    admin_tools = registry.available("admin")
    assert "learning.stats" in {tool["name"] for tool in user_tools}
    assert "admin.execution_detail" not in {tool["name"] for tool in user_tools}
    assert "admin.execution_detail" in {tool["name"] for tool in admin_tools}

    forbidden = registry.invoke("admin.execution_detail", "user-1", "user")
    assert forbidden.ok is False
    assert forbidden.error_code == "forbidden"


def test_execution_details_are_redacted_and_admin_visible(client: TestClient) -> None:
    alice = login(client)
    admin = login(client, "admin", "admin213")
    bob = login(client, "Bob", "demo123")
    library = client.post(
        "/api/v1/vocabularies",
        headers=auth(alice),
        json={
            "subject": "english",
            "name": "Detail Library",
            "description": "",
            "tags": [],
            "entries": [
                {
                    "word": "detail",
                    "phonetic": "",
                    "partOfSpeech": "n.",
                    "meanings": ["细节"],
                    "example": "",
                    "exampleTranslation": "",
                }
            ],
        },
    ).json()
    run_response = client.post(
        "/api/v1/agent/runs/stream",
        headers=auth(alice),
        json={"message": f"创建任务，选择「{library['name']}」的所有单词"},
    )
    data_lines = [line[6:] for line in run_response.text.splitlines() if line.startswith("data: ")]
    import json

    events = [json.loads(item) for item in data_lines]
    confirmation = next(item for item in events if item["type"] == "confirmation_required")
    run_id = confirmation["run_id"]
    action = confirmation["data"]
    action["payload"]["credentials"] = {"password": "top-secret", "token": "abc123"}
    updated = client.patch(
        f"/api/v1/agent/actions/{run_id}/draft",
        headers=auth(alice),
        json={"action": action},
    )
    assert updated.status_code == 200, updated.text

    details = client.get(f"/api/v1/agent/runs/{run_id}/details", headers=auth(alice))
    assert details.status_code == 200, details.text
    body = details.json()
    assert body["promptVersion"]
    assert "top-secret" not in details.text
    assert "abc123" not in details.text
    assert body["availableTools"]
    assert client.get(f"/api/v1/agent/runs/{run_id}/details", headers=auth(bob)).status_code == 404
    assert (
        client.get(f"/api/v1/agent/runs/{run_id}/details", headers=auth(admin)).status_code == 200
    )


def test_openai_adapter_analyzes_unknown_headers(settings) -> None:
    settings = settings.model_copy(update={"llm_api_key": SecretStr("test-key")})
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured.update(json.loads(request.content))
        return httpx.Response(
            200,
            json=_completion(
                '{"mapping":{"word":0,"phonetic":-1,"partOfSpeech":-1,'
                '"meaning":1,"example":-1,"exampleTranslation":-1},'
                '"confidence":0.93,"reason":"header semantics"}'
            ),
            request=request,
        )

    adapter = OpenAICompatibleAdapter(
        settings,
        client=httpx.Client(transport=httpx.MockTransport(handler)),
        backoff_seconds=0,
    )
    result = adapter.analyze_headers(["Lexeme", "Explain"], [["apple", "苹果"]])
    assert result["mapping"]["word"] == 0
    assert result["mapping"]["meaning"] == 1
    assert result["confidence"] == 0.93
    assert result["promptVersion"].startswith("v1:")
    assert "Lexeme" in captured["messages"][1]["content"]
    assert "少量样例行" in captured["messages"][0]["content"]


def test_openai_adapter_enriches_only_requested_fields(settings) -> None:
    settings = settings.model_copy(update={"llm_api_key": SecretStr("test-key")})
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured.update(json.loads(request.content))
        return httpx.Response(
            200,
            json=_completion(
                '{"entries":[{"index":0,"phonetic":"/ˈæpl/","meanings":["苹果"]},'
                '{"index":1,"phonetic":"píng guǒ"}],"confidence":0.9,"reason":"dictionary"}'
            ),
            request=request,
        )

    adapter = OpenAICompatibleAdapter(
        settings,
        client=httpx.Client(transport=httpx.MockTransport(handler)),
        backoff_seconds=0,
    )
    result = adapter.enrich_entries(
        [
            {"index": 0, "word": "apple", "needs": ["phonetic", "meaning"], "existing": {}},
            {"index": 1, "word": "苹果", "needs": ["phonetic"], "existing": {}},
        ]
    )
    assert result["entries"][0]["meanings"] == ["苹果"]
    assert result["entries"][1]["phonetic"] == "píng guǒ"
    assert result["promptVersion"].startswith("v1:")
    assert "只补充 needs" in captured["messages"][0]["content"]
