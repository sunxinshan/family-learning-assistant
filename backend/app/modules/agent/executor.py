"""Tool Executor：统一做工具查找、权限、参数校验、身份注入和结果规范化。"""

import json
import logging
from typing import Any

from pydantic import ValidationError

from app.core.exceptions import AppError
from app.modules.agent.tools import ToolContext, ToolRegistry, ToolResult

logger = logging.getLogger("app.agent.tools")


class ToolExecutor:
    def __init__(self, registry: ToolRegistry) -> None:
        self.registry = registry

    def execute(
        self,
        name: str,
        arguments: dict[str, Any] | None,
        *,
        context: ToolContext,
    ) -> ToolResult:
        tool = self.registry.get(name)
        if tool is None:
            return ToolResult(False, error_code="tool_not_found", error_message="工具不存在")

        if tool.required_role != "user" and context.role != "admin":
            return ToolResult(False, error_code="forbidden", error_message="无权使用该工具")

        if context.workflow not in tool.workflows:
            logger.warning(
                "tool workflow mismatch tool=%s workflow=%s run_id=%s",
                tool.name,
                context.workflow,
                context.run_id,
            )
            return ToolResult(
                False, error_code="forbidden", error_message="当前流程不允许调用该工具"
            )

        try:
            args = tool.args_schema.model_validate(arguments or {})
        except ValidationError as exc:
            errors = [
                {
                    "field": ".".join(str(part) for part in item["loc"]),
                    "message": item["msg"],
                }
                for item in exc.errors(include_url=False)
            ]
            return ToolResult(
                False,
                error_code="invalid_arguments",
                error_message=json.dumps(errors, ensure_ascii=False),
            )

        try:
            value = tool.handler(context, args)
        except AppError as exc:
            logger.info(
                "tool business error tool=%s code=%s run_id=%s",
                tool.name,
                exc.code,
                context.run_id,
            )
            return ToolResult(
                False,
                value={"service_code": exc.code},
                error_code="business_error",
                error_message=exc.message,
            )
        except Exception:
            logger.exception("tool execution failed tool=%s run_id=%s", tool.name, context.run_id)
            return ToolResult(
                False,
                error_code="tool_execution_error",
                error_message="工具执行失败，请稍后重试",
            )

        return ToolResult(True, value=value)
