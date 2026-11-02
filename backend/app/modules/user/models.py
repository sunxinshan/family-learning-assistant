from datetime import datetime

from sqlalchemy import ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.core.models import IdMixin, TimestampMixin, UTCDateTime


class User(IdMixin, TimestampMixin, Base):
    __tablename__ = "users"

    nickname: Mapped[str] = mapped_column(String(80), unique=True, index=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(String(20), default="user", nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(20), default="active", nullable=False, index=True)
    last_active_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)


class UserSession(IdMixin, Base):
    __tablename__ = "user_sessions"

    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    refresh_token_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
