from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.core.exceptions import AppError
from app.modules.content.parser import parse_vocabulary

HEADERS = "Lexeme,Speak,Kind,Explain,Sample,SampleCN\napple,/ˈæpl/,n.,苹果,An apple.,一个苹果。\n"


class FakeAnalyzer:
    def __init__(self, mapping: dict[str, int] | None = None) -> None:
        self.calls = 0
        self.mapping = mapping or {
            "word": 0,
            "phonetic": 1,
            "pos": 2,
            "meaning": 3,
            "example": 4,
            "translation": 5,
        }

    def analyze_headers(self, headers: list[str], samples: list[list[str]]) -> dict[str, Any]:
        self.calls += 1
        assert headers[0] == "Lexeme"
        assert samples and samples[0][0] == "apple"
        return {
            "mapping": self.mapping,
            "confidence": 0.91,
            "reason": "测试模型映射",
            "usage": {"prompt_tokens": 12, "completion_tokens": 8, "total_tokens": 20},
        }


def test_standard_headers_do_not_call_model(tmp_path: Path) -> None:
    path = tmp_path / "standard.csv"
    path.write_text(
        "单词,音标,词性,词义,例句,例句翻译\napple,/ˈæpl/,n.,苹果,An apple.,一个苹果。\n",
        encoding="utf-8",
    )
    analyzer = FakeAnalyzer()
    draft, errors, mapping = parse_vocabulary(path, "standard.csv", analyzer)
    assert analyzer.calls == 0
    assert errors == []
    assert draft["entries"][0]["word"] == "apple"
    assert mapping["source"] == "rules"


def test_unknown_headers_use_model_mapping(tmp_path: Path) -> None:
    path = tmp_path / "unusual.csv"
    path.write_text(HEADERS, encoding="utf-8")
    analyzer = FakeAnalyzer()
    draft, errors, mapping = parse_vocabulary(path, "unusual.csv", analyzer)
    assert analyzer.calls == 1
    assert errors == []
    assert draft["entries"][0] == {
        "word": "apple",
        "phonetic": "/ˈæpl/",
        "partOfSpeech": "n.",
        "meanings": ["苹果"],
        "example": "An apple.",
        "exampleTranslation": "一个苹果。",
    }
    assert mapping["source"] == "llm"
    assert mapping["confidence"] == 0.91
    assert mapping["fields"]["word"]["header"] == "Lexeme"
    assert mapping["usage"]["total_tokens"] == 20


def test_invalid_model_mapping_is_rejected(tmp_path: Path) -> None:
    path = tmp_path / "invalid.csv"
    path.write_text(HEADERS, encoding="utf-8")
    analyzer = FakeAnalyzer(
        {
            "word": 0,
            "phonetic": 0,
            "pos": 2,
            "meaning": 3,
            "example": 4,
            "translation": 5,
        }
    )
    with pytest.raises(AppError) as error:
        parse_vocabulary(path, "invalid.csv", analyzer)
    assert error.value.code == "header_mapping_failed"


def test_api_uses_mock_model_for_unusual_headers(client: TestClient) -> None:
    login = client.post("/api/v1/auth/login", json={"nickname": "Alice", "password": "demo123"})
    token = login.json()["access_token"]
    upload = client.post(
        "/api/v1/materials",
        headers={"Authorization": f"Bearer {token}"},
        files={"file": ("unusual.csv", HEADERS, "text/csv")},
    )
    assert upload.status_code == 201, upload.text
    extraction = client.post(
        f"/api/v1/materials/{upload.json()['id']}/extractions",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert extraction.status_code == 201, extraction.text
    body = extraction.json()
    assert body["mappingSource"] == "llm"
    assert body["mapping"]["fields"]["word"]["header"] == "Lexeme"
    assert body["extractedJson"]["entries"][0]["meanings"] == ["苹果"]


def _login(client: TestClient) -> str:
    response = client.post("/api/v1/auth/login", json={"nickname": "Alice", "password": "demo123"})
    return response.json()["access_token"]


def _extract(client: TestClient, token: str, filename: str, content: str) -> dict:
    upload = client.post(
        "/api/v1/materials",
        headers={"Authorization": f"Bearer {token}"},
        files={"file": (filename, content, "text/csv")},
    )
    assert upload.status_code == 201, upload.text
    response = client.post(
        f"/api/v1/materials/{upload.json()['id']}/extractions",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_word_only_english_file_auto_enriches_phonetic_and_meaning(client: TestClient) -> None:
    token = _login(client)
    extraction = _extract(client, token, "english.csv", "Word\napple\nbook\n")
    entries = extraction["extractedJson"]["entries"]
    assert entries[0]["phonetic"] == "/ˈæpl/"
    assert entries[0]["meanings"] == ["苹果"]
    assert entries[1]["phonetic"] == "/bʊk/"
    assert entries[1]["meanings"] == ["书"]
    assert extraction["mapping"]["enrichment"]["source"] == "mock"
    assert extraction["mapping"]["enrichment"]["completed"] == 2
    assert extraction["errorsJson"] == []


def test_chinese_words_auto_enrich_pinyin(client: TestClient) -> None:
    token = _login(client)
    extraction = _extract(client, token, "chinese.csv", "词语\n苹果\n学习\n")
    entries = extraction["extractedJson"]["entries"]
    assert entries[0]["phonetic"] == "píng guǒ"
    assert entries[0]["meanings"] == ["苹果"]
    assert entries[1]["phonetic"] == "xué xí"
    assert extraction["mapping"]["enrichment"]["completed"] == 2


def test_unresolved_english_enrichment_is_marked_for_manual_edit(client: TestClient) -> None:
    token = _login(client)
    extraction = _extract(client, token, "unknown.csv", "Word\nzzzzunknown\n")
    entry = extraction["extractedJson"]["entries"][0]
    assert entry["phonetic"] == ""
    assert entry["meanings"] == []
    messages = [item["message"] for item in extraction["errorsJson"]]
    assert any("音标" in message for message in messages)
    assert any("中文释义" in message for message in messages)
