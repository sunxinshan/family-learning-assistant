import hashlib
import json
import re
from typing import Any, TypedDict

from app.core.database import Database
from app.core.exceptions import AppError
from app.modules.learning.service import LearningService
from app.modules.practice.repository import PracticeRepository
from app.modules.practice.service import PracticeService
from app.modules.task.repository import TaskRepository
from app.modules.task.schemas import DictationConfig, TaskCreate
from app.modules.task.service import TaskService
from app.modules.vocabulary.repository import VocabularyRepository
from app.modules.vocabulary.service import VocabularyService


class AgentState(TypedDict, total=False):
    user_id: str
    conversation_id: str
    run_id: str
    text: str
    route: str
    response: str
    pending_action: dict[str, Any] | None
    draft_version: int
    config_hash: str | None


def _hash_payload(payload: dict[str, Any]) -> str:
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _parse_selected_ids(text: str, entries: list[Any]) -> list[str]:
    if "所有" in text or "全部" in text:
        return [entry.id for entry in entries]
    tokens = text.replace("，", ",").split()
    indexes: set[int] = set()
    for token in tokens:
        for part in token.split(","):
            if not part:
                continue
            range_match = re.fullmatch(r"(\d+)-(\d+)", part)
            if range_match:
                start, end = int(range_match.group(1)), int(range_match.group(2))
                indexes.update(range(max(1, start), min(len(entries), end) + 1))
            elif part.isdigit() and 1 <= int(part) <= len(entries):
                indexes.add(int(part))
    if indexes:
        return [entry.id for index, entry in enumerate(entries, start=1) if index in indexes]
    return [entry.id for entry in entries]


def _prepare_task_action(state: AgentState, service: "AgentBusinessService") -> AgentState:
    text = state["text"]
    libraries = service.available_libraries(state["user_id"], state["run_id"])
    quoted = re.search(r"[「“\"]([^」”\"]+)[」”\"]", text)
    library = (
        next((item for item in libraries if quoted and quoted.group(1) in item.name), None)
        if quoted
        else None
    ) or (libraries[0] if libraries else None)
    if not library:
        return {**state, "route": "chat", "response": "当前没有可用词库，请先创建或复制词库。"}
    selected_ids = _parse_selected_ids(text, library.entries)
    repeat_count = 2
    repeat_match = re.search(r"朗读\s*(\d+)\s*次", text)
    if repeat_match:
        repeat_count = max(1, min(5, int(repeat_match.group(1))))
    dictation = {
        "mode": "offline" if "线下听写" in text else "online",
        "playbackMode": "auto" if "自动播放" in text else "manual",
        "intervalSeconds": 5,
        "hint": "meaning" if any(word in text for word in ("中文", "释义")) else "phonetic",
        "repeatCount": repeat_count,
    }
    mode = "fixed" if "固定" in text else "long_term"
    draft = {
        "name": quoted.group(1) if quoted and "任务" not in quoted.group(1) else "听写任务",
        "type": "dictation",
        "mode": mode,
        "targetCount": len(selected_ids),
        "libraryId": library.id,
        "selectedEntryIds": selected_ids,
        "wordsPerGroup": min(5, len(selected_ids)),
        "repeatUntilCorrect": "强制" in text,
        "dictation": dictation,
    }
    action = _build_task_action(state["run_id"], draft, library.name)
    return {
        **state,
        "route": "task_create",
        "response": "已整理任务配置，请确认。",
        "pending_action": action,
        "draft_version": 1,
        "config_hash": _hash_payload(action["payload"]),
    }


def _build_task_action(action_id: str, draft: dict[str, Any], library_name: str) -> dict[str, Any]:
    return {
        "id": action_id,
        "operation": "create_task",
        "title": "创建学习任务",
        "description": "请检查任务配置。确认前不会写入任何任务数据。",
        "target": draft["name"],
        "fields": [
            {"label": "学习类型", "value": "听写练习"},
            {"label": "任务模式", "value": "固定任务" if draft["mode"] == "fixed" else "长期任务"},
            {"label": "内容来源", "value": library_name},
            {"label": "已选词条", "value": f"{len(draft['selectedEntryIds'])} 项"},
            {"label": "朗读次数", "value": f"{draft['dictation']['repeatCount']} 次"},
        ],
        "impact": "确认后将保存任务与当前词库内容快照。",
        "confirmLabel": "确认创建",
        "payload": {"taskDraft": draft},
    }


class AgentBusinessService:
    def __init__(self, database: Database) -> None:
        self.database = database

    def available_libraries(self, user_id: str, _: str) -> list[Any]:
        with self.database.session() as session:
            return VocabularyService(VocabularyRepository(session)).list_available(user_id, None)

    def learning_stats_text(self, user_id: str) -> str:
        with self.database.session() as session:
            settings = self.database.settings if hasattr(self.database, "settings") else None
            if settings is None:
                raise RuntimeError("settings not attached to database")
            practice = PracticeService(PracticeRepository(session), session, settings)
            stats = LearningService(practice, settings).stats(user_id)
            return (
                f"已完成练习 {stats.practice_count} 次，"
                f"平均正确率 {stats.average_accuracy}%，"
                f"已掌握 {stats.mastered_count} 个词，"
                f"待复习 {stats.review_count} 个。"
            )

    def execute(self, action: dict[str, Any], user_id: str, role: str = "user") -> str:
        with self.database.session() as session:
            task_service = TaskService(TaskRepository(session), session)
            payload = action.get("payload", {})
            if action["operation"] == "create_task":
                draft = payload["taskDraft"]
                created = task_service.create(
                    user_id,
                    role,
                    TaskCreate.model_validate(
                        {
                            "name": draft["name"],
                            "type": "dictation",
                            "mode": draft["mode"],
                            "libraryId": draft["libraryId"],
                            "selectedEntryIds": draft["selectedEntryIds"],
                            "wordsPerGroup": draft["wordsPerGroup"],
                            "repeatUntilCorrect": draft["repeatUntilCorrect"],
                            "dictation": draft.get("dictation") or DictationConfig().model_dump(),
                        }
                    ),
                )
                return f"任务「{created.name}」已创建。"
            if action["operation"] == "delete_task":
                task_id = payload["taskId"]
                task_service.delete(task_id, user_id)
                return "任务及其练习记录已删除。"
            raise AppError("unsupported_action", "暂不支持该操作")
