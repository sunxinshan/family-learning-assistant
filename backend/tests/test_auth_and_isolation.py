from fastapi.testclient import TestClient


def login(client: TestClient, nickname: str, password: str) -> dict:
    response = client.post(
        "/api/v1/auth/login",
        json={"nickname": nickname, "password": password},
    )
    assert response.status_code == 200, response.text
    return response.json()


def auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def test_login_and_current_user(client: TestClient) -> None:
    data = login(client, "Alice", "demo123")
    response = client.get("/api/v1/users/me", headers=auth(data["access_token"]))

    assert response.status_code == 200
    assert response.json()["nickname"] == "Alice"
    assert response.json()["role"] == "user"


def test_user_cannot_access_other_users_task(client: TestClient) -> None:
    alice = login(client, "Alice", "demo123")
    bob = login(client, "Bob", "demo123")

    library = client.post(
        "/api/v1/vocabularies",
        headers=auth(alice["access_token"]),
        json={
            "subject": "english",
            "name": "Alice Library",
            "description": "",
            "tags": ["test"],
            "entries": [
                {
                    "word": "apple",
                    "phonetic": "/ˈæpl/",
                    "partOfSpeech": "n.",
                    "meanings": ["苹果"],
                    "example": "An apple.",
                    "exampleTranslation": "一个苹果。",
                }
            ],
        },
    )
    assert library.status_code == 201, library.text
    library_id = library.json()["id"]
    entry_id = library.json()["entries"][0]["id"]
    task = client.post(
        "/api/v1/tasks",
        headers=auth(alice["access_token"]),
        json={
            "name": "Alice Task",
            "type": "dictation",
            "mode": "fixed",
            "libraryId": library_id,
            "selectedEntryIds": [entry_id],
            "wordsPerGroup": 1,
            "repeatUntilCorrect": False,
            "dictation": {"mode": "online", "playbackMode": "manual"},
        },
    )
    assert task.status_code == 201, task.text

    forbidden = client.get(
        f"/api/v1/tasks/{task.json()['id']}",
        headers=auth(bob["access_token"]),
    )
    assert forbidden.status_code == 403


def test_admin_cannot_modify_user_task(client: TestClient) -> None:
    alice = login(client, "Alice", "demo123")
    admin = login(client, "admin", "admin213")
    users = client.get("/api/v1/admin/users", headers=auth(admin["access_token"]))
    assert users.status_code == 200
    assert len(users.json()) >= 2
    assert client.get("/api/v1/admin/admin", headers=auth(alice["access_token"])).status_code == 404
