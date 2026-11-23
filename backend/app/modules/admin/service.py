import logging
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from sqlalchemy.orm import Session

from app.core.exceptions import AppError
from app.core.models import new_id
from app.infrastructure.checkpoint import checkpoint_not_found_error
from app.modules.admin.checkpoint_repository import CheckpointRepository
from app.modules.admin.models import OperationLog
from app.modules.admin.repository import OperationLogRepository
from app.modules.admin.schemas import (
    AdminUserOut,
    CheckpointDetailOut,
    CheckpointListItemOut,
    CheckpointListOut,
    CheckpointReplayOut,
    CheckpointThreadOut,
    CheckpointWriteOut,
    OperationLogOut,
    ReplayDiffOut,
    ReplayRunOut,
    ReplaySourceOut,
)
from app.modules.learning.service import LearningService
from app.modules.user.service import UserService

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    # 只在类型检查期引入 agent 运行时：admin 与 agent 已互相依赖
    # （checkpoint_repository 导入 agent.redaction），运行期硬 import 会加重环。
    from app.modules.agent.runtime import AgentRuntime


class AdminService:
    def __init__(
        self,
        user_service: UserService,
        learning_service: LearningService,
        log_repository: OperationLogRepository,
        session: Session,
        checkpoint_repository: CheckpointRepository,
    ) -> None:
        self.user_service = user_service
        self.learning_service = learning_service
        self.log_repository = log_repository
        self.session = session
        self.checkpoint_repository = checkpoint_repository

    def log(
        self,
        actor_id: str,
        action: str,
        target_type: str,
        target_id: str | None,
        target_name: str,
        metadata: dict | None = None,
        result: str = "success",
    ) -> None:
        self.log_repository.add(
            OperationLog(
                id=new_id(),
                actor_user_id=actor_id,
                action=action,
                target_type=target_type,
                target_id=target_id,
                target_name=target_name,
                result=result,
                metadata_json=metadata or {},
                created_at=datetime.now(UTC),
                updated_at=datetime.now(UTC),
            )
        )

    def list_users(self) -> list[AdminUserOut]:
        result = []
        for user in self.user_service.list_users():
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
        user = self.user_service.set_status(user_id, status)
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
        user = self.user_service.get_user(user_id)
        password = self.user_service.reset_password(user)
        self.log(admin_id, "重置用户密码", "user", user.id, user.nickname)
        return password

    def logs(self) -> list[OperationLogOut]:
        return [OperationLogOut.model_validate(item) for item in self.log_repository.list()]

    def list_checkpoints(self, thread_id: str | None, limit: int, offset: int) -> CheckpointListOut:
        data = self.checkpoint_repository.list(thread_id, limit, offset)
        return CheckpointListOut(
            items=[CheckpointListItemOut(**item) for item in data["items"]],
            total=data["total"],
            threads=[CheckpointThreadOut(**thread) for thread in data["threads"]],
        )

    def get_checkpoint(self, thread_id: str, checkpoint_id: str) -> CheckpointDetailOut:
        data = self.checkpoint_repository.get(thread_id, checkpoint_id)
        if data is None:
            raise checkpoint_not_found_error()
        return CheckpointDetailOut(
            thread_id=data["thread_id"],
            checkpoint_ns=data["checkpoint_ns"],
            checkpoint_id=data["checkpoint_id"],
            parent_checkpoint_id=data["parent_checkpoint_id"],
            step=data["step"],
            source=data["source"],
            size_bytes=data["size_bytes"],
            channel_values=data["channel_values"],
            metadata=data["metadata"],
            writes=[CheckpointWriteOut(**write) for write in data["writes"]],
        )

    def replay_checkpoint(
        self,
        admin_id: str,
        thread_id: str,
        checkpoint_id: str,
        agent_runtime: "AgentRuntime",
    ) -> CheckpointReplayOut:
        """从历史 checkpoint 重放一次，供管理员调试。

        只做编排：存在性校验、调用运行时、记操作日志、组装响应。
        锚点解析、terminal / interrupted / ambiguous / unsupported_route 等 409
        全部由 ``AgentRuntime.replay_from_checkpoint`` 抛，本方法只负责透传。

        成功与失败都记一条 admin 操作日志（带结果码，T-FIX-03）。注意
        ``get_session`` 在异常时会 rollback，所以失败日志必须显式 commit，
        否则「重放失败」这条记录会被一起回滚掉。
        """
        try:
            if self.checkpoint_repository.get(thread_id, checkpoint_id) is None:
                raise checkpoint_not_found_error()
            data = agent_runtime.replay_from_checkpoint(thread_id, checkpoint_id)
        except AppError as exc:
            self._log_replay_failure(admin_id, thread_id, checkpoint_id, exc.code)
            raise
        except Exception:
            logger.exception(
                "重放 checkpoint 内部错误 thread_id=%s checkpoint_id=%s", thread_id, checkpoint_id
            )
            self._log_replay_failure(admin_id, thread_id, checkpoint_id, "internal_error")
            raise
        # 唯一写入：管理端操作日志（admin 日志表），不是重放本身的业务写入。
        self.log(
            admin_id, "重放 checkpoint", "checkpoint", checkpoint_id, thread_id, {"code": "ok"}
        )
        return CheckpointReplayOut(
            source=ReplaySourceOut(**data["source"]),
            replay=ReplayRunOut(**data["replay"]),
            diff=ReplayDiffOut(**data["diff"]),
        )

    def _log_replay_failure(
        self, admin_id: str, thread_id: str, checkpoint_id: str, code: str
    ) -> None:
        """失败留痕：自己 commit，避免被请求级事务回滚（T-FIX-03）。"""
        try:
            self.log(
                admin_id,
                "重放 checkpoint 失败",
                "checkpoint",
                checkpoint_id,
                thread_id,
                {"code": code},
                result="failure",
            )
            self.session.commit()
        except Exception:  # noqa: BLE001 - 审计失败不能掩盖原始错误
            logger.warning(
                "重放失败日志写入失败 thread_id=%s code=%s", thread_id, code, exc_info=True
            )
