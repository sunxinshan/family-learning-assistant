from datetime import datetime

from app.api.schemas import CamelModel
from app.modules.learning.schemas import LearningStatsOut
from app.modules.user.schemas import UserPublic


class AdminUserOut(UserPublic):
    practice_count: int
    accuracy: int


class UserStatusUpdate(CamelModel):
    status: str


class OperationLogOut(CamelModel):
    id: str
    actor_user_id: str
    action: str
    target_type: str
    target_id: str | None
    target_name: str
    result: str
    created_at: datetime


class ResetPasswordOut(CamelModel):
    nickname: str
    temporary_password: str


class AdminLearningStatsOut(LearningStatsOut):
    pass
