import hashlib
import secrets
from datetime import UTC, datetime, timedelta

import jwt
from pwdlib import PasswordHash

from app.core.config import Settings
from app.core.exceptions import AppError
from app.core.models import new_id
from app.modules.user.models import User, UserSession
from app.modules.user.repository import UserRepository


class UserService:
    def __init__(self, repository: UserRepository, settings: Settings) -> None:
        self.repository = repository
        self.settings = settings
        self.password_hash = PasswordHash.recommended()

    def _hash_refresh_token(self, token: str) -> str:
        return hashlib.sha256(token.encode("utf-8")).hexdigest()

    def _create_access_token(self, user: User) -> str:
        now = datetime.now(UTC)
        payload = {
            "sub": user.id,
            "role": user.role,
            "iat": now,
            "exp": now + timedelta(minutes=self.settings.access_token_minutes),
        }
        return jwt.encode(
            payload,
            self.settings.jwt_secret.get_secret_value(),
            algorithm="HS256",
        )

    def _issue_tokens(self, user: User) -> tuple[str, str]:
        access = self._create_access_token(user)
        refresh = secrets.token_urlsafe(48)
        session = UserSession(
            id=new_id(),
            user_id=user.id,
            refresh_token_hash=self._hash_refresh_token(refresh),
            expires_at=datetime.now(UTC) + timedelta(days=self.settings.refresh_token_days),
            created_at=datetime.now(UTC),
        )
        self.repository.create_session(session)
        return access, refresh

    def register(self, nickname: str, password: str) -> tuple[User, str, str]:
        if self.repository.get_by_nickname(nickname):
            raise AppError("nickname_taken", "该昵称已被使用", status_code=409)
        user = User(
            id=new_id(),
            nickname=nickname,
            password_hash=self.password_hash.hash(password),
            role="user",
            status="active",
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )
        self.repository.add(user)
        access, refresh = self._issue_tokens(user)
        return user, access, refresh

    def login(self, nickname: str, password: str) -> tuple[User, str, str]:
        user = self.repository.get_by_nickname(nickname)
        if not user or not self.password_hash.verify(password, user.password_hash):
            raise AppError("invalid_credentials", "昵称或密码不正确", status_code=401)
        if user.status != "active":
            raise AppError("user_disabled", "该账户已停用", status_code=403)
        user.last_active_at = datetime.now(UTC)
        access, refresh = self._issue_tokens(user)
        return user, access, refresh

    def refresh(self, refresh_token: str) -> tuple[User, str, str]:
        session = self.repository.get_session_by_hash(self._hash_refresh_token(refresh_token))
        if not session or session.revoked_at or session.expires_at <= datetime.now(UTC):
            raise AppError("invalid_refresh_token", "登录状态已失效", status_code=401)
        user = self.repository.get_by_id(session.user_id)
        if not user or user.status != "active":
            raise AppError("user_disabled", "该账户不可用", status_code=403)
        self.repository.revoke_session(session)
        access, new_refresh = self._issue_tokens(user)
        return user, access, new_refresh

    def authenticate_token(self, token: str) -> User:
        try:
            payload = jwt.decode(
                token,
                self.settings.jwt_secret.get_secret_value(),
                algorithms=["HS256"],
            )
        except jwt.PyJWTError as exc:
            raise AppError("invalid_token", "登录状态无效", status_code=401) from exc
        user = self.repository.get_by_id(str(payload.get("sub", "")))
        if not user or user.status != "active":
            raise AppError("user_disabled", "该账户不可用", status_code=401)
        return user

    def update_profile(self, user: User, nickname: str) -> User:
        existing = self.repository.get_by_nickname(nickname)
        if existing and existing.id != user.id:
            raise AppError("nickname_taken", "该昵称已被使用", status_code=409)
        user.nickname = nickname
        return user

    def change_password(self, user: User, old_password: str, new_password: str) -> None:
        if not self.password_hash.verify(old_password, user.password_hash):
            raise AppError("invalid_password", "原密码不正确", status_code=400)
        user.password_hash = self.password_hash.hash(new_password)
        self.repository.delete_sessions_for_user(user.id)

    def logout(self, refresh_token: str) -> None:
        session = self.repository.get_session_by_hash(self._hash_refresh_token(refresh_token))
        if session and not session.revoked_at:
            self.repository.revoke_session(session)

    def reset_password(self, user: User) -> str:
        password = f"Fla-{secrets.token_urlsafe(8)}"
        user.password_hash = self.password_hash.hash(password)
        self.repository.delete_sessions_for_user(user.id)
        return password
