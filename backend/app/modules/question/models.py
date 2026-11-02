from sqlalchemy import JSON, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.core.models import IdMixin, TimestampMixin


class Question(IdMixin, TimestampMixin, Base):
    __tablename__ = "questions"

    subject: Mapped[str] = mapped_column(String(30), index=True, nullable=False)
    question_type: Mapped[str] = mapped_column(String(30), nullable=False)
    prompt_json: Mapped[dict] = mapped_column(JSON, nullable=False)
    answer_json: Mapped[dict] = mapped_column(JSON, nullable=False)
    rule_json: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    source_module: Mapped[str] = mapped_column(String(30), nullable=False)
    source_ref_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
