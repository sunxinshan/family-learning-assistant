import json
import time
from collections.abc import Callable
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

    def generate_guidance(self, system: str, user_input: str) -> dict[str, Any]: ...

    def chat_with_tools(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        *,
        temperature: float = 0.2,
    ) -> dict[str, Any]: ...


_MOCK_WORDS = {
    "apple": {"phonetic": "/ˈæpl/", "meanings": ["苹果"]},
    "book": {"phonetic": "/bʊk/", "meanings": ["书"]},
    "hello": {"phonetic": "/həˈləʊ/", "meanings": ["你好"]},
    "world": {"phonetic": "/wɜːld/", "meanings": ["世界"]},
    "agent": {"phonetic": "/ˈeɪdʒənt/", "meanings": ["代理；智能体"]},
    "graph": {"phonetic": "/ɡræf/", "meanings": ["图；图表"]},
    "orbit": {"phonetic": "/ˈɔːbɪt/", "meanings": ["轨道"]},
    "signal": {"phonetic": "/ˈsɪɡnəl/", "meanings": ["信号"]},
    "private": {"phonetic": "/ˈpraɪvət/", "meanings": ["私人的"]},
    "shared": {"phonetic": "/ʃeəd/", "meanings": ["共享的"]},
    "detail": {"phonetic": "/ˈdiːteɪl/", "meanings": ["细节"]},
    "changed": {"phonetic": "/tʃeɪndʒd/", "meanings": ["改变了的"]},
}

_MOCK_PINYIN = {
    "苹": "píng",
    "果": "guǒ",
    "书": "shū",
    "学": "xué",
    "习": "xí",
    "语": "yǔ",
    "文": "wén",
    "你": "nǐ",
    "好": "hǎo",
    "世": "shì",
    "界": "jiè",
    "词": "cí",
    "库": "kù",
}

_MOCK_GUIDANCE_TOPICS = (
    (
        ("任务", "听写"),
        "创建、修改或删除听写任务",
        "用我的词库「单词本」创建听写任务，每组 5 个",
    ),
    (
        ("词库", "单词本", "导入", "excel", "csv", "Excel", "CSV"),
        "创建个人词库，或把上传的 Excel/CSV 文件导入成词库",
        "把这次上传的 Excel 导入成「三年级英语」词库",
    ),
    (
        ("学习", "正确率", "错题", "掌握", "统计", "记录"),
        "查看练习次数、平均正确率、已掌握和待复习的词数",
        "看看我最近的学习记录",
    ),
)


def _mock_pinyin(word: str) -> str:
    values = [_MOCK_PINYIN.get(character) for character in word if not character.isspace()]
    if not values or any(value is None for value in values):
        return ""
    return " ".join(str(value) for value in values)


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

    def enrich_entries(self, entries: list[dict[str, Any]]) -> dict[str, Any]:
        enriched = []
        for item in entries:
            word = str(item.get("word", "")).strip()
            needs = set(item.get("needs", []))
            known = _MOCK_WORDS.get(word.casefold(), {})
            result: dict[str, Any] = {"index": item["index"]}
            if "phonetic" in needs:
                result["phonetic"] = known.get("phonetic") or _mock_pinyin(word)
            if "meaning" in needs:
                result["meanings"] = known.get("meanings", [])
            enriched.append(result)
        return {
            "entries": enriched,
            "confidence": 0.7,
            "reason": "Mock 本地演示词表与拼音映射",
            "source": "mock",
            "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
        }

    def generate_guidance(self, system: str, user_input: str) -> dict[str, Any]:
        text = " ".join(str(user_input).split())
        excerpt = text[:40] + ("…" if len(text) > 40 else "")
        if any(word in text for word in ("教材", "课本")):
            reply = (
                "我理解你想根据教材或课本内容自动生成听写，不过当前版本暂时不支持直接读取教材。"
                "你可以先创建或导入一个词库，再用它创建听写任务。"
            )
        elif not text or text.rstrip("！!。.？?，, ") in {"你好", "hi", "hello", "在吗", "在么"}:
            reply = (
                "你好！我可以帮你创建、修改或删除听写任务，创建或导入词库，也能查看学习统计。"
                "你可以试着说：「用我的词库创建听写任务，选择所有单词」。"
            )
        else:
            for keywords, capability, example in _MOCK_GUIDANCE_TOPICS:
                if any(keyword in text for keyword in keywords):
                    reply = (
                        f"我理解你想处理「{excerpt}」。我可以帮你{capability}。"
                        f"你可以这样说：「{example}」"
                    )
                    break
            else:
                reply = (
                    f"我理解你想问「{excerpt}」，不过这个我暂时还做不到。"
                    "目前我可以帮你创建、修改、删除听写任务，创建或导入词库，以及查看学习统计。"
                    "你可以换个说法描述你的学习目标。"
                )
        return {
            "text": reply,
            "source": "mock",
            "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
        }

    def chat_with_tools(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        *,
        temperature: float = 0.2,
    ) -> dict[str, Any]:
        return {
            "text": "（Mock）当前没有可执行的工具调用。",
            "tool_calls": [],
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

    def _post(
        self,
        body: dict[str, Any],
        parser: Callable[[dict[str, Any]], dict[str, Any]],
    ) -> dict[str, Any]:
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
                    json=body,
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
                return parser(response.json())
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

    @staticmethod
    def _token_usage(payload: dict[str, Any]) -> dict[str, int]:
        usage = payload.get("usage") or {}
        return {
            "prompt_tokens": int(usage.get("prompt_tokens", 0)),
            "completion_tokens": int(usage.get("completion_tokens", 0)),
            "total_tokens": int(usage.get("total_tokens", 0)),
        }

    def _chat(self, system: str, user: str, *, json_mode: bool) -> dict[str, Any]:
        body: dict[str, Any] = {
            "model": self.settings.llm_model,
            "temperature": 0 if json_mode else 0.4,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        }
        if json_mode:
            body["response_format"] = {"type": "json_object"}

        def parse(payload: dict[str, Any]) -> dict[str, Any]:
            content = payload["choices"][0]["message"]["content"]
            usage = self._token_usage(payload)
            if json_mode:
                parsed = json.loads(content)
                parsed["source"] = "llm"
                parsed["usage"] = usage
                return parsed
            return {"text": str(content or "").strip(), "source": "llm", "usage": usage}

        return self._post(body, parse)

    def chat_with_tools(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        *,
        temperature: float = 0.2,
    ) -> dict[str, Any]:
        body: dict[str, Any] = {
            "model": self.settings.llm_model,
            "temperature": temperature,
            "messages": messages,
            "tool_choice": "auto",
        }
        if tools:
            body["tools"] = tools

        def parse(payload: dict[str, Any]) -> dict[str, Any]:
            message = payload["choices"][0]["message"]
            calls: list[dict[str, Any]] = []
            for item in message.get("tool_calls") or []:
                function = item.get("function") or {}
                raw = function.get("arguments") or "{}"
                try:
                    arguments = json.loads(raw) if isinstance(raw, str) else raw
                except ValueError:
                    arguments = None
                calls.append(
                    {
                        "id": str(item.get("id") or ""),
                        "name": str(function.get("name") or ""),
                        "arguments": arguments,
                        "raw_arguments": raw if isinstance(raw, str) else json.dumps(raw),
                    }
                )
            return {
                "text": str(message.get("content") or "").strip(),
                "tool_calls": calls,
                "source": "llm",
                "usage": self._token_usage(payload),
            }

        return self._post(body, parse)

    def _chat_json(self, system: str, user: str) -> dict[str, Any]:
        return self._chat(system, user, json_mode=True)

    def generate_guidance(self, system: str, user_input: str) -> dict[str, Any]:
        return self._chat(system, user_input, json_mode=False)

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

    def enrich_entries(self, entries: list[dict[str, Any]]) -> dict[str, Any]:
        prompt = PromptRegistry(Path(self.settings.prompt_dir)).get("entry_enrichment")
        result = self._chat_json(
            prompt.content,
            json.dumps({"entries": entries}, ensure_ascii=False),
        )
        result["promptVersion"] = f"{prompt.version}:{prompt.content_hash[:12]}"
        return result


def create_llm_adapter(settings: Settings) -> LLMAdapter:
    if settings.llm_provider == "openai_compatible":
        return OpenAICompatibleAdapter(settings)
    return MockLLMAdapter()
