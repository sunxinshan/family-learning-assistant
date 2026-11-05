from fastapi import APIRouter, Depends, Request, Response, status
from fastapi.responses import StreamingResponse

from app.core.exceptions import AppError
from app.core.security import RuntimeContext, get_runtime_context
from app.modules.agent.redaction import redact
from app.modules.agent.repository import AgentRepository
from app.modules.agent.runtime import AgentRuntime
from app.modules.agent.schemas import (
    ActionConfirmRequest,
    ActionUpdateRequest,
    AgentRunDetailOut,
    AgentRunOut,
    AgentRunRequest,
)

router = APIRouter(prefix="/agent", tags=["agent"])


def get_runtime(request: Request) -> AgentRuntime:
    return request.app.state.agent_runtime


@router.post("/runs/stream")
def run_agent(
    payload: AgentRunRequest,
    context: RuntimeContext = Depends(get_runtime_context),
    runtime: AgentRuntime = Depends(get_runtime),
) -> StreamingResponse:
    run_id = runtime.start_run(context.user_id, context.role, payload.message, payload.material_id)
    return StreamingResponse(
        runtime.stream_run(run_id, context.user_id),
        media_type="text/event-stream",
    )


@router.get("/runs/active", response_model=AgentRunOut | None)
def get_active_run(
    request: Request,
    context: RuntimeContext = Depends(get_runtime_context),
) -> AgentRunOut | None:
    with request.app.state.database.session() as session:
        run = AgentRepository(session).get_active_for_user(context.user_id)
        if not run:
            return None
        return AgentRunOut.model_validate(
            {
                "id": run.id,
                "conversation_id": run.conversation_id,
                "status": run.status,
                "pending_action": run.pending_action_json,
                "draft_version": run.draft_version,
                "config_hash": run.config_hash,
            }
        )


@router.get("/runs/{run_id}")
def get_run(
    run_id: str,
    request: Request,
    context: RuntimeContext = Depends(get_runtime_context),
) -> AgentRunOut:
    with request.app.state.database.session() as session:
        run = AgentRepository(session).get_run(run_id)
        if not run or run.user_id != context.user_id:
            raise AppError("run_not_found", "执行记录不存在", status_code=404)
        return AgentRunOut.model_validate(
            {
                "id": run.id,
                "conversation_id": run.conversation_id,
                "status": run.status,
                "pending_action": run.pending_action_json,
                "draft_version": run.draft_version,
                "config_hash": run.config_hash,
            }
        )


@router.get("/runs/{run_id}/details", response_model=AgentRunDetailOut)
def get_run_details(
    run_id: str,
    request: Request,
    context: RuntimeContext = Depends(get_runtime_context),
) -> AgentRunDetailOut:
    with request.app.state.database.session() as session:
        repository = AgentRepository(session)
        run = repository.get_run(run_id)
        if not run or (run.user_id != context.user_id and context.role != "admin"):
            raise AppError("run_not_found", "执行记录不存在", status_code=404)
        events = repository.list_events(run.id)
        duration_ms = max(0, int((run.updated_at - run.created_at).total_seconds() * 1000))
        tools = request.app.state.agent_runtime.tool_registry.available(context.role)
        return AgentRunDetailOut.model_validate(
            {
                "id": run.id,
                "conversation_id": run.conversation_id,
                "user_id": run.user_id,
                "status": run.status,
                "pending_action": redact(run.pending_action_json),
                "draft_version": run.draft_version,
                "config_hash": run.config_hash,
                "prompt_version": run.prompt_version,
                "token_usage": redact(run.token_usage_json),
                "error_message": redact(run.error_message),
                "duration_ms": duration_ms,
                "events": [redact(event.payload_json) for event in events],
                "available_tools": tools,
                "created_at": run.created_at,
                "updated_at": run.updated_at,
            }
        )


@router.get("/runs/{run_id}/events")
def replay_events(
    run_id: str,
    after_sequence: int = 0,
    context: RuntimeContext = Depends(get_runtime_context),
    runtime: AgentRuntime = Depends(get_runtime),
) -> StreamingResponse:
    runtime.validate_run_access(run_id, context.user_id)
    return StreamingResponse(
        runtime.event_stream(run_id, context.user_id, after_sequence),
        media_type="text/event-stream",
    )


@router.patch("/actions/{run_id}/draft")
def update_action(
    run_id: str,
    payload: ActionUpdateRequest,
    context: RuntimeContext = Depends(get_runtime_context),
    runtime: AgentRuntime = Depends(get_runtime),
) -> dict:
    return runtime.update_action(run_id, context.user_id, context.role, payload.action)


@router.post("/actions/{run_id}/confirm")
def confirm_action(
    run_id: str,
    payload: ActionConfirmRequest,
    context: RuntimeContext = Depends(get_runtime_context),
    runtime: AgentRuntime = Depends(get_runtime),
) -> StreamingResponse:
    runtime.validate_confirm(
        run_id,
        context.user_id,
        run_id,
        payload.draft_version,
        payload.config_hash,
    )
    _, after_sequence = runtime.start_confirm(
        run_id,
        context.user_id,
        run_id,
        payload.draft_version,
        payload.config_hash,
    )
    return StreamingResponse(
        runtime.stream_run(run_id, context.user_id, after_sequence),
        media_type="text/event-stream",
    )


@router.post("/actions/{run_id}/cancel", status_code=status.HTTP_204_NO_CONTENT)
def cancel_action(
    run_id: str,
    context: RuntimeContext = Depends(get_runtime_context),
    runtime: AgentRuntime = Depends(get_runtime),
) -> Response:
    runtime.cancel(run_id, context.user_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
