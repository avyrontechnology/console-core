from sqlalchemy import Column, DateTime, Integer, String, func

from src.components.database.base_model import MetaData
from src.core.db import Base


class AuditLog(MetaData):
    __tablename__ = "console_audit_logs"

    action = Column(String, nullable=False)
    resource = Column(String, nullable=False, index=True)
    resource_id = Column(Integer, nullable=True, index=True)
    resource_previous_state = Column(String, nullable=True)
    resource_current_state = Column(String, nullable=True)
    performed_by = Column(Integer, nullable=True)
    details = Column(String, nullable=True)
