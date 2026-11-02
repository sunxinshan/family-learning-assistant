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


def _confirm(
    client: TestClient, token: str, run_id: str, version: int, config_hash: str
) -> list[dict]:
    response = client.post(
        f"/api/v1/agent/actions/{run_id}/confirm",
        headers=auth(token),
        json={"draftVersion": version, "configHash": config_hash},
    )
    assert response.status_code == 200, response.text
    return parse_sse(response.text)


def _create_page_task(
    client: TestClient, token: str, library: dict, mode: str = "long_term"
) -> dict:
    response = client.post(
        "/api/v1/tasks",
        headers=auth(token),
        json={
            "name": "Workflow Task",
            "type": "dictation",
            "mode": mode,
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
    assert response.status_code == 201, response.text
    return response.json()


def test_agent_updates_long_term_task_through_task_service(client: TestClient) -> None:
    token = login(client)
    library = create_library(client, token)
    task = _create_page_task(client, token, library)
    events = start_run(
        client,
        token,
        f"修改任务「{task['name']}」，改成每组1个，自动播放，间隔8秒，朗读3次，中文",
    )
    confirmation = find_event(events, "confirmation_required")
    action = confirmation["data"]
    assert action["operation"] == "update_task"
    assert action["payload"]["taskId"] == task["id"]
    _confirm(
        client,
        token,
        confirmation["run_id"],
        action["draft_version"],
        _run_hash(client, token, confirmation["run_id"]),
    )
    updated = client.get(f"/api/v1/tasks/{task['id']}", headers=auth(token)).json()
    assert updated["config"]["wordsPerGroup"] == 1
    assert updated["config"]["dictation"]["playbackMode"] == "auto"
    assert updated["config"]["dictation"]["intervalSeconds"] == 8
    assert updated["config"]["dictation"]["repeatCount"] == 3
    assert updated["config"]["dictation"]["hint"] == "meaning"


def test_agent_deletes_task_with_two_stage_confirmation(client: TestClient) -> None:
    token = login(client)
    library = create_library(client, token)
    task = _create_page_task(client, token, library)
    events = start_run(client, token, f"删除任务「{task['name']}」")
    first = find_event(events, "confirmation_required")
    assert first["data"]["stage"] == 1
    run_id = first["run_id"]

    second_events = _confirm(
        client, token, run_id, first["data"]["draft_version"], _run_hash(client, token, run_id)
    )
    assert client.get(f"/api/v1/tasks/{task['id']}", headers=auth(token)).status_code == 200
    second = find_event(second_events, "confirmation_required")
    assert second["data"]["stage"] == 2
    assert second["data"]["draft_version"] == 2

    _confirm(
        client, token, run_id, second["data"]["draft_version"], _run_hash(client, token, run_id)
    )
    assert client.get(f"/api/v1/tasks/{task['id']}", headers=auth(token)).status_code == 404


def test_agent_creates_and_imports_vocabulary(client: TestClient) -> None:
    token = login(client)
    events = start_run(client, token, "创建英语词库「Agent Words」，标签 agent,demo")
    action = find_event(events, "confirmation_required")["data"]
    assert action["operation"] == "create_vocabulary"
    assert action["payload"]["vocabularyDraft"]["name"] == "Agent Words"
    assert action["payload"]["vocabularyDraft"]["tags"] == ["agent", "demo"]
    _confirm(
        client,
        token,
        action["id"],
        action["draft_version"],
        _run_hash(client, token, action["id"]),
    )
    created = client.get("/api/v1/vocabularies?scope=mine", headers=auth(token)).json()
    assert next(item for item in created if item["name"] == "Agent Words")

    upload = client.post(
        "/api/v1/materials",
        headers=auth(token),
        files={
            "file": (
                "agent-import.csv",
                "单词,音标,词性,词义\norbit,/ˈɔːbɪt/,n.,轨道\nsignal,/ˈsɪɡnəl/,n.,信号\n",
                "text/csv",
            )
        },
    )
    assert upload.status_code == 201, upload.text
    response = client.post(
        "/api/v1/agent/runs/stream",
        headers=auth(token),
        json={
            "message": "导入词库「Agent Imported」",
            "materialId": upload.json()["id"],
        },
    )
    assert response.status_code == 200, response.text
    import_events = parse_sse(response.text)
    import_action = find_event(import_events, "confirmation_required")["data"]
    assert import_action["operation"] == "import_vocabulary"
    assert len(import_action["payload"]["vocabularyDraft"]["entries"]) == 2
    entry_ids = [entry["id"] for entry in import_action["payload"]["vocabularyDraft"]["entries"]]
    assert len(set(entry_ids)) == 2
    import_action["payload"]["vocabularyDraft"]["name"] = "Agent Imported Edited"
    updated = client.patch(
        f"/api/v1/agent/actions/{import_action['id']}/draft",
        headers=auth(token),
        json={"action": import_action},
    )
    assert updated.status_code == 200, updated.text
    revised = updated.json()
    _confirm(
        client,
        token,
        import_action["id"],
        revised["draft_version"],
        _run_hash(client, token, import_action["id"]),
    )
    libraries = client.get("/api/v1/vocabularies?scope=mine", headers=auth(token)).json()
    imported = next(item for item in libraries if item["name"] == "Agent Imported Edited")
    assert len(imported["entries"]) == 2


def test_active_run_endpoint_restores_pending_action(client: TestClient) -> None:
    token = login(client)
    library = create_library(client, token)
    events = start_run(client, token, f"创建任务，选择「{library['name']}」的所有单词")
    confirmation = find_event(events, "confirmation_required")
    active = client.get("/api/v1/agent/runs/active", headers=auth(token))
    assert active.status_code == 200, active.text
    assert active.json()["id"] == confirmation["run_id"]
    assert active.json()["pendingAction"]["operation"] == "create_task"


def test_task_create_without_library_keeps_actionable_message(client: TestClient) -> None:
    token = login(client)
    events = start_run(client, token, "创建任务，选择所有单词")
    message = find_event(events, "message")
    assert "当前没有可用词库" in message["data"]["content"]


def test_sse_disconnect_does_not_cancel_background_run(client: TestClient) -> None:
    token = login(client)
    library = create_library(client, token)
    with client.stream(
        "POST",
        "/api/v1/agent/runs/stream",
        headers=auth(token),
        json={"message": f"创建任务，选择「{library['name']}」的所有单词"},
    ) as response:
        assert response.status_code == 200
        first_data = next(line[6:] for line in response.iter_lines() if line.startswith("data: "))
    first = json.loads(first_data)
    run_id = first["run_id"]

    deadline = 5.0
    status = "running"
    while deadline > 0 and status == "running":
        run = client.get(f"/api/v1/agent/runs/{run_id}", headers=auth(token)).json()
        status = run["status"]
        if status == "running":
            import time

            time.sleep(0.05)
            deadline -= 0.05
    assert status == "waiting_confirmation"

    replay = client.get(f"/api/v1/agent/runs/{run_id}/events?after_sequence=1", headers=auth(token))
    events = parse_sse(replay.text)
    assert {event["type"] for event in events} >= {"message", "confirmation_required", "done"}
    assert all(event["sequence"] > 1 for event in events)


def test_agent_selects_prefix_count_defaults_fixed_and_returns_task_link(
    client: TestClient,
) -> None:
    token = login(client)
    entries = [
        {
            "word": f"word{index}",
            "phonetic": f"/w{index}/",
            "partOfSpeech": "n.",
            "meanings": [f"词{index}"],
            "example": "",
            "exampleTranslation": "",
        }
        for index in range(1, 13)
    ]
    library = client.post(
        "/api/v1/vocabularies",
        headers=auth(token),
        json={
            "subject": "english",
            "name": "Prefix Library",
            "description": "",
            "tags": [],
            "entries": entries,
        },
    ).json()
    events = start_run(client, token, "选择词库「Prefix Library」的前10个单词生成学习任务")
    confirmation = find_event(events, "confirmation_required")
    draft = confirmation["data"]["payload"]["taskDraft"]
    assert draft["mode"] == "fixed"
    assert len(draft["selectedEntryIds"]) == 10
    assert draft["selectedEntryIds"] == [entry["id"] for entry in library["entries"][:10]]

    confirmed = _confirm(
        client,
        token,
        confirmation["run_id"],
        confirmation["data"]["draft_version"],
        _run_hash(client, token, confirmation["run_id"]),
    )
    message = find_event(confirmed, "message")
    assert message["data"]["links"][0]["label"] == "打开任务"
    assert message["data"]["links"][0]["to"].startswith("/tasks/")


def test_agent_task_defaults_to_fixed_with_no_selection(client: TestClient) -> None:
    token = login(client)
    library = create_library(client, token)
    events = start_run(client, token, f"创建任务，选择「{library['name']}」")
    action = find_event(events, "confirmation_required")["data"]
    draft = action["payload"]["taskDraft"]
    assert draft["mode"] == "fixed"
    assert draft["selectedEntryIds"] == []
