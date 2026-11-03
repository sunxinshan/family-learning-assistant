from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.exceptions import AppError
from app.core.models import new_id
from app.modules.practice.models import PracticeAnswer, PracticeAttempt
from app.modules.practice.repository import PracticeRepository
from app.modules.practice.schemas import (
    AnswerOut,
    AnswerSubmit,
    AttemptOut,
    SelfCheckSubmit,
    WrongQuestionGroupOut,
    WrongQuestionOut,
    WrongQuestionsOut,
)
from app.modules.question.repository import QuestionRepository
from app.modules.question.service import QuestionService
from app.modules.task.repository import TaskRepository
from app.modules.task.service import PracticeEntry, TaskPracticeDefinition, TaskService
from app.modules.vocabulary.repository import VocabularyRepository
from app.modules.vocabulary.service import VocabularyService

WRONG_QUESTION_CORRECT_STREAK = 2
# 开启「答对后才能进入下一组」时，错词要连续两轮都拼对才算过关。
GROUP_REQUIRED_CORRECT_STREAK = 2


@dataclass
class WrongQuestionState:
    active: bool = False
    consecutive_correct: int = 0
    last_wrong_at: datetime | None = None


def answer_to_out(answer: PracticeAnswer) -> AnswerOut:
    return AnswerOut(
        id=answer.id,
        question_id=answer.question_id,
        snapshot_entry_id=answer.snapshot_entry_id,
        prompt=answer.prompt,
        expected=answer.expected,
        given=answer.given,
        correct=answer.is_correct,
        evaluation_source=answer.evaluation_source,
        answered_at=answer.answered_at,
        duration_ms=answer.duration_ms,
    )


def attempt_to_out(attempt: PracticeAttempt) -> AttemptOut:
    # 同一个词在强制答对模式下会被重复作答，正确数要按词去重，否则会出现 3/2。
    correct_entry_ids = {answer.snapshot_entry_id for answer in attempt.answers if answer.is_correct}
    return AttemptOut(
        id=attempt.id,
        task_id=attempt.task_id,
        user_id=attempt.user_id,
        task_type=attempt.task_type,
        kind=attempt.kind,
        target_entry_ids=list(attempt.target_entry_ids or []),
        status=attempt.status,
        current_index=attempt.current_index,
        round_no=attempt.round_no or 1,
        answers=[answer_to_out(answer) for answer in attempt.answers],
        started_at=attempt.started_at,
        updated_at=attempt.updated_at,
        completed_at=attempt.completed_at,
        score=len(correct_entry_ids),
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
        active = self.repository.get_active(task_id, user_id, kind="regular")
        if active:
            return attempt_to_out(self._ensure_round_queue(active))
        definition = self.task_service.get_practice_definition(task_id, user_id)
        now = datetime.now(UTC)
        # 强制答对模式按组推进：先取第一组，本组练到没有错词才换下一组。
        queue = (
            self.task_service.list_group_entry_ids(task_id, 1, definition.words_per_group)
            if definition.repeat_until_correct
            else []
        )
        attempt = PracticeAttempt(
            id=new_id(),
            task_id=task_id,
            user_id=user_id,
            task_type=definition.type,
            attempt_no=self.repository.next_attempt_no(task_id, user_id),
            kind="regular",
            target_entry_ids=queue,
            round_no=1,
            status="in_progress",
            current_index=0,
            total=definition.target_count,
            started_at=now,
            updated_at=now,
        )
        return attempt_to_out(self.repository.add_attempt(attempt))

    def start_or_resume_wrong(self, task_id: str, user_id: str) -> AttemptOut:
        active = self.repository.get_active(task_id, user_id, kind="wrong")
        if active:
            return attempt_to_out(active)
        wrong_questions = self.get_wrong_questions(task_id, user_id)
        target_ids = [
            entry.snapshot_entry_id for group in wrong_questions.groups for entry in group.entries
        ]
        if not target_ids:
            raise AppError("no_wrong_questions", "当前任务没有待复习错题", status_code=409)
        definition = self.task_service.get_practice_definition(task_id, user_id)
        now = datetime.now(UTC)
        attempt = PracticeAttempt(
            id=new_id(),
            task_id=task_id,
            user_id=user_id,
            task_type=definition.type,
            attempt_no=self.repository.next_attempt_no(task_id, user_id),
            kind="wrong",
            target_entry_ids=target_ids,
            status="in_progress",
            current_index=0,
            total=len(target_ids),
            started_at=now,
            updated_at=now,
        )
        return attempt_to_out(self.repository.add_attempt(attempt))

    def get(self, attempt_id: str, user_id: str) -> AttemptOut:
        return attempt_to_out(self._owned_attempt(attempt_id, user_id))

    def get_active(self, task_id: str, user_id: str, kind: str = "regular") -> AttemptOut | None:
        self.task_service.get(task_id, user_id)
        attempt = self.repository.get_active(task_id, user_id, kind=kind)
        return None if attempt is None else attempt_to_out(attempt)

    def list(self, user_id: str) -> list[AttemptOut]:
        return [attempt_to_out(item) for item in self.repository.list_for_user(user_id)]

    def get_wrong_questions(self, task_id: str, user_id: str) -> WrongQuestionsOut:
        definition = self.task_service.get_practice_definition(task_id, user_id)
        states: dict[str, WrongQuestionState] = {}
        for answer in self.repository.answers_for_task(task_id, user_id):
            state = states.setdefault(answer.snapshot_entry_id, WrongQuestionState())
            if answer.is_correct:
                if state.active:
                    state.consecutive_correct += 1
                    if state.consecutive_correct >= WRONG_QUESTION_CORRECT_STREAK:
                        state.active = False
                        state.consecutive_correct = 0
            else:
                state.active = True
                state.consecutive_correct = 0
                state.last_wrong_at = answer.answered_at

        grouped: dict[int, list[WrongQuestionOut]] = {}
        for entry in definition.entries:
            state = states.get(entry.id)
            if not state or not state.active or state.last_wrong_at is None:
                continue
            group_index = (
                1
                if definition.mode == "fixed"
                else (entry.sequence_no - 1) // max(definition.words_per_group, 1) + 1
            )
            grouped.setdefault(group_index, []).append(
                WrongQuestionOut(
                    snapshot_entry_id=entry.id,
                    word=entry.word,
                    phonetic=entry.phonetic,
                    meanings=entry.meanings,
                    example=entry.example,
                    example_translation=entry.example_translation,
                    consecutive_correct=state.consecutive_correct,
                    last_wrong_at=state.last_wrong_at,
                    group_index=group_index,
                )
            )

        groups = [
            WrongQuestionGroupOut(group_index=group_index, entries=entries)
            for group_index, entries in sorted(grouped.items())
        ]
        return WrongQuestionsOut(
            task_id=task_id,
            total=sum(len(group.entries) for group in groups),
            required_correct_streak=WRONG_QUESTION_CORRECT_STREAK,
            groups=groups,
        )

    def _attempt_entries(
        self, attempt: PracticeAttempt, definition: TaskPracticeDefinition
    ) -> list[PracticeEntry]:
        if attempt.kind != "wrong":
            return definition.entries
        target_ids = list(attempt.target_entry_ids or [])
        by_id = {entry.id: entry for entry in definition.entries}
        return [by_id[entry_id] for entry_id in target_ids if entry_id in by_id]

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

    def _recalculate_progress(self, task, user_id: str) -> None:
        if task.task_mode == "fixed" and not self._repeat_mode(task):
            attempted = self.repository.count_attempted_entries(task.id, user_id)
            progress = round(attempted / max(task.target_count, 1) * 100)
        else:
            answers = self.repository.answers_for_task(task.id, user_id)
            streaks: dict[str, int] = {}
            wrong_seen: set[str] = set()
            for answer in answers:
                if answer.is_correct:
                    streaks[answer.snapshot_entry_id] = streaks.get(answer.snapshot_entry_id, 0) + 1
                else:
                    streaks[answer.snapshot_entry_id] = 0
                    wrong_seen.add(answer.snapshot_entry_id)
            # 强制答对模式：拼错过的词要连对两次才算过关，没错过的词答对一次就过。
            repeat = self._repeat_mode(task)
            required = GROUP_REQUIRED_CORRECT_STREAK if repeat else self.settings.mastery_threshold
            if repeat:
                mastered = sum(
                    1
                    for entry_id, value in streaks.items()
                    if value >= 1 and (entry_id not in wrong_seen or value >= required)
                )
            else:
                mastered = sum(1 for value in streaks.values() if value >= required)
            progress = round(mastered / max(task.target_count, 1) * 100)
        self.task_service.set_progress(task, progress)

    @staticmethod
    def _repeat_mode(task) -> bool:
        return bool(task.config_json.get("repeat_until_correct"))

    @staticmethod
    def _entry_answers(attempt: PracticeAttempt, entry_id: str) -> list[PracticeAnswer]:
        return [answer for answer in attempt.answers if answer.snapshot_entry_id == entry_id]

    def _correct_streak(self, attempt: PracticeAttempt, entry_id: str) -> int:
        """这个词自己最近连续拼对了几次。

        轮次制下一轮只答一次，所以「连对两次」就意味着连续两轮都拼对。
        """
        streak = 0
        for previous in reversed(self._entry_answers(attempt, entry_id)):
            if not previous.is_correct:
                break
            streak += 1
        return streak

    def _needs_more_practice(self, attempt: PracticeAttempt, entry_id: str) -> bool:
        """拼错过的词要再连续拼对两次才算过关；一次都没错的词走过一轮就过。"""
        answers = self._entry_answers(attempt, entry_id)
        if not answers:
            return True
        if not any(not answer.is_correct for answer in answers):
            return False
        return self._correct_streak(attempt, entry_id) < GROUP_REQUIRED_CORRECT_STREAK

    def _ensure_round_queue(self, attempt: PracticeAttempt) -> PracticeAttempt:
        """兼容旧版本创建、还没有轮次队列的进行中练习。"""
        if attempt.kind != "regular" or attempt.target_entry_ids:
            return attempt
        task = self.task_service.get_practice_metadata(attempt.task_id, attempt.user_id)
        if not self._repeat_mode(task):
            return attempt
        words_per_group = max(int(task.config_json.get("words_per_group") or 1), 1)
        group_index = attempt.current_index // words_per_group + 1
        ids = self.task_service.list_group_entry_ids(task.id, group_index, words_per_group)
        if not ids:
            return attempt
        pending = [entry_id for entry_id in ids if self._needs_more_practice(attempt, entry_id)]
        attempt.target_entry_ids = pending or ids
        attempt.current_index = 0
        attempt.round_no = 1
        self.repository.session.flush()
        return attempt

    def _close_round(
        self,
        attempt: PracticeAttempt,
        task,
        queue: list[str],
        last_sequence_no: int,
        now: datetime,
    ) -> None:
        """一轮走完后收尾：本组还有错词就再来一轮，全过关就换下一组。"""
        pending = [
            entry_id for entry_id in queue if self._needs_more_practice(attempt, entry_id)
        ]
        if pending:
            attempt.target_entry_ids = pending
            attempt.current_index = 0
            attempt.round_no = (attempt.round_no or 1) + 1
            return
        words_per_group = max(int(task.config_json.get("words_per_group") or 1), 1)
        total_groups = max(int(task.config_json.get("total_groups") or 1), 1)
        group_index = (max(last_sequence_no, 1) - 1) // words_per_group + 1
        next_group = group_index + 1
        next_ids = (
            self.task_service.list_group_entry_ids(task.id, next_group, words_per_group)
            if next_group <= total_groups
            else []
        )
        if not next_ids:
            attempt.target_entry_ids = []
            attempt.current_index = attempt.total
            attempt.status = "completed"
            attempt.completed_at = now
            return
        attempt.target_entry_ids = next_ids
        attempt.current_index = 0
        attempt.round_no = 1

    def submit_answer(self, attempt_id: str, user_id: str, payload: AnswerSubmit) -> AttemptOut:
        attempt = self._owned_attempt(attempt_id, user_id)
        if attempt.status != "in_progress":
            raise AppError("attempt_completed", "本次练习已经完成", status_code=409)
        task = self.task_service.get_practice_metadata(attempt.task_id, user_id)
        repeat_mode = self._repeat_mode(task) and attempt.kind != "wrong"
        queue = list(attempt.target_entry_ids or []) if (repeat_mode or attempt.kind == "wrong") else []
        if queue:
            if attempt.current_index >= len(queue):
                raise AppError("attempt_completed", "本次练习已经完成", status_code=409)
            entry = self.task_service.get_practice_entry(
                task.id, entry_id=queue[attempt.current_index]
            )
        else:
            if attempt.current_index >= attempt.total:
                raise AppError("attempt_completed", "本次练习已经完成", status_code=409)
            entry = self.task_service.get_practice_entry(
                task.id, sequence_no=attempt.current_index + 1
            )
        question = self.question_service.create_dictation_question(
            subject=task.subject,
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
            # 同一个词允许重复作答，序号按「第几次作答」递增，满足 (attempt_id, sequence_no) 唯一约束。
            sequence_no=len(attempt.answers) + 1,
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
        attempt.updated_at = now
        if not queue:
            # 普通任务：按快照顺序线性推进，答错也进入下一个词。
            attempt.current_index += 1
            if attempt.current_index >= attempt.total:
                attempt.status = "completed"
                attempt.completed_at = now
        elif attempt.kind == "wrong":
            # 错题复习：每次把错题过一遍，连着两次复习都对就移出错题池。
            attempt.current_index += 1
            if attempt.current_index >= len(queue):
                attempt.status = "completed"
                attempt.completed_at = now
        else:
            # 强制答对：本组这一轮走完再决定是重练错词还是换组。
            attempt.current_index += 1
            if attempt.current_index >= len(queue):
                self._close_round(attempt, task, queue, entry.sequence_no, now)
        self.repository.session.flush()
        self._recalculate_progress(task, user_id)
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
        if definition.dictation_mode != "offline":
            raise AppError("self_check_not_allowed", "线上听写请直接提交答案", status_code=409)
        entries = self._attempt_entries(attempt, definition)
        wrong = set(payload.wrong_entry_ids)
        known_ids = {entry.id for entry in entries}
        if not wrong.issubset(known_ids):
            raise AppError("invalid_wrong_entries", "自查词条不属于当前任务", status_code=422)
        now = datetime.now(UTC)
        elapsed = max(0, int((now - attempt.started_at).total_seconds() * 1000))
        for index, entry in enumerate(entries, start=1):
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
        attempt.current_index = len(entries)
        attempt.total = len(entries)
        attempt.status = "completed"
        attempt.completed_at = now
        attempt.updated_at = now
        self.repository.session.flush()
        task = self.task_service.get_practice_metadata(attempt.task_id, user_id)
        self._recalculate_progress(task, user_id)
        return attempt_to_out(attempt)
