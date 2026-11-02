from datetime import UTC, datetime

from sqlalchemy import select

from app.core.database import Database
from app.core.models import new_id
from app.modules.user.models import User
from app.modules.user.repository import UserRepository
from app.modules.user.service import UserService
from app.modules.vocabulary.models import SubjectConfig


def seed_demo(database: Database) -> None:
    with database.session() as session:
        for code, name, order in (("english", "英语", 1), ("chinese", "语文", 2)):
            if not session.get(SubjectConfig, code):
                session.add(
                    SubjectConfig(code=code, display_name=name, enabled=True, sort_order=order)
                )
        for nickname, password, role in (
            ("Alice", "demo123", "user"),
            ("Bob", "demo123", "user"),
            ("admin", "admin213", "admin"),
            ("admin1", "admin222", "admin"),
        ):
            user = session.scalar(select(User).where(User.nickname == nickname))
            if not user:
                service = UserService(UserRepository(session), database.settings)
                now = datetime.now(UTC)
                session.add(
                    User(
                        id=new_id(),
                        nickname=nickname,
                        password_hash=service.password_hash.hash(password),
                        role=role,
                        status="active",
                        created_at=now,
                        updated_at=now,
                    )
                )


def seed_bootstrap_admins(database: Database) -> None:
    settings = database.settings
    pairs = (
        (settings.bootstrap_admin_1_nickname, settings.bootstrap_admin_1_password),
        (settings.bootstrap_admin_2_nickname, settings.bootstrap_admin_2_password),
    )
    with database.session() as session:
        for nickname, password in pairs:
            if not nickname or not password:
                continue
            existing = session.scalar(select(User).where(User.nickname == nickname))
            if existing:
                continue
            if len(password.get_secret_value()) < 12:
                raise ValueError("Bootstrap admin password must be at least 12 characters")
            now = datetime.now(UTC)
            service = UserService(UserRepository(session), settings)
            session.add(
                User(
                    id=new_id(),
                    nickname=nickname,
                    password_hash=service.password_hash.hash(password.get_secret_value()),
                    role="admin",
                    status="active",
                    created_at=now,
                    updated_at=now,
                )
            )
