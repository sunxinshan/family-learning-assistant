from datetime import datetime

from pydantic import Field

from app.api.schemas import CamelModel


class AnswerOut(CamelModel):
    id: str
    question_id: str | None
    snapshot_entry_id: str
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
    kind: str
    target_entry_ids: list[str]
    status: str
    current_index: int
    # 强制答对模式的轮次：一组要练几轮，每轮只走一遍本轮待练的词。
    round_no: int = 1
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


class WrongQuestionOut(CamelModel):
    snapshot_entry_id: str
    word: str
    phonetic: str
    meanings: list[str]
    example: str
    example_translation: str
    consecutive_correct: int
    last_wrong_at: datetime
    group_index: int


class WrongQuestionGroupOut(CamelModel):
    group_index: int
    entries: list[WrongQuestionOut]


class WrongQuestionsOut(CamelModel):
    task_id: str
    total: int
    required_correct_streak: int
    groups: list[WrongQuestionGroupOut]
