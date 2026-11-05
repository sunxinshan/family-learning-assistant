from typing import Any

from pydantic import BaseModel, ConfigDict

from app.core.exceptions import AppError
from app.modules.agent.executor import ToolExecutor
from app.modules.agent.tools import ToolContext, ToolDefinition, ToolRegistry


class EchoArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")

    message: str


class ForbiddenArgs(BaseModel):
    pass


def _context(role: str = "user", workflow: str = "demo") -> ToolContext:
    return ToolContext(user_id="user-1", role=role, run_id="run-1", workflow=workflow)


def _registry() -> ToolRegistry:
    def echo(context: ToolContext, args: EchoArgs) -> dict[str, str]:
        return {"message": args.message, "user": context.user_id}

    return ToolRegistry(
        None,  # type: ignore[arg-type]
        definitions=[
            ToolDefinition(
                name="demo.echo",
                label="回显",
                description="回显参数",
                args_schema=EchoArgs,
                required_role="user",
                workflows=frozenset({"demo"}),
                handler=echo,
            ),
            ToolDefinition(
                name="admin.secret",
                label="管理员工具",
                description="仅管理员",
                args_schema=ForbiddenArgs,
                required_role="admin",
                workflows=frozenset({"demo"}),
                handler=lambda _context, _args: {"ok": True},
            ),
            ToolDefinition(
                name="demo.business_error",
                label="业务失败",
                description="业务异常",
                args_schema=ForbiddenArgs,
                required_role="user",
                workflows=frozenset({"demo"}),
                handler=lambda _context, _args: (_ for _ in ()).throw(
                    AppError("no_entries_selected", "请至少选择一个词条", status_code=422)
                ),
            ),
            ToolDefinition(
                name="demo.crash",
                label="未知异常",
                description="未知异常",
                args_schema=ForbiddenArgs,
                required_role="user",
                workflows=frozenset({"demo"}),
                handler=lambda _context, _args: (_ for _ in ()).throw(RuntimeError("boom")),
            ),
        ],
    )


def test_executor_injects_identity_and_returns_value() -> None:
    executor = ToolExecutor(_registry())
    result = executor.execute("demo.echo", {"message": "hello"}, context=_context())
    assert result.ok is True
    assert result.value == {"message": "hello", "user": "user-1"}


def test_executor_accepts_provider_safe_name() -> None:
    executor = ToolExecutor(_registry())
    result = executor.execute("demo_echo", {"message": "hello"}, context=_context())
    assert result.ok is True


def test_executor_rejects_invalid_and_extra_arguments() -> None:
    executor = ToolExecutor(_registry())
    missing = executor.execute("demo.echo", {}, context=_context())
    assert missing.ok is False
    assert missing.error_code == "invalid_arguments"
    assert "message" in (missing.error_message or "")

    extra = executor.execute(
        "demo.echo", {"message": "hi", "user_id": "other"}, context=_context()
    )
    assert extra.ok is False
    assert extra.error_code == "invalid_arguments"


def test_executor_rejects_admin_tool_for_user() -> None:
    result = ToolExecutor(_registry()).execute("admin.secret", {}, context=_context())
    assert result.ok is False
    assert result.error_code == "forbidden"


def test_executor_rejects_wrong_workflow() -> None:
    result = ToolExecutor(_registry()).execute(
        "demo.echo", {"message": "hi"}, context=_context(workflow="other")
    )
    assert result.ok is False
    assert result.error_code == "forbidden"


def test_executor_unknown_tool() -> None:
    result = ToolExecutor(_registry()).execute("missing.tool", {}, context=_context())
    assert result.ok is False
    assert result.error_code == "tool_not_found"


def test_executor_maps_business_and_unexpected_errors() -> None:
    executor = ToolExecutor(_registry())
    business = executor.execute("demo.business_error", {}, context=_context())
    assert business.ok is False
    assert business.error_code == "business_error"
    assert business.value == {"service_code": "no_entries_selected"}

    crash = executor.execute("demo.crash", {}, context=_context())
    assert crash.ok is False
    assert crash.error_code == "tool_execution_error"


def test_registry_tool_names_are_provider_safe() -> None:
    registry = _registry()
    tool = registry.get("demo.echo")
    assert tool is not None
    assert tool.llm_name == "demo_echo"
    schema: dict[str, Any] = registry.to_openai_tools("user", "demo")[0]["function"]
    assert schema["name"] == "demo_echo"
