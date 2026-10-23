from contextlib import AbstractContextManager
from typing import Callable, List, Optional

from sqlalchemy import desc, select
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

    async def list_audit_logs(
        self,
        resource: Optional[str] = None,
        action: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> List[AuditLog]:
        async with self.__session_factory() as session:
            query = select(AuditLog)
            if resource:
                query = query.where(AuditLog.resource == resource)
            if action:
                query = query.where(AuditLog.action == action)
            query = query.order_by(desc(AuditLog.created_at)).limit(limit).offset(
                offset
            )
            result = await session.execute(query)
            return list(result.scalars().all())
