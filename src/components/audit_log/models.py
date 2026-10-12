import uuid
from sqlalchemy import Column, DateTime, String, func
from sqlalchemy.dialects.postgresql import UUID

from src.components.database.base_model import MetaData
from src.core.db import Base


class AuditLog(MetaData):
    __tablename__ = "console_audit_logs"

    action = Column(String, nullable=False)
    resource = Column(String, nullable=False, index=True)
    resource_id = Column(String(36), nullable=True, index=True)
    resource_previous_state = Column(String, nullable=True)
    resource_current_state = Column(String, nullable=True)
    performed_by = Column(UUID(as_uuid=True), nullable=True)
    details = Column(String, nullable=True)
