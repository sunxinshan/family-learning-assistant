from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.core.database import get_session
from app.core.security import RuntimeContext, get_runtime_context
from app.modules.practice.repository import PracticeRepository
from app.modules.practice.schemas import AnswerSubmit, AttemptOut, SelfCheckSubmit
from app.modules.practice.service import PracticeService

router = APIRouter(tags=["practice"])


def get_practice_service(
    request: Request,
    session: Session = Depends(get_session),
) -> PracticeService:
    return PracticeService(PracticeRepository(session), session, request.app.state.settings)


@router.post("/tasks/{task_id}/attempts", response_model=AttemptOut)
def start_attempt(
    task_id: str,
    context: RuntimeContext = Depends(get_runtime_context),
    service: PracticeService = Depends(get_practice_service),
) -> AttemptOut:
    return service.start_or_resume(task_id, context.user_id)


@router.get("/tasks/{task_id}/attempts/active", response_model=AttemptOut | None)
def active_attempt(
    task_id: str,
    context: RuntimeContext = Depends(get_runtime_context),
    service: PracticeService = Depends(get_practice_service),
) -> AttemptOut | None:
    return service.get_active(task_id, context.user_id)


@router.get("/attempts/{attempt_id}", response_model=AttemptOut)
def get_attempt(
    attempt_id: str,
    context: RuntimeContext = Depends(get_runtime_context),
    service: PracticeService = Depends(get_practice_service),
) -> AttemptOut:
    return service.get(attempt_id, context.user_id)


@router.get("/attempts", response_model=list[AttemptOut])
def list_attempts(
    context: RuntimeContext = Depends(get_runtime_context),
    service: PracticeService = Depends(get_practice_service),
) -> list[AttemptOut]:
    return service.list(context.user_id)


@router.post("/attempts/{attempt_id}/answers", response_model=AttemptOut)
def submit_answer(
    attempt_id: str,
    payload: AnswerSubmit,
    context: RuntimeContext = Depends(get_runtime_context),
    service: PracticeService = Depends(get_practice_service),
) -> AttemptOut:
    return service.submit_answer(attempt_id, context.user_id, payload)


@router.post("/attempts/{attempt_id}/self-check", response_model=AttemptOut)
def submit_self_check(
    attempt_id: str,
    payload: SelfCheckSubmit,
    context: RuntimeContext = Depends(get_runtime_context),
    service: PracticeService = Depends(get_practice_service),
) -> AttemptOut:
    return service.submit_self_check(attempt_id, context.user_id, payload)
