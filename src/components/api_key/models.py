import uuid
from sqlalchemy import Boolean, Column, ForeignKey, String, JSON
from sqlalchemy.orm import relationship
from sqlalchemy.dialects.postgresql import UUID

from src.components.database.base_model import MetaData
from src.core.db import Base
import secrets

class ApiKey(MetaData):
    __tablename__ = "console_api_keys"

    key = Column(
        String(128),
        unique=True,
        nullable=False,
        index=True,
        default=lambda: secrets.token_hex(32)  # 64-character random key
    )
    scopes = Column(JSON, nullable=True)
    user_context = Column(JSON, nullable=True)
    is_active = Column(Boolean, default=True, nullable=False)
    partner_id = Column(
        UUID(as_uuid=True),
        ForeignKey("console_partners.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Relationship to Partner
    partner = relationship("Partner", back_populates="api_keys")

    def __repr__(self):
        return f"<ApiKey(key={self.key}, active={self.is_active})>"