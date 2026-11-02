from fastapi.testclient import TestClient


def test_live_health(client: TestClient) -> None:
    response = client.get("/api/v1/health/live")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    assert response.json()["environment"] == "test"
    assert response.headers["X-Request-ID"]


def test_ready_health_checks_database(client: TestClient) -> None:
    response = client.get("/api/v1/health/ready")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_request_id_header_is_echoed(client: TestClient) -> None:
    response = client.get(
        "/api/v1/health/live",
        headers={"X-Request-ID": "test-request-123"},
    )

    assert response.headers["X-Request-ID"] == "test-request-123"
