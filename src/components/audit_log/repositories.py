from contextlib import AbstractContextManager
from typing import Callable

from sqlalchemy.orm import Session

from src.components.audit_log.models import AuditLog
from src.components.audit_log.schema import AuditLogSchema


class AuditLogRepository:
    def __init__(
        self,
        session_factory: Callable[..., AbstractContextManager[Session]],
    ) -> None:
        self.__session_factory = session_factory

    async def create_audit_log(self, log_entry: AuditLogSchema):
        async with self.__session_factory() as session:
            audit_log: AuditLog = AuditLog(**log_entry.model_dump())
            session.add(audit_log)
            await session.commit()
            await session.refresh(audit_log)
            return audit_log
