from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.modules.practice.models import PracticeAnswer, PracticeAttempt


class PracticeRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def _attempt_query(self):
        return select(PracticeAttempt).options(selectinload(PracticeAttempt.answers))

    def get_attempt(self, attempt_id: str) -> PracticeAttempt | None:
        return self.session.scalar(self._attempt_query().where(PracticeAttempt.id == attempt_id))

    def get_active(self, task_id: str, user_id: str) -> PracticeAttempt | None:
        return self.session.scalar(
            self._attempt_query().where(
                PracticeAttempt.task_id == task_id,
                PracticeAttempt.user_id == user_id,
                PracticeAttempt.status == "in_progress",
            )
        )

    def list_for_user(self, user_id: str) -> list[PracticeAttempt]:
        return list(
            self.session.scalars(
                self._attempt_query()
                .where(PracticeAttempt.user_id == user_id)
                .order_by(PracticeAttempt.updated_at.desc())
            )
        )

    def add_attempt(self, attempt: PracticeAttempt) -> PracticeAttempt:
        self.session.add(attempt)
        self.session.flush()
        return attempt

    def add_answer(self, answer: PracticeAnswer) -> PracticeAnswer:
        self.session.add(answer)
        self.session.flush()
        return answer

    def answers_for_task(self, task_id: str, user_id: str) -> list[PracticeAnswer]:
        return list(
            self.session.scalars(
                select(PracticeAnswer)
                .join(PracticeAttempt, PracticeAttempt.id == PracticeAnswer.attempt_id)
                .where(PracticeAttempt.task_id == task_id, PracticeAttempt.user_id == user_id)
                .order_by(PracticeAnswer.answered_at)
            )
        )
