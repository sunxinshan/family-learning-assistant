import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, TypedDict

from app.core.database import Database
from app.core.exceptions import AppError
from app.core.models import new_id
from app.modules.agent.llm import create_llm_adapter
from app.modules.agent.tool_schemas import TaskCreatePreviewArgs
from app.modules.content.repository import ContentRepository
from app.modules.content.schemas import ContentExtractionUpdate
from app.modules.content.service import ContentService
from app.modules.learning.service import LearningService
from app.modules.material.repository import MaterialRepository
from app.modules.material.service import MaterialService
from app.modules.practice.repository import PracticeRepository
from app.modules.practice.service import PracticeService
from app.modules.task.repository import TaskRepository
from app.modules.task.schemas import TaskCreate, TaskUpdate
from app.modules.task.service import TaskService
from app.modules.vocabulary.repository import VocabularyRepository
from app.modules.vocabulary.schemas import VocabularyCreate
from app.modules.vocabulary.service import VocabularyService


@dataclass(frozen=True)
class AgentActionResult:
    message: str
    links: list[dict[str, str]]


class AgentState(TypedDict, total=False):
    user_id: str
    role: str
    conversation_id: str
    run_id: str
    text: str
    material_id: str | None
    route: str
    response: str
    pending_action: dict[str, Any] | None
    draft_version: int
    config_hash: str | None
    token_usage: dict[str, int] | None
    links: list[dict[str, str]] | None
    tool_trace: list[dict[str, Any]] | None
    history: list[dict[str, str]] | None


def _hash_payload(payload: dict[str, Any]) -> str:
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _quoted(text: str) -> str | None:
    match = re.search(r"[「“\"]([^」”\"]+)[」”\"]", text)
    return match.group(1).strip() if match else None


def _parse_selected_ids(text: str, entries: list[Any]) -> list[str]:
    if "所有" in text or "全部" in text:
        return [entry.id for entry in entries]
    prefix_match = re.search(r"前\s*(\d+)\s*(?:个|项|词|单词)?", text)
    if prefix_match:
        count = max(0, min(len(entries), int(prefix_match.group(1))))
        return [entry.id for entry in entries[:count]]
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
    return []


def _decorate_action(action: dict[str, Any]) -> dict[str, Any]:
    digest = _hash_payload(action.get("payload", {}))
    action["draft_version"] = 1
    action["draftVersion"] = 1
    action["config_hash"] = digest
    action["configHash"] = digest
    return action


def _prepare_task_action(state: AgentState, service: "AgentBusinessService") -> AgentState:
    text = state["text"]
    libraries = service.available_libraries(state["user_id"])
    quoted = _quoted(text)
    library = (
        next((item for item in libraries if quoted and quoted in item.name), None)
        if quoted
        else None
    ) or (libraries[0] if libraries else None)
    if not library:
        return {
            **state,
            "route": "chat",
            "response": "当前没有可用词库，请先创建词库或复制已发布的公共词库。",
        }
    selected_ids = _parse_selected_ids(text, library.entries)
    repeat_count = 2
    repeat_match = re.search(r"朗读\s*(\d+)\s*次", text)
    if repeat_match:
        repeat_count = max(1, min(5, int(repeat_match.group(1))))
    interval = 8
    interval_match = re.search(r"间隔\s*(\d+)\s*秒", text)
    if interval_match:
        interval = max(2, min(60, int(interval_match.group(1))))
    dictation = {
        "mode": "offline" if "线下听写" in text else "online",
        "playbackMode": "auto" if "自动播放" in text else "manual",
        "intervalSeconds": interval,
        "hint": "meaning" if any(word in text for word in ("中文", "释义")) else "phonetic",
        "repeatCount": repeat_count,
    }
    mode = "long_term" if "长期" in text else "fixed"
    draft = {
        "name": (
            quoted
            if quoted and "任务" not in quoted and quoted not in library.name
            else f"{library.name} · 听写"
        ),
        "type": "dictation",
        "mode": mode,
        "targetCount": len(selected_ids),
        "libraryId": library.id,
        "selectedEntryIds": selected_ids,
        "wordsPerGroup": min(5, len(selected_ids)),
        "repeatUntilCorrect": "强制" in text,
        "dictation": dictation,
    }
    action = _decorate_action(_build_task_create_action(state["run_id"], draft, library.name))
    return {
        **state,
        "route": "task_create",
        "response": "已整理任务配置，请检查后确认。确认前不会写入任何任务数据。",
        "pending_action": action,
        "draft_version": 1,
        "config_hash": action["config_hash"],
    }


def _build_task_create_action(
    action_id: str, draft: dict[str, Any], library_name: str
) -> dict[str, Any]:
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
        "impact": "确认后将保存任务与当前词库内容快照。后续修改原词库不会影响该任务。",
        "confirmLabel": "确认创建",
        "payload": {"taskDraft": draft},
    }


def _update_changes_from_text(
    text: str, task: Any, current_config: dict[str, Any]
) -> dict[str, Any]:
    config = dict(current_config)
    group_match = re.search(r"(?:每组|每天)\s*(\d+)\s*个", text)
    if group_match:
        config["wordsPerGroup"] = max(1, int(group_match.group(1)))
        config["totalGroups"] = (task.target_count + config["wordsPerGroup"] - 1) // config[
            "wordsPerGroup"
        ]
    if "自动播放" in text:
        dictation = dict(config["dictation"])
        dictation["playbackMode"] = "auto"
        interval_match = re.search(r"间隔\s*(\d+)\s*秒", text)
        if interval_match:
            dictation["intervalSeconds"] = max(2, min(60, int(interval_match.group(1))))
        config["dictation"] = dictation
    if "手动播放" in text:
        dictation = dict(config["dictation"])
        dictation["playbackMode"] = "manual"
        config["dictation"] = dictation
    if "线下听写" in text:
        dictation = dict(config["dictation"])
        dictation["mode"] = "offline"
        config["dictation"] = dictation
    if "线上听写" in text:
        dictation = dict(config["dictation"])
        dictation["mode"] = "online"
        config["dictation"] = dictation
    repeat_match = re.search(r"朗读\s*(\d+)\s*次", text)
    if repeat_match:
        dictation = dict(config["dictation"])
        dictation["repeatCount"] = max(1, min(5, int(repeat_match.group(1))))
        config["dictation"] = dictation
    if any(word in text for word in ("中文", "释义")):
        dictation = dict(config["dictation"])
        dictation["hint"] = "meaning"
        config["dictation"] = dictation
    if "音标" in text:
        dictation = dict(config["dictation"])
        dictation["hint"] = "phonetic"
        config["dictation"] = dictation
    if "强制答对" in text or "必须答对" in text:
        config["repeatUntilCorrect"] = True
    renamed = re.search(r"改名为[「“\"]([^」”\"]+)[」”\"]", text)
    requested_mode = task.mode
    if "长期任务" in text or "长周期" in text:
        requested_mode = "long_term"
    elif "固定任务" in text:
        requested_mode = "fixed"
    return {
        "name": renamed.group(1) if renamed else task.name,
        "config": config,
        "targetCount": task.target_count,
        "mode": requested_mode,
    }


def _build_task_update_action(task: Any, changes: dict[str, Any]) -> dict[str, Any]:
    before_config = task.config.model_dump(by_alias=True)
    after_config = changes["config"]
    return {
        "id": "",
        "operation": "update_task",
        "title": "修改学习任务",
        "description": "以下为本次修改的前后差异，确认后才会更新任务。",
        "target": task.name,
        "fields": [{"label": "内容来源", "value": task.library_name}],
        "diff": [
            {
                "label": "任务名称",
                "before": task.name,
                "after": changes["name"],
            },
            {
                "label": "每组数量",
                "before": str(before_config["wordsPerGroup"]),
                "after": str(after_config["wordsPerGroup"]),
            },
            {
                "label": "播放方式",
                "before": before_config["dictation"]["playbackMode"],
                "after": after_config["dictation"]["playbackMode"],
            },
            {
                "label": "朗读次数",
                "before": str(before_config["dictation"]["repeatCount"]),
                "after": str(after_config["dictation"]["repeatCount"]),
            },
        ],
        "impact": "任务内容快照保持不变，修改后的配置将在后续练习中生效。",
        "confirmLabel": "确认修改",
        "payload": {"taskId": task.id, "changes": changes},
    }


def _build_delete_action(task: Any, stage: int) -> dict[str, Any]:
    return {
        "id": "",
        "operation": "delete_task",
        "title": "删除学习任务" if stage == 1 else "再次确认删除",
        "description": (
            "这是第一次确认。删除任务会同时移除其历史练习记录。"
            if stage == 1
            else "此操作不可撤销。请再次确认永久删除该任务及其练习记录。"
        ),
        "target": task.name,
        "fields": [
            {"label": "任务状态", "value": "已完成" if task.status == "completed" else "进行中"},
            {"label": "学习进度", "value": f"{task.progress}%"},
            {"label": "内容来源", "value": task.library_name},
        ],
        "impact": "任务、练习 Attempt、答题记录和由此产生的错题记录将被一并删除。",
        "confirmLabel": "继续删除" if stage == 1 else "永久删除",
        "danger": True,
        "stage": stage,
        "payload": {"taskId": task.id},
    }


def _parse_tags(text: str) -> list[str]:
    match = re.search(r"标签\s*[:：]?\s*([^\n。]+)", text)
    if not match:
        return []
    return [
        item.strip()
        for item in re.split(r"[,，、]", match.group(1))
        if item.strip() and not item.strip().startswith(("并", "然后", "创建"))
    ]


def _resolve_selection(args: "TaskCreatePreviewArgs", entry_ids: list[str]) -> list[str]:
    if args.selection_mode == "all":
        return list(entry_ids)
    if args.selection_mode == "prefix":
        if not args.prefix_count:
            raise AppError("invalid_arguments", "请指定要选择的词条数量", status_code=422)
        return entry_ids[: args.prefix_count]
    if args.selection_mode == "range":
        start = args.range_start or 1
        end = args.range_end or len(entry_ids)
        if start > end:
            raise AppError("invalid_arguments", "词条区间起始值不能大于结束值", status_code=422)
        return entry_ids[max(start - 1, 0) : min(end, len(entry_ids))]
    if args.selection_mode == "ids":
        allowed = set(entry_ids)
        unknown = [entry_id for entry_id in args.entry_ids if entry_id not in allowed]
        if unknown:
            raise AppError("invalid_entry_selection", "部分词条不属于该词库", status_code=422)
        return list(dict.fromkeys(args.entry_ids))
    return []


class AgentBusinessService:
    def __init__(self, database: Database) -> None:
        self.database = database

    def available_libraries(self, user_id: str) -> list[Any]:
        with self.database.session() as session:
            return VocabularyService(VocabularyRepository(session)).list_available(user_id, None)

    def available_tasks(self, user_id: str) -> list[Any]:
        with self.database.session() as session:
            return TaskService(TaskRepository(session), session).list(user_id)

    def build_task_create_preview(
        self, user_id: str, role: str, run_id: str, args: TaskCreatePreviewArgs
    ) -> dict[str, Any]:
        """按结构化参数生成任务创建预览。

        只做确定性的选择解析、范围校验和默认值补齐，不读取用户原始文本。
        """
        with self.database.session() as session:
            library = VocabularyService(VocabularyRepository(session)).get_accessible(
                args.library_id, user_id, role
            )
        entry_ids = [entry.id for entry in library.entries]
        if not entry_ids:
            raise AppError("empty_library", "该词库还没有词条", status_code=422)
        selected_ids = _resolve_selection(args, entry_ids)
        if not selected_ids:
            raise AppError("no_entries_selected", "请至少选择一个词条", status_code=422)
        count = len(selected_ids)
        words_per_group = (
            count
            if args.task_mode == "fixed"
            else min(max(args.words_per_group or min(5, count), 1), count)
        )
        draft = {
            "name": args.name,
            "type": "dictation",
            "mode": args.task_mode,
            "targetCount": count,
            "libraryId": library.id,
            "selectedEntryIds": selected_ids,
            "wordsPerGroup": words_per_group,
            "repeatUntilCorrect": args.repeat_until_correct,
            "dictation": {
                "mode": args.dictation_mode,
                "playbackMode": args.playback_mode,
                "intervalSeconds": args.interval_seconds if args.playback_mode == "auto" else 8,
                "hint": "phonetic" if library.subject == "chinese" else args.hint,
                "repeatCount": args.repeat_count,
                "speechEnabled": args.speech_enabled,
            },
        }
        action = _build_task_create_action(run_id, draft, library.name)
        return _decorate_action(action)

    def _find_task(self, user_id: str, text: str) -> Any:
        tasks = self.available_tasks(user_id)
        quoted = _quoted(text)
        task = next((item for item in tasks if quoted and quoted in item.name), None)
        return (
            task
            or next((item for item in tasks if item.status == "in_progress"), None)
            or (tasks[0] if tasks else None)
        )

    def prepare_task_update(self, state: AgentState) -> AgentState:
        with self.database.session() as session:
            task_service = TaskService(TaskRepository(session), session)
            tasks = task_service.list(state["user_id"])
            quoted = _quoted(state["text"])
            task = next((item for item in tasks if quoted and quoted in item.name), None)
            task = (
                task
                or next((item for item in tasks if item.status == "in_progress"), None)
                or (tasks[0] if tasks else None)
            )
            if not task:
                return {
                    **state,
                    "route": "chat",
                    "response": "没有找到可以修改的任务。",
                }
            changes = _update_changes_from_text(
                state["text"], task, task.config.model_dump(by_alias=True)
            )
            action = _build_task_update_action(task, changes)
            action["id"] = state["run_id"]
            _decorate_action(action)
            return {
                **state,
                "route": "task_update",
                "response": "已生成任务修改预览，请检查后确认。",
                "pending_action": action,
                "draft_version": 1,
                "config_hash": action["config_hash"],
            }

    def prepare_task_delete(self, state: AgentState) -> AgentState:
        task = self._find_task(state["user_id"], state["text"])
        if not task:
            return {**state, "route": "chat", "response": "没有找到可以删除的任务。"}
        action = _build_delete_action(task, 1)
        action["id"] = state["run_id"]
        _decorate_action(action)
        return {
            **state,
            "route": "task_delete",
            "response": "删除任务需要两阶段确认。请先核对下面的删除影响。",
            "pending_action": action,
            "draft_version": 1,
            "config_hash": action["config_hash"],
        }

    def prepare_vocabulary_create(self, state: AgentState) -> AgentState:
        subject = (
            "chinese" if any(word in state["text"] for word in ("语文", "中文")) else "english"
        )
        name = _quoted(state["text"]) or "我的新词库"
        draft = {
            "subject": subject,
            "name": name,
            "description": "由学习助手创建",
            "tags": _parse_tags(state["text"]),
            "entries": [],
        }
        action = {
            "id": state["run_id"],
            "operation": "create_vocabulary",
            "title": "创建个人词库",
            "description": "可继续编辑学科、名称、描述、标签和词条，确认前不会保存。",
            "target": name,
            "fields": [
                {"label": "学科", "value": "英语" if subject == "english" else "语文"},
                {"label": "词条数量", "value": "0 项"},
                {"label": "保存位置", "value": "我的词库"},
            ],
            "impact": "确认后该词库将只属于当前用户。",
            "confirmLabel": "确认创建词库",
            "payload": {"vocabularyDraft": draft},
        }
        _decorate_action(action)
        return {
            **state,
            "route": "vocabulary_create",
            "response": "已整理词库草稿。请补充词条并确认。",
            "pending_action": action,
            "draft_version": 1,
            "config_hash": action["config_hash"],
        }

    def prepare_vocabulary_import(self, state: AgentState) -> AgentState:
        material_id = state.get("material_id")
        if not material_id:
            return {
                **state,
                "route": "chat",
                "response": "请先上传 .xlsx 或 .csv 文件，我会解析后在对话框中展示可编辑预览。",
            }
        with self.database.session() as session:
            content = ContentService(
                ContentRepository(session),
                MaterialService(MaterialRepository(session), self.database.settings),
                VocabularyService(VocabularyRepository(session)),
                create_llm_adapter(self.database.settings),
            )
            subject = (
                "chinese"
                if any(word in state["text"] for word in ("语文", "中文", "汉字"))
                else "english"
            )
            extraction = content.extract(
                material_id, state["user_id"], state.get("role", "user"), subject
            )
            draft = VocabularyCreate.model_validate(extraction.extracted_json).model_dump(
                by_alias=True
            )
            for entry in draft["entries"]:
                entry["id"] = new_id()
            quoted = _quoted(state["text"])
            if quoted:
                draft["name"] = quoted
            action = {
                "id": state["run_id"],
                "operation": "import_vocabulary",
                "title": "导入词库",
                "description": "解析结果尚未保存。可在确认前编辑全部字段。",
                "target": draft["name"],
                "fields": [
                    {"label": "解析词条", "value": f"{len(draft['entries'])} 项"},
                    {"label": "解析错误", "value": f"{len(extraction.errors_json)} 项"},
                    {
                        "label": "列名识别",
                        "value": ("模型识别" if extraction.mapping_source == "llm" else "规则识别"),
                    },
                    {
                        "label": "自动补充",
                        "value": (
                            f"{extraction.mapping_json.get('enrichment', {}).get('completed', 0)}"
                            " 项"
                        ),
                    },
                    {"label": "保存位置", "value": "我的词库"},
                ],
                "impact": "确认后将生成独立个人词库；原始文件不进入正式业务数据。",
                "confirmLabel": "确认导入",
                "payload": {
                    "vocabularyDraft": draft,
                    "extractionId": extraction.id,
                    "extractionVersion": extraction.version,
                    "fileName": Path(extraction.material_id).name,
                },
            }
            _decorate_action(action)
        return {
            **state,
            "route": "vocabulary_import",
            "response": "文件已解析为可编辑词库草稿，请检查后确认。",
            "pending_action": action,
            "draft_version": 1,
            "config_hash": action["config_hash"],
        }

    def validate_action(self, action: dict[str, Any], user_id: str, role: str = "user") -> None:
        operation = action.get("operation")
        payload = action.get("payload")
        if not isinstance(payload, dict):
            raise AppError("invalid_action", "操作缺少 payload", status_code=422)
        if operation == "create_task":
            draft = payload.get("taskDraft")
            if not isinstance(draft, dict):
                raise AppError("invalid_action", "任务配置缺失", status_code=422)
            task_payload = TaskCreate.model_validate(draft)
            with self.database.session() as session:
                TaskService(TaskRepository(session), session).validate_create(
                    user_id, role, task_payload
                )
            return
        if operation == "update_task":
            changes = payload.get("changes")
            task_id = payload.get("taskId")
            if not isinstance(changes, dict) or not isinstance(task_id, str):
                raise AppError("invalid_action", "任务修改配置缺失", status_code=422)
            config = changes.get("config") or {}
            update = TaskUpdate.model_validate(
                {
                    "name": changes.get("name") or "",
                    "wordsPerGroup": config.get("wordsPerGroup"),
                    "repeatUntilCorrect": config.get("repeatUntilCorrect"),
                    "dictation": config.get("dictation"),
                }
            )
            with self.database.session() as session:
                TaskService(TaskRepository(session), session).validate_update(
                    task_id, user_id, update
                )
            return
        if operation == "delete_task":
            task_id = payload.get("taskId")
            if not isinstance(task_id, str):
                raise AppError("invalid_action", "任务标识缺失", status_code=422)
            with self.database.session() as session:
                TaskService(TaskRepository(session), session).get(task_id, user_id)
            return
        if operation in {"create_vocabulary", "import_vocabulary"}:
            draft = payload.get("vocabularyDraft")
            if not isinstance(draft, dict):
                raise AppError("invalid_action", "词库草稿缺失", status_code=422)
            VocabularyCreate.model_validate(draft)
            if operation == "import_vocabulary" and payload.get("extractionId"):
                extraction_id = payload["extractionId"]
                with self.database.session() as session:
                    ContentService(
                        ContentRepository(session),
                        MaterialService(MaterialRepository(session), self.database.settings),
                        VocabularyService(VocabularyRepository(session)),
                        create_llm_adapter(self.database.settings),
                    ).get_owned(extraction_id, user_id, role)
            return
        raise AppError("unsupported_action", "暂不支持该操作", status_code=422)

    def stage_delete_confirmation(self, action: dict[str, Any], user_id: str) -> dict[str, Any]:
        payload = action.get("payload", {})
        with self.database.session() as session:
            task = TaskService(TaskRepository(session), session).get(
                payload.get("taskId", ""), user_id
            )
        next_action = _build_delete_action(task, 2)
        next_action["id"] = action["id"]
        next_action["payload"]["firstConfirmationId"] = action["id"]
        return _decorate_action(next_action)

    def learning_stats_text(self, user_id: str) -> str:
        with self.database.session() as session:
            practice = PracticeService(PracticeRepository(session), session, self.database.settings)
            stats = LearningService(practice, self.database.settings).stats(user_id)
            return (
                f"已完成练习 {stats.practice_count} 次，"
                f"平均正确率 {stats.average_accuracy}%，"
                f"已掌握 {stats.mastered_count} 个词，"
                f"待复习 {stats.review_count} 个。"
            )

    def execute(
        self, action: dict[str, Any], user_id: str, role: str = "user"
    ) -> AgentActionResult:
        self.validate_action(action, user_id, role)
        with self.database.session() as session:
            task_service = TaskService(TaskRepository(session), session)
            vocabulary_service = VocabularyService(VocabularyRepository(session))
            payload = action.get("payload", {})
            operation = action["operation"]
            if operation == "create_task":
                draft = payload["taskDraft"]
                created = task_service.create(user_id, role, TaskCreate.model_validate(draft))
                return AgentActionResult(
                    f"任务「{created.name}」已创建。",
                    [{"label": "打开任务", "to": f"/tasks/{created.id}"}],
                )
            if operation == "update_task":
                changes = payload["changes"]
                config = changes["config"]
                updated = task_service.update(
                    payload["taskId"],
                    user_id,
                    TaskUpdate.model_validate(
                        {
                            "name": changes["name"],
                            "wordsPerGroup": (
                                None
                                if changes.get("mode") == "fixed"
                                else config.get("wordsPerGroup")
                            ),
                            "repeatUntilCorrect": config.get("repeatUntilCorrect"),
                            "dictation": config.get("dictation"),
                        }
                    ),
                )
                return AgentActionResult(
                    f"任务「{updated.name}」已更新。",
                    [{"label": "打开任务", "to": f"/tasks/{updated.id}"}],
                )
            if operation == "delete_task":
                task_service.delete(payload["taskId"], user_id)
                return AgentActionResult("任务及其练习记录已删除。", [])
            if operation == "create_vocabulary":
                created_library = vocabulary_service.create(
                    user_id,
                    role,
                    VocabularyCreate.model_validate(payload["vocabularyDraft"]),
                )
                return AgentActionResult(
                    f"词库「{created_library.name}」已创建。",
                    [{"label": "打开词库", "to": f"/vocabulary/{created_library.id}"}],
                )
            if operation == "import_vocabulary":
                draft = VocabularyCreate.model_validate(payload["vocabularyDraft"])
                extraction_id = payload.get("extractionId")
                if extraction_id:
                    content = ContentService(
                        ContentRepository(session),
                        MaterialService(MaterialRepository(session), self.database.settings),
                        VocabularyService(VocabularyRepository(session)),
                        create_llm_adapter(self.database.settings),
                    )
                    extraction = content.get_owned(extraction_id, user_id, role)
                    extraction = content.update(
                        extraction.id,
                        user_id,
                        role,
                        ContentExtractionUpdate(
                            extracted_json=draft.model_dump(by_alias=True),
                            version=extraction.version,
                        ),
                    )
                    imported = content.confirm(extraction.id, user_id, role, extraction.version)
                else:
                    imported = vocabulary_service.create(user_id, role, draft)
                return AgentActionResult(
                    f"词库「{imported.name}」已导入，共 {len(imported.entries)} 个词条。",
                    [{"label": "打开词库", "to": f"/vocabulary/{imported.id}"}],
                )
            raise AppError("unsupported_action", "暂不支持该操作")
