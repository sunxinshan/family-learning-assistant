from io import BytesIO

from fastapi import APIRouter, Depends, status
from fastapi.responses import StreamingResponse
from openpyxl import Workbook
from sqlalchemy.orm import Session

from app.core.database import get_session
from app.core.security import RuntimeContext, get_runtime_context
from app.modules.content.repository import ContentRepository
from app.modules.content.schemas import ContentExtractionOut, ContentExtractionUpdate
from app.modules.content.service import ContentService
from app.modules.material.repository import MaterialRepository
from app.modules.vocabulary.schemas import VocabularyOut

router = APIRouter(tags=["content"])


def get_content_service(session: Session = Depends(get_session)) -> ContentService:
    return ContentService(ContentRepository(session), MaterialRepository(session))


@router.get("/vocabularies/import-template")
def download_template(_: RuntimeContext = Depends(get_runtime_context)) -> StreamingResponse:
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "词库导入"
    sheet.append(["单词", "音标", "词性", "词义", "例句", "例句翻译"])
    sheet.append(
        [
            "serendipity",
            "/ˌserənˈdɪpəti/",
            "n.",
            "机缘巧合；意外发现美好事物的能力",
            "Finding this café was pure serendipity.",
            "发现这家咖啡馆纯属机缘巧合。",
        ]
    )
    sheet.append(
        [
            "resilient",
            "/rɪˈzɪliənt/",
            "adj.",
            "有韧性的；能迅速恢复的",
            "Children are often remarkably resilient.",
            "孩子往往有惊人的恢复力。",
        ]
    )
    stream = BytesIO()
    workbook.save(stream)
    return StreamingResponse(
        BytesIO(stream.getvalue()),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": 'attachment; filename="vocabulary-template.xlsx"'},
    )


@router.post(
    "/materials/{material_id}/extractions",
    response_model=ContentExtractionOut,
    status_code=status.HTTP_201_CREATED,
)
def create_extraction(
    material_id: str,
    context: RuntimeContext = Depends(get_runtime_context),
    service: ContentService = Depends(get_content_service),
) -> ContentExtractionOut:
    extraction = service.extract(material_id, context.user_id, context.role)
    return ContentExtractionOut.model_validate(extraction)


@router.get("/content/extractions/{extraction_id}", response_model=ContentExtractionOut)
def get_extraction(
    extraction_id: str,
    context: RuntimeContext = Depends(get_runtime_context),
    service: ContentService = Depends(get_content_service),
) -> ContentExtractionOut:
    return ContentExtractionOut.model_validate(
        service.get_owned(extraction_id, context.user_id, context.role)
    )


@router.patch("/content/extractions/{extraction_id}", response_model=ContentExtractionOut)
def update_extraction(
    extraction_id: str,
    payload: ContentExtractionUpdate,
    context: RuntimeContext = Depends(get_runtime_context),
    service: ContentService = Depends(get_content_service),
) -> ContentExtractionOut:
    return ContentExtractionOut.model_validate(
        service.update(extraction_id, context.user_id, context.role, payload)
    )


@router.post(
    "/content/extractions/{extraction_id}/confirm",
    response_model=VocabularyOut,
    status_code=status.HTTP_201_CREATED,
)
def confirm_extraction(
    extraction_id: str,
    version: int,
    context: RuntimeContext = Depends(get_runtime_context),
    service: ContentService = Depends(get_content_service),
) -> VocabularyOut:
    return service.confirm(extraction_id, context.user_id, context.role, version)
