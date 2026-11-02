from datetime import datetime
from typing import Any

from app.api.schemas import CamelModel


class ConversationOut(CamelModel):
    id: str
    user_id: str
    title: str
    status: str
    messages: list[dict[str, Any]]
    created_at: datetime
    updated_at: datetime


class MessageAppend(CamelModel):
    message: dict[str, Any]
