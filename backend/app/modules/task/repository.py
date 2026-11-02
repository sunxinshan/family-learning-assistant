from sqlalchemy import select
from sqlalchemy.orm import Session, raiseload, selectinload

from app.modules.task.models import LearningTask, TaskSnapshot


class TaskRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def _query(self):
        return select(LearningTask).options(
            selectinload(LearningTask.snapshot).selectinload(TaskSnapshot.entries)
        )

    def get(self, task_id: str) -> LearningTask | None:
        return self.session.scalar(self._query().where(LearningTask.id == task_id))

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
