"""管理后台用的 checkpoint 只读视图。

checkpoint 数据存放在独立的库（本地 SQLite / 生产 MySQL），与业务库分离，
这里只做查询与反序列化，不写数据、不建表、不清理。

列表页不解析 checkpoint BLOB，只取元信息；详情页才反序列化 channel_values，
避免一次拉取几十条大对象。返回给管理端前统一走 redact() 脱敏。
"""

from __future__ import annotations

import json
import logging
from functools import lru_cache
from pathlib import Path
from typing import Any

from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import SQLAlchemyError

from app.core.config import Settings
from app.modules.agent.redaction import redact

logger = logging.getLogger(__name__)

_EMPTY: dict[str, Any] = {"items": [], "total": 0, "threads": []}

# 这些键名字里带 token，但只是用量统计，不含任何凭证；调试时恰恰需要看到。
_VISIBLE_SECRET_LIKE_KEYS = frozenset({"token_usage", "token_count"})


@lru_cache(maxsize=4)
def _engine_for(url: str) -> Engine:
    return create_engine(url, pool_pre_ping=True)


class CheckpointRepository:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.serde = JsonPlusSerializer()

    # --- 连接 -------------------------------------------------------------
    def _url(self) -> str | None:
        """checkpoint 库地址；SQLite 文件不存在时返回 None（不创建文件）。"""
        if self.settings.checkpoint_backend == "mysql":
            return self.settings.checkpoint_url or None
        path = Path(self.settings.checkpoint_sqlite_path).expanduser()
        if not path.is_absolute():
            path = Path.cwd() / path
        if not path.exists():
            return None
        return f"sqlite:///{path}"

    # --- 反序列化 ---------------------------------------------------------
    def _metadata(self, raw: Any) -> dict[str, Any]:
        if not raw:
            return {}
        if isinstance(raw, (bytes, bytearray)):
            raw = bytes(raw).decode("utf-8", "replace")
        try:
            value = json.loads(raw)
        except (TypeError, ValueError):
            return {}
        return value if isinstance(value, dict) else {}

    def _decode(self, kind: Any, raw: Any) -> Any:
        if not raw or not kind:
            return None
        try:
            return self.serde.loads_typed((str(kind), bytes(raw)))
        except Exception:  # noqa: BLE001 - 单条数据损坏不应让整个管理页 500
            logger.warning("checkpoint payload deserialize failed", exc_info=True)
            return None

    # --- 查询 -------------------------------------------------------------
    def list_threads(self, limit: int = 100) -> list[dict[str, Any]]:
        url = self._url()
        if url is None:
            return []
        try:
            with _engine_for(url).connect() as conn:
                rows = (
                    conn.execute(
                        text(
                            "select thread_id, count(*) as n, max(checkpoint_id) as latest "
                            "from checkpoints group by thread_id "
                            "order by latest desc limit :limit"
                        ),
                        {"limit": limit},
                    )
                    .mappings()
                    .all()
                )
                if not rows:
                    return []
                latest_rows = (
                    conn.execute(
                        text(
                            "select thread_id, metadata from ("
                            "  select thread_id, metadata, row_number() over ("
                            "    partition by thread_id order by checkpoint_id desc"
                            "  ) as rn from checkpoints"
                            ") t where rn = 1"
                        )
                    )
                    .mappings()
                    .all()
                )
        except SQLAlchemyError:
            logger.warning("checkpoint threads query failed", exc_info=True)
            return []
        steps = {
            row["thread_id"]: self._metadata(row["metadata"]).get("step") for row in latest_rows
        }
        return [
            {
                "thread_id": row["thread_id"],
                "checkpoint_count": int(row["n"]),
                "latest_checkpoint_id": row["latest"],
                "latest_step": steps.get(row["thread_id"]),
            }
            for row in rows
        ]

    def list(self, thread_id: str | None, limit: int, offset: int) -> dict[str, Any]:
        url = self._url()
        if url is None:
            return dict(_EMPTY)
        where = "where thread_id = :thread_id" if thread_id else ""
        params: dict[str, Any] = {"limit": limit, "offset": offset}
        count_params: dict[str, Any] = {}
        if thread_id:
            params["thread_id"] = thread_id
            count_params["thread_id"] = thread_id
        try:
            with _engine_for(url).connect() as conn:
                total = conn.execute(
                    text(f"select count(*) from checkpoints {where}"), count_params
                ).scalar_one()
                rows = (
                    conn.execute(
                        text(
                            "select thread_id, checkpoint_ns, checkpoint_id, "
                            "parent_checkpoint_id, type, metadata, "
                            "length(checkpoint) as size_bytes "
                            f"from checkpoints {where} "
                            "order by checkpoint_id desc limit :limit offset :offset"
                        ),
                        params,
                    )
                    .mappings()
                    .all()
                )
        except SQLAlchemyError:
            logger.warning("checkpoint list query failed", exc_info=True)
            return dict(_EMPTY)
        items = []
        for row in rows:
            meta = self._metadata(row["metadata"])
            items.append(
                {
                    "thread_id": row["thread_id"],
                    "checkpoint_ns": row["checkpoint_ns"],
                    "checkpoint_id": row["checkpoint_id"],
                    "parent_checkpoint_id": row["parent_checkpoint_id"],
                    "step": meta.get("step"),
                    "source": meta.get("source"),
                    "size_bytes": int(row["size_bytes"] or 0),
                }
            )
        return {"items": items, "total": int(total), "threads": self.list_threads()}

    def get(self, thread_id: str, checkpoint_id: str) -> dict[str, Any] | None:
        url = self._url()
        if url is None:
            return None
        try:
            with _engine_for(url).connect() as conn:
                row = (
                    conn.execute(
                        text(
                            "select thread_id, checkpoint_ns, checkpoint_id, "
                            "parent_checkpoint_id, type, checkpoint, metadata, "
                            "length(checkpoint) as size_bytes from checkpoints "
                            "where thread_id = :thread_id and checkpoint_id = :checkpoint_id"
                        ),
                        {"thread_id": thread_id, "checkpoint_id": checkpoint_id},
                    )
                    .mappings()
                    .first()
                )
                if row is None:
                    return None
                write_rows = (
                    conn.execute(
                        text(
                            "select task_id, idx, channel, type, value from writes "
                            "where thread_id = :thread_id and checkpoint_id = :checkpoint_id "
                            "order by task_id, idx"
                        ),
                        {"thread_id": thread_id, "checkpoint_id": checkpoint_id},
                    )
                    .mappings()
                    .all()
                )
        except SQLAlchemyError:
            logger.warning("checkpoint detail query failed", exc_info=True)
            return None

        payload = self._decode(row["type"], row["checkpoint"]) or {}
        channel_values = payload.get("channel_values")
        if not isinstance(channel_values, dict):
            channel_values = {}
        meta = self._metadata(row["metadata"])
        return {
            "thread_id": row["thread_id"],
            "checkpoint_ns": row["checkpoint_ns"],
            "checkpoint_id": row["checkpoint_id"],
            "parent_checkpoint_id": row["parent_checkpoint_id"],
            "step": meta.get("step"),
            "source": meta.get("source"),
            "size_bytes": int(row["size_bytes"] or 0),
            "channel_values": redact(channel_values, allow_keys=_VISIBLE_SECRET_LIKE_KEYS),
            "metadata": redact(meta),
            "writes": [
                {
                    "task_id": write["task_id"],
                    "idx": int(write["idx"]),
                    "channel": write["channel"],
                    "type": write["type"],
                    "value": redact(self._decode(write["type"], write["value"])),
                }
                for write in write_rows
            ],
        }

    # --- 节点反查 / 统计 ---------------------------------------------------
    def routing_target(self, thread_id: str, checkpoint_id: str) -> str | None:
        """反查某个 checkpoint 上 ``branch:to:<node>`` 写入指向的**下一跳**节点。

        ⚠️ 返回的是「下一跳」，**不是**「产出该 checkpoint 的节点」。两者差一层：

        - ``routing_target(X)`` = X 之后要执行的节点（= X 的子 checkpoint 的 next）
        - 「产出 X 的节点」= X 的父快照的 next（自环时可能等于本值，但不要依赖）

        重放要的是后者，由 ``AgentRuntime.replay_from_checkpoint`` 自己从父快照取，
        **不要**用本方法当 ``as_node`` 锚点 —— 实测传错会让重放一个节点都不跑，
        还返回 200（见 .specs/checkpoint-replay/T02-SUMMARY.md「决策与偏离」1）。

        入参是**某个 checkpoint 的 id**，本方法只按这个 id 直接查 writes 表，不做二次查询。
        只命中一条时返回节点名；命中 0 条（终点/无分支）返回 None；命中多条
        （并行分支、自环）无法判定唯一节点，返回 None 并记 warning。
        """
        url = self._url()
        if url is None:
            return None
        try:
            with _engine_for(url).connect() as conn:
                channels = [
                    str(row[0])
                    for row in conn.execute(
                        text(
                            "select channel from writes "
                            "where thread_id = :thread_id and checkpoint_id = :checkpoint_id "
                            "and channel like 'branch:to:%'"
                        ),
                        {"thread_id": thread_id, "checkpoint_id": checkpoint_id},
                    )
                ]
        except SQLAlchemyError:
            logger.warning(
                "checkpoint producing node query failed thread_id=%s checkpoint_id=%s",
                thread_id,
                checkpoint_id,
                exc_info=True,
            )
            return None
        if len(channels) != 1:
            if len(channels) > 1:
                logger.warning(
                    "checkpoint has multiple branch writes thread_id=%s checkpoint_id=%s "
                    "channels=%s",
                    thread_id,
                    checkpoint_id,
                    channels,
                )
            return None
        return channels[0].split("branch:to:", 1)[1]

    def count_thread(self, thread_id: str) -> int:
        """该 thread 在 checkpoints 表的行数；库不可用时返回 0，不抛异常。"""
        url = self._url()
        if url is None:
            return 0
        try:
            with _engine_for(url).connect() as conn:
                total = conn.execute(
                    text("select count(*) from checkpoints where thread_id = :thread_id"),
                    {"thread_id": thread_id},
                ).scalar_one()
        except SQLAlchemyError:
            logger.warning(
                "checkpoint thread count query failed thread_id=%s", thread_id, exc_info=True
            )
            return 0
        return int(total)
