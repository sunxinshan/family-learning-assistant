from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.core.database import get_session
from app.core.security import RuntimeContext, require_admin
from app.modules.admin.repository import OperationLogRepository
from app.modules.admin.schemas import (
    AdminUserOut,
    OperationLogOut,
    ResetPasswordOut,
    UserStatusUpdate,
)
from app.modules.admin.service import AdminService
from app.modules.learning.service import LearningService
from app.modules.practice.repository import PracticeRepository
from app.modules.practice.service import PracticeService
from app.modules.user.repository import UserRepository
from app.modules.user.service import UserService

router = APIRouter(prefix="/admin", tags=["admin"])


def get_admin_service(
    request: Request,
    session: Session = Depends(get_session),
) -> AdminService:
    settings = request.app.state.settings
    users = UserRepository(session)
    user_service = UserService(users, settings)
    practice_service = PracticeService(PracticeRepository(session), session, settings)
    learning = LearningService(practice_service, settings)
    return AdminService(users, user_service, learning, OperationLogRepository(session), session)


@router.get("/users", response_model=list[AdminUserOut])
def list_users(
    _: RuntimeContext = Depends(require_admin),
    service: AdminService = Depends(get_admin_service),
) -> list[AdminUserOut]:
    return service.list_users()


@router.patch("/users/{user_id}/status", response_model=AdminUserOut)
def update_user_status(
    user_id: str,
    payload: UserStatusUpdate,
    context: RuntimeContext = Depends(require_admin),
    service: AdminService = Depends(get_admin_service),
) -> AdminUserOut:
    return service.set_status(context.user_id, user_id, payload.status)


@router.post("/users/{user_id}/reset-password", response_model=ResetPasswordOut)
def reset_password(
    user_id: str,
    context: RuntimeContext = Depends(require_admin),
    service: AdminService = Depends(get_admin_service),
    session: Session = Depends(get_session),
) -> ResetPasswordOut:
    password = service.reset_password(context.user_id, user_id)
    user = UserRepository(session).get_by_id(user_id)
    return ResetPasswordOut(nickname=user.nickname if user else "", temporary_password=password)


@router.get("/logs", response_model=list[OperationLogOut])
def list_logs(
    _: RuntimeContext = Depends(require_admin),
    service: AdminService = Depends(get_admin_service),
) -> list[OperationLogOut]:
    return service.logs()
