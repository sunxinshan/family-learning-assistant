from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.exceptions import AppError


def test_not_found_uses_error_envelope(client: TestClient) -> None:
    response = client.get("/does-not-exist")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"
    assert response.json()["error"]["request_id"]
    assert response.headers["X-Request-ID"]


def test_application_error_uses_error_envelope(app: FastAPI) -> None:
    @app.get("/_test/app-error")
    def raise_app_error() -> None:
        raise AppError(
            "business_rule_failed",
            "业务规则未满足",
            details={"field": "name"},
        )

    with TestClient(app) as client:
        response = client.get("/_test/app-error")

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "business_rule_failed"
    assert response.json()["error"]["details"] == {"field": "name"}


def test_validation_error_uses_error_envelope(app: FastAPI) -> None:
    @app.get("/_test/validation")
    def validation(required_value: int) -> dict[str, int]:
        return {"value": required_value}

    with TestClient(app) as client:
        response = client.get("/_test/validation")

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "request_validation_error"
    assert response.json()["error"]["details"]
