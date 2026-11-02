from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine, make_url
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker
from sqlalchemy.pool import StaticPool
from starlette.requests import Request

from app.core.config import Settings


class Base(DeclarativeBase):
    pass


def _engine_options(database_url: str) -> dict[str, Any]:
    if database_url.startswith("sqlite"):
        database_path = make_url(database_url).database
        if database_path and database_path != ":memory:":
            path = Path(database_path).expanduser()
            if not path.is_absolute():
                path = Path.cwd() / path
            path.parent.mkdir(parents=True, exist_ok=True)
        options: dict[str, Any] = {"connect_args": {"check_same_thread": False}}
        if database_path == ":memory:":
            options["poolclass"] = StaticPool
        return options
    return {"pool_pre_ping": True, "pool_recycle": 1800}


class Database:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.engine: Engine = create_engine(
            settings.database_url,
            future=True,
            **_engine_options(settings.database_url),
        )
        if settings.database_url.startswith("sqlite"):

            @event.listens_for(self.engine, "connect")
            def _enable_sqlite_foreign_keys(dbapi_connection, _):
                cursor = dbapi_connection.cursor()
                cursor.execute("PRAGMA foreign_keys=ON")
                cursor.close()

        self.session_factory = sessionmaker(
            bind=self.engine,
            autoflush=False,
            expire_on_commit=False,
            class_=Session,
        )

    @contextmanager
    def session(self) -> Iterator[Session]:
        session = self.session_factory()
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def dispose(self) -> None:
        self.engine.dispose()


def get_session(request: Request) -> Iterator[Session]:
    database: Database = request.app.state.database
    with database.session() as session:
        yield session
