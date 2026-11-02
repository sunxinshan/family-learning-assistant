import unicodedata
from datetime import UTC, datetime, timedelta

from app.core.exceptions import AppError
from app.core.models import new_id
from app.modules.vocabulary.models import (
    Vocabulary,
    VocabularyLearningState,
    VocabularyTag,
    WordEntry,
)
from app.modules.vocabulary.repository import VocabularyRepository
from app.modules.vocabulary.schemas import VocabularyCreate, VocabularyUpdate, WordEntryIn

SUBJECTS = {"english": "英语", "chinese": "语文"}


def normalize_word(value: str) -> str:
    return unicodedata.normalize("NFKC", value).strip().casefold()


class VocabularyService:
    def __init__(self, repository: VocabularyRepository) -> None:
        self.repository = repository

    def _assert_subject(self, subject: str) -> None:
        if subject not in SUBJECTS:
            raise AppError("invalid_subject", "不支持的学科")

    def _can_edit(self, library: Vocabulary, user_id: str, role: str) -> bool:
        if library.owner_user_id == user_id:
            return True
        return role == "admin" and library.visibility == "public"

    def get_accessible(self, library_id: str, user_id: str, role: str) -> Vocabulary:
        library = self.repository.get(library_id)
        if not library:
            raise AppError("library_not_found", "词库不存在", status_code=404)
        accessible = (
            library.owner_user_id == user_id
            or (library.visibility == "public" and library.published)
            or role == "admin"
        )
        if not accessible:
            raise AppError("forbidden", "你无权访问该词库", status_code=403)
        return library

    def list_available(self, user_id: str, subject: str | None) -> list[Vocabulary]:
        return self.repository.list_available(user_id, subject)

    def list_mine(self, user_id: str) -> list[Vocabulary]:
        return self.repository.list_mine(user_id)

    def list_public(self, role: str, subject: str | None = None) -> list[Vocabulary]:
        libraries = self.repository.list_public(include_drafts=role == "admin")
        return [item for item in libraries if not subject or item.subject == subject]

    def _build_entries(self, library_id: str, entries: list[WordEntryIn]) -> list[WordEntry]:
        result: list[WordEntry] = []
        seen: set[str] = set()
        now = datetime.now(UTC)
        for position, entry in enumerate(entries):
            normalized = normalize_word(entry.word)
            if not normalized:
                raise AppError("invalid_word", "单词不能为空")
            if normalized in seen or self.repository.entry_word_exists(library_id, normalized):
                raise AppError("duplicate_word", f"词条重复：{entry.word}", status_code=409)
            seen.add(normalized)
            result.append(
                WordEntry(
                    id=new_id(),
                    vocabulary_id=library_id,
                    word=entry.word.strip(),
                    normalized_word=normalized,
                    phonetic=entry.phonetic.strip(),
                    part_of_speech=entry.part_of_speech.strip(),
                    meanings=[item.strip() for item in entry.meanings if item.strip()],
                    example=entry.example.strip(),
                    example_translation=entry.example_translation.strip(),
                    position=position,
                    created_at=now,
                    updated_at=now,
                )
            )
        return result

    def create(self, user_id: str, role: str, payload: VocabularyCreate) -> Vocabulary:
        self._assert_subject(payload.subject)
        visibility = payload.visibility or "personal"
        if visibility == "public" and role != "admin":
            raise AppError("forbidden", "普通用户不能创建公共词库", status_code=403)
        now = datetime.now(UTC)
        library = Vocabulary(
            id=new_id(),
            owner_user_id=user_id if visibility == "personal" else None,
            subject=payload.subject,
            name=payload.name.strip(),
            description=payload.description.strip(),
            visibility=visibility,
            published=False,
            created_at=now,
            updated_at=now,
        )
        library.tags = [
            VocabularyTag(id=new_id(), vocabulary_id=library.id, name=tag.strip(), created_at=now)
            for tag in dict.fromkeys(payload.tags)
            if tag.strip()
        ]
        library.entries = self._build_entries(library.id, payload.entries)
        return self.repository.add(library)

    def update(
        self, library_id: str, user_id: str, role: str, payload: VocabularyUpdate
    ) -> Vocabulary:
        library = self.get_accessible(library_id, user_id, role)
        if not self._can_edit(library, user_id, role):
            raise AppError("forbidden", "你无权编辑该词库", status_code=403)
        self._assert_subject(payload.subject)
        library.subject = payload.subject
        library.name = payload.name.strip()
        library.description = payload.description.strip()
        library.updated_at = datetime.now(UTC)
        library.tags.clear()
        for tag in dict.fromkeys(payload.tags):
            if tag.strip():
                library.tags.append(
                    VocabularyTag(
                        id=new_id(),
                        vocabulary_id=library.id,
                        name=tag.strip(),
                        created_at=library.updated_at,
                    )
                )
        return library

    def copy(self, library_id: str, user_id: str, role: str) -> Vocabulary:
        source = self.get_accessible(library_id, user_id, role)
        if source.visibility != "public" or not source.published:
            raise AppError("invalid_source", "只能复制已发布的公共词库")
        now = datetime.now(UTC)
        copy = Vocabulary(
            id=new_id(),
            owner_user_id=user_id,
            subject=source.subject,
            name=f"{source.name} · 我的副本",
            description=source.description,
            visibility="personal",
            published=False,
            source_vocabulary_id=source.id,
            created_at=now,
            updated_at=now,
        )
        copy.tags = [
            VocabularyTag(id=new_id(), vocabulary_id=copy.id, name=tag.name, created_at=now)
            for tag in source.tags
        ]
        copy.entries = [
            WordEntry(
                id=new_id(),
                vocabulary_id=copy.id,
                word=entry.word,
                normalized_word=entry.normalized_word,
                phonetic=entry.phonetic,
                part_of_speech=entry.part_of_speech,
                meanings=list(entry.meanings),
                example=entry.example,
                example_translation=entry.example_translation,
                position=entry.position,
                created_at=now,
                updated_at=now,
            )
            for entry in source.entries
        ]
        return self.repository.add(copy)

    def add_entries(
        self, library_id: str, user_id: str, role: str, entries: list[WordEntryIn]
    ) -> Vocabulary:
        library = self.get_accessible(library_id, user_id, role)
        if not self._can_edit(library, user_id, role):
            raise AppError("forbidden", "你无权编辑该词库", status_code=403)
        start = len(library.entries)
        built = self._build_entries(library.id, entries)
        for offset, entry in enumerate(built):
            entry.position = start + offset
        self.repository.add_entries(built)
        library.entries.extend(built)
        library.updated_at = datetime.now(UTC)
        return library

    def update_entry(
        self, library_id: str, entry_id: str, user_id: str, role: str, payload: WordEntryIn
    ) -> Vocabulary:
        library = self.get_accessible(library_id, user_id, role)
        if not self._can_edit(library, user_id, role):
            raise AppError("forbidden", "你无权编辑该词库", status_code=403)
        entry = next((item for item in library.entries if item.id == entry_id), None)
        if not entry:
            raise AppError("entry_not_found", "词条不存在", status_code=404)
        normalized = normalize_word(payload.word)
        if self.repository.entry_word_exists(library.id, normalized, exclude_id=entry.id):
            raise AppError("duplicate_word", "同一词库中不能出现重复词条", status_code=409)
        entry.word = payload.word.strip()
        entry.normalized_word = normalized
        entry.phonetic = payload.phonetic.strip()
        entry.part_of_speech = payload.part_of_speech.strip()
        entry.meanings = [item.strip() for item in payload.meanings if item.strip()]
        entry.example = payload.example.strip()
        entry.example_translation = payload.example_translation.strip()
        entry.updated_at = datetime.now(UTC)
        library.updated_at = entry.updated_at
        return library

    def remove_entries(
        self, library_id: str, entry_ids: list[str], user_id: str, role: str
    ) -> None:
        library = self.get_accessible(library_id, user_id, role)
        if not self._can_edit(library, user_id, role):
            raise AppError("forbidden", "你无权编辑该词库", status_code=403)
        targets = [entry for entry in library.entries if entry.id in entry_ids]
        self.repository.delete_entries(targets)

    def record_learning_answer(
        self,
        user_id: str,
        entry_id: str,
        answer_id: str,
        correct: bool,
        mastery_threshold: int,
        review_intervals: list[int],
    ) -> None:
        state = self.repository.get_learning_state(user_id, entry_id)
        now = datetime.now(UTC)
        if not state:
            state = VocabularyLearningState(
                id=new_id(),
                user_id=user_id,
                vocabulary_entry_id=entry_id,
                status="learning",
                correct_streak=0,
                updated_at=now,
            )
            state = self.repository.add_learning_state(state)
        state.correct_streak = state.correct_streak + 1 if correct else 0
        state.last_answer_id = answer_id
        state.updated_at = now
        if state.correct_streak >= mastery_threshold:
            state.status = "mastered"
        interval_index = min(max(state.correct_streak - 1, 0), len(review_intervals) - 1)
        state.next_review_at = now + timedelta(days=review_intervals[interval_index])

    def publish(self, library_id: str, admin_id: str, role: str, published: bool) -> Vocabulary:
        if role != "admin":
            raise AppError("forbidden", "仅管理员可以发布公共词库", status_code=403)
        library = self.get_accessible(library_id, admin_id, role)
        if library.visibility != "public":
            raise AppError("invalid_library", "该资源不是公共词库")
        library.published = published
        library.updated_at = datetime.now(UTC)
        return library
