from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.modules.practice.models import PracticeAnswer, PracticeAttempt


def login(client: TestClient, nickname: str = "Alice", password: str = "demo123") -> str:
    response = client.post("/api/v1/auth/login", json={"nickname": nickname, "password": password})
    assert response.status_code == 200, response.text
    return response.json()["access_token"]


def auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def create_library(client: TestClient, token: str, name: str = "Regression Library") -> dict:
    response = client.post(
        "/api/v1/vocabularies",
        headers=auth(token),
        json={
            "subject": "english",
            "name": name,
            "description": "",
            "tags": ["regression"],
            "entries": [
                {
                    "word": "alpha",
                    "phonetic": "/alpha/",
                    "partOfSpeech": "n.",
                    "meanings": ["阿尔法"],
                    "example": "",
                    "exampleTranslation": "",
                },
                {
                    "word": "beta",
                    "phonetic": "/beta/",
                    "partOfSpeech": "n.",
                    "meanings": ["贝塔"],
                    "example": "",
                    "exampleTranslation": "",
                },
            ],
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def create_task(
    client: TestClient,
    token: str,
    library: dict,
    *,
    mode: str = "fixed",
    dictation_mode: str = "online",
) -> dict:
    response = client.post(
        "/api/v1/tasks",
        headers=auth(token),
        json={
            "name": "Regression Task",
            "type": "dictation",
            "mode": mode,
            "libraryId": library["id"],
            "selectedEntryIds": [entry["id"] for entry in library["entries"]],
            "wordsPerGroup": 1,
            "repeatUntilCorrect": False,
            "dictation": {
                "mode": dictation_mode,
                "playbackMode": "manual",
                "intervalSeconds": 5,
                "hint": "phonetic",
                "repeatCount": 2,
            },
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_task_snapshot_is_immutable_and_fixed_config_locked(client: TestClient) -> None:
    token = login(client)
    library = create_library(client, token)
    task = create_task(client, token, library)

    updated_library = client.patch(
        f"/api/v1/vocabularies/{library['id']}/entries/{library['entries'][0]['id']}",
        headers=auth(token),
        json={
            "word": "changed",
            "phonetic": "/changed/",
            "partOfSpeech": "n.",
            "meanings": ["改变"],
            "example": "",
            "exampleTranslation": "",
        },
    )
    assert updated_library.status_code == 200, updated_library.text

    refreshed = client.get(f"/api/v1/tasks/{task['id']}", headers=auth(token))
    assert refreshed.status_code == 200
    assert refreshed.json()["snapshot"][0]["word"] == "alpha"

    locked = client.patch(
        f"/api/v1/tasks/{task['id']}",
        headers=auth(token),
        json={"name": "Renamed", "wordsPerGroup": 2},
    )
    assert locked.status_code == 409
    assert locked.json()["error"]["code"] == "fixed_task_locked"

    renamed = client.patch(
        f"/api/v1/tasks/{task['id']}",
        headers=auth(token),
        json={"name": "Renamed"},
    )
    assert renamed.status_code == 200
    assert renamed.json()["name"] == "Renamed"


def test_long_term_task_update_is_persisted(client: TestClient) -> None:
    token = login(client)
    library = create_library(client, token)
    task = create_task(client, token, library, mode="long_term")

    response = client.patch(
        f"/api/v1/tasks/{task['id']}",
        headers=auth(token),
        json={
            "name": "Long Term Updated",
            "wordsPerGroup": 1,
            "repeatUntilCorrect": True,
            "dictation": {
                "mode": "offline",
                "playbackMode": "auto",
                "intervalSeconds": 8,
                "hint": "meaning",
                "repeatCount": 3,
            },
        },
    )
    assert response.status_code == 200, response.text
    refreshed = client.get(f"/api/v1/tasks/{task['id']}", headers=auth(token)).json()
    assert refreshed["name"] == "Long Term Updated"
    assert refreshed["config"]["wordsPerGroup"] == 1
    assert refreshed["config"]["repeatUntilCorrect"] is True
    assert refreshed["config"]["dictation"]["intervalSeconds"] == 8
    assert refreshed["config"]["dictation"]["hint"] == "meaning"


def test_attempt_resumes_and_rejects_cross_user_access(client: TestClient) -> None:
    alice = login(client)
    bob = login(client, "Bob")
    library = create_library(client, alice)
    task = create_task(client, alice, library)

    started = client.post(f"/api/v1/tasks/{task['id']}/attempts", headers=auth(alice))
    assert started.status_code == 200, started.text
    attempt_id = started.json()["id"]
    answer = client.post(
        f"/api/v1/attempts/{attempt_id}/answers",
        headers=auth(alice),
        json={"given": task["snapshot"][0]["word"], "durationMs": 100},
    )
    assert answer.status_code == 200, answer.text

    resumed = client.post(f"/api/v1/tasks/{task['id']}/attempts", headers=auth(alice))
    assert resumed.status_code == 200
    assert resumed.json()["id"] == attempt_id
    assert resumed.json()["currentIndex"] == 1

    forbidden = client.get(f"/api/v1/attempts/{attempt_id}", headers=auth(bob))
    assert forbidden.status_code == 403


def test_repeat_submission_does_not_duplicate_facts(client: TestClient) -> None:
    token = login(client)
    library = create_library(client, token)
    task = create_task(client, token, library)
    attempt = client.post(f"/api/v1/tasks/{task['id']}/attempts", headers=auth(token)).json()

    for entry in task["snapshot"]:
        response = client.post(
            f"/api/v1/attempts/{attempt['id']}/answers",
            headers=auth(token),
            json={"given": entry["word"], "durationMs": 100},
        )
        assert response.status_code == 200, response.text

    duplicate = client.post(
        f"/api/v1/attempts/{attempt['id']}/answers",
        headers=auth(token),
        json={"given": task["snapshot"][-1]["word"], "durationMs": 100},
    )
    assert duplicate.status_code == 409
    stats = client.get("/api/v1/learning/stats", headers=auth(token))
    assert stats.json()["practiceCount"] == 1
    assert stats.json()["averageAccuracy"] == 100


def test_offline_self_check_validates_mode_and_entry_ids(client: TestClient) -> None:
    token = login(client)
    library = create_library(client, token)
    online_task = create_task(client, token, library)
    online_attempt = client.post(
        f"/api/v1/tasks/{online_task['id']}/attempts", headers=auth(token)
    ).json()
    online_check = client.post(
        f"/api/v1/attempts/{online_attempt['id']}/self-check",
        headers=auth(token),
        json={"wrongEntryIds": []},
    )
    assert online_check.status_code == 409

    offline_task = create_task(client, token, library, dictation_mode="offline")
    offline_attempt = client.post(
        f"/api/v1/tasks/{offline_task['id']}/attempts", headers=auth(token)
    ).json()
    invalid = client.post(
        f"/api/v1/attempts/{offline_attempt['id']}/self-check",
        headers=auth(token),
        json={"wrongEntryIds": ["not-a-snapshot-entry"]},
    )
    assert invalid.status_code == 422


def test_deleting_task_cascades_practice_facts(client: TestClient, app: FastAPI) -> None:
    token = login(client)
    library = create_library(client, token)
    task = create_task(client, token, library)
    attempt = client.post(f"/api/v1/tasks/{task['id']}/attempts", headers=auth(token)).json()
    client.post(
        f"/api/v1/attempts/{attempt['id']}/answers",
        headers=auth(token),
        json={"given": task["snapshot"][0]["word"], "durationMs": 100},
    )

    deleted = client.delete(f"/api/v1/tasks/{task['id']}", headers=auth(token))
    assert deleted.status_code == 204
    assert client.get(f"/api/v1/tasks/{task['id']}", headers=auth(token)).status_code == 404
    assert client.get(f"/api/v1/attempts/{attempt['id']}", headers=auth(token)).status_code == 404

    with app.state.database.session() as session:
        assert session.scalar(select(func.count()).select_from(PracticeAttempt)) == 0
        assert session.scalar(select(func.count()).select_from(PracticeAnswer)) == 0
