from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.core.database import Base, Database
from app.main import create_app


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    settings = Settings(
        _env_file=None,
        environment="test",
        database_url=f"sqlite:///{tmp_path / 'test.db'}",
        log_format="console",
        log_level="WARNING",
        seed_demo_data=True,
        checkpoint_sqlite_path=str(tmp_path / "checkpoints.db"),
    )
    database = Database(settings)
    Base.metadata.create_all(database.engine)
    database.dispose()
    return settings


@pytest.fixture
def app(settings: Settings) -> FastAPI:
    return create_app(settings)


@pytest.fixture
def client(app: FastAPI) -> Iterator[TestClient]:
    with TestClient(app) as test_client:
        yield test_client
