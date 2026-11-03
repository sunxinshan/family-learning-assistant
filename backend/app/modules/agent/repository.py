from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.agent.models import AgentRun, AgentRunEvent


class AgentRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def get_run(self, run_id: str) -> AgentRun | None:
        return self.session.get(AgentRun, run_id)

    def get_active_for_user(self, user_id: str) -> AgentRun | None:
        # 只选主键再回表：pending_action_json 可能有数百 KB，
        # 直接排序整行会顶爆 MySQL 的 sort_buffer_size（1038 Out of sort memory）。
        run_id = self.session.scalar(
            select(AgentRun.id)
            .where(
                AgentRun.user_id == user_id,
                AgentRun.status.in_(["running", "waiting_confirmation"]),
            )
            .order_by(AgentRun.created_at.desc())
            .limit(1)
        )
        return self.session.get(AgentRun, run_id) if run_id else None

    def get_active_for_conversation(self, conversation_id: str) -> AgentRun | None:
        run_id = self.session.scalar(
            select(AgentRun.id)
            .where(
                AgentRun.conversation_id == conversation_id,
                AgentRun.status.in_(["running", "waiting_confirmation"]),
            )
            .order_by(AgentRun.created_at.desc())
            .limit(1)
        )
        return self.session.get(AgentRun, run_id) if run_id else None

    def add_run(self, run: AgentRun) -> AgentRun:
        self.session.add(run)
        self.session.flush()
        return run

    def add_event(self, event: AgentRunEvent) -> AgentRunEvent:
        self.session.add(event)
        self.session.flush()
        return event

    def list_events(self, run_id: str, after_sequence: int = 0) -> list[AgentRunEvent]:
        # 同上：先按 sequence 只取主键排序，再回表，避免事件里的大 payload 参与排序。
        ids = list(
            self.session.scalars(
                select(AgentRunEvent.id)
                .where(
                    AgentRunEvent.run_id == run_id,
                    AgentRunEvent.sequence > after_sequence,
                )
                .order_by(AgentRunEvent.sequence)
            )
        )
        if not ids:
            return []
        rows = {
            event.id: event
            for event in self.session.scalars(select(AgentRunEvent).where(AgentRunEvent.id.in_(ids)))
        }
        return [rows[event_id] for event_id in ids if event_id in rows]

    def next_sequence(self, run_id: str) -> int:
        last = self.session.scalar(
            select(AgentRunEvent.sequence)
            .where(AgentRunEvent.run_id == run_id)
            .order_by(AgentRunEvent.sequence.desc())
            .limit(1)
        )
        return (last or 0) + 1

    def extend_lease(self, run: AgentRun, seconds: int = 120) -> None:
        run.lease_until = datetime.now(UTC).replace(microsecond=0) + __import__(
            "datetime"
        ).timedelta(seconds=seconds)
