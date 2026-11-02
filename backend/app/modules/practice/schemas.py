from datetime import datetime

from pydantic import Field

from app.api.schemas import CamelModel


class AnswerOut(CamelModel):
    id: str
    question_id: str | None
    prompt: str
    expected: str
    given: str
    correct: bool
    evaluation_source: str
    answered_at: datetime
    duration_ms: int


class AttemptOut(CamelModel):
    id: str
    task_id: str
    user_id: str
    task_type: str
    status: str
    current_index: int
    answers: list[AnswerOut]
    started_at: datetime
    updated_at: datetime
    completed_at: datetime | None
    score: int
    total: int


class AnswerSubmit(CamelModel):
    given: str = Field(min_length=1, max_length=1000)
    duration_ms: int = Field(default=0, ge=0)


class SelfCheckSubmit(CamelModel):
    wrong_entry_ids: list[str]
