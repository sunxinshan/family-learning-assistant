from fastapi.testclient import TestClient

from tests.test_phase5_regression import auth, create_library, create_task, login


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


def make_task(
    client: TestClient, token: str, *, repeat_until_correct: bool, words_per_group: int = 1
) -> tuple[dict, dict]:
    library = create_library(client, token, name=f"Streak Library {repeat_until_correct}")
    task = create_task(client, token, library, mode="fixed")
    response = client.patch(
        f"/api/v1/tasks/{task['id']}",
        headers=auth(token),
        json={"name": task["name"], "repeatUntilCorrect": repeat_until_correct},
    )
    assert response.status_code == 200, response.text
    return library, response.json()


def test_repeat_until_correct_keeps_the_word_until_two_in_a_row(client: TestClient) -> None:
    token = login(client)
    library, task = make_task(client, token, repeat_until_correct=True)
    attempt = start_attempt(client, token, task["id"])
    assert attempt["total"] == 2
    assert attempt["currentIndex"] == 0

    # 拼错：停在本词，不进入下一个词。
    wrong = answer(client, token, attempt["id"], "alpah")
    assert wrong["currentIndex"] == 0
    assert wrong["answers"][-1]["correct"] is False
    assert wrong["answers"][-1]["snapshotEntryId"] == task["snapshot"][0]["id"]

    # 第一次拼对：连续正确只有 1 次，仍停在本词。
    first_ok = answer(client, token, attempt["id"], "alpha")
    assert first_ok["currentIndex"] == 0
    assert first_ok["answers"][-1]["correct"] is True

    # 第二次连续拼对：才放行到第二个词。
    second_ok = answer(client, token, attempt["id"], "alpha")
    assert second_ok["currentIndex"] == 1
    assert second_ok["status"] == "in_progress"

    # 同一个词的三次作答序号必须是递增的唯一值。
    sequences = [item["id"] for item in second_ok["answers"]]
    assert len(sequences) == len(set(sequences)) == 3

    answer(client, token, attempt["id"], "beta")
    finished = answer(client, token, attempt["id"], "beta")
    assert finished["currentIndex"] == 2
    assert finished["status"] == "completed"
    assert finished["score"] == 2
    assert finished["total"] == 2


def test_repeat_until_correct_resets_the_streak_after_a_wrong_answer(client: TestClient) -> None:
    token = login(client)
    _library, task = make_task(client, token, repeat_until_correct=True)
    attempt = start_attempt(client, token, task["id"])

    # 对 → 错 → 对：错的那次把连续正确清零，所以第二次拼对仍然过不了。
    answer(client, token, attempt["id"], "alpha")
    reset = answer(client, token, attempt["id"], "alpah")
    assert reset["currentIndex"] == 0
    third = answer(client, token, attempt["id"], "alpha")
    assert third["currentIndex"] == 0

    passed = answer(client, token, attempt["id"], "alpha")
    assert passed["currentIndex"] == 1


def test_without_repeat_until_correct_a_wrong_answer_still_advances(client: TestClient) -> None:
    token = login(client)
    _library, task = make_task(client, token, repeat_until_correct=False)
    attempt = start_attempt(client, token, task["id"])

    wrong = answer(client, token, attempt["id"], "alpah")
    assert wrong["currentIndex"] == 1
    assert wrong["score"] == 0

    finished = answer(client, token, attempt["id"], "beta")
    assert finished["status"] == "completed"
    assert finished["score"] == 1
    assert finished["total"] == 2
