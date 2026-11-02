from fastapi.testclient import TestClient
from pydantic import SecretStr, ValidationError

from app.core.config import Settings


def login(client: TestClient, nickname: str, password: str) -> dict:
    response = client.post("/api/v1/auth/login", json={"nickname": nickname, "password": password})
    assert response.status_code == 200, response.text
    return response.json()


def auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def test_refresh_rotation_reuse_and_logout(client: TestClient) -> None:
    session = login(client, "Alice", "demo123")
    rotated = client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": session["refresh_token"]},
    )
    assert rotated.status_code == 200, rotated.text
    new_session = rotated.json()
    assert new_session["refresh_token"] != session["refresh_token"]
    assert new_session["access_token"] != session["access_token"]

    reused = client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": session["refresh_token"]},
    )
    assert reused.status_code == 401

    assert (
        client.get("/api/v1/users/me", headers=auth(new_session["access_token"])).status_code == 200
    )
    logout = client.post(
        "/api/v1/auth/logout",
        json={"refresh_token": new_session["refresh_token"]},
    )
    assert logout.status_code == 204
    revoked = client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": new_session["refresh_token"]},
    )
    assert revoked.status_code == 401


def test_invalid_and_disabled_tokens_are_rejected(client: TestClient) -> None:
    assert client.get("/api/v1/users/me", headers=auth("not-a-jwt")).status_code == 401
    bob = login(client, "Bob", "demo123")
    admin = login(client, "Admin", "admin123")
    users = client.get("/api/v1/admin/users", headers=auth(admin["access_token"])).json()
    bob_id = next(item["id"] for item in users if item["nickname"] == "Bob")
    assert (
        client.patch(
            f"/api/v1/admin/users/{bob_id}/status",
            headers=auth(admin["access_token"]),
            json={"status": "disabled"},
        ).status_code
        == 200
    )
    assert client.get("/api/v1/users/me", headers=auth(bob["access_token"])).status_code == 401


def test_security_headers_and_runtime_metrics(client: TestClient) -> None:
    health = client.get("/api/v1/health/live")
    assert health.headers["X-Content-Type-Options"] == "nosniff"
    assert health.headers["X-Frame-Options"] == "DENY"
    assert health.headers["Referrer-Policy"] == "no-referrer"
    assert health.headers["X-Request-ID"]
    metrics = client.get("/api/v1/health/metrics")
    assert metrics.status_code == 200
    body = metrics.json()
    assert body["requestsTotal"] >= 1
    assert body["errorsTotal"] == 0
    assert body["latencyMaxMs"] >= 0


def test_upload_size_limit_is_enforced(client: TestClient) -> None:
    token = login(client, "Alice", "demo123")["access_token"]
    oversized = b"a" * (10 * 1024 * 1024 + 1)
    response = client.post(
        "/api/v1/materials",
        headers=auth(token),
        files={"file": ("large.csv", oversized, "text/csv")},
    )
    assert response.status_code == 413
    assert response.json()["error"]["code"] == "file_too_large"


def test_production_configuration_rejects_demo_secret_and_seed() -> None:
    try:
        Settings(
            _env_file=None,
            environment="production",
            database_url="mysql+pymysql://user:pass@localhost/db",
            jwt_secret=SecretStr("dev-only-change-me-use-at-least-32-bytes"),
            seed_demo_data=False,
        )
    except ValidationError:
        pass
    else:
        raise AssertionError("production accepted the development JWT secret")

    try:
        Settings(
            _env_file=None,
            environment="production",
            database_url="mysql+pymysql://user:pass@localhost/db",
            jwt_secret=SecretStr("a-production-secret-that-is-long-enough-123"),
            seed_demo_data=True,
        )
    except ValidationError:
        pass
    else:
        raise AssertionError("production accepted demo seeding")


def test_bootstrap_admins_are_created_without_demo_seed(settings) -> None:
    from app.main import create_app

    configured = settings.model_copy(
        update={
            "seed_demo_data": False,
            "bootstrap_admin_1_nickname": "BootstrapAdmin",
            "bootstrap_admin_1_password": SecretStr("bootstrap-admin-password"),
            "bootstrap_admin_2_nickname": "BootstrapManager",
            "bootstrap_admin_2_password": SecretStr("bootstrap-manager-password"),
        }
    )
    with TestClient(create_app(configured)) as client:
        for nickname, password in (
            ("BootstrapAdmin", "bootstrap-admin-password"),
            ("BootstrapManager", "bootstrap-manager-password"),
        ):
            response = client.post(
                "/api/v1/auth/login", json={"nickname": nickname, "password": password}
            )
            assert response.status_code == 200, response.text
            assert response.json()["user"]["role"] == "admin"
