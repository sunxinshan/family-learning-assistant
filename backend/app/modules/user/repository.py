from datetime import UTC, datetime

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.modules.user.models import User, UserSession


class UserRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def get_by_id(self, user_id: str) -> User | None:
        return self.session.get(User, user_id)

    def get_by_nickname(self, nickname: str) -> User | None:
        return self.session.scalar(select(User).where(User.nickname == nickname))

    def list_users(self) -> list[User]:
        return list(self.session.scalars(select(User).order_by(User.created_at)))

    def add(self, user: User) -> User:
        self.session.add(user)
        self.session.flush()
        return user

    def create_session(self, user_session: UserSession) -> UserSession:
        self.session.add(user_session)
        self.session.flush()
        return user_session

    def delete_sessions_for_user(self, user_id: str) -> None:
        self.session.execute(
            update(UserSession)
            .where(UserSession.user_id == user_id, UserSession.revoked_at.is_(None))
            .values(revoked_at=datetime.now(UTC))
        )

    def get_session_by_hash(self, token_hash: str) -> UserSession | None:
        return self.session.scalar(
            select(UserSession).where(UserSession.refresh_token_hash == token_hash)
        )

    def revoke_session(self, user_session: UserSession) -> None:
        user_session.revoked_at = datetime.now(UTC)
        self.session.flush()
