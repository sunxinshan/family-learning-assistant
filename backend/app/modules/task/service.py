from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app.core.exceptions import AppError
from app.core.models import new_id
from app.modules.task.models import LearningTask, TaskSnapshot, TaskSnapshotEntry
from app.modules.task.repository import TaskRepository
from app.modules.task.schemas import (
    DictationConfig,
    SnapshotEntryOut,
    TaskConfigOut,
    TaskCreate,
    TaskOut,
    TaskUpdate,
)
from app.modules.vocabulary.repository import VocabularyRepository
from app.modules.vocabulary.service import VocabularyService


@dataclass(frozen=True)
class PracticeEntry:
    id: str
    source_entry_id: str | None
    sequence_no: int
    word: str
    phonetic: str
    meanings: list[str]
    example: str


@dataclass(frozen=True)
class TaskPracticeDefinition:
    id: str
    user_id: str
    type: str
    mode: str
    target_count: int
    subject: str
    entries: list[PracticeEntry]


def task_to_out(task: LearningTask) -> TaskOut:
    snapshot = task.snapshot
    entries = [
        SnapshotEntryOut(
            id=entry.id,
            word=entry.word,
            phonetic=entry.phonetic,
            part_of_speech=entry.part_of_speech,
            meanings=entry.meanings,
            example=entry.example,
            example_translation=entry.example_translation,
        )
        for entry in snapshot.entries
    ]
    config = task.config_json
    return TaskOut(
        id=task.id,
        user_id=task.user_id,
        name=task.name,
        subject=task.subject,
        type=task.task_type,
        mode=task.task_mode,
        status=task.status,
        progress=task.progress,
        target_count=task.target_count,
        library_id=task.library_source_id,
        library_name=config.get("library_name", ""),
        config=TaskConfigOut(
            question_count=task.target_count,
            words_per_group=config["words_per_group"],
            total_groups=config["total_groups"],
            repeat_until_correct=config["repeat_until_correct"],
            dictation=DictationConfig.model_validate(config["dictation"]),
        ),
        snapshot=entries,
        created_at=task.created_at,
        updated_at=task.updated_at,
    )


class TaskService:
    def __init__(self, repository: TaskRepository, session: Session) -> None:
        self.repository = repository
        self.vocabulary_service = VocabularyService(VocabularyRepository(session))

    def _owned(self, task_id: str, user_id: str) -> LearningTask:
        task = self.repository.get(task_id)
        if not task:
            raise AppError("task_not_found", "任务不存在", status_code=404)
        if task.user_id != user_id:
            raise AppError("forbidden", "你无权访问该任务", status_code=403)
        return task

    def list(self, user_id: str) -> list[TaskOut]:
        return [task_to_out(task) for task in self.repository.list_for_user(user_id)]

    def get(self, task_id: str, user_id: str) -> TaskOut:
        return task_to_out(self._owned(task_id, user_id))

    def get_practice_definition(self, task_id: str, user_id: str) -> TaskPracticeDefinition:
        task = self._owned(task_id, user_id)
        return TaskPracticeDefinition(
            id=task.id,
            user_id=task.user_id,
            type=task.task_type,
            mode=task.task_mode,
            target_count=task.target_count,
            subject=task.subject,
            entries=[
                PracticeEntry(
                    id=entry.id,
                    source_entry_id=entry.source_entry_id,
                    sequence_no=entry.sequence_no,
                    word=entry.word,
                    phonetic=entry.phonetic,
                    meanings=list(entry.meanings),
                    example=entry.example,
                )
                for entry in task.snapshot.entries
            ],
        )

    def set_progress(self, task_id: str, progress: int) -> TaskOut:
        task = self.repository.get(task_id)
        if not task:
            raise AppError("task_not_found", "任务不存在", status_code=404)
        task.progress = max(task.progress, max(0, min(progress, 100)))
        task.status = "completed" if task.progress >= 100 else "in_progress"
        task.updated_at = datetime.now(UTC)
        return task_to_out(task)

    def create(self, user_id: str, role: str, payload: TaskCreate) -> TaskOut:
        library = self.vocabulary_service.get_accessible(payload.library_id, user_id, role)
        selected_ids = set(payload.selected_entry_ids)
        selected = [entry for entry in library.entries if entry.id in selected_ids]
        if not selected:
            raise AppError("no_entries_selected", "请至少选择一个词条")
        if len(selected) != len(selected_ids):
            raise AppError("invalid_entry_selection", "部分词条不属于该词库")
        count = len(selected)
        words_per_group = count if payload.mode == "fixed" else min(payload.words_per_group, count)
        total_groups = (
            1 if payload.mode == "fixed" else (count + words_per_group - 1) // words_per_group
        )
        now = datetime.now(UTC)
        task = LearningTask(
            id=new_id(),
            user_id=user_id,
            name=payload.name.strip(),
            subject=library.subject,
            task_type=payload.type,
            task_mode=payload.mode,
            status="in_progress",
            progress=0,
            target_count=count,
            library_source_id=library.id,
            config_json={
                "library_name": library.name,
                "words_per_group": words_per_group,
                "total_groups": total_groups,
                "repeat_until_correct": payload.repeat_until_correct,
                "dictation": (payload.dictation or DictationConfig()).model_dump(by_alias=False),
            },
            created_at=now,
            updated_at=now,
        )
        snapshot = TaskSnapshot(
            id=new_id(),
            task_id=task.id,
            source_library_id=library.id,
        )
        snapshot.entries = [
            TaskSnapshotEntry(
                id=new_id(),
                snapshot_id=snapshot.id,
                source_entry_id=entry.id,
                sequence_no=index,
                word=entry.word,
                normalized_word=entry.normalized_word,
                phonetic=entry.phonetic,
                part_of_speech=entry.part_of_speech,
                meanings=list(entry.meanings),
                example=entry.example,
                example_translation=entry.example_translation,
            )
            for index, entry in enumerate(selected, start=1)
        ]
        task.snapshot = snapshot
        self.repository.add(task)
        return task_to_out(task)

    def update(self, task_id: str, user_id: str, payload: TaskUpdate) -> TaskOut:
        task = self._owned(task_id, user_id)
        if task.task_mode == "fixed" and (
            payload.words_per_group is not None
            or payload.repeat_until_correct is not None
            or payload.dictation is not None
        ):
            raise AppError("fixed_task_locked", "固定任务只能修改名称", status_code=409)
        task.name = payload.name.strip()
        config = dict(task.config_json)
        if payload.words_per_group is not None:
            config["words_per_group"] = min(payload.words_per_group, task.target_count)
            config["total_groups"] = (task.target_count + config["words_per_group"] - 1) // config[
                "words_per_group"
            ]
        if payload.repeat_until_correct is not None:
            config["repeat_until_correct"] = payload.repeat_until_correct
        if payload.dictation is not None:
            config["dictation"] = payload.dictation.model_dump(by_alias=False)
        task.config_json = config
        task.updated_at = datetime.now(UTC)
        return task_to_out(task)

    def delete(self, task_id: str, user_id: str) -> None:
        task = self._owned(task_id, user_id)
        self.repository.delete(task)
