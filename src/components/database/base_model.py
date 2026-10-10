from sqlalchemy import BigInteger, Column, Integer, String
from sqlalchemy.dialects.postgresql import JSON

from src.components.common.datetime import DateTimeUtil
from src.core.db import Base


class MetaData(Base):
    __abstract__ = True

    id = Column(Integer, primary_key=True, autoincrement=True)
    created_by = Column(Integer, nullable=True)
    deleted_by = Column(Integer, nullable=True)
    description = Column(String(200), nullable=True)
    additional_info = Column(JSON, nullable=True)
    updated_by = Column(Integer, nullable=True, index=True)
    created_at = Column(
        BigInteger, default=lambda: int(DateTimeUtil.get_current_time()), nullable=False
    )
    updated_at = Column(
        BigInteger, onupdate=lambda: int(DateTimeUtil.get_current_time()), nullable=True
    )
    deleted_at = Column(BigInteger, nullable=True)
