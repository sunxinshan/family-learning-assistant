"""Rename legacy English Forest tables before installing the new schema."""

import os

from sqlalchemy import create_engine, inspect, text

TRACKED_PREFIXES = ("checkpoint", "legacy_")


def main() -> None:
    url = os.environ.get("LEGACY_DATABASE_URL")
    if not url:
        raise SystemExit("LEGACY_DATABASE_URL is required")
    engine = create_engine(url)
    with engine.begin() as connection:
        tables = inspect(connection).get_table_names()
        if "legacy_users" in tables:
            print("legacy schema already prepared")
            return
        targets = [name for name in tables if not name.startswith(TRACKED_PREFIXES)]
        if not targets:
            raise SystemExit("no legacy tables found")
        connection.execute(text("SET FOREIGN_KEY_CHECKS=0"))
        clauses = ", ".join(f"`{name}` TO `legacy_{name}`" for name in targets)
        connection.execute(text(f"RENAME TABLE {clauses}"))
        connection.execute(text("SET FOREIGN_KEY_CHECKS=1"))
        print(f"renamed {len(targets)} legacy tables")
    engine.dispose()


if __name__ == "__main__":
    main()
