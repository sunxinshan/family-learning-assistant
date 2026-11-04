"""意图识别失败后的兜底引导。

只负责读取 capability_guide.md、组装兜底 Prompt 并调用 LLM 生成自然语言引导，
不解析业务参数，不创建或修改任何业务数据。
"""

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.core.exceptions import AppError
from app.modules.agent.llm import LLMAdapter
from app.modules.agent.prompt_registry import PromptRegistry

logger = logging.getLogger("app.agent.guidance")

FALLBACK_GUIDANCE_TEXT = (
    "抱歉，我暂时没能理解你的需求。可以换一种说法，描述你想完成的学习任务、"
    "词库或学习记录吗？"
)


@dataclass(frozen=True)
class GuidanceResult:
    text: str
    source: str
    guide_version: str | None = None
    usage: dict[str, int] | None = None
    failure_reason: str | None = None


class FallbackGuidanceService:
    def __init__(self, llm: LLMAdapter, prompt_dir: str | Path) -> None:
        self.llm = llm
        self.registry = PromptRegistry(Path(prompt_dir))

    def respond(self, user_input: str) -> GuidanceResult:
        try:
            guide = self.registry.get_document("capability_guide")
        except AppError as exc:
            logger.warning("capability guide unavailable code=%s", exc.code)
            return GuidanceResult(
                FALLBACK_GUIDANCE_TEXT,
                "fallback",
                failure_reason="guide_unavailable",
            )

        try:
            prompt = self.registry.get("fallback_guidance")
            system = prompt.render({"capability_guide": guide.content})
        except AppError as exc:
            logger.warning(
                "fallback prompt unavailable code=%s guide=%s", exc.code, guide.content_hash[:12]
            )
            return GuidanceResult(
                FALLBACK_GUIDANCE_TEXT,
                "fallback",
                guide.content_hash[:12],
                failure_reason="prompt_unavailable",
            )

        try:
            result: dict[str, Any] = self.llm.generate_guidance(system, user_input)
        except AppError as exc:
            logger.warning(
                "fallback guidance llm failed code=%s guide=%s",
                exc.code,
                guide.content_hash[:12],
            )
            return GuidanceResult(
                FALLBACK_GUIDANCE_TEXT,
                "fallback",
                guide.content_hash[:12],
                failure_reason=exc.code,
            )

        text = str(result.get("text") or "").strip()
        if not text:
            logger.warning("fallback guidance empty response guide=%s", guide.content_hash[:12])
            return GuidanceResult(
                FALLBACK_GUIDANCE_TEXT,
                "fallback",
                guide.content_hash[:12],
                failure_reason="empty_response",
            )

        usage = result.get("usage")
        return GuidanceResult(
            text,
            str(result.get("source") or "llm"),
            guide.content_hash[:12],
            usage if isinstance(usage, dict) else None,
        )
