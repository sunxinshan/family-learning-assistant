from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.admin.models import OperationLog


class OperationLogRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def add(self, log: OperationLog) -> OperationLog:
        self.session.add(log)
        self.session.flush()
        return log

    def list(self, limit: int = 100) -> list[OperationLog]:
        return list(
            self.session.scalars(
                select(OperationLog).order_by(OperationLog.created_at.desc()).limit(limit)
            )
        )
