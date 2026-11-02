from fastapi.testclient import TestClient


def login(client: TestClient, nickname: str, password: str) -> str:
    response = client.post("/api/v1/auth/login", json={"nickname": nickname, "password": password})
    assert response.status_code == 200, response.text
    return response.json()["access_token"]


def auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def test_csv_import_preview_edit_and_confirm(client: TestClient) -> None:
    token = login(client, "Alice", "demo123")
    upload = client.post(
        "/api/v1/materials",
        headers=auth(token),
        files={
            "file": (
                "unit-words.csv",
                "单词,音标,词性,词义,例句,例句翻译\n"
                "apple,/ˈæpl/,n.,苹果,An apple.,一个苹果。\n"
                "book,/bʊk/,n.,书,A book.,一本书。\n",
                "text/csv",
            )
        },
    )
    assert upload.status_code == 201, upload.text
    extraction = client.post(
        f"/api/v1/materials/{upload.json()['id']}/extractions",
        headers=auth(token),
    )
    assert extraction.status_code == 201, extraction.text
    preview = extraction.json()
    assert preview["extractedJson"]["name"] == "unit-words"
    assert len(preview["extractedJson"]["entries"]) == 2
    assert preview["errorsJson"] == []

    preview["extractedJson"]["name"] = "Edited Import"
    preview["extractedJson"]["subject"] = "english"
    preview["extractedJson"]["tags"] = ["imported", "unit"]
    preview["extractedJson"]["entries"][0]["meanings"] = ["苹果", "苹果公司"]
    updated = client.patch(
        f"/api/v1/content/extractions/{preview['id']}",
        headers=auth(token),
        json={"version": preview["version"], "extractedJson": preview["extractedJson"]},
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["version"] == 2

    stale = client.post(
        f"/api/v1/content/extractions/{preview['id']}/confirm?version=1",
        headers=auth(token),
    )
    assert stale.status_code == 409

    confirmed = client.post(
        f"/api/v1/content/extractions/{preview['id']}/confirm?version=2",
        headers=auth(token),
    )
    assert confirmed.status_code == 201, confirmed.text
    library = confirmed.json()
    assert library["name"] == "Edited Import"
    assert library["tags"] == ["imported", "unit"]
    assert library["entries"][0]["meanings"] == ["苹果", "苹果公司"]

    repeated = client.post(
        f"/api/v1/content/extractions/{preview['id']}/confirm?version=2",
        headers=auth(token),
    )
    assert repeated.status_code == 409


def test_import_template_and_unsupported_file(client: TestClient) -> None:
    token = login(client, "Alice", "demo123")
    template = client.get("/api/v1/vocabularies/import-template", headers=auth(token))
    assert template.status_code == 200
    assert template.content[:2] == b"PK"
    assert "attachment" in template.headers["content-disposition"]

    unsupported = client.post(
        "/api/v1/materials",
        headers=auth(token),
        files={"file": ("words.txt", b"hello", "text/plain")},
    )
    assert unsupported.status_code in {400, 415}
    assert "xlsx" in unsupported.json()["error"]["message"]


def test_import_isolation(client: TestClient) -> None:
    alice = login(client, "Alice", "demo123")
    bob = login(client, "Bob", "demo123")
    upload = client.post(
        "/api/v1/materials",
        headers=auth(alice),
        files={
            "file": (
                "private.csv",
                "单词,词义\nsecret,秘密\n",
                "text/csv",
            )
        },
    )
    assert upload.status_code == 201
    extraction = client.post(
        f"/api/v1/materials/{upload.json()['id']}/extractions",
        headers=auth(alice),
    )
    assert extraction.status_code == 201
    forbidden = client.get(
        f"/api/v1/content/extractions/{extraction.json()['id']}",
        headers=auth(bob),
    )
    assert forbidden.status_code == 403


def test_admin_user_management_and_logs(client: TestClient) -> None:
    alice = login(client, "Alice", "demo123")
    admin = login(client, "admin", "admin213")
    manager = login(client, "admin1", "admin222")

    assert client.get("/api/v1/admin/users", headers=auth(alice)).status_code == 403
    assert client.get("/api/v1/admin/logs", headers=auth(alice)).status_code == 403

    users = client.get("/api/v1/admin/users", headers=auth(admin))
    assert users.status_code == 200
    admin_users = [item for item in users.json() if item["role"] == "admin"]
    assert {item["nickname"] for item in admin_users} >= {"admin", "admin1"}
    bob = next(item for item in users.json() if item["nickname"] == "Bob")

    disabled = client.patch(
        f"/api/v1/admin/users/{bob['id']}/status",
        headers=auth(manager),
        json={"status": "disabled"},
    )
    assert disabled.status_code == 200, disabled.text
    assert disabled.json()["status"] == "disabled"
    assert (
        client.post(
            "/api/v1/auth/login", json={"nickname": "Bob", "password": "demo123"}
        ).status_code
        == 403
    )
    assert "demoPassword" not in disabled.text
    assert "passwordHash" not in disabled.text

    reset = client.post(
        f"/api/v1/admin/users/{bob['id']}/reset-password",
        headers=auth(admin),
    )
    assert reset.status_code == 200, reset.text
    assert reset.json()["temporaryPassword"]
    assert (
        client.post(
            "/api/v1/auth/login",
            json={"nickname": "Bob", "password": reset.json()["temporaryPassword"]},
        ).status_code
        == 403
    )

    logs = client.get("/api/v1/admin/logs", headers=auth(admin))
    assert logs.status_code == 200
    assert {item["action"] for item in logs.json()} >= {"更新用户状态", "重置用户密码"}


def test_admin_cannot_modify_another_users_task(client: TestClient) -> None:
    alice = login(client, "Alice", "demo123")
    admin = login(client, "admin", "admin213")
    library = client.post(
        "/api/v1/vocabularies",
        headers=auth(alice),
        json={
            "subject": "english",
            "name": "Alice Private",
            "description": "",
            "tags": [],
            "entries": [
                {
                    "word": "private",
                    "phonetic": "",
                    "partOfSpeech": "adj.",
                    "meanings": ["私人的"],
                    "example": "",
                    "exampleTranslation": "",
                }
            ],
        },
    ).json()
    task = client.post(
        "/api/v1/tasks",
        headers=auth(alice),
        json={
            "name": "Alice Task",
            "type": "dictation",
            "mode": "fixed",
            "libraryId": library["id"],
            "selectedEntryIds": [library["entries"][0]["id"]],
            "wordsPerGroup": 1,
            "dictation": {"mode": "online", "playbackMode": "manual"},
        },
    ).json()
    assert client.get(f"/api/v1/tasks/{task['id']}", headers=auth(admin)).status_code == 403
    assert client.delete(f"/api/v1/tasks/{task['id']}", headers=auth(admin)).status_code == 403


def test_admin_can_read_user_learning_stats_but_not_user_tasks(client: TestClient) -> None:
    admin = login(client, "admin", "admin213")
    users = client.get("/api/v1/admin/users", headers=auth(admin)).json()
    bob = next(item for item in users if item["nickname"] == "Bob")
    stats = client.get(f"/api/v1/admin/users/{bob['id']}/learning-stats", headers=auth(admin))
    assert stats.status_code == 200, stats.text
    assert stats.json()["practiceCount"] == 0


def test_english_and_chinese_templates_have_different_headers(client: TestClient) -> None:
    from io import BytesIO

    from openpyxl import load_workbook

    token = login(client, "Alice", "demo123")
    english = client.get(
        "/api/v1/vocabularies/import-template?subject=english", headers=auth(token)
    )
    chinese = client.get(
        "/api/v1/vocabularies/import-template?subject=chinese", headers=auth(token)
    )
    assert english.status_code == 200
    assert chinese.status_code == 200
    english_headers = [cell.value for cell in load_workbook(BytesIO(english.content)).active[1]]
    chinese_headers = [cell.value for cell in load_workbook(BytesIO(chinese.content)).active[1]]
    assert english_headers[:2] == ["单词", "音标"]
    assert chinese_headers[:2] == ["词语", "拼音"]
    assert "english-vocabulary-template" in english.headers["content-disposition"]
    assert "chinese-vocabulary-template" in chinese.headers["content-disposition"]


def test_admin_can_publish_own_private_vocabulary(client: TestClient) -> None:
    admin = login(client, "admin", "admin213")
    created = client.post(
        "/api/v1/vocabularies",
        headers=auth(admin),
        json={
            "subject": "english",
            "name": "Admin Private",
            "description": "",
            "tags": ["admin"],
            "entries": [
                {
                    "word": "publish",
                    "phonetic": "/ˈpʌblɪʃ/",
                    "partOfSpeech": "v.",
                    "meanings": ["发布"],
                    "example": "",
                    "exampleTranslation": "",
                }
            ],
        },
    )
    assert created.status_code == 201, created.text
    assert created.json()["visibility"] == "personal"
    visibility = client.patch(
        f"/api/v1/vocabularies/{created.json()['id']}/visibility",
        headers=auth(admin),
        json={"visibility": "public"},
    )
    assert visibility.status_code == 200, visibility.text
    assert visibility.json()["visibility"] == "public"
    assert visibility.json()["published"] is True
    assert visibility.json()["ownerId"] is None
    public = client.get(
        "/api/v1/vocabularies?scope=public&subject=english", headers=auth(admin)
    ).json()
    assert any(item["id"] == created.json()["id"] for item in public)
