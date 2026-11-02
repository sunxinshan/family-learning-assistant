from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from app.core.exceptions import AppError
from app.modules.agent.service import AgentBusinessService


@dataclass(frozen=True)
class ToolDefinition:
    name: str
    label: str
    required_role: str
    handler: Callable[..., Any]


@dataclass(frozen=True)
class ToolResult:
    ok: bool
    value: Any = None
    error_code: str | None = None
    error_message: str | None = None


class ToolRegistry:
    """Permission-filtered tools. Every handler delegates to a module Service."""

    def __init__(self, business: AgentBusinessService) -> None:
        self.business = business
        self._tools = {
            "learning.stats": ToolDefinition(
                "learning.stats",
                "读取学习统计",
                "user",
                lambda user_id, _args: business.learning_stats_text(user_id),
            ),
            "task.create_preview": ToolDefinition(
                "task.create_preview",
                "创建任务确认草稿",
                "user",
                lambda user_id, _args: [item.id for item in business.available_tasks(user_id)],
            ),
            "task.update_preview": ToolDefinition(
                "task.update_preview",
                "创建任务修改确认草稿",
                "user",
                lambda user_id, _args: [item.id for item in business.available_tasks(user_id)],
            ),
            "task.delete_preview": ToolDefinition(
                "task.delete_preview",
                "创建任务删除确认草稿",
                "user",
                lambda user_id, _args: [item.id for item in business.available_tasks(user_id)],
            ),
            "vocabulary.create_preview": ToolDefinition(
                "vocabulary.create_preview",
                "创建词库确认草稿",
                "user",
                lambda user_id, _args: [item.id for item in business.available_libraries(user_id)],
            ),
            "vocabulary.import_preview": ToolDefinition(
                "vocabulary.import_preview",
                "创建词库导入确认草稿",
                "user",
                lambda user_id, _args: [item.id for item in business.available_libraries(user_id)],
            ),
            "admin.execution_detail": ToolDefinition(
                "admin.execution_detail",
                "查看完整执行详情",
                "admin",
                lambda _user_id, _args: {"scope": "admin"},
            ),
        }

    def available(self, role: str = "user") -> list[dict[str, str]]:
        return [
            {"name": tool.name, "label": tool.label}
            for tool in self._tools.values()
            if tool.required_role == "user" or role == "admin"
        ]

    def invoke(
        self,
        name: str,
        user_id: str,
        role: str,
        args: dict[str, Any] | None = None,
    ) -> ToolResult:
        tool = self._tools.get(name)
        if not tool:
            return ToolResult(False, error_code="tool_not_found", error_message="Tool 不存在")
        if tool.required_role == "admin" and role != "admin":
            return ToolResult(False, error_code="forbidden", error_message="无权使用该 Tool")
        try:
            return ToolResult(True, value=tool.handler(user_id, args or {}))
        except AppError as exc:
            return ToolResult(False, error_code=exc.code, error_message=exc.message)
