from sqlalchemy import JSON, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.core.models import IdMixin, TimestampMixin


class OperationLog(IdMixin, TimestampMixin, Base):
    __tablename__ = "operation_logs"

    actor_user_id: Mapped[str] = mapped_column(String(36), index=True, nullable=False)
    action: Mapped[str] = mapped_column(String(100), nullable=False)
    target_type: Mapped[str] = mapped_column(String(50), nullable=False)
    target_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    target_name: Mapped[str] = mapped_column(String(255), default="", nullable=False)
    result: Mapped[str] = mapped_column(String(20), default="success", nullable=False)
    metadata_json: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
