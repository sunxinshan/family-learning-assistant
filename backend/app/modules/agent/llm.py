from typing import Any, Protocol

import httpx

from app.core.config import Settings


class LLMAdapter(Protocol):
    def classify_intent(self, text: str) -> dict[str, Any]: ...


class MockLLMAdapter:
    def classify_intent(self, text: str) -> dict[str, Any]:
        lowered = text.strip()
        if any(word in lowered for word in ("创建", "新建", "生成", "安排")) and "任务" in lowered:
            route = "task_create"
        elif any(word in lowered for word in ("修改", "调整", "改成")) and "任务" in lowered:
            route = "task_update"
        elif "删除" in lowered and "任务" in lowered:
            route = "task_delete"
        elif any(word in lowered for word in ("学习记录", "正确率", "错题", "掌握")):
            route = "learning"
        else:
            route = "chat"
        return {"route": route, "confidence": 0.99, "source": "mock"}


class OpenAICompatibleAdapter:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def classify_intent(self, text: str) -> dict[str, Any]:
        if not self.settings.llm_api_key:
            raise RuntimeError("FLA_LLM_API_KEY is not configured")
        response = httpx.post(
            f"{self.settings.llm_base_url.rstrip('/')}/chat/completions",
            headers={"Authorization": f"Bearer {self.settings.llm_api_key.get_secret_value()}"},
            json={
                "model": self.settings.llm_model,
                "temperature": 0,
                "response_format": {"type": "json_object"},
                "messages": [
                    {
                        "role": "system",
                        "content": (
                            "Classify the user's route as one of: task_create, task_update, "
                            "task_delete, learning, chat, unclear. Return JSON with route."
                        ),
                    },
                    {"role": "user", "content": text},
                ],
            },
            timeout=self.settings.llm_timeout_seconds,
        )
        response.raise_for_status()
        import json

        content = response.json()["choices"][0]["message"]["content"]
        parsed = json.loads(content)
        parsed["source"] = "llm"
        return parsed


def create_llm_adapter(settings: Settings) -> LLMAdapter:
    if settings.llm_provider == "openai_compatible":
        return OpenAICompatibleAdapter(settings)
    return MockLLMAdapter()
