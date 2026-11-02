import json
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
from app.modules.conversation.repository import ConversationRepository
from app.modules.conversation.service import ConversationService


def _now() -> datetime:
    return datetime.now(UTC)


def build_agent_graph(
    checkpointer: BaseCheckpointSaver, llm: LLMAdapter, business: AgentBusinessService
):
    def classify(state: AgentState) -> AgentState:
        intent = llm.classify_intent(state["text"])
        route = str(intent.get("route", "chat"))
        if route not in {
            "task_create",
            "task_update",
            "task_delete",
            "learning",
            "chat",
            "unclear",
        }:
            route = "unclear"
        return {**state, "route": route}

    def prepare(state: AgentState) -> AgentState:
        if state.get("route") == "task_create":
            return _prepare_task_action(state, business)
        return {
            **state,
            "response": "该工作流将在后续阶段开放。",
            "route": "chat",
        }

    def respond(state: AgentState) -> AgentState:
        if state.get("route") == "learning":
            return {**state, "response": business.learning_stats_text(state["user_id"])}
        return {
            **state,
            "response": (
                "我可以帮你创建和管理学习任务、导入词库或查看学习记录。请直接描述你的目标。"
            ),
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
            return {**state, "pending_action": None, "response": "操作已取消，没有写入业务数据。"}
        if resume_value.get("action_id") != action.get("id"):
            return {**state, "pending_action": None, "response": "确认的操作已失效，请重新发起。"}
        if resume_value.get("draft_version") != state.get("draft_version"):
            return {**state, "pending_action": None, "response": "配置版本已变化，请重新确认。"}
        result = business.execute(action, state["user_id"], role=state.get("role", "user"))
        return {**state, "pending_action": None, "response": result}

    def route_after_classify(state: AgentState) -> str:
        if state.get("route") in {"task_create", "task_update", "task_delete"}:
            return "prepare"
        if state.get("route") in {"learning", "chat", "unclear"}:
            return "respond"
        return "respond"

    def after_prepare(state: AgentState) -> str:
        return "wait" if state.get("pending_action") else "respond"

    def after_confirm(state: AgentState) -> str:
        return "wait" if state.get("pending_action") else END

    graph = StateGraph(AgentState)
    graph.add_node("classify", classify)
    graph.add_node("prepare", prepare)
    graph.add_node("respond", respond)
    graph.add_node("wait", wait_for_confirmation)
    graph.add_edge(START, "classify")
    graph.add_conditional_edges(
        "classify", route_after_classify, {"prepare": "prepare", "respond": "respond"}
    )
    graph.add_conditional_edges("prepare", after_prepare, {"wait": "wait", "respond": "respond"})
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
        self.graph = build_agent_graph(checkpointer, llm, self.business)

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
        self, conversation_service, conversation, content: dict[str, Any], run_id: str
    ) -> None:
        conversation_service.append_message(
            conversation,
            message_type=str(content.get("role", "assistant")),
            content=content,
            run_id=run_id,
        )

    def run(self, user_id: str, role: str, text: str) -> Iterator[str]:
        with self.database.session() as session:
            repository = AgentRepository(session)
            conversations = self._conversation_service(session)
            conversation = conversations.get_or_create(user_id)
            active = repository.get_active_for_conversation(conversation.id)
            if active and active.lease_until and active.lease_until > _now():
                raise AppError(
                    "conversation_busy", "当前会话还有未完成操作，请先确认或取消", status_code=409
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
            user_message = {
                "id": new_id(),
                "role": "user",
                "kind": "text",
                "content": text,
                "createdAt": now.isoformat(),
            }
            self._store_message(conversations, conversation, user_message, run.id)
            start_event = self._append_event(
                repository, run, "progress", {"stage": "thinking", "message": "正在理解你的需求"}
            )
            session.commit()
            yield self._sse(start_event)

            self.graph.invoke(
                {
                    "user_id": user_id,
                    "role": role,
                    "conversation_id": conversation.id,
                    "run_id": run.id,
                    "text": text,
                    "pending_action": None,
                    "draft_version": 0,
                },
                self._config(conversation.id),
            )
            snapshot = self.graph.get_state(self._config(conversation.id))
            values = snapshot.values
            pending_action = values.get("pending_action")
            response = values.get("response", "")
            assistant_message = {
                "id": new_id(),
                "role": "assistant",
                "kind": "text",
                "content": response,
                "createdAt": _now().isoformat(),
            }
            self._store_message(conversations, conversation, assistant_message, run.id)
            msg_event = self._append_event(repository, run, "message", {"content": response})
            yield self._sse(msg_event)
            if pending_action:
                run.status = "waiting_confirmation"
                run.pending_action_json = pending_action
                run.draft_version = int(values.get("draft_version", 1))
                run.config_hash = values.get("config_hash")
                action_event = self._append_event(
                    repository, run, "confirmation_required", pending_action
                )
                yield self._sse(action_event)
            else:
                run.status = "completed"
            run.lease_until = _now() + timedelta(minutes=2)
            run.updated_at = _now()
            done_event = self._append_event(repository, run, "done", {"executionId": run.id})
            session.commit()
            yield self._sse(done_event)

    def confirm(
        self, run_id: str, user_id: str, action_id: str, draft_version: int, config_hash: str
    ) -> Iterator[str]:
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
            run.status = "running"
            run.lease_until = _now() + timedelta(minutes=2)
            progress = self._append_event(
                repository, run, "progress", {"stage": "executing", "message": "正在执行已确认操作"}
            )
            session.commit()
            yield self._sse(progress)
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
            snapshot = self.graph.get_state(self._config(run.thread_id))
            values = snapshot.values
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
                    "createdAt": _now().isoformat(),
                },
                run.id,
            )
            message = self._append_event(repository, run, "message", {"content": response})
            yield self._sse(message)
            if pending_action:
                run.status = "waiting_confirmation"
                run.pending_action_json = pending_action
                run.draft_version = int(values.get("draft_version", run.draft_version))
                run.config_hash = values.get("config_hash")
                confirmation = self._append_event(
                    repository, run, "confirmation_required", pending_action
                )
                yield self._sse(confirmation)
            else:
                run.status = "completed"
                run.pending_action_json = None
            done = self._append_event(repository, run, "done", {"executionId": run.id})
            session.commit()
            yield self._sse(done)

    def update_action(self, run_id: str, user_id: str, action: dict[str, Any]) -> dict[str, Any]:
        with self.database.session() as session:
            repository = AgentRepository(session)
            run = repository.get_run(run_id)
            if not run or run.user_id != user_id:
                raise AppError("run_not_found", "执行记录不存在", status_code=404)
            if run.status != "waiting_confirmation" or not run.pending_action_json:
                raise AppError("run_not_waiting", "当前操作不在等待确认状态", status_code=409)
            if action.get("id") != run.id:
                raise AppError("action_mismatch", "操作标识不匹配", status_code=409)
            current_version = run.draft_version
            new_version = current_version + 1
            action["draft_version"] = new_version
            config_hash = _hash_payload(action.get("payload", {}))
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
        with self.database.session() as session:
            repository = AgentRepository(session)
            run = repository.get_run(run_id)
            if not run or run.user_id != user_id:
                raise AppError("run_not_found", "执行记录不存在", status_code=404)
            for event in repository.list_events(run_id, after_sequence):
                yield self._sse(event.payload_json)
