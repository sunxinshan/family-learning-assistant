import csv
import io
import unicodedata
from pathlib import Path

from openpyxl import load_workbook

from app.core.exceptions import AppError

WORD_HEADERS = {"word", "单词", "词形", "词汇"}
PHONETIC_HEADERS = {"phonetic", "音标", "拼音"}
POS_HEADERS = {"partofspeech", "part_of_speech", "词性"}
MEANING_HEADERS = {"meaning", "meanings", "词义", "释义", "中文释义"}
EXAMPLE_HEADERS = {"example", "例句", "英文例句"}
TRANSLATION_HEADERS = {"exampletranslation", "example_translation", "例句翻译", "翻译"}


def normalize_header(value: object) -> str:
    return (
        str(value or "").replace("\ufeff", "").strip().lower().replace(" ", "_").replace("-", "_")
    )


def normalize_word(value: str) -> str:
    return unicodedata.normalize("NFKC", value).strip().casefold()


def _read_rows(path: Path) -> list[list[object]]:
    if path.suffix.lower() == ".csv":
        text = path.read_text(encoding="utf-8-sig")
        return list(csv.reader(io.StringIO(text)))
    workbook = load_workbook(path, read_only=True, data_only=True)
    sheet = workbook.active
    rows = [list(row) for row in sheet.iter_rows(values_only=True)]
    workbook.close()
    return rows


def _cell(row: list[object], indexes: dict[str, int], key: str) -> str:
    index = indexes[key]
    return "" if index < 0 or index >= len(row) else str(row[index] or "").strip()


def parse_vocabulary(path: Path, filename: str) -> tuple[dict, list[dict]]:
    rows = _read_rows(path)
    if not rows:
        raise AppError("empty_file", "文件内容为空")
    headers = [normalize_header(item) for item in rows[0]]
    indexes = {
        "word": next((i for i, header in enumerate(headers) if header in WORD_HEADERS), -1),
        "phonetic": next((i for i, header in enumerate(headers) if header in PHONETIC_HEADERS), -1),
        "pos": next((i for i, header in enumerate(headers) if header in POS_HEADERS), -1),
        "meaning": next((i for i, header in enumerate(headers) if header in MEANING_HEADERS), -1),
        "example": next((i for i, header in enumerate(headers) if header in EXAMPLE_HEADERS), -1),
        "translation": next(
            (i for i, header in enumerate(headers) if header in TRANSLATION_HEADERS), -1
        ),
    }
    if indexes["word"] < 0 or indexes["meaning"] < 0:
        raise AppError("invalid_headers", "文件必须包含单词和词义列")

    entries: list[dict] = []
    errors: list[dict] = []
    seen: set[str] = set()
    for row_number, row in enumerate(rows[1:], start=2):
        word = _cell(row, indexes, "word")
        if not word:
            if any(str(item or "").strip() for item in row):
                errors.append({"row": row_number, "message": "缺少单词"})
            continue
        normalized = normalize_word(word)
        if normalized in seen:
            errors.append({"row": row_number, "message": f"重复词条：{word}"})
            continue
        meaning_text = _cell(row, indexes, "meaning").replace("；", ";")
        meanings = [item.strip() for item in meaning_text.split(";") if item.strip()]
        if not meanings:
            errors.append({"row": row_number, "message": f"词条缺少词义：{word}"})
            continue
        seen.add(normalized)
        entries.append(
            {
                "word": word,
                "phonetic": _cell(row, indexes, "phonetic"),
                "partOfSpeech": _cell(row, indexes, "pos"),
                "meanings": meanings,
                "example": _cell(row, indexes, "example"),
                "exampleTranslation": _cell(row, indexes, "translation"),
            }
        )
    draft = {
        "subject": "english",
        "name": Path(filename).stem or "导入词库",
        "description": f"从 {filename} 导入的词库",
        "tags": ["Excel 导入"],
        "entries": entries,
    }
    return draft, errors
