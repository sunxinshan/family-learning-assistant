from datetime import UTC, datetime

from sqlalchemy import JSON, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.core.models import IdMixin, TimestampMixin, UTCDateTime


class Conversation(IdMixin, TimestampMixin, Base):
    __tablename__ = "conversations"

    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    title: Mapped[str] = mapped_column(String(150), default="学习助手", nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="active", nullable=False)
    messages: Mapped[list["ConversationMessage"]] = relationship(
        cascade="all, delete-orphan", lazy="selectin", order_by="ConversationMessage.sequence_no"
    )


class ConversationMessage(IdMixin, Base):
    __tablename__ = "conversation_messages"
    __table_args__ = (
        UniqueConstraint("conversation_id", "sequence_no", name="uq_message_sequence"),
    )

    conversation_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("conversations.id", ondelete="CASCADE"), index=True, nullable=False
    )
    sequence_no: Mapped[int] = mapped_column(Integer, nullable=False)
    message_type: Mapped[str] = mapped_column(String(30), nullable=False)
    content_json: Mapped[dict] = mapped_column(JSON, nullable=False)
    tool_call_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    run_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        UTCDateTime(), default=lambda: datetime.now(UTC), nullable=False
    )
