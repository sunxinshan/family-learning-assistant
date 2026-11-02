from dataclasses import dataclass

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.database import get_session
from app.core.exceptions import AppError
from app.modules.user.models import User
from app.modules.user.repository import UserRepository
from app.modules.user.service import UserService

bearer_scheme = HTTPBearer(auto_error=False)


@dataclass(frozen=True)
class RuntimeContext:
    user_id: str
    role: str


def get_user_service(
    request: Request,
    session: Session = Depends(get_session),
) -> UserService:
    return UserService(UserRepository(session), request.app.state.settings)


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    service: UserService = Depends(get_user_service),
) -> User:
    if not credentials or credentials.scheme.lower() != "bearer":
        raise AppError("unauthorized", "请先登录", status_code=401)
    return service.authenticate_token(credentials.credentials)


def get_runtime_context(user: User = Depends(get_current_user)) -> RuntimeContext:
    return RuntimeContext(user_id=user.id, role=user.role)


def require_admin(context: RuntimeContext = Depends(get_runtime_context)) -> RuntimeContext:
    if context.role != "admin":
        raise AppError("forbidden", "仅管理员可以执行此操作", status_code=403)
    return context
