from datetime import UTC, datetime

from app.core.models import new_id
from app.modules.question.models import Question
from app.modules.question.repository import QuestionRepository


class QuestionService:
    def __init__(self, repository: QuestionRepository) -> None:
        self.repository = repository

    def create_dictation_question(
        self,
        *,
        subject: str,
        word: str,
        phonetic: str,
        meanings: list[str],
        example: str,
        attempt_id: str,
    ) -> Question:
        now = datetime.now(UTC)
        return self.repository.add(
            Question(
                id=new_id(),
                subject=subject,
                question_type="dictation",
                prompt_json={
                    "word": word,
                    "phonetic": phonetic,
                    "meanings": meanings,
                    "example": example,
                },
                answer_json={"text": word},
                rule_json={"case_sensitive": False, "trim": True},
                source_module="practice",
                source_ref_id=attempt_id,
                created_at=now,
                updated_at=now,
            )
        )
