import concurrent.futures
import json
import logging
import threading
import time
import uuid
from collections.abc import Callable, Iterator
from datetime import UTC, datetime, timedelta
from typing import Any

import pymysql
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command, interrupt

from app.core.config import Settings
from app.core.database import Database
from app.core.exceptions import AppError
from app.core.models import new_id
from app.infrastructure.checkpoint import CheckpointerManager, checkpoint_not_found_error
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

# MySQL checkpointer 复用一条长连接（PyMySQLSaver 内部就是单条 pymysql.Connection）。
# MySQL 的 wait_timeout（生产 28800 秒）会把空闲连接踢掉，但客户端对象留在进程里不会自愈，
# 下一次 checkpoint 读写就抛 InterfaceError(0, '')，最终被兜成「执行失败，请稍后重试」。
# 因此每次图调用前探活，并在真正的连接级异常上重连重试一次。
_CHECKPOINT_RETRY_ERRORS: tuple[type[BaseException], ...] = (
    pymysql.err.InterfaceError,
    pymysql.err.OperationalError,
)

# 调试重放的硬超时：超过就放弃等待并返回 504，避免长时间占住请求线程。
_REPLAY_TIMEOUT_SECONDS = 60

# 超时后给孤儿线程的收尾宽限：还在跑就把连接的所有权移交给它，请求线程不再 close。
_REPLAY_DRAIN_SECONDS = 2.0

# 重放会真跑图节点，凡「节点自己写业务表」的路由都不能重放。
# 目前只有 vocabulary_import：prepare 会调 ContentService.extract()，插入
# content_extractions 并把 material.status 改成 parsed（REVIEW C-1 / T-FIX-02）。
_UNSAFE_REPLAY_ROUTES = frozenset({"vocabulary_import"})

# 已被放弃、但线程仍在跑的重放：thread_id → 放弃时刻。只用于日志与 v2 的 TTL 清理，
# 不是锁也不是状态机；线程结束后自行移除。
_ABANDONED_REPLAY_THREADS: dict[str, float] = {}
_ABANDONED_REPLAY_LOCK = threading.Lock()


def _revive_checkpoint_connection(
    checkpointer: BaseCheckpointSaver, broken: BaseException | None = None
) -> bool:
    """对底层连接做一次 ping(reconnect=True)；不支持的 saver（如 SQLite）直接跳过。"""
    connection = getattr(checkpointer, "conn", None)
    ping = getattr(connection, "ping", None)
    if ping is None:
        return False
    try:
        ping(reconnect=True)
    except Exception:
        logger.warning("checkpoint 连接重连失败", exc_info=True)
        return False
    if broken is not None:
        logger.warning("checkpoint 连接已断开，已重连后重试：%s", broken)
    return True


def _with_checkpoint_retry[T](
    checkpointer: BaseCheckpointSaver,
    operation: Callable[..., T],
    /,
    *args: Any,
    **kwargs: Any,
) -> T:
    """先探活再调用；遇到连接级异常时重连并重试一次。

    重试以 LangGraph 的 checkpoint 为界，从最近一次成功的 checkpoint 继续，
    与用户手动重试的语义一致。非连接类异常原样抛出。
    """
    _revive_checkpoint_connection(checkpointer)
    try:
        return operation(*args, **kwargs)
    except _CHECKPOINT_RETRY_ERRORS as exc:
        if not _revive_checkpoint_connection(checkpointer, broken=exc):
            raise
        return operation(*args, **kwargs)


class _ReplayAbandoned(RuntimeError):
    """重放已被放弃：worker 线程不该再重连、也不该再写。"""


def _invoke_replay_graph[T](
    graph: Any,
    checkpointer: BaseCheckpointSaver,
    replay_thread: str,
    abandoned: threading.Event,
) -> T:
    """在 worker 线程里跑图；超时后被放弃时**不再** ping(reconnect=True)。

    超时返回 504 后，请求线程会（或即将）关掉这条连接。若 worker 下一次
    checkpoint 写抛 ``InterfaceError`` 就调 ``ping(reconnect=True)``，pymysql 会真的
    重连出一条**无人关闭**的连接，每次超时泄漏一条（REVIEW M-1）。
    这里用取消标志把「重连」这条路堵掉，让孤儿线程安静地失败退出。
    """
    config = {"configurable": {"thread_id": replay_thread}}

    def _run() -> T:
        if abandoned.is_set():
            raise _ReplayAbandoned()
        return graph.invoke(None, config)

    _revive_checkpoint_connection(checkpointer)
    try:
        return _run()
    except _CHECKPOINT_RETRY_ERRORS as exc:
        if abandoned.is_set():
            raise _ReplayAbandoned() from exc
        if not _revive_checkpoint_connection(checkpointer, broken=exc):
            raise
        return _run()


def _drain_replay_future(future: concurrent.futures.Future) -> bool:
    """超时后再等一小会儿，看孤儿线程能不能自己收尾。

    返回 True 表示线程已结束（正常或异常），此刻关连接是安全的；
    False 表示它还在跑，连接不能由请求线程关。
    """
    try:
        future.result(timeout=_REPLAY_DRAIN_SECONDS)
    except TimeoutError:
        return False
    except BaseException:  # noqa: BLE001 - 线程以异常结束，同样算「已退出」
        return True
    return True


def _hand_over_checkpointer(
    future: concurrent.futures.Future,
    replay_thread: str,
    manager: CheckpointerManager,
) -> None:
    """把连接交给孤儿线程：它结束后自己关，异常与结局都进日志。

    这样既不会「请求线程关掉还在用的连接 → worker 重连复活」，
    也不会「谁都不关 → 连接永久泄漏」。
    """
    with _ABANDONED_REPLAY_LOCK:
        _ABANDONED_REPLAY_THREADS[replay_thread] = time.time()
    logger.warning(
        "重放超时且未在 %.1fs 内收尾，连接移交给孤儿线程：replay_thread=%s",
        _REPLAY_DRAIN_SECONDS,
        replay_thread,
    )

    def _finalize(completed: concurrent.futures.Future) -> None:
        with _ABANDONED_REPLAY_LOCK:
            _ABANDONED_REPLAY_THREADS.pop(replay_thread, None)
        error = completed.exception()
        if error is None:
            logger.warning("重放孤儿线程已结束：replay_thread=%s", replay_thread)
        else:
            logger.error(
                "重放孤儿线程异常结束：replay_thread=%s error=%r",
                replay_thread,
                error,
                exc_info=error,
            )
        try:
            manager.close()
        except Exception:  # noqa: BLE001 - 收尾阶段不再抛给任何人
            logger.warning("重放孤儿线程关闭 checkpoint 连接失败", exc_info=True)

    future.add_done_callback(_finalize)


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
                    _with_checkpoint_retry(
                        self.checkpointer,
                        self.graph.invoke,
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
                    values = _with_checkpoint_retry(
                        self.checkpointer,
                        self.graph.get_state,
                        self._config(conversation_id),
                    ).values
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
                    _with_checkpoint_retry(
                        self.checkpointer,
                        self.graph.invoke,
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
                    values = _with_checkpoint_retry(
                        self.checkpointer,
                        self.graph.get_state,
                        self._config(run.thread_id),
                    ).values
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
            _with_checkpoint_retry(
                self.checkpointer,
                self.graph.update_state,
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

    def replay_from_checkpoint(self, thread_id: str, checkpoint_id: str) -> dict[str, Any]:
        """从历史 checkpoint 分叉重跑，供管理员调试。只读：不落库、不写业务数据。

        两条硬约束（ADR-020）：
        1. 自开一条 checkpointer 连接（``CheckpointerManager``），绝不用 ``self.checkpointer``：
           ``PyMySQLSaver`` 内部只有一条 pymysql 连接，并发跑两个图会让 cursor 互相打断，
           正是 11-20 那次 ``InterfaceError`` 的成因。
        2. 绝不获取 ``self._execution_lock``：那个锁被 ``_execute_new_run`` / ``_execute_confirm``
           持有，重放抢锁会让真实用户排队，而他们的执行租约只有 2 分钟，排队就会过期。

        锚点由本方法自己解析（父快照的 next），不从外部传入 —— 见下方注释。

        第三条约束（T-FIX-02）：重放会**真跑**图节点，所以「节点自己写业务表」的路由
        一律拒绝（``_UNSAFE_REPLAY_ROUTES``，目前是 vocabulary_import）：
        它的 prepare 会解析文件、插入 content_extractions 并改 material.status，
        AC-3「不写业务表」在这条路由上结构性地做不到 —— 明确 409，而不是假装修好了。
        """
        started = time.perf_counter()
        prompt_version = f"{self.prompt.version}:{self.prompt.content_hash[:12]}"
        # 不用 with：超时后连接不能由请求线程关（T-FIX-04），改由 close() 幂等收尾，
        # 必要时把所有权移交给孤儿线程。
        manager = CheckpointerManager(self.settings)
        saver = manager.__enter__()
        abandoned = threading.Event()
        deferred_close = False
        try:
            graph = build_agent_graph(
                saver, self.llm, self.business, self.guidance, self.tool_workflow
            )
            src = _with_checkpoint_retry(
                saver,
                graph.get_state,
                {"configurable": {"thread_id": thread_id, "checkpoint_id": checkpoint_id}},
            )
            # 存在性看 created_at：不存在的 checkpoint 会返回 created_at=None /
            # metadata=None / tasks=() 的空快照，但 values 同样是 {}。
            # 真实入口 checkpoint 的 values 也是 {}（输入存在 pending writes 里），
            # 所以不能用 `not src.values` 判存在，否则会把「存在的入口」误报成 404。
            if src.created_at is None:
                raise checkpoint_not_found_error()
            if any(task.interrupts for task in src.tasks):
                raise AppError(
                    "checkpoint_interrupted", "Checkpoint 存在未解决的确认中断", status_code=409
                )
            if not src.next:
                raise AppError(
                    "checkpoint_terminal", "Checkpoint 已到终点，没有可重放的节点", status_code=409
                )

            # as_node 要的是「产出该 checkpoint 的节点」，即**父快照的 next**。
            # 不能取父的 writes.branch:to 目标：那是「下一跳」，差一层。
            # 实测：mid(next=('b',), values={'text':'a'}) 的父的 branch:to 也是 'b'，
            # 但产出 a 这个值的节点是父的 next[0]='a'。传 'b' 会让 next 变成 b 的后继，
            # 一个节点都不跑，等于没重放。
            if not src.parent_config:
                raise AppError(
                    "checkpoint_terminal", "该 checkpoint 是入口，没有可重放的节点", status_code=409
                )
            parent = _with_checkpoint_retry(saver, graph.get_state, src.parent_config)
            if len(parent.next) != 1:
                raise AppError(
                    "replay_anchor_ambiguous",
                    "无法唯一确定该 checkpoint 的产出节点，可能来自并行分支",
                    status_code=409,
                )
            anchor = parent.next[0]

            # T-FIX-02：该路由的 prepare 有业务写，重放不安全 → 先拒绝，不跑图。
            # 取值来源是 state 里的 route（classify 写入，之后沿链继承），
            # 父快照兜底覆盖「本快照 values 里还没有 route」的入口形态。
            replay_route_guard = src.values.get("route") or parent.values.get("route")
            if replay_route_guard in _UNSAFE_REPLAY_ROUTES:
                raise AppError(
                    "replay_unsupported_route",
                    f"{replay_route_guard} 路由的 prepare 会产生解析产物"
                    "（写 content_extractions 并改 material.status），重放不安全",
                    status_code=409,
                )

            # 重放跑在新 thread：同 thread 指定 checkpoint_id 会在原链 fork 出新分支，
            # 用户下次打开对话 get_state(thread_id) 就会看到调试结果（ADR-017）。
            new_tid = f"replay-{uuid.uuid4()}"
            base_usage = dict(src.values.get("token_usage") or {})
            _with_checkpoint_retry(
                saver,
                graph.update_state,
                {"configurable": {"thread_id": new_tid}},
                src.values,
                as_node=anchor,
            )
            # 不带 as_node 时 next 会被重算成入口节点，已完成节点会被重跑一遍（seq=[a,a,b]）；
            # 带 anchor 才是「重放」而非「重复执行」。
            executor = concurrent.futures.ThreadPoolExecutor(
                max_workers=1, thread_name_prefix=f"replay-{new_tid}"
            )
            try:
                future = executor.submit(_invoke_replay_graph, graph, saver, new_tid, abandoned)
                future.result(timeout=_REPLAY_TIMEOUT_SECONDS)
            except TimeoutError as exc:
                # 先置取消标志：孤儿线程此后不再 ping(reconnect=True) 把连接复活（T-FIX-04）。
                abandoned.set()
                logger.warning(
                    "agent checkpoint replay timeout source_thread=%s source_checkpoint=%s "
                    "replay_thread=%s timeout=%ss",
                    thread_id,
                    checkpoint_id,
                    new_tid,
                    _REPLAY_TIMEOUT_SECONDS,
                )
                # 已置取消标志的孤儿线程不会再写成功：它要么很快结束（连接交给外层 finally 关），
                # 要么还在跑（连接移交给它，它结束时自己关）。
                if not _drain_replay_future(future):
                    deferred_close = True
                    _hand_over_checkpointer(future, new_tid, manager)
                raise AppError("replay_timeout", "重放超时，请稍后重试", status_code=504) from exc
            finally:
                # 不能用 with：__exit__ 会 shutdown(wait=True)，超时形同虚设一直阻塞。
                # 线程无法 kill，只能 wait=False 让它自生自灭；日志已留 replay_thread 供清理。
                executor.shutdown(wait=False, cancel_futures=True)

            final = _with_checkpoint_retry(
                saver, graph.get_state, {"configurable": {"thread_id": new_tid}}
            )
            out = final.values
            # 停在 wait（等人工确认）也是 200，但必须让调用方看得出「没跑完」（T-FIX-05）。
            replay_interrupted = bool(final.next) or any(task.interrupts for task in final.tasks)
            # update_state 会把原 checkpoint 的 usage 继承过来，这里只回传本次增量。
            out_usage = out.get("token_usage") or {}
            delta = {
                key: max(0, int(out_usage.get(key, 0)) - int(base_usage.get(key, 0)))
                for key in out_usage
            }
            token_usage = delta if any(delta.values()) else None
            checkpoint_rows_added = sum(
                1
                for _ in _with_checkpoint_retry(
                    saver,
                    lambda: list(graph.get_state_history({"configurable": {"thread_id": new_tid}})),
                )
            )
        finally:
            # 只在「孤儿线程已结束」时由请求线程关连接；已移交的情况由孤儿线程自己关。
            if not deferred_close:
                try:
                    manager.close()
                except Exception:  # noqa: BLE001 - 收尾失败不能覆盖真正的错误
                    logger.warning("重放 checkpoint 连接关闭失败", exc_info=True)

        source_prompt_version: str | None = None
        run_id = src.values.get("run_id")
        if run_id:
            with self.database.session() as session:
                run = session.get(AgentRun, run_id)
                source_prompt_version = run.prompt_version if run else None

        duration_ms = int((time.perf_counter() - started) * 1000)
        source_route = src.values.get("route")
        source_response = src.values.get("response")
        source_pending = src.values.get("pending_action")
        replay_route = out.get("route")
        replay_response = out.get("response")
        replay_pending = out.get("pending_action")
        logger.info(
            "agent checkpoint replay source_thread=%s source_checkpoint=%s replay_thread=%s "
            "prompt_version=%s duration_ms=%s",
            thread_id,
            checkpoint_id,
            new_tid,
            prompt_version,
            duration_ms,
        )
        return {
            "source": {
                "thread_id": thread_id,
                "checkpoint_id": checkpoint_id,
                "step": (src.metadata or {}).get("step"),
                "next": list(src.next),
                "route": source_route,
                "response": source_response,
                "pending_action": source_pending,
                "prompt_version": source_prompt_version,
            },
            "replay": {
                "thread_id": new_tid,
                "route": replay_route,
                "response": replay_response,
                "pending_action": replay_pending,
                "interrupted": replay_interrupted,
                "token_usage": token_usage,
                "duration_ms": duration_ms,
                "prompt_version": prompt_version,
                "model": self.settings.llm_model,
                "checkpoint_rows_added": checkpoint_rows_added,
            },
            "diff": {
                "route_changed": source_route != replay_route,
                "response_changed": source_response != replay_response,
                "pending_action_changed": source_pending != replay_pending,
            },
        }
