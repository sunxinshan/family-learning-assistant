from datetime import datetime

from app.api.schemas import CamelModel


class MaterialOut(CamelModel):
    id: str
    original_filename: str
    mime_type: str
    size_bytes: int
    status: str
    created_at: datetime
