from sqlalchemy import Select, func, or_, select
from sqlalchemy.orm import Session, selectinload

from app.modules.vocabulary.models import (
    Vocabulary,
    VocabularyLearningState,
    VocabularyTag,
    WordEntry,
)


class VocabularyRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def _base_query(self) -> Select[tuple[Vocabulary]]:
        return select(Vocabulary).options(
            selectinload(Vocabulary.tags),
            selectinload(Vocabulary.entries),
        )

    def get(self, library_id: str) -> Vocabulary | None:
        return self.session.scalar(self._base_query().where(Vocabulary.id == library_id))

    def list_mine(self, user_id: str) -> list[Vocabulary]:
        return list(
            self.session.scalars(
                self._base_query()
                .where(Vocabulary.owner_user_id == user_id)
                .order_by(Vocabulary.updated_at.desc())
            )
        )

    def list_public(self, include_drafts: bool = False) -> list[Vocabulary]:
        query = self._base_query().where(Vocabulary.visibility == "public")
        if not include_drafts:
            query = query.where(Vocabulary.published.is_(True))
        return list(self.session.scalars(query.order_by(Vocabulary.updated_at.desc())))

    def list_available(self, user_id: str, subject: str | None = None) -> list[Vocabulary]:
        query = self._base_query().where(
            or_(
                Vocabulary.owner_user_id == user_id,
                (Vocabulary.visibility == "public") & Vocabulary.published.is_(True),
            )
        )
        if subject:
            query = query.where(Vocabulary.subject == subject)
        return list(self.session.scalars(query.order_by(Vocabulary.updated_at.desc())))

    def add(self, library: Vocabulary) -> Vocabulary:
        self.session.add(library)
        self.session.flush()
        self.session.refresh(library)
        return library

    def delete(self, library: Vocabulary) -> None:
        self.session.delete(library)
        self.session.flush()

    def replace_tags(self, library: Vocabulary, tags: list[str]) -> None:
        library.tags.clear()
        for tag in tags:
            library.tags.append(
                VocabularyTag(vocabulary_id=library.id, name=tag, created_at=library.updated_at)
            )
        self.session.flush()

    def entry_word_exists(
        self, library_id: str, normalized_word: str, exclude_id: str | None = None
    ) -> bool:
        query = select(func.count(WordEntry.id)).where(
            WordEntry.vocabulary_id == library_id,
            WordEntry.normalized_word == normalized_word,
        )
        if exclude_id:
            query = query.where(WordEntry.id != exclude_id)
        return bool(self.session.scalar(query))

    def add_entries(self, entries: list[WordEntry]) -> None:
        self.session.add_all(entries)
        self.session.flush()

    def get_learning_state(self, user_id: str, entry_id: str) -> VocabularyLearningState | None:
        return self.session.scalar(
            select(VocabularyLearningState).where(
                VocabularyLearningState.user_id == user_id,
                VocabularyLearningState.vocabulary_entry_id == entry_id,
            )
        )

    def add_learning_state(self, state: VocabularyLearningState) -> VocabularyLearningState:
        self.session.add(state)
        self.session.flush()
        return state

    def delete_entries(self, entries: list[WordEntry]) -> None:
        for entry in entries:
            self.session.delete(entry)
        self.session.flush()
