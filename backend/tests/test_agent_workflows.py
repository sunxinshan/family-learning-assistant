import json
from collections.abc import Iterable

from fastapi.testclient import TestClient

from app.main import create_app


def login(client: TestClient, nickname: str = "Alice", password: str = "demo123") -> str:
    response = client.post("/api/v1/auth/login", json={"nickname": nickname, "password": password})
    assert response.status_code == 200, response.text
    return response.json()["access_token"]


def auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def parse_sse(text: str) -> list[dict]:
    events = []
    for block in text.strip().split("\n\n"):
        data = next((line[6:] for line in block.splitlines() if line.startswith("data: ")), None)
        if data:
            events.append(json.loads(data))
    return events


def start_run(client: TestClient, token: str, message: str) -> list[dict]:
    response = client.post(
        "/api/v1/agent/runs/stream",
        headers=auth(token),
        json={"message": message},
    )
    assert response.status_code == 200, response.text
    events = parse_sse(response.text)
    assert events[-1]["type"] == "done"
    return events


def create_library(client: TestClient, token: str, name: str = "Agent Library") -> dict:
    response = client.post(
        "/api/v1/vocabularies",
        headers=auth(token),
        json={
            "subject": "english",
            "name": name,
            "description": "",
            "tags": ["agent"],
            "entries": [
                {
                    "word": "agent",
                    "phonetic": "/ˈeɪdʒənt/",
                    "partOfSpeech": "n.",
                    "meanings": ["代理"],
                    "example": "",
                    "exampleTranslation": "",
                },
                {
                    "word": "graph",
                    "phonetic": "/ɡræf/",
                    "partOfSpeech": "n.",
                    "meanings": ["图"],
                    "example": "",
                    "exampleTranslation": "",
                },
            ],
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def find_event(events: Iterable[dict], event_type: str) -> dict:
    return next(event for event in events if event["type"] == event_type)


def test_agent_task_create_confirm_edit_and_idempotency(client: TestClient) -> None:
    token = login(client)
    library = create_library(client, token)

    events = start_run(
        client,
        token,
        f"创建固定任务，选择「{library['name']}」的所有单词，线下听写，自动播放，朗读3次，中文",
    )
    confirmation = find_event(events, "confirmation_required")
    run_id = confirmation["run_id"]
    action = confirmation["data"]
    assert action["operation"] == "create_task"
    assert action["payload"]["taskDraft"]["selectedEntryIds"] == [
        entry["id"] for entry in library["entries"]
    ]
    assert action["payload"]["taskDraft"]["dictation"]["repeatCount"] == 3
    assert client.get("/api/v1/tasks", headers=auth(token)).json() == []

    action["payload"]["taskDraft"]["name"] = "Edited by User"
    action["payload"]["taskDraft"]["dictation"]["intervalSeconds"] = 9
    updated = client.patch(
        f"/api/v1/agent/actions/{run_id}/draft",
        headers=auth(token),
        json={"action": action},
    )
    assert updated.status_code == 200, updated.text
    updated_action = updated.json()
    assert updated_action["draft_version"] == 2

    old_confirm = client.post(
        f"/api/v1/agent/actions/{run_id}/confirm",
        headers=auth(token),
        json={"draftVersion": 1, "configHash": _run_hash(client, token, run_id)},
    )
    assert old_confirm.status_code == 409

    confirm = client.post(
        f"/api/v1/agent/actions/{run_id}/confirm",
        headers=auth(token),
        json={
            "draftVersion": updated_action["draft_version"],
            "configHash": updated.headers.get("x-config-hash") or _run_hash(client, token, run_id),
        },
    )
    assert confirm.status_code == 200, confirm.text
    assert find_event(parse_sse(confirm.text), "done")
    tasks = client.get("/api/v1/tasks", headers=auth(token)).json()
    assert len(tasks) == 1
    assert tasks[0]["name"] == "Edited by User"
    assert tasks[0]["config"]["dictation"]["intervalSeconds"] == 9

    repeated = client.post(
        f"/api/v1/agent/actions/{run_id}/confirm",
        headers=auth(token),
        json={
            "draftVersion": updated_action["draft_version"],
            "configHash": _run_hash(client, token, run_id),
        },
    )
    assert repeated.status_code in {200, 409}
    if repeated.status_code == 200:
        assert client.get("/api/v1/tasks", headers=auth(token)).json() == tasks
    else:
        assert repeated.json()["error"]["code"] == "run_not_waiting"


def _run_hash(client: TestClient, token: str, run_id: str) -> str:
    run = client.get(f"/api/v1/agent/runs/{run_id}", headers=auth(token))
    assert run.status_code == 200, run.text
    return run.json()["configHash"]


def test_agent_cancel_does_not_write_and_replays_events(client: TestClient) -> None:
    token = login(client)
    library = create_library(client, token)
    events = start_run(client, token, f"创建任务，选择「{library['name']}」的所有单词")
    run_id = find_event(events, "confirmation_required")["run_id"]

    replay = client.get(
        f"/api/v1/agent/runs/{run_id}/events?after_sequence=2",
        headers=auth(token),
    )
    assert replay.status_code == 200
    replayed = parse_sse(replay.text)
    assert [item["sequence"] for item in replayed] == sorted(item["sequence"] for item in replayed)
    assert all(item["sequence"] > 2 for item in replayed)

    cancel = client.post(f"/api/v1/agent/actions/{run_id}/cancel", headers=auth(token))
    assert cancel.status_code == 204
    assert client.get("/api/v1/tasks", headers=auth(token)).json() == []


def test_agent_pending_action_survives_process_restart(settings) -> None:
    with TestClient(create_app(settings)) as first:
        token = login(first)
        library = create_library(first, token)
        events = start_run(first, token, f"创建任务，选择「{library['name']}」的所有单词")
        confirmation = find_event(events, "confirmation_required")
        run_id = confirmation["run_id"]
        action = confirmation["data"]
        action["payload"]["taskDraft"]["name"] = "Restart Confirmed"
        updated = first.patch(
            f"/api/v1/agent/actions/{run_id}/draft",
            headers=auth(token),
            json={"action": action},
        ).json()
        config_hash = _run_hash(first, token, run_id)

    with TestClient(create_app(settings)) as second:
        token = login(second)
        confirmed = second.post(
            f"/api/v1/agent/actions/{run_id}/confirm",
            headers=auth(token),
            json={"draftVersion": updated["draft_version"], "configHash": config_hash},
        )
        assert confirmed.status_code == 200, confirmed.text
        tasks = second.get("/api/v1/tasks", headers=auth(token)).json()
        assert tasks[0]["name"] == "Restart Confirmed"
        conversation = second.get("/api/v1/conversations/current", headers=auth(token))
        assert conversation.status_code == 200
        assert len(conversation.json()["messages"]) >= 2


def test_agent_cross_user_cannot_confirm_or_read_action(client: TestClient) -> None:
    alice = login(client)
    bob = login(client, "Bob")
    library = create_library(client, alice)
    events = start_run(client, alice, f"创建任务，选择「{library['name']}」的所有单词")
    run_id = find_event(events, "confirmation_required")["run_id"]

    assert client.get(f"/api/v1/agent/runs/{run_id}", headers=auth(bob)).status_code == 404
    assert (
        client.post(
            f"/api/v1/agent/actions/{run_id}/cancel",
            headers=auth(bob),
        ).status_code
        == 404
    )


def test_agent_learning_query_is_read_only(client: TestClient) -> None:
    token = login(client)
    events = start_run(client, token, "查看我的学习记录和正确率")
    message = find_event(events, "message")
    assert "已完成练习" in message["data"]["content"]
    assert client.get("/api/v1/learning/stats", headers=auth(token)).json()["practiceCount"] == 0
