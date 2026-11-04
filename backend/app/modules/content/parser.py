import csv
import io
import re
import unicodedata
from pathlib import Path
from typing import Any, Protocol

from openpyxl import load_workbook

from app.core.exceptions import AppError

WORD_HEADERS = {
    "word",
    "words",
    "单词",
    "词形",
    "词汇",
    "词语",
    "英文单词",
    "englishword",
    "english_word",
    "term",
    "vocabulary",
}
PHONETIC_HEADERS = {
    "phonetic",
    "phonetics",
    "ipa",
    "音标",
    "拼音",
    "读音",
    "pronunciation",
}
POS_HEADERS = {
    "partofspeech",
    "part_of_speech",
    "pos",
    "词性",
    "词类",
    "part",
    "type",
}
MEANING_HEADERS = {
    "meaning",
    "meanings",
    "definition",
    "translation",
    "gloss",
    "词义",
    "释义",
    "中文释义",
    "中文意思",
    "意思",
    "解释",
    "含义",
    "翻译",
}
EXAMPLE_HEADERS = {
    "example",
    "examples",
    "sentence",
    "sample",
    "例句",
    "英文例句",
    "示例",
    "句子",
}
TRANSLATION_HEADERS = {
    "exampletranslation",
    "example_translation",
    "sentencetranslation",
    "sentence_translation",
    "example_cn",
    "例句翻译",
    "翻译",
    "例句中文",
    "句子翻译",
}

CANONICAL_FIELDS = (
    "word",
    "phonetic",
    "pos",
    "meaning",
    "example",
    "translation",
)
HEADER_SETS = {
    "word": WORD_HEADERS,
    "phonetic": PHONETIC_HEADERS,
    "pos": POS_HEADERS,
    "meaning": MEANING_HEADERS,
    "example": EXAMPLE_HEADERS,
    "translation": TRANSLATION_HEADERS,
}
# 表头映射 Prompt 里使用的字段名，与内部 CANONICAL_FIELDS 对齐。
MAPPING_ALIASES = {
    "partOfSpeech": "pos",
    "part_of_speech": "pos",
    "exampleTranslation": "translation",
    "example_translation": "translation",
}


class HeaderAnalyzer(Protocol):
    def analyze_headers(self, headers: list[str], samples: list[list[str]]) -> dict[str, Any]: ...


def normalize_header(value: object) -> str:
    return (
        str(value or "").replace("\ufeff", "").strip().lower().replace(" ", "_").replace("-", "_")
    )


def normalize_word(value: str) -> str:
    return unicodedata.normalize("NFKC", value).strip().casefold()


def read_vocabulary_rows(path: Path) -> list[list[object]]:
    if path.suffix.lower() == ".csv":
        text = path.read_text(encoding="utf-8-sig")
        return list(csv.reader(io.StringIO(text)))
    workbook = load_workbook(path, read_only=True, data_only=True)
    sheet = workbook.active
    # 部分导出工具会把 dimension 写成 A1，只读模式会据此截断整张表；
    # 重置后按实际行数据读取，避免表头之外的内容被丢弃。
    sheet.reset_dimensions()
    rows = [list(row) for row in sheet.iter_rows(values_only=True)]
    workbook.close()
    return rows


def _cell(row: list[object], indexes: dict[str, int], key: str) -> str:
    index = indexes[key]
    return "" if index < 0 or index >= len(row) else str(row[index] or "").strip()


def _header_matches(header: str, field: str) -> bool:
    if header in HEADER_SETS[field]:
        return True
    # “单词 / 短语”“word/phrase”这类复合表头按分隔符拆开后逐段匹配。
    parts = {part.strip("_ ") for part in re.split(r"[/、,，|]+", header)}
    return any(part and part in HEADER_SETS[field] for part in parts)


def _rule_mapping(raw_headers: list[object]) -> dict[str, int]:
    normalized = [normalize_header(item) for item in raw_headers]
    mapping: dict[str, int] = {}
    used: set[int] = set()
    for field in CANONICAL_FIELDS:
        index = next(
            (
                i
                for i, header in enumerate(normalized)
                if i not in used and _header_matches(header, field)
            ),
            -1,
        )
        mapping[field] = index
        if index >= 0:
            used.add(index)
    return mapping


def _sample_rows(rows: list[list[object]], limit: int = 5) -> list[list[str]]:
    samples: list[list[str]] = []
    for row in rows[1 : limit + 1]:
        samples.append([str(item or "")[:200] for item in row[:30]])
    return samples


def _validate_mapping(mapping: object, header_count: int) -> dict[str, int]:
    if not isinstance(mapping, dict):
        raise AppError("header_mapping_failed", "模型未返回有效列映射", status_code=422)
    # 模型 Prompt 使用 partOfSpeech / exampleTranslation，解析层统一转成内部字段名。
    source = dict(mapping)
    for alias, field in MAPPING_ALIASES.items():
        if field not in source and alias in source:
            source[field] = source[alias]
    result: dict[str, int] = {}
    used: set[int] = set()
    for field in CANONICAL_FIELDS:
        value = source.get(field, -1)
        if isinstance(value, bool) or not isinstance(value, int):
            raise AppError("header_mapping_failed", "模型列映射索引格式错误", status_code=422)
        if value < -1 or value >= header_count:
            raise AppError("header_mapping_failed", "模型列映射索引越界", status_code=422)
        if value >= 0 and value in used:
            raise AppError(
                "header_mapping_failed", "模型重复使用同一列映射多个字段", status_code=422
            )
        if value >= 0:
            used.add(value)
        result[field] = value
    if result["word"] < 0:
        raise AppError(
            "invalid_headers",
            "无法识别单词列，请检查表头或调整列名后重试",
            status_code=422,
        )
    return result


def _mapping_info(
    raw_headers: list[object],
    mapping: dict[str, int],
    *,
    source: str,
    confidence: float | None = None,
    reason: str = "",
    usage: dict[str, int] | None = None,
) -> dict[str, Any]:
    return {
        "fields": {
            field: {
                "index": index,
                "header": str(raw_headers[index] or "") if index >= 0 else "",
            }
            for field, index in mapping.items()
        },
        "unmappedHeaders": [
            str(header or "")
            for index, header in enumerate(raw_headers)
            if index not in {value for value in mapping.values() if value >= 0}
        ],
        "source": source,
        "confidence": confidence,
        "reason": reason,
        "usage": usage or {},
    }


def parse_vocabulary(
    path: Path,
    filename: str,
    header_analyzer: HeaderAnalyzer | None = None,
    subject: str = "english",
) -> tuple[dict, list[dict], dict[str, Any]]:
    rows = read_vocabulary_rows(path)
    if not rows:
        raise AppError("empty_file", "文件内容为空")
    raw_headers = rows[0]
    mapping = _rule_mapping(raw_headers)
    mapping_info = _mapping_info(raw_headers, mapping, source="rules", confidence=1.0)
    if mapping["word"] < 0:
        if not header_analyzer:
            raise AppError(
                "invalid_headers",
                "文件必须包含单词列；当前环境未配置表头分析模型",
                status_code=422,
            )
        analyzed = header_analyzer.analyze_headers(
            [str(item or "") for item in raw_headers],
            _sample_rows(rows),
        )
        mapping = _validate_mapping(analyzed.get("mapping"), len(raw_headers))
        mapping_info = _mapping_info(
            raw_headers,
            mapping,
            source="llm",
            confidence=float(analyzed.get("confidence", 0.0) or 0.0),
            reason=str(analyzed.get("reason", ""))[:500],
            usage=analyzed.get("usage") or {},
        )

    entries: list[dict] = []
    errors: list[dict] = []
    seen: set[str] = set()
    for row_number, row in enumerate(rows[1:], start=2):
        word = _cell(row, mapping, "word")
        if not word:
            if any(str(item or "").strip() for item in row):
                errors.append({"row": row_number, "message": "缺少单词"})
            continue
        normalized = normalize_word(word)
        if normalized in seen:
            errors.append({"row": row_number, "message": f"重复词条：{word}"})
            continue
        meaning_text = _cell(row, mapping, "meaning").replace("；", ";")
        meanings = [item.strip() for item in meaning_text.split(";") if item.strip()]
        seen.add(normalized)
        entries.append(
            {
                "word": word,
                "phonetic": _cell(row, mapping, "phonetic"),
                "partOfSpeech": _cell(row, mapping, "pos"),
                "meanings": meanings,
                "example": _cell(row, mapping, "example"),
                "exampleTranslation": _cell(row, mapping, "translation"),
            }
        )
    draft = {
        "subject": subject,
        "name": Path(filename).stem or "导入词库",
        "description": f"从 {filename} 导入的词库",
        "tags": ["Excel 导入"],
        "entries": entries,
    }
    return draft, errors, mapping_info
