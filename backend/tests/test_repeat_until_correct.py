from fastapi.testclient import TestClient

from tests.test_phase5_regression import auth, login


def make_library(client: TestClient, token: str, words: list[str], name: str) -> dict:
    response = client.post(
        "/api/v1/vocabularies",
        headers=auth(token),
        json={
            "subject": "english",
            "name": name,
            "description": "",
            "tags": ["repeat"],
            "entries": [
                {
                    "word": word,
                    "phonetic": f"/{word}/",
                    "partOfSpeech": "n.",
                    "meanings": [word],
                    "example": "",
                    "exampleTranslation": "",
                }
                for word in words
            ],
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def make_task(
    client: TestClient,
    token: str,
    library: dict,
    *,
    repeat_until_correct: bool,
    mode: str = "fixed",
    words_per_group: int = 1,
) -> dict:
    response = client.post(
        "/api/v1/tasks",
        headers=auth(token),
        json={
            "name": f"Repeat Task {repeat_until_correct}-{mode}-{words_per_group}",
            "type": "dictation",
            "mode": mode,
            "libraryId": library["id"],
            "selectedEntryIds": [entry["id"] for entry in library["entries"]],
            "wordsPerGroup": words_per_group,
            "repeatUntilCorrect": repeat_until_correct,
            "dictation": {
                "mode": "online",
                "playbackMode": "manual",
                "intervalSeconds": 8,
                "hint": "phonetic",
                "repeatCount": 1,
                "speechEnabled": True,
            },
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def start_attempt(client: TestClient, token: str, task_id: str) -> dict:
    response = client.post(f"/api/v1/tasks/{task_id}/attempts", headers=auth(token))
    assert response.status_code in (200, 201), response.text
    return response.json()


def answer(client: TestClient, token: str, attempt_id: str, given: str) -> dict:
    response = client.post(
        f"/api/v1/attempts/{attempt_id}/answers",
        headers=auth(token),
        json={"given": given, "durationMs": 800},
    )
    assert response.status_code == 200, response.text
    return response.json()


def test_group_replays_only_the_wrong_words(client: TestClient) -> None:
    token = login(client)
    library = make_library(client, token, ["alpha", "beta"], "Repeat Library A")
    task = make_task(
        client, token, library, repeat_until_correct=True, mode="fixed", words_per_group=2
    )
    alpha, beta = (entry["id"] for entry in task["snapshot"])
    attempt = start_attempt(client, token, task["id"])
    # 第一轮就是整组词，顺序与快照一致。
    assert attempt["targetEntryIds"] == [alpha, beta]
    assert attempt["currentIndex"] == 0
    assert attempt["roundNo"] == 1

    # 答错的词照样进入下一个词，不在原地卡住。
    first = answer(client, token, attempt["id"], "alpha")
    assert first["currentIndex"] == 1
    assert first["roundNo"] == 1

    # 本组这一轮走完：只把答错的 beta 留到第二轮。
    second = answer(client, token, attempt["id"], "bet")
    assert second["answers"][-1]["correct"] is False
    assert second["targetEntryIds"] == [beta]
    assert second["currentIndex"] == 0
    assert second["roundNo"] == 2
    assert second["status"] == "in_progress"

    # 第二轮拼对一次还不够，还要再来一轮。
    third = answer(client, token, attempt["id"], "beta")
    assert third["roundNo"] == 3
    assert third["targetEntryIds"] == [beta]
    assert third["currentIndex"] == 0

    # 连续两轮拼对，本组过关。
    finished = answer(client, token, attempt["id"], "beta")
    assert finished["status"] == "completed"
    assert finished["score"] == 2
    assert finished["total"] == 2


def test_group_passes_in_one_round_when_nothing_is_wrong(client: TestClient) -> None:
    token = login(client)
    library = make_library(client, token, ["alpha", "beta"], "Repeat Library B")
    task = make_task(
        client, token, library, repeat_until_correct=True, mode="fixed", words_per_group=2
    )
    attempt = start_attempt(client, token, task["id"])

    answer(client, token, attempt["id"], "alpha")
    finished = answer(client, token, attempt["id"], "beta")
    # 没有拼错过的词不用重练，一轮就结束。
    assert finished["status"] == "completed"
    assert finished["roundNo"] == 1
    assert finished["score"] == 2


def test_next_group_starts_after_the_current_group_passes(client: TestClient) -> None:
    token = login(client)
    library = make_library(client, token, ["alpha", "beta", "gamma", "delta"], "Repeat Library C")
    task = make_task(
        client, token, library, repeat_until_correct=True, mode="long_term", words_per_group=2
    )
    gamma, delta = (entry["id"] for entry in task["snapshot"][2:])
    attempt = start_attempt(client, token, task["id"])
    assert len(attempt["targetEntryIds"]) == 2

    answer(client, token, attempt["id"], "alpha")
    first_group = answer(client, token, attempt["id"], "beta")
    # 第一组没出错，直接进入第二组，轮次重新从 1 开始。
    assert first_group["status"] == "in_progress"
    assert first_group["targetEntryIds"] == [gamma, delta]
    assert first_group["currentIndex"] == 0
    assert first_group["roundNo"] == 1

    answer(client, token, attempt["id"], "gamma")
    finished = answer(client, token, attempt["id"], "delta")
    assert finished["status"] == "completed"
    assert finished["score"] == 4


def test_without_repeat_until_correct_a_wrong_answer_still_advances(client: TestClient) -> None:
    token = login(client)
    library = make_library(client, token, ["alpha", "beta"], "Repeat Library D")
    task = make_task(client, token, library, repeat_until_correct=False, mode="fixed")
    attempt = start_attempt(client, token, task["id"])
    assert attempt["targetEntryIds"] == []

    wrong = answer(client, token, attempt["id"], "alpah")
    assert wrong["currentIndex"] == 1
    assert wrong["score"] == 0

    finished = answer(client, token, attempt["id"], "beta")
    assert finished["status"] == "completed"
    assert finished["score"] == 1
    assert finished["total"] == 2
