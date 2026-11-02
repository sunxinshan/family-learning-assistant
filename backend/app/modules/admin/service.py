from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app.core.exceptions import AppError
from app.core.models import new_id
from app.modules.admin.models import OperationLog
from app.modules.admin.repository import OperationLogRepository
from app.modules.admin.schemas import AdminUserOut, OperationLogOut
from app.modules.learning.service import LearningService
from app.modules.user.repository import UserRepository
from app.modules.user.service import UserService


class AdminService:
    def __init__(
        self,
        user_repository: UserRepository,
        user_service: UserService,
        learning_service: LearningService,
        log_repository: OperationLogRepository,
        session: Session,
    ) -> None:
        self.user_repository = user_repository
        self.user_service = user_service
        self.learning_service = learning_service
        self.log_repository = log_repository
        self.session = session

    def log(
        self,
        actor_id: str,
        action: str,
        target_type: str,
        target_id: str | None,
        target_name: str,
        metadata: dict | None = None,
    ) -> None:
        self.log_repository.add(
            OperationLog(
                id=new_id(),
                actor_user_id=actor_id,
                action=action,
                target_type=target_type,
                target_id=target_id,
                target_name=target_name,
                result="success",
                metadata_json=metadata or {},
                created_at=datetime.now(UTC),
                updated_at=datetime.now(UTC),
            )
        )

    def list_users(self) -> list[AdminUserOut]:
        result = []
        for user in self.user_repository.list_users():
            stats = self.learning_service.stats(user.id)
            result.append(
                AdminUserOut(
                    id=user.id,
                    nickname=user.nickname,
                    role=user.role,
                    status=user.status,
                    created_at=user.created_at,
                    last_active_at=user.last_active_at,
                    practice_count=stats.practice_count,
                    accuracy=stats.average_accuracy,
                )
            )
        return result

    def set_status(self, admin_id: str, user_id: str, status: str) -> AdminUserOut:
        if status not in {"active", "disabled"}:
            raise AppError("invalid_status", "用户状态无效")
        user = self.user_repository.get_by_id(user_id)
        if not user:
            raise AppError("user_not_found", "用户不存在", status_code=404)
        user.status = status
        self.log(admin_id, "更新用户状态", "user", user.id, user.nickname, {"status": status})
        stats = self.learning_service.stats(user.id)
        return AdminUserOut(
            id=user.id,
            nickname=user.nickname,
            role=user.role,
            status=user.status,
            created_at=user.created_at,
            last_active_at=user.last_active_at,
            practice_count=stats.practice_count,
            accuracy=stats.average_accuracy,
        )

    def reset_password(self, admin_id: str, user_id: str) -> str:
        user = self.user_repository.get_by_id(user_id)
        if not user:
            raise AppError("user_not_found", "用户不存在", status_code=404)
        password = self.user_service.reset_password(user)
        self.log(admin_id, "重置用户密码", "user", user.id, user.nickname)
        return password

    def logs(self) -> list[OperationLogOut]:
        return [OperationLogOut.model_validate(item) for item in self.log_repository.list()]
