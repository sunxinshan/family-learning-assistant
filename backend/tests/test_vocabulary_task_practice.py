from fastapi.testclient import TestClient


def login(client: TestClient, nickname: str, password: str) -> str:
    response = client.post(
        "/api/v1/auth/login",
        json={"nickname": nickname, "password": password},
    )
    assert response.status_code == 200
    return response.json()["access_token"]


def auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def create_library(client: TestClient, token: str) -> dict:
    response = client.post(
        "/api/v1/vocabularies",
        headers=auth(token),
        json={
            "subject": "english",
            "name": "Core words",
            "description": "integration",
            "tags": ["test", "core"],
            "entries": [
                {
                    "word": "hello",
                    "phonetic": "/həˈləʊ/",
                    "partOfSpeech": "interj.",
                    "meanings": ["你好"],
                    "example": "Hello, world.",
                    "exampleTranslation": "你好，世界。",
                },
                {
                    "word": "world",
                    "phonetic": "/wɜːld/",
                    "partOfSpeech": "n.",
                    "meanings": ["世界"],
                    "example": "The world is large.",
                    "exampleTranslation": "世界很大。",
                },
            ],
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_vocabulary_copy_is_independent(client: TestClient) -> None:
    alice = login(client, "Alice", "demo123")
    admin = login(client, "Admin", "admin123")
    public = client.post(
        "/api/v1/vocabularies",
        headers=auth(admin),
        json={
            "subject": "english",
            "name": "Public words",
            "description": "",
            "tags": [],
            "visibility": "public",
            "entries": [
                {
                    "word": "shared",
                    "phonetic": "",
                    "partOfSpeech": "adj.",
                    "meanings": ["共享的"],
                    "example": "",
                    "exampleTranslation": "",
                }
            ],
        },
    )
    assert public.status_code == 201, public.text
    library_id = public.json()["id"]
    assert (
        client.post(f"/api/v1/vocabularies/{library_id}/publish", headers=auth(admin)).status_code
        == 200
    )
    copied = client.post(f"/api/v1/vocabularies/{library_id}/copy", headers=auth(alice))
    assert copied.status_code == 201
    assert copied.json()["ownerId"] != public.json()["ownerId"]
    assert copied.json()["entries"][0]["id"] != public.json()["entries"][0]["id"]


def test_task_practice_and_learning_flow(client: TestClient) -> None:
    token = login(client, "Alice", "demo123")
    library = create_library(client, token)
    task = client.post(
        "/api/v1/tasks",
        headers=auth(token),
        json={
            "name": "Dictation One",
            "type": "dictation",
            "mode": "fixed",
            "libraryId": library["id"],
            "selectedEntryIds": [entry["id"] for entry in library["entries"]],
            "wordsPerGroup": 2,
            "repeatUntilCorrect": False,
            "dictation": {
                "mode": "online",
                "playbackMode": "manual",
                "intervalSeconds": 5,
                "hint": "phonetic",
                "repeatCount": 2,
            },
        },
    )
    assert task.status_code == 201, task.text
    task_data = task.json()
    attempt = client.post(
        f"/api/v1/tasks/{task_data['id']}/attempts",
        headers=auth(token),
    )
    assert attempt.status_code == 200, attempt.text
    attempt_id = attempt.json()["id"]
    assert attempt.json()["total"] == 2

    first = client.post(
        f"/api/v1/attempts/{attempt_id}/answers",
        headers=auth(token),
        json={"given": "hello", "durationMs": 1200},
    )
    assert first.status_code == 200, first.text
    assert first.json()["score"] == 1
    second = client.post(
        f"/api/v1/attempts/{attempt_id}/answers",
        headers=auth(token),
        json={"given": "world", "durationMs": 900},
    )
    assert second.status_code == 200, second.text
    assert second.json()["status"] == "completed"

    refreshed_task = client.get(f"/api/v1/tasks/{task_data['id']}", headers=auth(token))
    assert refreshed_task.status_code == 200
    assert refreshed_task.json()["progress"] == 100
    assert refreshed_task.json()["status"] == "completed"

    stats = client.get("/api/v1/learning/stats", headers=auth(token))
    assert stats.status_code == 200, stats.text
    assert stats.json()["practiceCount"] == 1
    assert stats.json()["averageAccuracy"] == 100


def test_offline_self_check_records_source(client: TestClient) -> None:
    token = login(client, "Alice", "demo123")
    library = create_library(client, token)
    task = client.post(
        "/api/v1/tasks",
        headers=auth(token),
        json={
            "name": "Offline Dictation",
            "type": "dictation",
            "mode": "fixed",
            "libraryId": library["id"],
            "selectedEntryIds": [library["entries"][0]["id"]],
            "wordsPerGroup": 1,
            "repeatUntilCorrect": False,
            "dictation": {"mode": "offline", "playbackMode": "auto"},
        },
    )
    assert task.status_code == 201, task.text
    attempt = client.post(f"/api/v1/tasks/{task.json()['id']}/attempts", headers=auth(token))
    result = client.post(
        f"/api/v1/attempts/{attempt.json()['id']}/self-check",
        headers=auth(token),
        json={"wrongEntryIds": [task.json()["snapshot"][0]["id"]]},
    )
    assert result.status_code == 200, result.text
    assert result.json()["answers"][0]["evaluationSource"] == "self_report"
    assert result.json()["answers"][0]["correct"] is False
