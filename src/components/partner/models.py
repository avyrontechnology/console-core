from sqlalchemy import Boolean, Column, Enum, ForeignKey, Integer, String
from sqlalchemy.orm import relationship
from sqlalchemy_utils import force_auto_coercion

from src.components.database.base_model import MetaData
from src.components.partner.constant import BillingCycle, PartnerStatus
from src.components.partner_address.models import PartnerAddress
from src.components.partner_meta_data.models import PartnerMetaData
from src.components.partner_role_permission.models import PartnerRolePermission
from src.components.user.models import User
from src.core.db import Base

force_auto_coercion()


class Partner(MetaData):
    __tablename__ = "console_partners"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(128), unique=True, nullable=False, index=True)
    company_legal_name = Column(String(128), unique=True, nullable=False, index=True)
    description = Column(String(256))
    cin_no = Column(String(32), unique=True, nullable=True)
    gst_no = Column(String(32), unique=True, nullable=True)
    active_license = Column(Integer, default=0)
    created_by = Column(
        Integer, ForeignKey("console_users.id", ondelete="RESTRICT"), index=True
    )
    updated_by = Column(
        Integer, ForeignKey("console_users.id", ondelete="RESTRICT"), index=True
    )
    deleted_by = Column(
        Integer, ForeignKey("console_users.id", ondelete="RESTRICT"), index=True
    )
    parent_id = Column(
        Integer, ForeignKey("console_partners.id", ondelete="RESTRICT"), index=True
    )
    partner_logo_id = Column(
        Integer, ForeignKey("digital_assets.id", ondelete="SET NULL"), index=True
    )
    is_active = Column(Boolean, default=True, index=True)
    is_deleted = Column(Boolean, default=False)
    is_maglo_publisher = Column(Boolean, default=False)
    partner_status = Column(String(32), default=PartnerStatus.ACTIVE, nullable=False)
    is_feedback_enabled = Column(Boolean, default=True, index=True)
    is_internal = Column(Boolean, default=False, index=True)
    billing_cycle = Column(String(32), nullable=True)

    # Relationships to User for creator, updater, deleter
    creator = relationship(
        "User", foreign_keys=[created_by], back_populates="created_partners"
    )
    updater = relationship(
        "User", foreign_keys=[updated_by], back_populates="updated_partners"
    )
    deleter = relationship(
        "User", foreign_keys=[deleted_by], back_populates="deleted_partners"
    )

    # Self-referential relationship for parent-child structure
    parent = relationship("Partner", remote_side=[id], backref="child_partners")

    payments = relationship("Payment", back_populates="partner")

    # One-to-One and One-to-Many relationships
    meta_data = relationship("PartnerMetaData", back_populates="partner", uselist=False)
    partner_role_permissions = relationship(
        "PartnerRolePermission", back_populates="partner"
    )
    addresses = relationship("PartnerAddress", back_populates="partner")
    partner_logo = relationship(
        "DigitalAssets", foreign_keys=[partner_logo_id], uselist=False
    )

    users = relationship(
        "User", foreign_keys="[User.partner_id]", back_populates="partner"
    )

    api_keys = relationship(
        "ApiKey", back_populates="partner", cascade="all, delete-orphan"
    )

    wallet = relationship("Wallet", back_populates="partner", uselist=False)

    entitlements = relationship("Entitlement", back_populates="partner")

    orders = relationship("Order", back_populates="partner")

    def __repr__(self):
        return f"<Partner(id={self.id}, name={self.name}, active_license={self.active_license})>"

    @classmethod
    def validate_partner_status(cls, status: str) -> bool:
        return status in PartnerStatus.choices()
