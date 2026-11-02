from app.api.schemas import CamelModel
from app.modules.practice.schemas import AnswerOut, AttemptOut


class WeeklyPoint(CamelModel):
    label: str
    count: int
    accuracy: int


class LearningStatsOut(CamelModel):
    practice_count: int
    average_accuracy: int
    mastered_count: int
    review_count: int
    vocabulary_accuracy: int
    dictation_accuracy: int
    recent_attempts: list[AttemptOut]
    wrong_answers: list[AnswerOut]
    weekly_activity: list[WeeklyPoint]
