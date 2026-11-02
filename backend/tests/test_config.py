import pytest
from pydantic import ValidationError

from app.core.config import Settings


def test_invalid_database_scheme_is_rejected() -> None:
    with pytest.raises(ValidationError):
        Settings(_env_file=None, database_url="postgresql://localhost/test")


def test_sqlite_and_mysql_urls_are_accepted() -> None:
    sqlite = Settings(_env_file=None, database_url="sqlite:///./data/test.db")
    mysql = Settings(
        _env_file=None,
        database_url="mysql+pymysql://user:password@localhost/test",
    )

    assert sqlite.database_url.startswith("sqlite")
    assert mysql.database_url.startswith("mysql+pymysql")
