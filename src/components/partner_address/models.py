import uuid
from sqlalchemy import Boolean, Column, Enum, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import relationship
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy_utils import force_auto_coercion

from src.components.database.base_model import MetaData
from src.components.partner_address.schema import AddressType
from src.core.db import Base

force_auto_coercion()


class PartnerAddress(MetaData):
    __tablename__ = "console_addresses"

    address_1 = Column(String, nullable=False)
    address_2 = Column(String, nullable=True)
    address_type = Column(Enum(AddressType), nullable=False)
    city = Column(String, nullable=False)
    state = Column(String, nullable=False)
    country = Column(String, nullable=False)
    pincode = Column(String, nullable=False)
    is_address_same = Column(Boolean, default=False, nullable=True)
    partner_id = Column(
        UUID(as_uuid=True), ForeignKey("console_partners.id", ondelete="RESTRICT"), nullable=False
    )
    # bidirectional relation to partner
    partner = relationship("Partner", back_populates="addresses")

    # Unique constraint to ensure one partner can have only one address of each type
    __table_args__ = (
        UniqueConstraint("partner_id", "address_type", name="uq_partner_address_type"),
    )

    def __repr__(self):
        return (
            f"<PartnerAddress(address_type={self.address_type}, "
            f"city={self.city}, "
            f"pincode={self.pincode})>"
        )
