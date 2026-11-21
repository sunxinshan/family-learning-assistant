from datetime import datetime
from typing import Any

from app.api.schemas import CamelModel
from app.modules.learning.schemas import LearningStatsOut
from app.modules.user.schemas import UserPublic


class AdminUserOut(UserPublic):
    practice_count: int
    accuracy: int


class UserStatusUpdate(CamelModel):
    status: str


class OperationLogOut(CamelModel):
    id: str
    actor_user_id: str
    action: str
    target_type: str
    target_id: str | None
    target_name: str
    result: str
    created_at: datetime


class ResetPasswordOut(CamelModel):
    nickname: str
    temporary_password: str


class AdminLearningStatsOut(LearningStatsOut):
    pass


class CheckpointThreadOut(CamelModel):
    thread_id: str
    checkpoint_count: int
    latest_checkpoint_id: str
    latest_step: int | None = None


class CheckpointListItemOut(CamelModel):
    thread_id: str
    checkpoint_ns: str
    checkpoint_id: str
    parent_checkpoint_id: str | None = None
    step: int | None = None
    source: str | None = None
    size_bytes: int


class CheckpointListOut(CamelModel):
    items: list[CheckpointListItemOut]
    total: int
    threads: list[CheckpointThreadOut]


class CheckpointWriteOut(CamelModel):
    task_id: str
    idx: int
    channel: str
    type: str | None = None
    value: Any = None


class CheckpointDetailOut(CamelModel):
    thread_id: str
    checkpoint_ns: str
    checkpoint_id: str
    parent_checkpoint_id: str | None = None
    step: int | None = None
    source: str | None = None
    size_bytes: int
    channel_values: dict[str, Any]
    metadata: dict[str, Any]
    writes: list[CheckpointWriteOut]


class ReplaySourceOut(CamelModel):
    thread_id: str
    checkpoint_id: str
    step: int | None = None
    next: list[str]
    route: str | None = None
    response: str | None = None
    pending_action: dict[str, Any] | None = None
    prompt_version: str | None = None


class ReplayRunOut(CamelModel):
    thread_id: str
    route: str | None = None
    response: str | None = None
    pending_action: dict[str, Any] | None = None
    token_usage: dict[str, int] | None = None
    duration_ms: int
    prompt_version: str
    model: str
    checkpoint_rows_added: int


class ReplayDiffOut(CamelModel):
    route_changed: bool
    response_changed: bool
    pending_action_changed: bool


class CheckpointReplayOut(CamelModel):
    source: ReplaySourceOut
    replay: ReplayRunOut
    diff: ReplayDiffOut
