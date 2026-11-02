from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.exceptions import AppError
from app.core.models import new_id
from app.modules.practice.models import PracticeAnswer, PracticeAttempt
from app.modules.practice.repository import PracticeRepository
from app.modules.practice.schemas import AnswerOut, AnswerSubmit, AttemptOut, SelfCheckSubmit
from app.modules.question.repository import QuestionRepository
from app.modules.question.service import QuestionService
from app.modules.task.repository import TaskRepository
from app.modules.task.service import TaskService
from app.modules.vocabulary.repository import VocabularyRepository
from app.modules.vocabulary.service import VocabularyService


def answer_to_out(answer: PracticeAnswer) -> AnswerOut:
    return AnswerOut(
        id=answer.id,
        question_id=answer.question_id,
        prompt=answer.prompt,
        expected=answer.expected,
        given=answer.given,
        correct=answer.is_correct,
        evaluation_source=answer.evaluation_source,
        answered_at=answer.answered_at,
        duration_ms=answer.duration_ms,
    )


def attempt_to_out(attempt: PracticeAttempt) -> AttemptOut:
    return AttemptOut(
        id=attempt.id,
        task_id=attempt.task_id,
        user_id=attempt.user_id,
        task_type=attempt.task_type,
        status=attempt.status,
        current_index=attempt.current_index,
        answers=[answer_to_out(answer) for answer in attempt.answers],
        started_at=attempt.started_at,
        updated_at=attempt.updated_at,
        completed_at=attempt.completed_at,
        score=sum(1 for answer in attempt.answers if answer.is_correct),
        total=attempt.total,
    )


class PracticeService:
    def __init__(
        self, repository: PracticeRepository, session: Session, settings: Settings
    ) -> None:
        self.repository = repository
        self.settings = settings
        self.task_service = TaskService(TaskRepository(session), session)
        self.question_service = QuestionService(QuestionRepository(session))
        self.vocabulary_service = VocabularyService(VocabularyRepository(session))

    def _owned_attempt(self, attempt_id: str, user_id: str) -> PracticeAttempt:
        attempt = self.repository.get_attempt(attempt_id)
        if not attempt:
            raise AppError("attempt_not_found", "练习不存在", status_code=404)
        if attempt.user_id != user_id:
            raise AppError("forbidden", "你无权访问该练习", status_code=403)
        return attempt

    def start_or_resume(self, task_id: str, user_id: str) -> AttemptOut:
        active = self.repository.get_active(task_id, user_id)
        if active:
            return attempt_to_out(active)
        definition = self.task_service.get_practice_definition(task_id, user_id)
        now = datetime.now(UTC)
        attempt = PracticeAttempt(
            id=new_id(),
            task_id=task_id,
            user_id=user_id,
            task_type=definition.type,
            status="in_progress",
            current_index=0,
            total=definition.target_count,
            started_at=now,
            updated_at=now,
        )
        return attempt_to_out(self.repository.add_attempt(attempt))

    def get(self, attempt_id: str, user_id: str) -> AttemptOut:
        return attempt_to_out(self._owned_attempt(attempt_id, user_id))

    def list(self, user_id: str) -> list[AttemptOut]:
        return [attempt_to_out(item) for item in self.repository.list_for_user(user_id)]

    def _record_learning(
        self,
        user_id: str,
        source_entry_id: str | None,
        answer_id: str,
        correct: bool,
    ) -> None:
        if not source_entry_id:
            return
        self.vocabulary_service.record_learning_answer(
            user_id=user_id,
            entry_id=source_entry_id,
            answer_id=answer_id,
            correct=correct,
            mastery_threshold=self.settings.mastery_threshold,
            review_intervals=self.settings.review_intervals_days,
        )

    def _recalculate_progress(self, task_id: str, user_id: str) -> None:
        definition = self.task_service.get_practice_definition(task_id, user_id)
        answers = self.repository.answers_for_task(task_id, user_id)
        if definition.mode == "fixed":
            attempted = {answer.snapshot_entry_id for answer in answers}
            progress = round(len(attempted) / max(definition.target_count, 1) * 100)
        else:
            streaks: dict[str, int] = {}
            for answer in answers:
                streaks[answer.snapshot_entry_id] = (
                    streaks.get(answer.snapshot_entry_id, 0) + 1 if answer.is_correct else 0
                )
            mastered = sum(
                1 for value in streaks.values() if value >= self.settings.mastery_threshold
            )
            progress = round(mastered / max(definition.target_count, 1) * 100)
        self.task_service.set_progress(task_id, progress)

    def submit_answer(self, attempt_id: str, user_id: str, payload: AnswerSubmit) -> AttemptOut:
        attempt = self._owned_attempt(attempt_id, user_id)
        if attempt.status != "in_progress":
            raise AppError("attempt_completed", "本次练习已经完成", status_code=409)
        if attempt.current_index >= attempt.total:
            raise AppError("attempt_completed", "本次练习已经完成", status_code=409)
        definition = self.task_service.get_practice_definition(attempt.task_id, user_id)
        entry = next(
            (item for item in definition.entries if item.sequence_no == attempt.current_index + 1),
            None,
        )
        if not entry:
            raise AppError("question_not_found", "当前题目不存在", status_code=404)
        question = self.question_service.create_dictation_question(
            subject=definition.subject,
            word=entry.word,
            phonetic=entry.phonetic,
            meanings=entry.meanings,
            example=entry.example,
            attempt_id=attempt.id,
        )
        expected = entry.word.strip().casefold()
        given = payload.given.strip()
        is_correct = given.casefold() == expected
        now = datetime.now(UTC)
        answer = PracticeAnswer(
            id=new_id(),
            attempt_id=attempt.id,
            question_id=question.id,
            snapshot_entry_id=entry.id,
            sequence_no=attempt.current_index + 1,
            prompt=entry.word,
            expected=entry.word,
            given=given,
            is_correct=is_correct,
            evaluation_source="auto",
            answered_at=now,
            duration_ms=payload.duration_ms,
        )
        answer.attempt = attempt
        answer = self.repository.add_answer(answer)
        self._record_learning(user_id, entry.source_entry_id, answer.id, is_correct)
        attempt.current_index += 1
        attempt.updated_at = now
        if attempt.current_index >= attempt.total:
            attempt.status = "completed"
            attempt.completed_at = now
        self.repository.session.flush()
        self._recalculate_progress(attempt.task_id, user_id)
        return attempt_to_out(attempt)

    def submit_self_check(
        self,
        attempt_id: str,
        user_id: str,
        payload: SelfCheckSubmit,
    ) -> AttemptOut:
        attempt = self._owned_attempt(attempt_id, user_id)
        if attempt.status != "in_progress":
            raise AppError("attempt_completed", "本次练习已经完成", status_code=409)
        definition = self.task_service.get_practice_definition(attempt.task_id, user_id)
        wrong = set(payload.wrong_entry_ids)
        now = datetime.now(UTC)
        elapsed = max(0, int((now - attempt.started_at).total_seconds() * 1000))
        for index, entry in enumerate(definition.entries, start=1):
            is_correct = entry.id not in wrong
            question = self.question_service.create_dictation_question(
                subject=definition.subject,
                word=entry.word,
                phonetic=entry.phonetic,
                meanings=entry.meanings,
                example=entry.example,
                attempt_id=attempt.id,
            )
            answer = PracticeAnswer(
                id=new_id(),
                attempt_id=attempt.id,
                question_id=question.id,
                snapshot_entry_id=entry.id,
                sequence_no=index,
                prompt=entry.word,
                expected=entry.word,
                given="线下自查：正确" if is_correct else "线下自查：错误",
                is_correct=is_correct,
                evaluation_source="self_report",
                answered_at=now,
                duration_ms=elapsed if index == 1 else 0,
            )
            answer.attempt = attempt
            answer = self.repository.add_answer(answer)
            self._record_learning(user_id, entry.source_entry_id, answer.id, is_correct)
        attempt.current_index = len(definition.entries)
        attempt.total = len(definition.entries)
        attempt.status = "completed"
        attempt.completed_at = now
        attempt.updated_at = now
        self.repository.session.flush()
        self._recalculate_progress(attempt.task_id, user_id)
        return attempt_to_out(attempt)
