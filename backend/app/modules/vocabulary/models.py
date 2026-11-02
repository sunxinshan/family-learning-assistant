from datetime import datetime

from sqlalchemy import JSON, Boolean, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.core.models import IdMixin, TimestampMixin, UTCDateTime


class SubjectConfig(Base):
    __tablename__ = "subjects"

    code: Mapped[str] = mapped_column(String(30), primary_key=True)
    display_name: Mapped[str] = mapped_column(String(50), nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)


class Vocabulary(IdMixin, TimestampMixin, Base):
    __tablename__ = "vocabularies"

    owner_user_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=True
    )
    subject: Mapped[str] = mapped_column(
        String(30), ForeignKey("subjects.code"), index=True, nullable=False
    )
    name: Mapped[str] = mapped_column(String(150), nullable=False)
    description: Mapped[str] = mapped_column(String(1000), default="", nullable=False)
    visibility: Mapped[str] = mapped_column(String(20), default="personal", nullable=False)
    published: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    source_vocabulary_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("vocabularies.id", ondelete="SET NULL"), nullable=True
    )

    tags: Mapped[list["VocabularyTag"]] = relationship(
        back_populates="vocabulary", cascade="all, delete-orphan", lazy="selectin"
    )
    entries: Mapped[list["WordEntry"]] = relationship(
        back_populates="vocabulary",
        cascade="all, delete-orphan",
        lazy="selectin",
        order_by="WordEntry.position",
    )


class VocabularyTag(IdMixin, Base):
    __tablename__ = "vocabulary_tags"
    __table_args__ = (UniqueConstraint("vocabulary_id", "name", name="uq_vocabulary_tag"),)

    vocabulary_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("vocabularies.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(80), nullable=False)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    vocabulary: Mapped[Vocabulary] = relationship(back_populates="tags")


class WordEntry(IdMixin, TimestampMixin, Base):
    __tablename__ = "word_entries"
    __table_args__ = (UniqueConstraint("vocabulary_id", "normalized_word", name="uq_word_entry"),)

    vocabulary_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("vocabularies.id", ondelete="CASCADE"), nullable=False
    )
    word: Mapped[str] = mapped_column(String(200), nullable=False)
    normalized_word: Mapped[str] = mapped_column(String(200), nullable=False, index=True)
    phonetic: Mapped[str] = mapped_column(String(200), default="", nullable=False)
    part_of_speech: Mapped[str] = mapped_column(String(80), default="", nullable=False)
    meanings: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    example: Mapped[str] = mapped_column(String(1000), default="", nullable=False)
    example_translation: Mapped[str] = mapped_column(String(1000), default="", nullable=False)
    position: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    vocabulary: Mapped[Vocabulary] = relationship(back_populates="entries")


class VocabularyLearningState(IdMixin, Base):
    __tablename__ = "vocabulary_learning_states"
    __table_args__ = (
        UniqueConstraint("user_id", "vocabulary_entry_id", name="uq_vocab_learning_state"),
    )

    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    vocabulary_entry_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("word_entries.id", ondelete="CASCADE"), nullable=False
    )
    status: Mapped[str] = mapped_column(String(20), default="learning", nullable=False)
    correct_streak: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    last_answer_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    next_review_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
