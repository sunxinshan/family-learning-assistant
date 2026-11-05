import json
import logging
import threading
import time
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from typing import Any

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command, interrupt

from app.core.config import Settings
from app.core.database import Database
from app.core.exceptions import AppError
from app.core.models import new_id
from app.modules.agent.executor import ToolExecutor
from app.modules.agent.guidance import FallbackGuidanceService
from app.modules.agent.llm import LLMAdapter
from app.modules.agent.models import AgentRun, AgentRunEvent
from app.modules.agent.prompt_registry import PromptRegistry
from app.modules.agent.repository import AgentRepository
from app.modules.agent.service import (
    AgentBusinessService,
    AgentState,
    _hash_payload,
    _prepare_task_action,
)
from app.modules.agent.tool_workflow import TaskCreateToolWorkflow
from app.modules.agent.tools import ToolRegistry
from app.modules.conversation.repository import ConversationRepository
from app.modules.conversation.service import ConversationService

logger = logging.getLogger("app.agent")


def _now() -> datetime:
    return datetime.now(UTC)


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


def build_agent_graph(
    checkpointer: BaseCheckpointSaver,
    llm: LLMAdapter,
    business: AgentBusinessService,
    guidance: FallbackGuidanceService,
    tool_workflow: TaskCreateToolWorkflow | None = None,
):
    def classify(state: AgentState) -> AgentState:
        intent = llm.classify_intent(state["text"], state.get("history") or [])
        route = str(intent.get("route", "chat"))
        logger.info(
            "agent intent classified route=%s source=%s adapter=%s",
            route,
            intent.get("source"),
            type(llm).__name__,
        )
        if route not in {
            "task_create",
            "task_update",
            "task_delete",
            "vocabulary_create",
            "vocabulary_import",
            "learning",
            "chat",
            "unclear",
        }:
            route = "unclear"
        return {**state, "route": route, "token_usage": intent.get("usage")}

    def task_create_with_tools(state: AgentState) -> AgentState:
        if tool_workflow is None:
            return _prepare_task_action(state, business)
        return tool_workflow.run(state)

    def prepare(state: AgentState) -> AgentState:
        route = state.get("route")
        if route == "task_create":
            return _prepare_task_action(state, business)
        if route == "task_update":
            return business.prepare_task_update(state)
        if route == "task_delete":
            return business.prepare_task_delete(state)
        if route == "vocabulary_create":
            return business.prepare_vocabulary_create(state)
        if route == "vocabulary_import":
            return business.prepare_vocabulary_import(state)
        return {**state, "response": "暂时无法明确识别这个操作，请补充目标。", "route": "chat"}

    def respond(state: AgentState) -> AgentState:
        if state.get("route") == "learning":
            return {**state, "response": business.learning_stats_text(state["user_id"])}
        result = guidance.respond(state["text"])
        logger.info(
            "agent fallback guidance route=%s source=%s guide=%s failure=%s run_id=%s",
            state.get("route"),
            result.source,
            result.guide_version,
            result.failure_reason,
            state.get("run_id"),
        )
        return {
            **state,
            "response": result.text,
            "token_usage": _merge_usage(state.get("token_usage"), result.usage),
        }

    def wait_for_confirmation(state: AgentState) -> AgentState:
        action = state.get("pending_action")
        if not action:
            return state
        resume_value = interrupt(
            {
                "action": action,
                "draft_version": state.get("draft_version", 1),
                "config_hash": state.get("config_hash"),
            }
        )
        if not isinstance(resume_value, dict) or resume_value.get("decision") == "cancel":
            return {
                **state,
                "pending_action": None,
                "links": None,
                "response": "操作已取消，没有写入业务数据。",
            }
        if resume_value.get("action_id") != action.get("id"):
            return {
                **state,
                "pending_action": None,
                "links": None,
                "response": "确认的操作已失效，请重新发起。",
            }
        if resume_value.get("draft_version") != state.get("draft_version"):
            return {
                **state,
                "pending_action": None,
                "links": None,
                "response": "配置版本已变化，请重新确认。",
            }
        if resume_value.get("config_hash") != state.get("config_hash"):
            return {
                **state,
                "pending_action": None,
                "links": None,
                "response": "配置已变化，请重新确认。",
            }
        if action.get("operation") == "delete_task" and action.get("stage") == 1:
            next_action = business.stage_delete_confirmation(action, state["user_id"])
            next_version = int(state.get("draft_version", 1)) + 1
            return {
                **state,
                "pending_action": next_action,
                "draft_version": next_version,
                "config_hash": next_action["config_hash"],
                "links": None,
                "response": "第一次确认已记录，请再次确认永久删除。",
            }
        result = business.execute(action, state["user_id"], role=state.get("role", "user"))
        return {
            **state,
            "pending_action": None,
            "response": result.message,
            "links": result.links,
        }

    def route_after_classify(state: AgentState) -> str:
        if state.get("route") == "task_create" and tool_workflow is not None:
            return "tool_create"
        if state.get("route") in {
            "task_create",
            "task_update",
            "task_delete",
            "vocabulary_create",
            "vocabulary_import",
        }:
            return "prepare"
        if state.get("route") in {"learning", "chat", "unclear"}:
            return "respond"
        return "respond"

    def after_prepare(state: AgentState) -> str:
        return "wait" if state.get("pending_action") else END

    def after_confirm(state: AgentState) -> str:
        return "wait" if state.get("pending_action") else END

    graph = StateGraph(AgentState)
    graph.add_node("classify", classify)
    graph.add_node("tool_create", task_create_with_tools)
    graph.add_node("prepare", prepare)
    graph.add_node("respond", respond)
    graph.add_node("wait", wait_for_confirmation)
    graph.add_edge(START, "classify")
    graph.add_conditional_edges(
        "classify",
        route_after_classify,
        {"prepare": "prepare", "tool_create": "tool_create", "respond": "respond"},
    )
    graph.add_conditional_edges("prepare", after_prepare, {"wait": "wait", END: END})
    graph.add_conditional_edges("tool_create", after_prepare, {"wait": "wait", END: END})
    graph.add_conditional_edges("wait", after_confirm, {"wait": "wait", END: END})
    graph.add_edge("respond", END)
    return graph.compile(checkpointer=checkpointer)


class AgentRuntime:
    def __init__(
        self,
        database: Database,
        checkpointer: BaseCheckpointSaver,
        settings: Settings,
        llm: LLMAdapter,
    ) -> None:
        self.database = database
        self.checkpointer = checkpointer
        self.settings = settings
        self.llm = llm
        self.prompt = PromptRegistry(settings.prompt_dir).get("main_agent")
        self.business = AgentBusinessService(database)
        self.guidance = FallbackGuidanceService(llm, settings.prompt_dir)
        self.tool_registry = ToolRegistry(self.business)
        self.tool_executor = ToolExecutor(self.tool_registry)
        logger.info("agent tool calling enabled=%s", settings.agent_tool_calling_enabled)
        self.tool_workflow = (
            TaskCreateToolWorkflow(
                llm,
                self.business,
                self.tool_registry,
                self.tool_executor,
                settings.prompt_dir,
            )
            if settings.agent_tool_calling_enabled
            else None
        )
        self.graph = build_agent_graph(
            checkpointer, llm, self.business, self.guidance, self.tool_workflow
        )
        self._execution_lock = threading.Lock()

    def _config(self, conversation_id: str) -> dict[str, Any]:
        return {"configurable": {"thread_id": conversation_id}}

    def _sse(self, event: dict[str, Any]) -> str:
        payload = json.dumps(event, ensure_ascii=False)
        lines = [
            f"id: {event['sequence']}",
            f"event: {event['type']}",
            f"data: {payload}",
        ]
        return "\n".join(lines) + "\n\n"

    def _append_event(
        self,
        repository: AgentRepository,
        run: AgentRun,
        event_type: str,
        data: dict[str, Any],
    ) -> dict[str, Any]:
        sequence = repository.next_sequence(run.id)
        now = _now()
        payload = {
            "event_id": new_id(),
            "conversation_id": run.conversation_id,
            "run_id": run.id,
            "sequence": sequence,
            "type": event_type,
            "timestamp": now.isoformat(),
            "data": data,
        }
        repository.add_event(
            AgentRunEvent(
                id=payload["event_id"],
                run_id=run.id,
                conversation_id=run.conversation_id,
                sequence=sequence,
                event_type=event_type,
                payload_json=payload,
                created_at=now,
            )
        )
        return payload

    def _conversation_service(self, session) -> ConversationService:
        return ConversationService(ConversationRepository(session))

    def _store_message(
        self,
        conversation_service,
        conversation,
        content: dict[str, Any],
        run_id: str,
        *,
        message_type: str | None = None,
        tool_call_id: str | None = None,
    ) -> None:
        conversation_service.append_message(
            conversation,
            message_type=message_type or str(content.get("role", "assistant")),
            content=content,
            run_id=run_id,
            tool_call_id=tool_call_id,
        )

    def _persist_tool_trace(
        self,
        repository: AgentRepository,
        run: AgentRun,
        conversation_service,
        conversation,
        trace: dict[str, Any],
    ) -> None:
        execution = {
            "id": trace["id"],
            "tool": trace["name"],
            "label": trace["label"],
            "status": "success" if trace.get("ok") else "error",
            "args": trace.get("arguments") or {},
            "result": trace.get("result"),
            "durationMs": trace.get("duration_ms") or 0,
            "startedAt": trace.get("started_at"),
        }
        if not trace.get("ok"):
            execution["error"] = trace.get("error_message") or trace.get("error_code")
        self._store_message(
            conversation_service,
            conversation,
            {
                "id": new_id(),
                "role": "tool",
                "kind": "tool_call",
                "content": trace["label"],
                "toolCallId": trace["id"],
                "tool": trace["name"],
                "args": trace.get("arguments") or {},
                "createdAt": trace.get("started_at"),
            },
            run.id,
            message_type="tool_call",
            tool_call_id=trace["id"],
        )
        self._store_message(
            conversation_service,
            conversation,
            {
                "id": new_id(),
                "role": "tool",
                "kind": "execution",
                "content": trace["label"],
                "toolCallId": trace["id"],
                "createdAt": _now().isoformat(),
                "execution": execution,
            },
            run.id,
            message_type="tool_result",
            tool_call_id=trace["id"],
        )
        self._append_event(repository, run, "tool_status", execution)

    @staticmethod
    def _recent_history(conversation: Any, run_id: str) -> list[dict[str, str]]:
        """取最近 6 条自然语言消息，排除当前 run 的用户输入和工具消息。"""
        history: list[dict[str, str]] = []
        for message in conversation.messages:
            content = message.content_json or {}
            if message.run_id == run_id:
                continue
            if content.get("kind") != "text":
                continue
            role = content.get("role")
            if role not in {"user", "assistant"}:
                continue
            text = str(content.get("content") or "").strip()
            if not text:
                continue
            history.append({"role": role, "content": text[:500]})
        return history[-6:]

    def _record_failure(
        self,
        run_id: str,
        exc: Exception,
        *,
        preserve_pending: bool,
    ) -> None:
        with self.database.session() as session:
            repository = AgentRepository(session)
            run = repository.get_run(run_id)
            if not run:
                return
            code = exc.code if isinstance(exc, AppError) else "agent_execution_failed"
            message = exc.message if isinstance(exc, AppError) else "执行失败，请稍后重试"
            run.status = (
                "waiting_confirmation" if preserve_pending and run.pending_action_json else "failed"
            )
            run.error_message = message
            run.lease_until = None
            run.updated_at = _now()
            self._append_event(repository, run, "error", {"code": code, "message": message})
            self._append_event(
                repository, run, "done", {"executionId": run.id, "status": run.status}
            )

    def _execute_new_run(
        self,
        run_id: str,
        conversation_id: str,
        user_id: str,
        role: str,
        text: str,
        material_id: str | None,
    ) -> None:
        try:
            with self._execution_lock:
                with self.database.session() as session:
                    repository = AgentRepository(session)
                    run = repository.get_run(run_id)
                    if not run:
                        return
                    conversations = self._conversation_service(session)
                    conversation = conversations.get_owned(conversation_id, user_id)
                    history = self._recent_history(conversation, run_id)
                    self.graph.invoke(
                        {
                            "user_id": user_id,
                            "role": role,
                            "conversation_id": conversation_id,
                            "run_id": run_id,
                            "text": text,
                            "material_id": material_id,
                            "pending_action": None,
                            "draft_version": 0,
                            "tool_trace": None,
                            "links": None,
                            "history": history,
                        },
                        self._config(conversation_id),
                    )
                    values = self.graph.get_state(self._config(conversation_id)).values
                    pending_action = values.get("pending_action")
                    response = values.get("response", "")
                    for trace in values.get("tool_trace") or []:
                        self._persist_tool_trace(
                            repository, run, conversations, conversation, trace
                        )
                    self._store_message(
                        conversations,
                        conversation,
                        {
                            "id": new_id(),
                            "role": "assistant",
                            "kind": "text",
                            "content": response,
                            "links": values.get("links"),
                            "createdAt": _now().isoformat(),
                        },
                        run.id,
                    )
                    self._append_event(
                        repository,
                        run,
                        "message",
                        {"content": response, "links": values.get("links")},
                    )
                    if pending_action:
                        draft_version = int(values.get("draft_version", 1))
                        config_hash = values.get("config_hash")
                        pending_action = {
                            **pending_action,
                            "draft_version": draft_version,
                            "draftVersion": draft_version,
                            "config_hash": config_hash,
                            "configHash": config_hash,
                        }
                        run.status = "waiting_confirmation"
                        run.pending_action_json = pending_action
                        run.draft_version = draft_version
                        run.config_hash = config_hash
                        self._append_event(repository, run, "confirmation_required", pending_action)
                    else:
                        run.status = "completed"
                    run.lease_until = _now() + timedelta(minutes=2)
                    run.token_usage_json = values.get("token_usage")
                    run.error_message = None
                    run.updated_at = _now()
                    self._append_event(repository, run, "done", {"executionId": run.id})
        except Exception as exc:
            logger.exception("agent run worker failed run_id=%s", run_id)
            try:
                self._record_failure(run_id, exc, preserve_pending=False)
            except Exception:
                logger.exception("agent run failure persistence failed run_id=%s", run_id)

    def start_run(
        self,
        user_id: str,
        role: str,
        text: str,
        material_id: str | None = None,
    ) -> str:
        with self.database.session() as session:
            repository = AgentRepository(session)
            conversations = self._conversation_service(session)
            conversation = conversations.get_or_create(user_id)
            active = repository.get_active_for_conversation(conversation.id)
            if active and active.lease_until and active.lease_until > _now():
                raise AppError(
                    "conversation_busy", "当前会话还有未完成操作，请先确认或取消", status_code=409
                )
            if active:
                active.status = "failed"
                active.error_message = "执行租约过期"
                active.lease_until = None
                active.updated_at = _now()
                self._append_event(
                    repository,
                    active,
                    "error",
                    {"code": "lease_expired", "message": "执行租约过期，请重新发起"},
                )
            now = _now()
            run = repository.add_run(
                AgentRun(
                    id=new_id(),
                    conversation_id=conversation.id,
                    user_id=user_id,
                    status="running",
                    thread_id=conversation.id,
                    lease_until=now + timedelta(minutes=2),
                    draft_version=0,
                    prompt_version=f"{self.prompt.version}:{self.prompt.content_hash[:12]}",
                    created_at=now,
                    updated_at=now,
                )
            )
            self._store_message(
                conversations,
                conversation,
                {
                    "id": new_id(),
                    "role": "user",
                    "kind": "text",
                    "content": text,
                    "createdAt": now.isoformat(),
                },
                run.id,
            )
            self._append_event(
                repository,
                run,
                "progress",
                {"stage": "thinking", "message": "正在理解你的需求"},
            )
            run_id = run.id
            conversation_id = conversation.id
        thread = threading.Thread(
            target=self._execute_new_run,
            args=(run_id, conversation_id, user_id, role, text, material_id),
            name=f"agent-run-{run_id}",
            daemon=True,
        )
        thread.start()
        return run_id

    def stream_run(self, run_id: str, user_id: str, after_sequence: int = 0) -> Iterator[str]:
        cursor = after_sequence
        deadline = time.monotonic() + 300
        terminal = {"completed", "failed", "cancelled"}
        while time.monotonic() < deadline:
            with self.database.session() as session:
                repository = AgentRepository(session)
                run = repository.get_run(run_id)
                if not run or run.user_id != user_id:
                    raise AppError("run_not_found", "执行记录不存在", status_code=404)
                events = repository.list_events(run_id, cursor)
                status = run.status
            reached_done = False
            for event in events:
                cursor = event.sequence
                reached_done = reached_done or event.event_type == "done"
                yield self._sse(event.payload_json)
            if reached_done or (status in terminal and not events):
                return
            time.sleep(0.1)

    def validate_confirm(
        self, run_id: str, user_id: str, action_id: str, draft_version: int, config_hash: str
    ) -> None:
        with self.database.session() as session:
            repository = AgentRepository(session)
            run = repository.get_run(run_id)
            if not run or run.user_id != user_id:
                raise AppError("run_not_found", "执行记录不存在", status_code=404)
            if run.status != "waiting_confirmation" or not run.pending_action_json:
                raise AppError("run_not_waiting", "当前操作不在等待确认状态", status_code=409)
            if (
                action_id != run.id
                or draft_version != run.draft_version
                or config_hash != run.config_hash
            ):
                raise AppError(
                    "action_version_conflict", "确认配置已过期，请刷新预览", status_code=409
                )

    def validate_run_access(self, run_id: str, user_id: str) -> None:
        with self.database.session() as session:
            run = AgentRepository(session).get_run(run_id)
            if not run or run.user_id != user_id:
                raise AppError("run_not_found", "执行记录不存在", status_code=404)

    def _execute_confirm(
        self,
        run_id: str,
        user_id: str,
        action_id: str,
        draft_version: int,
        config_hash: str,
    ) -> None:
        try:
            with self._execution_lock:
                with self.database.session() as session:
                    repository = AgentRepository(session)
                    run = repository.get_run(run_id)
                    if not run:
                        return
                    self.graph.invoke(
                        Command(
                            resume={
                                "decision": "confirm",
                                "action_id": action_id,
                                "draft_version": draft_version,
                                "config_hash": config_hash,
                            }
                        ),
                        self._config(run.thread_id),
                    )
                    values = self.graph.get_state(self._config(run.thread_id)).values
                    pending_action = values.get("pending_action")
                    response = values.get("response", "")
                    conversations = self._conversation_service(session)
                    conversation = conversations.get_or_create(user_id)
                    self._store_message(
                        conversations,
                        conversation,
                        {
                            "id": new_id(),
                            "role": "assistant",
                            "kind": "text",
                            "content": response,
                            "links": values.get("links"),
                            "createdAt": _now().isoformat(),
                        },
                        run.id,
                    )
                    self._append_event(
                        repository,
                        run,
                        "message",
                        {"content": response, "links": values.get("links")},
                    )
                    if pending_action:
                        next_version = int(values.get("draft_version", run.draft_version))
                        next_hash = values.get("config_hash")
                        pending_action = {
                            **pending_action,
                            "draft_version": next_version,
                            "draftVersion": next_version,
                            "config_hash": next_hash,
                            "configHash": next_hash,
                        }
                        run.status = "waiting_confirmation"
                        run.pending_action_json = pending_action
                        run.draft_version = next_version
                        run.config_hash = next_hash
                        self._append_event(repository, run, "confirmation_required", pending_action)
                    else:
                        run.status = "completed"
                        run.pending_action_json = None
                        run.token_usage_json = values.get("token_usage")
                    run.error_message = None
                    run.updated_at = _now()
                    self._append_event(repository, run, "done", {"executionId": run.id})
        except Exception as exc:
            logger.exception("agent confirm worker failed run_id=%s", run_id)
            try:
                self._record_failure(run_id, exc, preserve_pending=True)
            except Exception:
                logger.exception("agent confirm failure persistence failed run_id=%s", run_id)

    def start_confirm(
        self, run_id: str, user_id: str, action_id: str, draft_version: int, config_hash: str
    ) -> tuple[str, int]:
        self.validate_confirm(run_id, user_id, action_id, draft_version, config_hash)
        with self.database.session() as session:
            repository = AgentRepository(session)
            run = repository.get_run(run_id)
            if not run:
                raise AppError("run_not_found", "执行记录不存在", status_code=404)
            run.status = "running"
            run.lease_until = _now() + timedelta(minutes=2)
            run.updated_at = _now()
            after_sequence = repository.next_sequence(run.id) - 1
            self._append_event(
                repository,
                run,
                "progress",
                {"stage": "executing", "message": "正在执行已确认操作"},
            )
        thread = threading.Thread(
            target=self._execute_confirm,
            args=(run_id, user_id, action_id, draft_version, config_hash),
            name=f"agent-confirm-{run_id}",
            daemon=True,
        )
        thread.start()
        return run_id, after_sequence

    def update_action(
        self, run_id: str, user_id: str, role: str, action: dict[str, Any]
    ) -> dict[str, Any]:
        with self.database.session() as session:
            repository = AgentRepository(session)
            run = repository.get_run(run_id)
            if not run or run.user_id != user_id:
                raise AppError("run_not_found", "执行记录不存在", status_code=404)
            if run.status != "waiting_confirmation" or not run.pending_action_json:
                raise AppError("run_not_waiting", "当前操作不在等待确认状态", status_code=409)
            if action.get("id") != run.id:
                raise AppError("action_mismatch", "操作标识不匹配", status_code=409)
            self.business.validate_action(action, user_id, role)
            current_version = run.draft_version
            new_version = current_version + 1
            action["draft_version"] = new_version
            action["draftVersion"] = new_version
            config_hash = _hash_payload(action.get("payload", {}))
            action["config_hash"] = config_hash
            action["configHash"] = config_hash
            self.graph.update_state(
                self._config(run.thread_id),
                {
                    "pending_action": action,
                    "draft_version": new_version,
                    "config_hash": config_hash,
                },
            )
            run.pending_action_json = action
            run.draft_version = new_version
            run.config_hash = config_hash
            run.updated_at = _now()
            session.commit()
            return action

    def cancel(self, run_id: str, user_id: str) -> None:
        with self.database.session() as session:
            repository = AgentRepository(session)
            run = repository.get_run(run_id)
            if not run or run.user_id != user_id:
                raise AppError("run_not_found", "执行记录不存在", status_code=404)
            run.status = "cancelled"
            run.pending_action_json = None
            run.updated_at = _now()
            session.commit()

    def event_stream(self, run_id: str, user_id: str, after_sequence: int) -> Iterator[str]:
        yield from self.stream_run(run_id, user_id, after_sequence)
