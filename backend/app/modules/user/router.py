from fastapi import APIRouter, Depends, Response, status

from app.core.security import (
    RuntimeContext,
    get_current_user,
    get_runtime_context,
    get_user_service,
)
from app.modules.user.models import User
from app.modules.user.schemas import (
    ChangePasswordRequest,
    LoginRequest,
    RefreshRequest,
    RegisterRequest,
    TokenResponse,
    UpdateProfileRequest,
    UserPublic,
)
from app.modules.user.service import UserService

router = APIRouter(tags=["auth"])


def _token_response(user: User, access: str, refresh: str) -> TokenResponse:
    return TokenResponse(
        access_token=access,
        refresh_token=refresh,
        user=UserPublic.model_validate(user),
    )


@router.post("/auth/register", response_model=TokenResponse, status_code=201)
def register(
    payload: RegisterRequest, service: UserService = Depends(get_user_service)
) -> TokenResponse:
    user, access, refresh = service.register(payload.nickname, payload.password)
    return _token_response(user, access, refresh)


@router.post("/auth/login", response_model=TokenResponse)
def login(payload: LoginRequest, service: UserService = Depends(get_user_service)) -> TokenResponse:
    user, access, refresh = service.login(payload.nickname, payload.password)
    return _token_response(user, access, refresh)


@router.post("/auth/refresh", response_model=TokenResponse)
def refresh(
    payload: RefreshRequest, service: UserService = Depends(get_user_service)
) -> TokenResponse:
    user, access, new_refresh = service.refresh(payload.refresh_token)
    return _token_response(user, access, new_refresh)


@router.post("/auth/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(payload: RefreshRequest, service: UserService = Depends(get_user_service)) -> Response:
    service.logout(payload.refresh_token)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/users/me", response_model=UserPublic)
def me(user: User = Depends(get_current_user)) -> User:
    return user


@router.patch("/users/me", response_model=UserPublic)
def update_me(
    payload: UpdateProfileRequest,
    user: User = Depends(get_current_user),
    service: UserService = Depends(get_user_service),
) -> User:
    return service.update_profile(user, payload.nickname.strip())


@router.post("/users/me/password", status_code=status.HTTP_204_NO_CONTENT)
def change_password(
    payload: ChangePasswordRequest,
    user: User = Depends(get_current_user),
    service: UserService = Depends(get_user_service),
) -> Response:
    service.change_password(user, payload.old_password, payload.new_password)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/auth/context")
def context(context: RuntimeContext = Depends(get_runtime_context)) -> dict[str, str]:
    return {"user_id": context.user_id, "role": context.role}
