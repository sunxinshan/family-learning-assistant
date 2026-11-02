from datetime import UTC, datetime

from fastapi import UploadFile

from app.core.config import Settings
from app.core.exceptions import AppError
from app.core.models import new_id
from app.infrastructure.storage import LocalFileStorage
from app.modules.material.models import Material
from app.modules.material.repository import MaterialRepository


class MaterialService:
    def __init__(self, repository: MaterialRepository, settings: Settings) -> None:
        self.repository = repository
        self.storage = LocalFileStorage(settings.upload_dir, settings.max_upload_bytes)

    async def upload(self, user_id: str, file: UploadFile) -> Material:
        storage_key, size, checksum = await self.storage.save(file, user_id)
        now = datetime.now(UTC)
        return self.repository.add(
            Material(
                id=new_id(),
                user_id=user_id,
                original_filename=file.filename or "upload",
                mime_type=file.content_type or "",
                size_bytes=size,
                storage_key=storage_key,
                checksum=checksum,
                status="uploaded",
                created_at=now,
                updated_at=now,
            )
        )

    def get_owned(self, material_id: str, user_id: str, role: str) -> Material:
        material = self.repository.get(material_id)
        if not material:
            raise AppError("material_not_found", "文件不存在", status_code=404)
        if material.user_id != user_id and role != "admin":
            raise AppError("forbidden", "你无权访问该文件", status_code=403)
        return material
