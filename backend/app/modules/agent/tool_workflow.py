"""task_create 场景的原生 Tool Calling 流程。

职责：构建受限工具集和上下文 → 调用 LLM → 执行 Tool → 生成预览草稿。
文本理解由 LLM 完成；这里只做确定性的上下文组装和结果转换。
"""

import json
import logging
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.core.exceptions import AppError
from app.modules.agent.executor import ToolExecutor
from app.modules.agent.llm import LLMAdapter
from app.modules.agent.prompt_registry import PromptRegistry
from app.modules.agent.service import AgentBusinessService, AgentState
from app.modules.agent.tools import ToolContext, ToolRegistry, ToolResult

logger = logging.getLogger("app.agent.tools")

PREVIEW_READY_TEXT = "已整理任务配置，请检查后确认。确认前不会写入任何任务数据。"
NO_LIBRARY_TEXT = "当前没有可用词库，请先创建词库或复制已发布的公共词库。"


def _merge_usage(
    current: dict[str, int] | None, extra: dict[str, int] | None
) -> dict[str, int] | None:
    if not extra:
        return current
    if not current:
        return {key: int(value) for key, value in extra.items()}
    merged = {key: int(value) for key, value in current.items()}
    for key, value in extra.items():
        merged[key] = merged.get(key, 0) + int(value)
    return merged


class TaskCreateToolWorkflow:
    workflow = "task_create"

    def __init__(
        self,
        llm: LLMAdapter,
        business: AgentBusinessService,
        registry: ToolRegistry,
        executor: ToolExecutor,
        prompt_dir: str | Path,
    ) -> None:
        self.llm = llm
        self.business = business
        self.registry = registry
        self.executor = executor
        self.prompt = PromptRegistry(Path(prompt_dir)).get("task_create_tools")

    def run(self, state: AgentState) -> dict[str, Any]:
        libraries = self.business.available_libraries(state["user_id"])
        if not libraries:
            return {**state, "response": NO_LIBRARY_TEXT, "route": "task_create"}

        system = self.prompt.render({"libraries": self._library_lines(libraries)})
        tools = self.registry.to_openai_tools(state.get("role", "user"), self.workflow)
        try:
            response = self.llm.chat_with_tools(
                [
                    {"role": "system", "content": system},
                    {"role": "user", "content": state["text"]},
                ],
                tools,
            )
        except AppError as exc:
            logger.warning(
                "task create tool llm failed code=%s run_id=%s", exc.code, state.get("run_id")
            )
            return {
                **state,
                "route": "task_create",
                "response": "我暂时无法整理任务配置，请稍后再试。",
            }

        usage = _merge_usage(state.get("token_usage"), response.get("usage"))
        calls = response.get("tool_calls") or []
        if not calls:
            logger.info(
                "task create tool llm returned text run_id=%s", state.get("run_id")
            )
            return {
                **state,
                "route": "task_create",
                "response": response.get("text") or "请补充词库和词条范围后再试。",
                "token_usage": usage,
            }

        if len(calls) > 1:
            logger.info(
                "task create tool multiple calls count=%s run_id=%s",
                len(calls),
                state.get("run_id"),
            )
        call = calls[0]
        tool = self.registry.get(str(call.get("name") or ""))
        context = ToolContext(
            user_id=state["user_id"],
            role=state.get("role", "user"),
            run_id=state["run_id"],
            workflow=self.workflow,
        )
        started_at = datetime.now(UTC)
        started = time.monotonic()
        outcome = self.executor.execute(
            str(call.get("name") or ""), call.get("arguments"), context=context
        )
        duration_ms = int((time.monotonic() - started) * 1000)
        trace = self._trace(call, tool, outcome, started_at, duration_ms)
        logger.info(
            "task create tool executed tool=%s ok=%s code=%s duration_ms=%s run_id=%s",
            trace["name"],
            outcome.ok,
            outcome.error_code,
            duration_ms,
            state.get("run_id"),
        )

        if not outcome.ok:
            logger.info(
                "task create tool failed code=%s tool=%s run_id=%s",
                outcome.error_code,
                call.get("name"),
                state.get("run_id"),
            )
            return {
                **state,
                "route": "task_create",
                "response": self._error_text(outcome),
                "tool_trace": [trace],
                "token_usage": usage,
            }

        action = outcome.value
        return {
            **state,
            "route": "task_create",
            "response": PREVIEW_READY_TEXT,
            "pending_action": action,
            "draft_version": action.get("draft_version", 1),
            "config_hash": action.get("config_hash"),
            "tool_trace": [trace],
            "token_usage": usage,
        }

    @staticmethod
    def _library_lines(libraries: list[Any]) -> str:
        lines = []
        for library in libraries:
            subject = "英语" if library.subject == "english" else "语文"
            lines.append(
                f"- id={library.id} | 名称={library.name} | 学科={subject} | "
                f"词条数={len(library.entries)}"
            )
        return "\n".join(lines)

    @staticmethod
    def _trace(
        call: dict[str, Any],
        tool: Any,
        outcome: ToolResult,
        started_at: datetime,
        duration_ms: int,
    ) -> dict[str, Any]:
        if outcome.ok and isinstance(outcome.value, dict):
            summary: Any = {
                "operation": outcome.value.get("operation"),
                "target": outcome.value.get("target"),
            }
        elif outcome.ok:
            summary = outcome.value
        else:
            summary = {"service_code": (outcome.value or {}).get("service_code")}
        return {
            "id": call.get("id") or f"call-{started_at.timestamp():.0f}",
            "name": tool.name if tool else str(call.get("name") or ""),
            "label": tool.label if tool else str(call.get("name") or ""),
            "arguments": call.get("arguments") or {},
            "ok": outcome.ok,
            "result": json.dumps(summary, ensure_ascii=False)[:2000],
            "error_code": outcome.error_code,
            "error_message": outcome.error_message,
            "duration_ms": duration_ms,
            "started_at": started_at.isoformat(),
        }

    @staticmethod
    def _error_text(outcome: ToolResult) -> str:
        if outcome.error_code == "invalid_arguments":
            return "我还缺少创建任务所需的信息，请补充词库、词条范围和任务名称后再试。"
        if outcome.error_code == "business_error" and outcome.error_message:
            return f"没能生成任务预览：{outcome.error_message}"
        return "暂时没能生成任务预览，请稍后再试。"
