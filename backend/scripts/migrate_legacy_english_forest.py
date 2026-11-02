"""Import preserved English Forest data into the new Family Learning schema."""

import os
import unicodedata
from datetime import UTC, datetime
from typing import Any

from pwdlib import PasswordHash
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import Session

from app.core.models import new_id
from app.modules.practice.models import PracticeAnswer, PracticeAttempt
from app.modules.task.models import LearningTask, TaskSnapshot, TaskSnapshotEntry
from app.modules.user.models import User
from app.modules.vocabulary.models import (
    Vocabulary,
    VocabularyLearningState,
    VocabularyTag,
    WordEntry,
)


def utc(value: Any) -> datetime:
    if not isinstance(value, datetime):
        raise ValueError(f"invalid datetime: {value!r}")
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def normalized(value: str) -> str:
    return unicodedata.normalize("NFKC", value or "").strip().casefold()


def main() -> None:
    source_url = os.environ.get("LEGACY_DATABASE_URL")
    target_url = os.environ.get("FLA_DATABASE_URL")
    if not source_url or not target_url:
        raise SystemExit("LEGACY_DATABASE_URL and FLA_DATABASE_URL are required")

    source_engine = create_engine(source_url)
    target_engine = create_engine(target_url)
    source_tables = set(inspect(source_engine).get_table_names())
    required = {
        "legacy_users",
        "legacy_word_libraries",
        "legacy_word_entries",
        "legacy_dictation_tasks",
        "legacy_dictation_task_items",
        "legacy_dictation_task_assignments",
        "legacy_dictation_submissions",
        "legacy_dictation_answer_results",
        "legacy_word_learning_states",
    }
    missing = sorted(required - source_tables)
    if missing:
        raise SystemExit(f"missing legacy tables: {', '.join(missing)}")

    password_hash = PasswordHash.recommended()
    admin_passwords = {"admin": "admin213", "admin1": "admin222"}
    user_map: dict[str, str] = {}
    library_map: dict[str, str] = {}
    entry_map: dict[str, str] = {}
    task_clone_map: dict[tuple[str, str], LearningTask] = {}
    snapshot_item_map: dict[tuple[str, str, str], str] = {}
    attempt_sequence: dict[tuple[str, str], int] = {}

    with source_engine.connect() as source, Session(target_engine) as target:
        if target.scalar(text("SELECT COUNT(*) FROM users")):
            raise SystemExit("target users table is not empty; refusing duplicate import")

        users = (
            source.execute(text("SELECT * FROM legacy_users ORDER BY created_at")).mappings().all()
        )
        used_nicknames: set[str] = set()
        for row in users:
            nickname = str(row["username"] or row["display_name"] or new_id())[:80]
            base = nickname
            suffix = 2
            while nickname in used_nicknames:
                nickname = f"{base[:75]}-{suffix}"
                suffix += 1
            used_nicknames.add(nickname)
            password = (
                password_hash.hash(admin_passwords[nickname])
                if nickname in admin_passwords
                else str(row["password_hash"])
            )
            target.add(
                User(
                    id=str(row["id"]),
                    nickname=nickname,
                    password_hash=password,
                    role="admin" if row["role"] == "admin" else "user",
                    status="active" if row["status"] == "active" else "disabled",
                    last_active_at=None,
                    created_at=utc(row["created_at"]),
                    updated_at=utc(row["updated_at"]),
                )
            )
            user_map[str(row["id"])] = str(row["id"])

        libraries = (
            source.execute(text("SELECT * FROM legacy_word_libraries ORDER BY created_at"))
            .mappings()
            .all()
        )
        entries = (
            source.execute(
                text(
                    "SELECT * FROM legacy_word_entries "
                    "ORDER BY library_id, original_order, created_at"
                )
            )
            .mappings()
            .all()
        )
        entries_by_library: dict[str, list[Any]] = {}
        for row in entries:
            entries_by_library.setdefault(str(row["library_id"]), []).append(row)

        for row in libraries:
            library_id = str(row["id"])
            library = Vocabulary(
                id=library_id,
                owner_user_id=None,
                subject=str(row["subject"] or "english"),
                name=str(row["name"] or "旧版词库")[:150],
                description=str(row["description"] or "")[:1000],
                visibility="public",
                published=True,
                source_vocabulary_id=None,
                created_at=utc(row["created_at"]),
                updated_at=utc(row["updated_at"]),
            )
            library.tags = [
                VocabularyTag(
                    id=new_id(),
                    vocabulary_id=library_id,
                    name="旧版迁移",
                    created_at=utc(row["created_at"]),
                )
            ]
            built_entries = []
            seen: set[str] = set()
            for position, entry_row in enumerate(entries_by_library.get(library_id, [])):
                word = str(entry_row["word"] or "").strip()
                key = normalized(word) or normalized(str(entry_row["normalized_word"] or ""))
                if not word or key in seen:
                    continue
                seen.add(key)
                meaning = str(entry_row["meaning"] or "").strip()
                meanings = [
                    item.strip() for item in meaning.replace("；", ";").split(";") if item.strip()
                ]
                if not meanings:
                    meanings = [word]
                entry_id = str(entry_row["id"])
                built_entries.append(
                    WordEntry(
                        id=entry_id,
                        vocabulary_id=library_id,
                        word=word,
                        normalized_word=key,
                        phonetic=str(entry_row["phonetic"] or "").strip(),
                        part_of_speech="",
                        meanings=meanings,
                        example="",
                        example_translation="",
                        position=position,
                        created_at=utc(entry_row["created_at"]),
                        updated_at=utc(entry_row["updated_at"]),
                    )
                )
                entry_map[entry_id] = entry_id
            library.entries = built_entries
            target.add(library)
            library_map[library_id] = library_id

        target.flush()

        states = source.execute(text("SELECT * FROM legacy_word_learning_states")).mappings().all()
        for row in states:
            user_id = user_map.get(str(row["user_id"]))
            entry_id = entry_map.get(str(row["word_entry_id"]))
            if not user_id or not entry_id:
                continue
            target.add(
                VocabularyLearningState(
                    id=str(row["id"]),
                    user_id=user_id,
                    vocabulary_entry_id=entry_id,
                    status="mastered" if row["status"] == "mastered" else "learning",
                    correct_streak=int(row["consecutive_correct"] or 0),
                    last_answer_id=None,
                    next_review_at=utc(row["next_review_at"]) if row["next_review_at"] else None,
                    updated_at=utc(row["updated_at"]),
                )
            )

        tasks = (
            source.execute(text("SELECT * FROM legacy_dictation_tasks ORDER BY created_at"))
            .mappings()
            .all()
        )
        items = (
            source.execute(
                text(
                    """
                SELECT ti.*, de.content AS dictionary_content, de.meaning AS dictionary_meaning,
                       de.phonetic AS dictionary_phonetic
                FROM legacy_dictation_task_items ti
                LEFT JOIN legacy_dictation_entries de ON de.id = ti.entry_id
                ORDER BY ti.task_id, ti.sequence, ti.created_at
                """
                )
            )
            .mappings()
            .all()
        )
        items_by_task: dict[str, list[Any]] = {}
        for item in items:
            items_by_task.setdefault(str(item["task_id"]), []).append(item)
        assignments = (
            source.execute(text("SELECT task_id, child_id FROM legacy_dictation_task_assignments"))
            .mappings()
            .all()
        )
        assigned_users: dict[str, list[str]] = {}
        for row in assignments:
            if str(row["child_id"]) in user_map:
                assigned_users.setdefault(str(row["task_id"]), []).append(str(row["child_id"]))
        submissions = (
            source.execute(
                text("SELECT * FROM legacy_dictation_submissions ORDER BY submitted_at, created_at")
            )
            .mappings()
            .all()
        )
        submission_users: dict[str, set[str]] = {}
        for row in submissions:
            if str(row["user_id"]) in user_map:
                submission_users.setdefault(str(row["task_id"]), set()).add(str(row["user_id"]))

        students = [
            user_id
            for user_id, mapped_id in user_map.items()
            if target.get(User, mapped_id).role == "user"
        ]

        def clone_task(task_row: Any, user_id: str) -> LearningTask:
            key = (str(task_row["id"]), user_id)
            if key in task_clone_map:
                return task_clone_map[key]
            task_items = items_by_task.get(str(task_row["id"]), [])
            count = len(task_items)
            config = task_row["config"] or {}
            if isinstance(config, str):
                import json

                try:
                    config = json.loads(config)
                except ValueError:
                    config = {}
            interval = max(2, min(int(config.get("interval_seconds") or 5), 60))
            repeat = max(1, min(int(config.get("repeat_times") or 1), 5))
            first_library = next(
                (
                    str(item["source_library_id"])
                    for item in task_items
                    if item["source_library_id"]
                ),
                str(task_row["id"]),
            )
            task = LearningTask(
                id=new_id(),
                user_id=user_id,
                name=str(task_row["title"] or "旧版听写任务")[:180],
                subject=str(task_row["subject"] or "english"),
                task_type="dictation",
                task_mode="fixed",
                status="in_progress",
                progress=0,
                target_count=count,
                library_source_id=first_library,
                config_json={
                    "library_name": "旧版听写任务",
                    "words_per_group": count,
                    "total_groups": 1,
                    "repeat_until_correct": False,
                    "dictation": {
                        "mode": "online",
                        "playbackMode": "auto" if config.get("interval_seconds") else "manual",
                        "intervalSeconds": interval,
                        "hint": "phonetic",
                        "repeatCount": repeat,
                    },
                },
                created_at=utc(task_row["created_at"]),
                updated_at=utc(task_row["updated_at"]),
            )
            snapshot = TaskSnapshot(
                id=new_id(),
                task_id=task.id,
                source_library_id=first_library,
            )
            snapshot.entries = []
            for sequence, item in enumerate(task_items, start=1):
                answer = str(item["answer_snapshot"] or item["dictionary_content"] or "").strip()
                prompt = str(item["prompt_snapshot"] or "").strip()
                if not answer:
                    continue
                if task.subject == "chinese":
                    meanings = [answer]
                    phonetic = prompt or str(item["dictionary_phonetic"] or "")
                else:
                    meanings = [prompt] if prompt else []
                    if not meanings:
                        meaning = str(item["dictionary_meaning"] or "").strip()
                        meanings = [meaning] if meaning else [answer]
                    phonetic = str(item["dictionary_phonetic"] or "")
                snapshot_entry = TaskSnapshotEntry(
                    id=new_id(),
                    snapshot_id=snapshot.id,
                    source_entry_id=None,
                    sequence_no=sequence,
                    word=answer,
                    normalized_word=normalized(answer),
                    phonetic=phonetic,
                    part_of_speech="",
                    meanings=meanings,
                    example="",
                    example_translation="",
                )
                snapshot.entries.append(snapshot_entry)
                snapshot_item_map[(str(task_row["id"]), user_id, str(item["id"]))] = (
                    snapshot_entry.id
                )
            task.snapshot = snapshot
            target.add(task)
            target.flush()
            task_clone_map[key] = task
            return task

        for task_row in tasks:
            targets = set(assigned_users.get(str(task_row["id"]), []))
            targets.update(submission_users.get(str(task_row["id"]), set()))
            if task_row["target_user_id"]:
                targets.add(str(task_row["target_user_id"]))
            if str(task_row["audience"] or "") == "public":
                targets.update(students)
            for user_id in sorted(item for item in targets if item in user_map):
                clone_task(task_row, user_id)

        results = (
            source.execute(
                text(
                    "SELECT * FROM legacy_dictation_answer_results "
                    "ORDER BY submission_id, created_at"
                )
            )
            .mappings()
            .all()
        )
        results_by_submission: dict[str, list[Any]] = {}
        for row in results:
            results_by_submission.setdefault(str(row["submission_id"]), []).append(row)
        submissions_by_task_user: dict[tuple[str, str], list[Any]] = {}
        for row in submissions:
            task_id = str(row["task_id"])
            user_id = str(row["user_id"])
            if task_id in {str(task["id"]) for task in tasks} and user_id in user_map:
                submissions_by_task_user.setdefault((task_id, user_id), []).append(row)

        for (task_id, user_id), user_submissions in submissions_by_task_user.items():
            task_row = next(row for row in tasks if str(row["id"]) == task_id)
            task = clone_task(task_row, user_id)
            for submission in sorted(
                user_submissions, key=lambda row: (row["submission_no"], row["created_at"])
            ):
                sequence_key = (task_id, user_id)
                attempt_sequence[sequence_key] = attempt_sequence.get(sequence_key, 0) + 1
                answer_rows = results_by_submission.get(str(submission["id"]), [])
                attempt = PracticeAttempt(
                    id=str(submission["id"]),
                    task_id=task.id,
                    user_id=user_id,
                    task_type="dictation",
                    attempt_no=attempt_sequence[sequence_key],
                    kind="regular",
                    target_entry_ids=[],
                    status="completed",
                    current_index=len(answer_rows),
                    total=len(answer_rows),
                    started_at=utc(submission["submitted_at"] or submission["created_at"]),
                    completed_at=utc(submission["completed_at"] or submission["updated_at"]),
                    updated_at=utc(submission["updated_at"]),
                )
                for sequence, result in enumerate(answer_rows, start=1):
                    item = next(
                        (
                            row
                            for row in items_by_task[task_id]
                            if str(row["id"]) == str(result["task_item_id"])
                        ),
                        None,
                    )
                    snapshot_entry_id = snapshot_item_map.get(
                        (task_id, user_id, str(result["task_item_id"]))
                    )
                    if not item or not snapshot_entry_id:
                        continue
                    word = str(item["answer_snapshot"] or item["dictionary_content"] or "")
                    attempt.answers.append(
                        PracticeAnswer(
                            id=str(result["id"]),
                            attempt_id=attempt.id,
                            question_id=None,
                            snapshot_entry_id=snapshot_entry_id,
                            sequence_no=sequence,
                            prompt=word,
                            expected=word,
                            given=str(result["recognized_text"] or ""),
                            is_correct=str(result["final_result"]) == "correct",
                            evaluation_source="auto",
                            answered_at=utc(result["created_at"]),
                            duration_ms=0,
                        )
                    )
                target.add(attempt)

        target.flush()
        for task in task_clone_map.values():
            attempted = {
                answer.snapshot_entry_id
                for attempt in target.query(PracticeAttempt).filter(
                    PracticeAttempt.task_id == task.id
                )
                for answer in attempt.answers
            }
            task.progress = round(len(attempted) / max(task.target_count, 1) * 100)
            task.status = "completed" if task.progress >= 100 else "in_progress"

        target.commit()

    print(
        {
            "users": len(user_map),
            "libraries": len(library_map),
            "entries": len(entry_map),
            "tasks": len(task_clone_map),
            "submissions": len(submissions),
            "answers": len(results),
        }
    )
    source_engine.dispose()
    target_engine.dispose()


if __name__ == "__main__":
    main()
