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
            ("Admin", "admin123", "admin"),
            ("Manager", "manager123", "admin"),
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
