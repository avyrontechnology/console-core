import uuid
from datetime import datetime

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import relationship

from src.components.database.base_model import MetaData


class UserMetadata(MetaData):
    __tablename__ = "console_user_metadata"

    user_id = Column(
        Integer, ForeignKey("console_users.id"), index=True, unique=True, nullable=False
    )
    meta_key = Column(
        String(50), default=lambda: str(uuid.uuid4()), nullable=False, unique=True
    )
    meta_value = Column(String)

    # Use lazy-loading for circular import safety
    user = relationship(
        "User", back_populates="metadata_entries", uselist=False, lazy="select"
    )

    def __repr__(self):
        return (
            f"<UserMetadata(id={self.id}, user_id={self.user_id}, "
            f"meta_key={self.meta_key}, meta_value={self.meta_value})>"
        )
