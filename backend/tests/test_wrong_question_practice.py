from fastapi.testclient import TestClient


def login(client: TestClient) -> str:
    response = client.post(
        "/api/v1/auth/login",
        json={"nickname": "Alice", "password": "demo123"},
    )
    assert response.status_code == 200, response.text
    return response.json()["access_token"]


def auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def create_library(client: TestClient, words: list[str]) -> dict:
    response = client.post(
        "/api/v1/vocabularies",
        headers=auth(login(client)),
        json={
            "subject": "english",
            "name": "Wrong question words",
            "description": "",
            "tags": [],
            "entries": [
                {
                    "word": word,
                    "phonetic": f"/{word}/",
                    "partOfSpeech": "n.",
                    "meanings": [word],
                    "example": f"Example {word}.",
                    "exampleTranslation": f"例句 {word}。",
                }
                for word in words
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
    words_per_group: int = 2,
) -> dict:
    response = client.post(
        "/api/v1/tasks",
        headers=auth(token),
        json={
            "name": "Wrong question review",
            "type": "dictation",
            "mode": mode,
            "libraryId": library["id"],
            "selectedEntryIds": [entry["id"] for entry in library["entries"]],
            "wordsPerGroup": words_per_group,
            "repeatUntilCorrect": False,
            "dictation": {
                "mode": "online",
                "playbackMode": "manual",
                "intervalSeconds": 5,
                "hint": "phonetic",
                "repeatCount": 1,
            },
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def submit_all(client: TestClient, token: str, task: dict, wrong_indexes: set[int]) -> dict:
    attempt = client.post(
        f"/api/v1/tasks/{task['id']}/attempts",
        headers=auth(token),
    )
    assert attempt.status_code == 200, attempt.text
    attempt_id = attempt.json()["id"]
    result = None
    for index, entry in enumerate(task["snapshot"]):
        given = f"wrong-{index}" if index in wrong_indexes else entry["word"]
        response = client.post(
            f"/api/v1/attempts/{attempt_id}/answers",
            headers=auth(token),
            json={"given": given, "durationMs": 100},
        )
        assert response.status_code == 200, response.text
        result = response.json()
    assert result is not None
    return result


def test_wrong_questions_clear_after_two_consecutive_correct_answers(client: TestClient) -> None:
    token = login(client)
    library = create_library(client, ["alpha", "bravo", "charlie"])
    task = create_task(client, token, library)
    submit_all(client, token, task, {0})

    wrong = client.get(
        f"/api/v1/tasks/{task['id']}/wrong-questions",
        headers=auth(token),
    )
    assert wrong.status_code == 200, wrong.text
    body = wrong.json()
    assert body["total"] == 1
    assert body["requiredCorrectStreak"] == 2
    assert body["groups"][0]["entries"][0]["word"] == "alpha"
    assert body["groups"][0]["entries"][0]["consecutiveCorrect"] == 0

    first_review = client.post(
        f"/api/v1/tasks/{task['id']}/wrong-attempts",
        headers=auth(token),
    )
    assert first_review.status_code == 200, first_review.text
    assert first_review.json()["kind"] == "wrong"
    assert first_review.json()["total"] == 1
    assert first_review.json()["targetEntryIds"] == [task["snapshot"][0]["id"]]
    first_answer = client.post(
        f"/api/v1/attempts/{first_review.json()['id']}/answers",
        headers=auth(token),
        json={"given": "alpha", "durationMs": 100},
    )
    assert first_answer.status_code == 200, first_answer.text

    still_wrong = client.get(
        f"/api/v1/tasks/{task['id']}/wrong-questions",
        headers=auth(token),
    ).json()
    assert still_wrong["total"] == 1
    assert still_wrong["groups"][0]["entries"][0]["consecutiveCorrect"] == 1

    second_review = client.post(
        f"/api/v1/tasks/{task['id']}/wrong-attempts",
        headers=auth(token),
    )
    assert second_review.status_code == 200, second_review.text
    second_answer = client.post(
        f"/api/v1/attempts/{second_review.json()['id']}/answers",
        headers=auth(token),
        json={"given": "alpha", "durationMs": 100},
    )
    assert second_answer.status_code == 200, second_answer.text

    cleared = client.get(
        f"/api/v1/tasks/{task['id']}/wrong-questions",
        headers=auth(token),
    ).json()
    assert cleared["total"] == 0
    assert cleared["groups"] == []
    no_questions = client.post(
        f"/api/v1/tasks/{task['id']}/wrong-attempts",
        headers=auth(token),
    )
    assert no_questions.status_code == 409
    assert no_questions.json()["error"]["code"] == "no_wrong_questions"


def test_long_term_wrong_questions_follow_original_group_numbers(client: TestClient) -> None:
    token = login(client)
    library = create_library(client, ["one", "two", "three", "four"])
    task = create_task(client, token, library, mode="long_term", words_per_group=2)
    submit_all(client, token, task, {0, 2})

    response = client.get(
        f"/api/v1/tasks/{task['id']}/wrong-questions",
        headers=auth(token),
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["total"] == 2
    assert [group["groupIndex"] for group in body["groups"]] == [1, 2]
    assert [group["entries"][0]["word"] for group in body["groups"]] == [
        "one",
        "three",
    ]

    wrong_attempt = client.post(
        f"/api/v1/tasks/{task['id']}/wrong-attempts",
        headers=auth(token),
    )
    assert wrong_attempt.status_code == 200, wrong_attempt.text
    assert wrong_attempt.json()["targetEntryIds"] == [
        task["snapshot"][0]["id"],
        task["snapshot"][2]["id"],
    ]
