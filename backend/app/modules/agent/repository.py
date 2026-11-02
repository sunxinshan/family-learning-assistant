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
        return self.session.scalar(
            select(AgentRun)
            .where(
                AgentRun.user_id == user_id,
                AgentRun.status.in_(["running", "waiting_confirmation"]),
            )
            .order_by(AgentRun.created_at.desc())
        )

    def get_active_for_conversation(self, conversation_id: str) -> AgentRun | None:
        return self.session.scalar(
            select(AgentRun)
            .where(
                AgentRun.conversation_id == conversation_id,
                AgentRun.status.in_(["running", "waiting_confirmation"]),
            )
            .order_by(AgentRun.created_at.desc())
        )

    def add_run(self, run: AgentRun) -> AgentRun:
        self.session.add(run)
        self.session.flush()
        return run

    def add_event(self, event: AgentRunEvent) -> AgentRunEvent:
        self.session.add(event)
        self.session.flush()
        return event

    def list_events(self, run_id: str, after_sequence: int = 0) -> list[AgentRunEvent]:
        return list(
            self.session.scalars(
                select(AgentRunEvent)
                .where(
                    AgentRunEvent.run_id == run_id,
                    AgentRunEvent.sequence > after_sequence,
                )
                .order_by(AgentRunEvent.sequence)
            )
        )

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
