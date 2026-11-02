from datetime import datetime
from typing import Any

from pydantic import Field

from app.api.schemas import CamelModel


class AgentRunRequest(CamelModel):
    message: str = Field(min_length=1, max_length=10000)
    material_id: str | None = None


class ActionUpdateRequest(CamelModel):
    action: dict[str, Any]


class ActionConfirmRequest(CamelModel):
    draft_version: int
    config_hash: str


class AgentRunOut(CamelModel):
    id: str
    conversation_id: str
    status: str
    pending_action: dict[str, Any] | None
    draft_version: int
    config_hash: str | None


class AgentRunDetailOut(AgentRunOut):
    user_id: str
    prompt_version: str | None
    token_usage: dict[str, Any] | None
    error_message: str | None
    duration_ms: int
    events: list[dict[str, Any]]
    available_tools: list[dict[str, str]]
    created_at: datetime
    updated_at: datetime
