from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy.orm import Session

from app.core.database import get_session
from app.core.security import RuntimeContext, get_runtime_context, require_admin
from app.modules.vocabulary.repository import VocabularyRepository
from app.modules.vocabulary.schemas import (
    SubjectOut,
    VocabularyCreate,
    VocabularyOut,
    VocabularyUpdate,
    VocabularyVisibilityUpdate,
    WordEntryIn,
)
from app.modules.vocabulary.service import SUBJECTS, VocabularyService, vocabulary_to_out

router = APIRouter(tags=["vocabulary"])


def get_vocabulary_service(session: Session = Depends(get_session)) -> VocabularyService:
    return VocabularyService(VocabularyRepository(session))


@router.get("/subjects", response_model=list[SubjectOut])
def subjects(_: RuntimeContext = Depends(get_runtime_context)) -> list[SubjectOut]:
    return [SubjectOut(code=code, display_name=name) for code, name in SUBJECTS.items()]


@router.get("/vocabularies", response_model=list[VocabularyOut])
def list_vocabularies(
    scope: str = Query("mine", pattern="^(mine|public|available)$"),
    subject: str | None = None,
    context: RuntimeContext = Depends(get_runtime_context),
    service: VocabularyService = Depends(get_vocabulary_service),
) -> list[VocabularyOut]:
    if scope == "mine":
        items = service.list_mine(context.user_id)
    elif scope == "public":
        items = service.list_public(context.role, subject)
    else:
        items = service.list_available(context.user_id, subject)
    return [vocabulary_to_out(item) for item in items if not subject or item.subject == subject]


@router.post("/vocabularies", response_model=VocabularyOut, status_code=status.HTTP_201_CREATED)
def create_vocabulary(
    payload: VocabularyCreate,
    context: RuntimeContext = Depends(get_runtime_context),
    service: VocabularyService = Depends(get_vocabulary_service),
) -> VocabularyOut:
    return vocabulary_to_out(service.create(context.user_id, context.role, payload))


@router.get("/vocabularies/{library_id}", response_model=VocabularyOut)
def get_vocabulary(
    library_id: str,
    context: RuntimeContext = Depends(get_runtime_context),
    service: VocabularyService = Depends(get_vocabulary_service),
) -> VocabularyOut:
    return vocabulary_to_out(service.get_accessible(library_id, context.user_id, context.role))


@router.patch("/vocabularies/{library_id}", response_model=VocabularyOut)
def update_vocabulary(
    library_id: str,
    payload: VocabularyUpdate,
    context: RuntimeContext = Depends(get_runtime_context),
    service: VocabularyService = Depends(get_vocabulary_service),
) -> VocabularyOut:
    return vocabulary_to_out(service.update(library_id, context.user_id, context.role, payload))


@router.post("/vocabularies/{library_id}/copy", response_model=VocabularyOut, status_code=201)
def copy_vocabulary(
    library_id: str,
    context: RuntimeContext = Depends(get_runtime_context),
    service: VocabularyService = Depends(get_vocabulary_service),
) -> VocabularyOut:
    return vocabulary_to_out(service.copy(library_id, context.user_id, context.role))


@router.patch("/vocabularies/{library_id}/visibility", response_model=VocabularyOut)
def set_vocabulary_visibility(
    library_id: str,
    payload: VocabularyVisibilityUpdate,
    context: RuntimeContext = Depends(require_admin),
    service: VocabularyService = Depends(get_vocabulary_service),
) -> VocabularyOut:
    return vocabulary_to_out(
        service.set_visibility(library_id, context.user_id, context.role, payload.visibility)
    )


@router.delete("/vocabularies/{library_id}", status_code=204)
def delete_vocabulary(
    library_id: str,
    context: RuntimeContext = Depends(get_runtime_context),
    service: VocabularyService = Depends(get_vocabulary_service),
) -> Response:
    service.delete(library_id, context.user_id, context.role)
    return Response(status_code=204)


@router.post("/vocabularies/{library_id}/entries", response_model=VocabularyOut, status_code=201)
def add_entries(
    library_id: str,
    payload: list[WordEntryIn],
    context: RuntimeContext = Depends(get_runtime_context),
    service: VocabularyService = Depends(get_vocabulary_service),
) -> VocabularyOut:
    return vocabulary_to_out(
        service.add_entries(library_id, context.user_id, context.role, payload)
    )


@router.patch("/vocabularies/{library_id}/entries/{entry_id}", response_model=VocabularyOut)
def update_entry(
    library_id: str,
    entry_id: str,
    payload: WordEntryIn,
    context: RuntimeContext = Depends(get_runtime_context),
    service: VocabularyService = Depends(get_vocabulary_service),
) -> VocabularyOut:
    return vocabulary_to_out(
        service.update_entry(library_id, entry_id, context.user_id, context.role, payload)
    )


@router.delete("/vocabularies/{library_id}/entries/{entry_id}", status_code=204)
def delete_entry(
    library_id: str,
    entry_id: str,
    context: RuntimeContext = Depends(get_runtime_context),
    service: VocabularyService = Depends(get_vocabulary_service),
) -> Response:
    service.remove_entries(library_id, [entry_id], context.user_id, context.role)
    return Response(status_code=204)


@router.post("/vocabularies/{library_id}/entries/batch-delete", status_code=204)
def batch_delete_entries(
    library_id: str,
    entry_ids: list[str],
    context: RuntimeContext = Depends(get_runtime_context),
    service: VocabularyService = Depends(get_vocabulary_service),
) -> Response:
    service.remove_entries(library_id, entry_ids, context.user_id, context.role)
    return Response(status_code=204)


@router.post("/vocabularies/{library_id}/publish", response_model=VocabularyOut)
def publish_vocabulary(
    library_id: str,
    context: RuntimeContext = Depends(require_admin),
    service: VocabularyService = Depends(get_vocabulary_service),
) -> VocabularyOut:
    return vocabulary_to_out(service.publish(library_id, context.user_id, context.role, True))


@router.post("/vocabularies/{library_id}/unpublish", response_model=VocabularyOut)
def unpublish_vocabulary(
    library_id: str,
    context: RuntimeContext = Depends(require_admin),
    service: VocabularyService = Depends(get_vocabulary_service),
) -> VocabularyOut:
    return vocabulary_to_out(service.publish(library_id, context.user_id, context.role, False))
