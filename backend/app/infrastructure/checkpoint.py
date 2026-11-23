import sqlite3
from contextlib import AbstractContextManager
from pathlib import Path
from types import TracebackType

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.checkpoint.sqlite import SqliteSaver

from app.core.config import Settings
from app.core.exceptions import AppError


def checkpoint_not_found_error() -> AppError:
    """「这个 checkpoint 不存在」——唯一来源，避免三处文案各写一遍。"""
    return AppError("checkpoint_not_found", "Checkpoint 不存在", status_code=404)


def checkpoint_store_unavailable_error() -> AppError:
    """「checkpoint 库连不上 / 读不了」——与「不存在」必须是两个错误码。

    管理员看到 404 会以为数据丢了，看到 503 才知道是库的问题。
    """
    return AppError(
        "checkpoint_store_unavailable",
        "Checkpoint 存储暂不可用，请稍后重试或检查 checkpoint 数据库连接",
        status_code=503,
    )


class CheckpointerManager(AbstractContextManager[BaseCheckpointSaver]):
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._sqlite_connection: sqlite3.Connection | None = None
        self._mysql_context: AbstractContextManager[BaseCheckpointSaver] | None = None
        self._closed = False
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

    def close(self) -> None:
        """幂等关闭：谁最后用完谁关，重复调用无副作用。

        重放超时后连接可能仍被孤儿线程使用，此时不能由请求线程关 ——
        由 ``AgentRuntime`` 在孤儿线程真正结束后回调本方法（见 T-FIX-04）。
        """
        if self._closed:
            return
        self._closed = True
        try:
            if self._mysql_context is not None:
                self._mysql_context.__exit__(None, None, None)
                self._mysql_context = None
            if self._sqlite_connection is not None:
                self._sqlite_connection.close()
                self._sqlite_connection = None
        finally:
            self.saver = None

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.close()
