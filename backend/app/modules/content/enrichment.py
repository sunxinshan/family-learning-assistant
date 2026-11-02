import re
from typing import Any, Protocol

from app.core.exceptions import AppError

_CJK = re.compile(r"[\u3400-\u9fff]")
_LATIN = re.compile(r"[A-Za-z]")
_BATCH_SIZE = 40


class EntryEnricher(Protocol):
    def enrich_entries(self, entries: list[dict[str, Any]]) -> dict[str, Any]: ...


def _has_latin(word: str) -> bool:
    return bool(_LATIN.search(word))


def _has_cjk(word: str) -> bool:
    return bool(_CJK.search(word))


def _requires(entry: dict[str, Any]) -> list[str]:
    word = str(entry.get("word", ""))
    missing: list[str] = []
    if _has_cjk(word):
        if not str(entry.get("phonetic", "")).strip():
            missing.append("phonetic")
    elif _has_latin(word):
        if not str(entry.get("phonetic", "")).strip():
            missing.append("phonetic")
        if not entry.get("meanings"):
            missing.append("meaning")
    return missing


def _apply_result(
    result: dict[str, Any],
    batch: list[dict[str, Any]],
    entries: list[dict[str, Any]],
) -> tuple[str | None, dict[str, int], str | None, str]:
    raw_entries = result.get("entries")
    if not isinstance(raw_entries, list):
        raise AppError("entry_enrichment_failed", "模型未返回有效的词条补充结果", status_code=422)
    batch_by_index = {item["index"]: item for item in batch}
    returned: set[int] = set()
    for item in raw_entries:
        if not isinstance(item, dict):
            raise AppError("entry_enrichment_failed", "模型词条补充格式错误", status_code=422)
        index = item.get("index")
        if (
            isinstance(index, bool)
            or not isinstance(index, int)
            or index not in batch_by_index
            or index in returned
        ):
            raise AppError(
                "entry_enrichment_failed",
                "模型返回了无效或重复的词条索引",
                status_code=422,
            )
        returned.add(index)
        entry = entries[index]
        needs = set(batch_by_index[index]["needs"])
        phonetic = item.get("phonetic")
        meanings = item.get("meanings")
        if "phonetic" in needs and isinstance(phonetic, str) and phonetic.strip():
            entry["phonetic"] = phonetic.strip()[:200]
        if "meaning" in needs and isinstance(meanings, list):
            cleaned = [str(value).strip()[:1000] for value in meanings if str(value).strip()]
            if cleaned:
                entry["meanings"] = cleaned
    return (
        result.get("source"),
        result.get("usage") or {},
        result.get("promptVersion"),
        str(result.get("reason", ""))[:500],
    )


def enrich_vocabulary_entries(
    entries: list[dict[str, Any]],
    enricher: EntryEnricher | None,
) -> tuple[list[dict[str, Any]], list[dict], dict[str, Any]]:
    errors: list[dict] = []
    requested: list[dict[str, Any]] = []
    requested_indexes: set[int] = set()
    for index, entry in enumerate(entries):
        word = str(entry.get("word", ""))
        if _has_cjk(word) and not entry.get("meanings"):
            entry["meanings"] = [word]
        needs = _requires(entry)
        if needs:
            requested.append(
                {
                    "index": index,
                    "word": word,
                    "needs": needs,
                    "existing": {
                        "phonetic": entry.get("phonetic", ""),
                        "meanings": entry.get("meanings", []),
                    },
                }
            )
            requested_indexes.add(index)

    metadata: dict[str, Any] = {
        "requested": len(requested),
        "completed": 0,
        "source": None,
        "usage": {},
        "promptVersion": None,
        "reason": "",
    }
    if requested and enricher is not None:
        sources: set[str] = set()
        usage = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
        prompt_versions: set[str] = set()
        reasons: list[str] = []
        try:
            for start in range(0, len(requested), _BATCH_SIZE):
                batch = requested[start : start + _BATCH_SIZE]
                result = enricher.enrich_entries(batch)
                source, batch_usage, prompt_version, reason = _apply_result(result, batch, entries)
                if source:
                    sources.add(str(source))
                for key in usage:
                    usage[key] += int(batch_usage.get(key, 0) or 0)
                if prompt_version:
                    prompt_versions.add(str(prompt_version))
                if reason:
                    reasons.append(reason)
            metadata.update(
                {
                    "source": ",".join(sorted(sources)) or None,
                    "usage": usage,
                    "promptVersion": ",".join(sorted(prompt_versions)) or None,
                    "reason": "；".join(reasons)[:500],
                }
            )
        except AppError as exc:
            metadata.update({"source": "failed", "reason": exc.message, "errorCode": exc.code})

    metadata["completed"] = sum(1 for index in requested_indexes if not _requires(entries[index]))
    for entry in entries:
        word = str(entry.get("word", ""))
        for field in _requires(entry):
            label = "音标" if field == "phonetic" else "中文释义"
            errors.append(
                {
                    "row": None,
                    "message": f"未能自动补充{label}：{word}，请在预览中手动填写",
                }
            )
    return entries, errors, metadata
