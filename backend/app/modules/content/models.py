from datetime import datetime

from sqlalchemy import JSON, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.core.models import IdMixin, TimestampMixin, UTCDateTime


class ContentExtraction(IdMixin, TimestampMixin, Base):
    __tablename__ = "content_extractions"

    user_id: Mapped[str] = mapped_column(String(36), index=True, nullable=False)
    material_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("materials.id", ondelete="CASCADE"), nullable=False
    )
    stage: Mapped[str] = mapped_column(String(30), default="preview", nullable=False)
    parser_type: Mapped[str] = mapped_column(String(20), nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="previewed", nullable=False)
    extracted_json: Mapped[dict] = mapped_column(JSON, nullable=False)
    errors_json: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    mapping_json: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    mapping_source: Mapped[str] = mapped_column(String(20), default="rules", nullable=False)
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    confirmed_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)

    @property
    def mapping(self) -> dict:
        return self.mapping_json
