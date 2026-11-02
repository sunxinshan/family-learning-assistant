from collections import defaultdict
from datetime import UTC, datetime, timedelta

from app.core.config import Settings
from app.modules.learning.schemas import LearningStatsOut, WeeklyPoint
from app.modules.practice.schemas import AnswerOut
from app.modules.practice.service import PracticeService


class LearningService:
    def __init__(self, practice_service: PracticeService, settings: Settings) -> None:
        self.practice_service = practice_service
        self.settings = settings

    def stats(self, user_id: str) -> LearningStatsOut:
        attempts = [
            item for item in self.practice_service.list(user_id) if item.status == "completed"
        ]
        answers = [answer for attempt in attempts for answer in attempt.answers]
        total = len(answers)
        correct = sum(1 for answer in answers if answer.correct)
        vocab_answers = [
            answer
            for attempt in attempts
            if attempt.task_type == "vocabulary"
            for answer in attempt.answers
        ]
        dictation_answers = [
            answer
            for attempt in attempts
            if attempt.task_type == "dictation"
            for answer in attempt.answers
        ]

        def accuracy(items: list[AnswerOut]) -> int:
            if not items:
                return 0
            return round(sum(1 for item in items if item.correct) / len(items) * 100)

        latest: dict[str, AnswerOut] = {}
        for answer in sorted(answers, key=lambda item: item.answered_at):
            latest[answer.prompt] = answer
        streaks: dict[str, int] = defaultdict(int)
        for answer in sorted(answers, key=lambda item: item.answered_at):
            streaks[answer.prompt] = streaks[answer.prompt] + 1 if answer.correct else 0
        mastered = sum(1 for value in streaks.values() if value >= self.settings.mastery_threshold)
        wrong = [item for item in latest.values() if not item.correct]
        wrong.sort(key=lambda item: item.answered_at, reverse=True)

        today = datetime.now(UTC).date()
        weekly = []
        for offset in range(6, -1, -1):
            day = today - timedelta(days=offset)
            day_attempts = [
                attempt
                for attempt in attempts
                if (attempt.completed_at or attempt.updated_at).date() == day
            ]
            day_answers = [answer for attempt in day_attempts for answer in attempt.answers]
            weekly.append(
                WeeklyPoint(
                    label=f"{day.month}/{day.day}",
                    count=len(day_attempts),
                    accuracy=accuracy(day_answers),
                )
            )

        return LearningStatsOut(
            practice_count=len(attempts),
            average_accuracy=round(correct / total * 100) if total else 0,
            mastered_count=mastered,
            review_count=len(wrong),
            vocabulary_accuracy=accuracy(vocab_answers),
            dictation_accuracy=accuracy(dictation_answers),
            recent_attempts=attempts[:8],
            wrong_answers=wrong[:8],
            weekly_activity=weekly,
        )
