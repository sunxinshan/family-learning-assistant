import json
import time
from pathlib import Path
from typing import Any, Protocol

import httpx

from app.core.config import Settings
from app.core.exceptions import AppError
from app.modules.agent.prompt_registry import PromptRegistry
from app.modules.content.parser import CANONICAL_FIELDS, _rule_mapping, normalize_header


class LLMAdapter(Protocol):
    def classify_intent(self, text: str) -> dict[str, Any]: ...

    def analyze_headers(self, headers: list[str], samples: list[list[str]]) -> dict[str, Any]: ...


class MockLLMAdapter:
    def classify_intent(self, text: str) -> dict[str, Any]:
        lowered = text.strip()
        if any(word in lowered for word in ("创建", "新建", "生成", "安排")) and "任务" in lowered:
            route = "task_create"
        elif any(word in lowered for word in ("修改", "调整", "改成")) and "任务" in lowered:
            route = "task_update"
        elif "删除" in lowered and "任务" in lowered:
            route = "task_delete"
        elif (
            any(word in lowered for word in ("导入", "上传", "Excel", "excel", "CSV", "csv"))
            and "词库" in lowered
        ):
            route = "vocabulary_import"
        elif any(word in lowered for word in ("创建", "新建", "整理")) and "词库" in lowered:
            route = "vocabulary_create"
        elif any(word in lowered for word in ("学习记录", "正确率", "错题", "掌握")):
            route = "learning"
        else:
            route = "chat"
        return {
            "route": route,
            "confidence": 0.99,
            "source": "mock",
            "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
        }

    def analyze_headers(self, headers: list[str], samples: list[list[str]]) -> dict[str, Any]:
        mapping = _rule_mapping(headers)
        used = {value for value in mapping.values() if value >= 0}
        keywords = {
            "word": ("word", "term", "vocab", "lexeme", "单词", "词语", "词汇"),
            "phonetic": ("phon", "ipa", "pronoun", "音标", "拼音", "读音"),
            "pos": ("partofspeech", "part_of_speech", "词性", "词类", "pos"),
            "meaning": (
                "mean",
                "defin",
                "gloss",
                "explain",
                "释义",
                "词义",
                "含义",
                "意思",
                "解释",
            ),
            "example": ("example", "sentence", "例句", "句子"),
            "translation": (
                "translation",
                "translate",
                "翻译",
                "例句中文",
                "句子翻译",
            ),
        }
        normalized = [normalize_header(header) for header in headers]
        for field in CANONICAL_FIELDS:
            if mapping[field] >= 0:
                continue
            index = next(
                (
                    i
                    for i, header in enumerate(normalized)
                    if i not in used and any(token in header for token in keywords[field])
                ),
                -1,
            )
            mapping[field] = index
            if index >= 0:
                used.add(index)
        return {
            "mapping": mapping,
            "confidence": 0.72,
            "reason": "Mock 词义与样例结构推断",
            "source": "mock",
            "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
        }


class OpenAICompatibleAdapter:
    def __init__(
        self,
        settings: Settings,
        *,
        client: httpx.Client | None = None,
        backoff_seconds: float = 0.25,
        max_attempts: int = 3,
    ) -> None:
        self.settings = settings
        self.client = client or httpx.Client(timeout=settings.llm_timeout_seconds)
        self.backoff_seconds = backoff_seconds
        self.max_attempts = max_attempts

    def _chat_json(self, system: str, user: str) -> dict[str, Any]:
        if not self.settings.llm_api_key:
            raise AppError("llm_not_configured", "LLM 服务尚未配置", status_code=503)
        last_error: Exception | None = None
        for attempt in range(self.max_attempts):
            try:
                response = self.client.post(
                    f"{self.settings.llm_base_url.rstrip('/')}/chat/completions",
                    headers={
                        "Authorization": (f"Bearer {self.settings.llm_api_key.get_secret_value()}")
                    },
                    json={
                        "model": self.settings.llm_model,
                        "temperature": 0,
                        "response_format": {"type": "json_object"},
                        "messages": [
                            {"role": "system", "content": system},
                            {"role": "user", "content": user},
                        ],
                    },
                )
                if response.status_code == 429:
                    last_error = AppError(
                        "llm_rate_limited", "LLM 请求过于频繁，请稍后重试", status_code=503
                    )
                    if attempt + 1 < self.max_attempts:
                        time.sleep(self.backoff_seconds * (2**attempt))
                        continue
                    raise last_error
                if response.status_code >= 500:
                    last_error = AppError("llm_unavailable", "LLM 服务暂时不可用", status_code=503)
                    if attempt + 1 < self.max_attempts:
                        time.sleep(self.backoff_seconds * (2**attempt))
                        continue
                    raise last_error
                response.raise_for_status()
                body = response.json()
                content = body["choices"][0]["message"]["content"]
                parsed = json.loads(content)
                parsed["source"] = "llm"
                usage = body.get("usage") or {}
                parsed["usage"] = {
                    "prompt_tokens": int(usage.get("prompt_tokens", 0)),
                    "completion_tokens": int(usage.get("completion_tokens", 0)),
                    "total_tokens": int(usage.get("total_tokens", 0)),
                }
                return parsed
            except AppError:
                raise
            except httpx.TimeoutException as exc:
                last_error = exc
                if attempt + 1 < self.max_attempts:
                    time.sleep(self.backoff_seconds * (2**attempt))
                    continue
                raise AppError("llm_timeout", "LLM 请求超时，请稍后重试", status_code=504) from exc
            except (httpx.HTTPError, KeyError, ValueError, TypeError) as exc:
                last_error = exc
                if attempt + 1 < self.max_attempts:
                    time.sleep(self.backoff_seconds * (2**attempt))
                    continue
                raise AppError(
                    "llm_invalid_response", "LLM 返回结果无法解析", status_code=502
                ) from exc
        raise AppError("llm_unavailable", "LLM 服务暂时不可用", status_code=503) from last_error

    def classify_intent(self, text: str) -> dict[str, Any]:
        return self._chat_json(
            (
                "Classify the user's route as one of: task_create, task_update, "
                "task_delete, vocabulary_create, vocabulary_import, learning, chat, "
                "unclear. Return JSON with route. Never include credentials."
            ),
            text,
        )

    def analyze_headers(self, headers: list[str], samples: list[list[str]]) -> dict[str, Any]:
        prompt = PromptRegistry(Path(self.settings.prompt_dir)).get("header_mapping")
        result = self._chat_json(
            prompt.content,
            json.dumps(
                {"headers": headers, "sampleRows": samples},
                ensure_ascii=False,
            ),
        )
        result["promptVersion"] = f"{prompt.version}:{prompt.content_hash[:12]}"
        return result


def create_llm_adapter(settings: Settings) -> LLMAdapter:
    if settings.llm_provider == "openai_compatible":
        return OpenAICompatibleAdapter(settings)
    return MockLLMAdapter()
