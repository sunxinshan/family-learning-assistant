from datetime import UTC, datetime
from pathlib import Path

from app.core.exceptions import AppError
from app.core.models import new_id
from app.modules.content.enrichment import enrich_vocabulary_entries
from app.modules.content.models import ContentExtraction
from app.modules.content.parser import HeaderAnalyzer, parse_vocabulary
from app.modules.content.repository import ContentRepository
from app.modules.content.schemas import ContentExtractionUpdate
from app.modules.material.service import MaterialService
from app.modules.vocabulary.schemas import VocabularyCreate, VocabularyOut
from app.modules.vocabulary.service import VocabularyService, vocabulary_to_out


class ContentService:
    def __init__(
        self,
        repository: ContentRepository,
        material_service: MaterialService,
        vocabulary_service: VocabularyService,
        header_analyzer: HeaderAnalyzer | None = None,
    ) -> None:
        self.repository = repository
        self.material_service = material_service
        self.vocabulary_service = vocabulary_service
        self.header_analyzer = header_analyzer

    def extract(
        self, material_id: str, user_id: str, role: str, subject: str = "english"
    ) -> ContentExtraction:
        material = self.material_service.get_owned(material_id, user_id, role)
        draft, errors, mapping = parse_vocabulary(
            Path(material.storage_key),
            material.original_filename,
            self.header_analyzer,
            subject,
        )
        entries, enrichment_errors, enrichment = enrich_vocabulary_entries(
            draft["entries"], self.header_analyzer
        )
        draft["entries"] = entries
        errors.extend(enrichment_errors)
        mapping["enrichment"] = enrichment
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
            mapping_json=mapping,
            mapping_source=str(mapping.get("source", "rules")),
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
        library = self.vocabulary_service.create(user_id, role, draft)
        extraction.status = "confirmed"
        extraction.confirmed_at = datetime.now(UTC)
        extraction.updated_at = extraction.confirmed_at
        return vocabulary_to_out(library)
