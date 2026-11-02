from datetime import datetime

from sqlalchemy import JSON, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.core.models import IdMixin, TimestampMixin, UTCDateTime


class AgentRun(IdMixin, TimestampMixin, Base):
    __tablename__ = "agent_runs"

    conversation_id: Mapped[str] = mapped_column(String(36), index=True, nullable=False)
    user_id: Mapped[str] = mapped_column(String(36), index=True, nullable=False)
    status: Mapped[str] = mapped_column(String(30), default="running", nullable=False)
    thread_id: Mapped[str] = mapped_column(String(36), index=True, nullable=False)
    lease_until: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    pending_action_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    draft_version: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    config_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    prompt_version: Mapped[str | None] = mapped_column(String(100), nullable=True)


class AgentRunEvent(IdMixin, Base):
    __tablename__ = "agent_run_events"
    __table_args__ = (UniqueConstraint("run_id", "sequence", name="uq_agent_run_event_sequence"),)

    run_id: Mapped[str] = mapped_column(String(36), index=True, nullable=False)
    conversation_id: Mapped[str] = mapped_column(String(36), index=True, nullable=False)
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    event_type: Mapped[str] = mapped_column(String(30), nullable=False)
    payload_json: Mapped[dict] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
