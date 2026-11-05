from collections.abc import Callable, Iterable
from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel

from app.modules.agent.service import AgentBusinessService
from app.modules.agent.tool_schemas import EmptyArgs, TaskCreatePreviewArgs


@dataclass(frozen=True)
class ToolContext:
    """由后端运行上下文注入的可信身份，不允许 LLM 提供或覆盖。"""

    user_id: str
    role: str
    run_id: str
    workflow: str


@dataclass(frozen=True)
class ToolDefinition:
    name: str
    label: str
    description: str
    args_schema: type[BaseModel]
    required_role: str
    workflows: frozenset[str]
    handler: Callable[[ToolContext, Any], Any]

    @property
    def llm_name(self) -> str:
        """Provider function name 只允许 [a-zA-Z0-9_-]，内部点号名映射为下划线。"""
        return self.name.replace(".", "_")


@dataclass(frozen=True)
class ToolResult:
    ok: bool
    value: Any = None
    error_code: str | None = None
    error_message: str | None = None


class ToolRegistry:
    """按角色和 Workflow 筛选工具，并转换为 LLM 原生工具定义。"""

    def __init__(
        self,
        business: AgentBusinessService,
        definitions: Iterable[ToolDefinition] | None = None,
    ) -> None:
        tools = list(definitions) if definitions is not None else self._default_tools(business)
        self._tools: dict[str, ToolDefinition] = {tool.name: tool for tool in tools}
        llm_names = [tool.llm_name for tool in tools]
        if len(set(llm_names)) != len(llm_names):
            raise ValueError("工具名称转换为 Provider 名称后重复")

    @staticmethod
    def _default_tools(business: AgentBusinessService) -> list[ToolDefinition]:
        return [
            ToolDefinition(
                name="learning.stats",
                label="读取学习统计",
                description=(
                    "读取当前用户的学习统计，包括练习次数、平均正确率、"
                    "已掌握词数和待复习词数。只读，不修改任何数据。"
                ),
                args_schema=EmptyArgs,
                required_role="user",
                workflows=frozenset({"learning"}),
                handler=lambda context, _args: business.learning_stats_text(context.user_id),
            ),
            ToolDefinition(
                name="task.create_preview",
                label="创建任务预览",
                description=(
                    "根据用户的学习需求生成听写任务创建预览，不会真正创建任务。"
                    "当用户希望新建一个听写学习任务时使用。"
                    "需要提供任务名称、词库和词条选择方式，其他参数可省略。"
                ),
                args_schema=TaskCreatePreviewArgs,
                required_role="user",
                workflows=frozenset({"task_create"}),
                handler=lambda context, args: business.build_task_create_preview(
                    context.user_id, context.role, context.run_id, args
                ),
            ),
        ]

    def get(self, name: str) -> ToolDefinition | None:
        tool = self._tools.get(name)
        if tool is not None:
            return tool
        # 同时接受 Provider 侧的下划线名称（task_create_preview）。
        return next((item for item in self._tools.values() if item.llm_name == name), None)

    def for_workflow(self, role: str, workflow: str) -> list[ToolDefinition]:
        return [
            tool
            for tool in self._tools.values()
            if workflow in tool.workflows
            and (tool.required_role == "user" or role == "admin")
        ]

    def to_openai_tools(self, role: str, workflow: str) -> list[dict[str, Any]]:
        return [
            {
                "type": "function",
                "function": {
                    "name": tool.llm_name,
                    "description": tool.description,
                    "parameters": tool.args_schema.model_json_schema(),
                },
            }
            for tool in self.for_workflow(role, workflow)
        ]

    def available(self, role: str = "user") -> list[dict[str, str]]:
        return [
            {"name": tool.name, "label": tool.label}
            for tool in self._tools.values()
            if tool.required_role == "user" or role == "admin"
        ]
