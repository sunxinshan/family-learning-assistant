from typing import Any

from pydantic import Field

from app.api.schemas import CamelModel


class AgentRunRequest(CamelModel):
    message: str = Field(min_length=1, max_length=10000)


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
