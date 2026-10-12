import uuid

from sqlalchemy import BigInteger, Column, String, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.dialects.postgresql import JSON

from src.components.common.datetime import DateTimeUtil
from src.core.db import Base


class MetaData(Base):
    __abstract__ = True

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, server_default=text("gen_random_uuid()"))
    created_by = Column(UUID(as_uuid=True), nullable=True)
    deleted_by = Column(UUID(as_uuid=True), nullable=True)
    description = Column(String(200), nullable=True)
    additional_info = Column(JSON, nullable=True)
    updated_by = Column(UUID(as_uuid=True), nullable=True, index=True)
    created_at = Column(
        BigInteger, default=lambda: int(DateTimeUtil.get_current_time()), nullable=False
    )
    updated_at = Column(
        BigInteger, onupdate=lambda: int(DateTimeUtil.get_current_time()), nullable=True
    )
    deleted_at = Column(BigInteger, nullable=True)
