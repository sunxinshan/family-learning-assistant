from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.core.database import get_session
from app.core.security import RuntimeContext, get_runtime_context
from app.modules.learning.schemas import LearningStatsOut
from app.modules.learning.service import LearningService
from app.modules.practice.repository import PracticeRepository
from app.modules.practice.service import PracticeService

router = APIRouter(tags=["learning"])


def get_learning_service(
    request: Request,
    session: Session = Depends(get_session),
) -> LearningService:
    practice = PracticeService(PracticeRepository(session), session, request.app.state.settings)
    return LearningService(practice, request.app.state.settings)


@router.get("/learning/stats", response_model=LearningStatsOut)
def learning_stats(
    context: RuntimeContext = Depends(get_runtime_context),
    service: LearningService = Depends(get_learning_service),
) -> LearningStatsOut:
    return service.stats(context.user_id)
