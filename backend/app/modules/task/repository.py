from sqlalchemy import select
from sqlalchemy.orm import Session, raiseload, selectinload

from app.modules.task.models import LearningTask, TaskSnapshot, TaskSnapshotEntry


class TaskRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def _query(self):
        return select(LearningTask).options(
            selectinload(LearningTask.snapshot).selectinload(TaskSnapshot.entries)
        )

    def get(self, task_id: str) -> LearningTask | None:
        return self.session.scalar(self._query().where(LearningTask.id == task_id))

    def get_metadata(self, task_id: str) -> LearningTask | None:
        return self.session.scalar(
            select(LearningTask)
            .options(raiseload(LearningTask.snapshot))
            .where(LearningTask.id == task_id)
        )

    def get_snapshot_entry(
        self, task_id: str, *, sequence_no: int | None = None, entry_id: str | None = None
    ):
        query = (
            select(TaskSnapshotEntry)
            .join(TaskSnapshot, TaskSnapshot.id == TaskSnapshotEntry.snapshot_id)
            .where(TaskSnapshot.task_id == task_id)
        )
        if entry_id is not None:
            query = query.where(TaskSnapshotEntry.id == entry_id)
        elif sequence_no is not None:
            query = query.where(TaskSnapshotEntry.sequence_no == sequence_no)
        else:
            return None
        return self.session.scalar(query)

    def list_entry_ids(self, task_id: str, start_sequence: int, end_sequence: int) -> list[str]:
        """按顺序返回某个分组区间内的快照词条 id，用于强制答对模式的分轮取词。"""
        rows = self.session.scalars(
            select(TaskSnapshotEntry.id)
            .join(TaskSnapshot, TaskSnapshot.id == TaskSnapshotEntry.snapshot_id)
            .where(
                TaskSnapshot.task_id == task_id,
                TaskSnapshotEntry.sequence_no >= start_sequence,
                TaskSnapshotEntry.sequence_no <= end_sequence,
            )
            .order_by(TaskSnapshotEntry.sequence_no)
        )
        return list(rows)

    def list_for_user(self, user_id: str, include_snapshot: bool = True) -> list[LearningTask]:
        query = select(LearningTask)
        if include_snapshot:
            query = query.options(
                selectinload(LearningTask.snapshot).selectinload(TaskSnapshot.entries)
            )
        else:
            query = query.options(raiseload(LearningTask.snapshot))
        return list(
            self.session.scalars(
                query
                .where(LearningTask.user_id == user_id)
                .order_by(LearningTask.updated_at.desc())
            )
        )

    def add(self, task: LearningTask) -> LearningTask:
        self.session.add(task)
        self.session.flush()
        return task

    def delete(self, task: LearningTask) -> None:
        self.session.delete(task)
        self.session.flush()
