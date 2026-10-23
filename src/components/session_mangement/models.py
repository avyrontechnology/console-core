import uuid
from sqlalchemy import BigInteger, Boolean, Column, ForeignKey, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from src.components.common.datetime import DateTimeUtil
from src.components.database.base_model import MetaData


class UserSession(MetaData):
    __tablename__ = "console_user_sessions"

    session_id = Column(String, primary_key=True, index=True)
    user_id = Column(
        UUID(as_uuid=True), ForeignKey("console_users.id"), nullable=False, index=True
    )
    ip_address = Column(String)
    device_info = Column(String)
    login_time = Column(
        BigInteger, default=lambda: int(DateTimeUtil.get_current_time())
    )
    logout_time = Column(BigInteger)
    is_active = Column(Boolean, default=True, nullable=False)
    expiry_time = Column(BigInteger)
    service_name = Column(String, index=True)
    
    # Relationships
    user = relationship("User", back_populates="sessions")
