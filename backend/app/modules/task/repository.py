from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

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

    def list_for_user(self, user_id: str) -> list[LearningTask]:
        return list(
            self.session.scalars(
                self._query()
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
