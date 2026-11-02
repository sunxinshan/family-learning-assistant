import sqlite3
from contextlib import AbstractContextManager
from pathlib import Path
from types import TracebackType

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.checkpoint.sqlite import SqliteSaver

from app.core.config import Settings


class CheckpointerManager(AbstractContextManager[BaseCheckpointSaver]):
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._sqlite_connection: sqlite3.Connection | None = None
        self._mysql_context: AbstractContextManager[BaseCheckpointSaver] | None = None
        self.saver: BaseCheckpointSaver | None = None

    def __enter__(self) -> BaseCheckpointSaver:
        if self.settings.checkpoint_backend == "mysql":
            from langgraph.checkpoint.mysql.pymysql import PyMySQLSaver

            self._mysql_context = PyMySQLSaver.from_conn_string(self.settings.checkpoint_url or "")
            self.saver = self._mysql_context.__enter__()
        else:
            path = Path(self.settings.checkpoint_sqlite_path)
            path.parent.mkdir(parents=True, exist_ok=True)
            self._sqlite_connection = sqlite3.connect(path, check_same_thread=False)
            self.saver = SqliteSaver(self._sqlite_connection)
        self.saver.setup()
        return self.saver

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        if self._mysql_context:
            self._mysql_context.__exit__(exc_type, exc_value, traceback)
        if self._sqlite_connection:
            self._sqlite_connection.close()
        self.saver = None
