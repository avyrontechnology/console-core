from datetime import datetime, timedelta

import uuid
from sqlalchemy import (
    BigInteger,
    Boolean,
    Column,
    Enum,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import relationship
from sqlalchemy.dialects.postgresql import UUID

from src.components.auth.constant import OtpConstants, OtpType
from src.components.database.base_model import MetaData
from src.components.user.models import User


class Permission(MetaData):
    __tablename__ = "console_permission"

    title = Column(String(56))  # e.g., create, read, delete, update
    slug = Column(String, unique=True, nullable=False)
    description = Column(String)
    category = Column(String, nullable=True)
    display_text = Column(String, nullable=True)
    is_internal = Column(Boolean, default=True, index=True)
    is_active = Column(Boolean, default=True)
    is_deleted = Column(Boolean, default=False)

    deleted_by = Column(UUID(as_uuid=True), ForeignKey(User.id))  # FK
    created_by = Column(UUID(as_uuid=True), ForeignKey(User.id))  # FK
    updated_by = Column(UUID(as_uuid=True), ForeignKey(User.id))  # FK

    # Define relationships with the User model
    created_user = relationship("User", foreign_keys=[created_by])
    updated_user = relationship("User", foreign_keys=[updated_by])
    deleted_user = relationship("User", foreign_keys=[deleted_by])


class Role(MetaData):
    __tablename__ = "console_role"
    name = Column(String(56))  # e.g., superAdmin, admin, Manager, Agent
    slug = Column(String, nullable=False)
    hierarchy = Column(Integer)
    # NULL => system default role (shared by every partner). A non-null
    # partner_id is a partner-defined custom role.
    partner_id = Column(
        UUID(as_uuid=True),
        ForeignKey("console_partners.id", ondelete="RESTRICT"),
        nullable=True,
        index=True,
    )
    # Semantic visibility tier (ALL | SUBTREE | OWN) that drives data scoping
    # instead of comparing raw hierarchy integers against hardcoded constants.
    data_scope = Column(String(16), nullable=True)
    # Provenance: the role this custom role's permissions were seeded from at
    # creation. NULL for system default roles. SET NULL on base removal so a
    # base role can be deleted without blocking (roles are soft-deleted anyway).
    base_role_id = Column(
        UUID(as_uuid=True),
        ForeignKey("console_role.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    description = Column(String)
    is_internal = Column(Boolean, default=True, index=True)
    is_active = Column(Boolean, default=True)
    is_deleted = Column(Boolean, default=False)

    created_by = Column(UUID(as_uuid=True), ForeignKey(User.id))  # FK
    updated_by = Column(UUID(as_uuid=True), ForeignKey(User.id))  # FK
    deleted_by = Column(UUID(as_uuid=True), ForeignKey(User.id))  # FK

    # Define relationships with the User model
    created_user = relationship("User", foreign_keys=[created_by])
    updated_user = relationship("User", foreign_keys=[updated_by])
    deleted_user = relationship("User", foreign_keys=[deleted_by])

    # Self-referential provenance link to the role this one was seeded from.
    base_role = relationship(
        "Role", remote_side="Role.id", foreign_keys=[base_role_id]
    )

    __table_args__ = (
        # Exactly one DEFAULT role per rank / slug (partner_id IS NULL).
        Index(
            "uq_role_default_hierarchy",
            "hierarchy",
            unique=True,
            postgresql_where=text("partner_id IS NULL"),
        ),
        Index(
            "uq_role_default_slug",
            "slug",
            unique=True,
            postgresql_where=text("partner_id IS NULL"),
        ),
        # Per-partner uniqueness for custom roles.
        UniqueConstraint("partner_id", "hierarchy", name="uq_role_partner_hierarchy"),
        UniqueConstraint("partner_id", "slug", name="uq_role_partner_slug"),
    )


class OTP(MetaData):
    __tablename__ = "console_otp"

    user_id = Column(
        UUID(as_uuid=True), ForeignKey("console_users.id"), nullable=False, index=True
    )
    otp = Column(String(6), nullable=False, index=True)
    otp_type = Column(Enum(OtpType), nullable=False)
    is_used = Column(Boolean, default=False, nullable=False)

    expires_at = Column(
        BigInteger,
        default=lambda: int(
            (
                datetime.now(datetime.timezone.utc)
                + timedelta(minutes=OtpConstants.OTP_TIMEOUT)
            ).timestamp()
        ),
        nullable=False,
    )

    # Relationship
    user = relationship("User", back_populates="otps")

    def __repr__(self):
        return f"<OTP(user_id={self.user_id}, otp_type={self.otp_type}, is_used={self.is_used})>"

    __table_args__ = (UniqueConstraint("user_id", "otp_type", name="uq_user_otp_type"),)
