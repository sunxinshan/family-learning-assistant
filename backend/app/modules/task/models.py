from sqlalchemy import JSON, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.core.models import IdMixin, TimestampMixin


class LearningTask(IdMixin, TimestampMixin, Base):
    __tablename__ = "tasks"

    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    name: Mapped[str] = mapped_column(String(180), nullable=False)
    subject: Mapped[str] = mapped_column(String(30), nullable=False)
    task_type: Mapped[str] = mapped_column(String(30), default="dictation", nullable=False)
    task_mode: Mapped[str] = mapped_column(String(20), nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="in_progress", nullable=False)
    progress: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    target_count: Mapped[int] = mapped_column(Integer, nullable=False)
    library_source_id: Mapped[str] = mapped_column(String(36), nullable=False)
    config_json: Mapped[dict] = mapped_column(JSON, nullable=False)
    snapshot: Mapped["TaskSnapshot"] = relationship(
        back_populates="task", cascade="all, delete-orphan", uselist=False, lazy="selectin"
    )


class TaskSnapshot(IdMixin, Base):
    __tablename__ = "task_snapshots"

    task_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("tasks.id", ondelete="CASCADE"), unique=True, nullable=False
    )
    source_library_id: Mapped[str] = mapped_column(String(36), nullable=False)
    task: Mapped[LearningTask] = relationship(back_populates="snapshot")
    entries: Mapped[list["TaskSnapshotEntry"]] = relationship(
        back_populates="snapshot",
        cascade="all, delete-orphan",
        lazy="selectin",
        order_by="TaskSnapshotEntry.sequence_no",
    )


class TaskSnapshotEntry(IdMixin, Base):
    __tablename__ = "task_snapshot_entries"
    __table_args__ = (UniqueConstraint("snapshot_id", "sequence_no", name="uq_snapshot_sequence"),)

    snapshot_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("task_snapshots.id", ondelete="CASCADE"), nullable=False
    )
    source_entry_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    sequence_no: Mapped[int] = mapped_column(Integer, nullable=False)
    word: Mapped[str] = mapped_column(String(200), nullable=False)
    normalized_word: Mapped[str] = mapped_column(String(200), nullable=False)
    phonetic: Mapped[str] = mapped_column(String(200), default="", nullable=False)
    part_of_speech: Mapped[str] = mapped_column(String(80), default="", nullable=False)
    meanings: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    example: Mapped[str] = mapped_column(String(1000), default="", nullable=False)
    example_translation: Mapped[str] = mapped_column(String(1000), default="", nullable=False)
    snapshot: Mapped[TaskSnapshot] = relationship(back_populates="entries")
