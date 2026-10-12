import uuid
from datetime import datetime, timedelta

from sqlalchemy import (
    BigInteger,
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    String,
)
from sqlalchemy.orm import relationship
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy_utils import EmailType

from src.components.database.base_model import MetaData


class PartnerMetaData(MetaData):
    __tablename__ = "console_partner_meta_data"

    partner_id = Column(
        UUID(as_uuid=True),
        ForeignKey("console_partners.id", ondelete="RESTRICT"),
        index=True,
        unique=True,
        nullable=False,
    )
    api_key = Column(
        String(50), default=lambda: str(uuid.uuid4()), nullable=False, unique=True
    )
    timezone = Column(String(50), nullable=True)

    talko_trail_expiry_time = Column(BigInteger, default=None, index=True)
    number_of_users = Column(Integer, default=0)
    type_of_business = Column(String(64), nullable=True)
    years_in_business = Column(Integer, nullable=True)
    annual_revenue = Column(BigInteger, nullable=True)

    # Partner Subscribed Services Info
    is_talko_enabled = Column(Boolean, default=False, index=True)

    # One-to-One relationship with Partner
    partner = relationship("Partner", back_populates="meta_data", uselist=False)

    def __repr__(self):
        return f"<PartnerMetaData(id={self.id}, api_key={self.api_key})>"
