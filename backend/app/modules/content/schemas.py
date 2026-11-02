from datetime import datetime
from typing import Any

from app.api.schemas import CamelModel


class ContentExtractionOut(CamelModel):
    id: str
    material_id: str
    stage: str
    parser_type: str
    status: str
    extracted_json: dict[str, Any]
    errors_json: list[Any]
    version: int
    confirmed_at: datetime | None
    created_at: datetime
    updated_at: datetime


class ContentExtractionUpdate(CamelModel):
    extracted_json: dict[str, Any]
    version: int
