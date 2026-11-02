from datetime import UTC, datetime
from pathlib import Path

from app.core.exceptions import AppError
from app.core.models import new_id
from app.modules.content.models import ContentExtraction
from app.modules.content.parser import parse_vocabulary
from app.modules.content.repository import ContentRepository
from app.modules.content.schemas import ContentExtractionUpdate
from app.modules.material.repository import MaterialRepository
from app.modules.vocabulary.repository import VocabularyRepository
from app.modules.vocabulary.schemas import VocabularyCreate, VocabularyOut
from app.modules.vocabulary.service import VocabularyService


class ContentService:
    def __init__(
        self,
        repository: ContentRepository,
        material_repository: MaterialRepository,
    ) -> None:
        self.repository = repository
        self.material_repository = material_repository

    def extract(self, material_id: str, user_id: str, role: str) -> ContentExtraction:
        material = self.material_repository.get(material_id)
        if not material:
            raise AppError("material_not_found", "文件不存在", status_code=404)
        if material.user_id != user_id and role != "admin":
            raise AppError("forbidden", "你无权解析该文件", status_code=403)
        draft, errors = parse_vocabulary(Path(material.storage_key), material.original_filename)
        now = datetime.now(UTC)
        extraction = ContentExtraction(
            id=new_id(),
            user_id=user_id,
            material_id=material.id,
            stage="preview",
            parser_type=Path(material.original_filename).suffix.lower().lstrip("."),
            status="previewed",
            extracted_json=draft,
            errors_json=errors,
            version=1,
            created_at=now,
            updated_at=now,
        )
        material.status = "parsed"
        return self.repository.add(extraction)

    def get_owned(self, extraction_id: str, user_id: str, role: str) -> ContentExtraction:
        extraction = self.repository.get(extraction_id)
        if not extraction:
            raise AppError("extraction_not_found", "解析结果不存在", status_code=404)
        if extraction.user_id != user_id and role != "admin":
            raise AppError("forbidden", "你无权访问该解析结果", status_code=403)
        return extraction

    def update(
        self,
        extraction_id: str,
        user_id: str,
        role: str,
        payload: ContentExtractionUpdate,
    ) -> ContentExtraction:
        extraction = self.get_owned(extraction_id, user_id, role)
        if extraction.version != payload.version:
            raise AppError("version_conflict", "预览版本已变化，请刷新后重试", status_code=409)
        extraction.extracted_json = payload.extracted_json
        extraction.version += 1
        extraction.updated_at = datetime.now(UTC)
        return extraction

    def confirm(
        self,
        extraction_id: str,
        user_id: str,
        role: str,
        version: int,
    ) -> VocabularyOut:
        extraction = self.get_owned(extraction_id, user_id, role)
        if extraction.status == "confirmed":
            raise AppError("already_confirmed", "该预览已确认", status_code=409)
        if extraction.version != version:
            raise AppError("version_conflict", "预览版本已变化，请刷新后重试", status_code=409)
        draft = VocabularyCreate.model_validate(extraction.extracted_json)
        service = VocabularyService(VocabularyRepository(self.repository.session))
        library = service.create(user_id, role, draft)
        extraction.status = "confirmed"
        extraction.confirmed_at = datetime.now(UTC)
        extraction.updated_at = extraction.confirmed_at
        return VocabularyOut.model_validate(library)
