from sqlalchemy.orm import Session

from app.modules.question.models import Question


class QuestionRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def add(self, question: Question) -> Question:
        self.session.add(question)
        self.session.flush()
        return question

    def get(self, question_id: str) -> Question | None:
        return self.session.get(Question, question_id)
