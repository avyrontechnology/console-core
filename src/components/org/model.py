import uuid

from sqlalchemy import Boolean, Column, DateTime, Integer, String, text
from sqlalchemy.dialects.postgresql import UUID

from src.core.db import Base


class Organization(Base):
    __tablename__ = "console_organization"

    id = Column(UUID(as_uuid=True), primary_key=True, index=True, default=uuid.uuid4, server_default=text("gen_random_uuid()"))
    name = Column(String(80), nullable=False, unique=True, index=True)
    org_key = Column(String(80), nullable=False, unique=True, index=True)
    # created_by = FK to user
    # updated_by = FK to User
    # deleted_by = FK to user
    # poc_user = FK to org user
    created_at = Column(DateTime)
    updated_at = Column(DateTime)
    deleted_at = Column(DateTime)
    is_active = Column(Boolean, default=True)
    is_deleted = Column(Boolean, default=False)
    description = Column(String(200))

    def __repr__(self):
        return "OrgModel(name=%s, org-key=%s)" % (self.name, self.org_key)
