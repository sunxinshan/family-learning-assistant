import sqlite3
from pathlib import Path

from fastapi.testclient import TestClient
from langgraph.checkpoint.base import empty_checkpoint
from langgraph.checkpoint.sqlite import SqliteSaver

from app.core.config import Settings


def login(client: TestClient, nickname: str, password: str) -> str:
    response = client.post("/api/v1/auth/login", json={"nickname": nickname, "password": password})
    assert response.status_code == 200, response.text
    return response.json()["access_token"]


def auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def seed_checkpoints(settings: Settings) -> tuple[str, str, str]:
    """写入两条 checkpoint，返回 (thread_id, 第一条 id, 第二条 id)。"""
    path = Path(settings.checkpoint_sqlite_path)
    conn = sqlite3.connect(path, check_same_thread=False)
    saver = SqliteSaver(conn)
    saver.setup()
    thread_id = "thread-cp-test"
    config = {"configurable": {"thread_id": thread_id, "checkpoint_ns": ""}}

    first = empty_checkpoint()
    first["channel_values"] = {
        "text": "第一条",
        "token_usage": {"prompt_tokens": 3},
    }
    config = saver.put(config, first, {"source": "input", "step": 0, "parents": {}}, {"text": 1})
    first_id = config["configurable"]["checkpoint_id"]

    second = empty_checkpoint()
    second["channel_values"] = {
        "text": "第二条",
        "api_key": "sk-this-should-not-leak",
    }
    config = saver.put(config, second, {"source": "loop", "step": 1, "parents": {}}, {"text": 2})
    second_id = config["configurable"]["checkpoint_id"]

    conn.commit()
    conn.close()
    return thread_id, first_id, second_id


def test_list_checkpoints(client: TestClient, settings: Settings) -> None:
    thread_id, _, _ = seed_checkpoints(settings)
    token = login(client, "admin", "admin213")

    response = client.get("/api/v1/admin/checkpoints", headers=auth(token))
    assert response.status_code == 200, response.text
    data = response.json()

    assert data["total"] == 2
    assert len(data["items"]) == 2
    assert {item["step"] for item in data["items"]} == {0, 1}
    assert all(item["threadId"] == thread_id for item in data["items"])
    assert data["threads"][0]["threadId"] == thread_id
    assert data["threads"][0]["checkpointCount"] == 2
    assert data["threads"][0]["latestStep"] == 1


def test_list_checkpoints_filters_and_paginates(client: TestClient, settings: Settings) -> None:
    thread_id, _, _ = seed_checkpoints(settings)
    token = login(client, "admin", "admin213")

    response = client.get(
        f"/api/v1/admin/checkpoints?thread_id={thread_id}&limit=1",
        headers=auth(token),
    )
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["total"] == 2
    assert len(data["items"]) == 1

    empty = client.get(
        "/api/v1/admin/checkpoints?thread_id=not-a-thread",
        headers=auth(token),
    )
    assert empty.status_code == 200
    assert empty.json()["total"] == 0
    assert empty.json()["items"] == []


def test_checkpoint_detail_returns_channels_and_redacts_secrets(
    client: TestClient, settings: Settings
) -> None:
    thread_id, first_id, second_id = seed_checkpoints(settings)
    token = login(client, "admin", "admin213")

    response = client.get(
        f"/api/v1/admin/checkpoints/{thread_id}/{second_id}",
        headers=auth(token),
    )
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["threadId"] == thread_id
    assert data["checkpointId"] == second_id
    assert data["step"] == 1
    assert data["source"] == "loop"
    assert data["channelValues"]["text"] == "第二条"
    assert data["channelValues"]["api_key"] == "[REDACTED]"
    assert isinstance(data["writes"], list)

    # token_usage 只是用量统计，不应被当成凭证整体隐藏
    first = client.get(
        f"/api/v1/admin/checkpoints/{thread_id}/{first_id}",
        headers=auth(token),
    )
    assert first.status_code == 200
    assert first.json()["channelValues"]["token_usage"] == {"prompt_tokens": 3}


def test_checkpoint_detail_returns_404_for_unknown_id(
    client: TestClient, settings: Settings
) -> None:
    thread_id, _, _ = seed_checkpoints(settings)
    token = login(client, "admin", "admin213")

    response = client.get(
        f"/api/v1/admin/checkpoints/{thread_id}/does-not-exist",
        headers=auth(token),
    )
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "checkpoint_not_found"


def test_checkpoints_require_admin(client: TestClient, settings: Settings) -> None:
    seed_checkpoints(settings)
    token = login(client, "Alice", "demo123")

    response = client.get("/api/v1/admin/checkpoints", headers=auth(token))
    assert response.status_code == 403

    anonymous = client.get("/api/v1/admin/checkpoints")
    assert anonymous.status_code == 401
