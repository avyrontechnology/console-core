from sqlalchemy import (
    Boolean,
    Column,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import relationship
from sqlalchemy_utils import EmailType, force_auto_coercion

from src.components.database.base_model import MetaData
from src.components.session_mangement.models import UserSession

force_auto_coercion()


class User(MetaData):
    __tablename__ = "console_users"

    id = Column(Integer, primary_key=True)
    name = Column(String(56))
    phone_number = Column(String(200), unique=True)
    email = Column(EmailType, unique=True)
    hashed_password = Column(String(128), nullable=False, default="")
    partner_id = Column(Integer, ForeignKey("console_partners.id"), index=True)
    role_id = Column(Integer, ForeignKey("console_role.id"), index=True)
    is_active = Column(Boolean, default=True, index=True)
    is_deleted = Column(Boolean, default=False)
    is_staff = Column(Boolean, default=False)
    is_admin = Column(Boolean, default=False)
    is_suspended = Column(Boolean, default=False)
    is_internal = Column(Boolean, default=False, index=True)
    is_email_verified = Column(Boolean, default=False)
    is_phone_number_verified = Column(Boolean, default=False)

    # User Enabled Services Info
    is_maglo_enabled = Column(Boolean, default=False, index=True)
    is_talko_enabled = Column(Boolean, default=False, index=True)
    is_babbler_enabled = Column(Boolean, default=False, index=True)

    description = Column(String(200))
    designation = Column(String)
    parent_id = Column(Integer, ForeignKey("console_users.id"), nullable=True)
    alternate_phone_number = Column(String(200), unique=True, nullable=True)
    is_walkthrough_completed = Column(Boolean, default=False, index=True)
    country_id = Column(
        Integer, ForeignKey("console_countries.id"), index=True, nullable=True
    )
    state_id = Column(
        Integer, ForeignKey("console_states.id"), index=True, nullable=True
    )
    city_id = Column(
        Integer, ForeignKey("console_cities.id"), index=True, nullable=True
    )

    is_maglo_publisher = Column(Boolean, default=False)

    cloud_agent_number = Column(String, nullable=True)
    current_status = Column(String(50), nullable=True, default="Away", index=True)
    # Per-user icon override for the user's current custom status. Standard
    # statuses always use their fixed default icon and ignore this column.
    current_status_icon = Column(String(100), nullable=True)
    # Self-referential relationship
    parent = relationship("User", remote_side="User.id", backref="children")

    created_partners = relationship(
        "Partner",
        foreign_keys="Partner.created_by",
        back_populates="creator",
        cascade="all, delete-orphan",
    )
    updated_partners = relationship(
        "Partner",
        foreign_keys="Partner.updated_by",
        back_populates="updater",
        cascade="all, delete-orphan",
    )
    deleted_partners = relationship(
        "Partner",
        foreign_keys="Partner.deleted_by",
        back_populates="deleter",
        cascade="all, delete-orphan",
    )

    # Lazy-loading to avoid circular import
    metadata_entries = relationship(
        "UserMetadata", back_populates="user", uselist=False, lazy="select"
    )

    sessions = relationship("UserSession", back_populates="user")

    # Relationships to country, state, and city
    country = relationship("Countries", back_populates="users")
    state = relationship("States", back_populates="users")
    city = relationship("Cities", back_populates="users")
    otps = relationship("OTP", back_populates="user", cascade="all, delete-orphan")

    partner = relationship("Partner", foreign_keys=[partner_id], back_populates="users")

    __table_args__ = (
        # Ensures only one user per partner_id can have is_maglo_publisher=True
        UniqueConstraint(
            "partner_id", "is_maglo_publisher", name="uq_partner_maglo_publisher"
        ),
        # created_at/updated_at are inherited from MetaData; indexed here
        # only (not on MetaData itself) since the User Listing filters
        # (MGL-9482) are the only range-scan users of these columns.
        Index("ix_console_users_created_at", "created_at"),
        Index("ix_console_users_updated_at", "updated_at"),
    )

    def __repr__(self):
        return f"<User(id={self.id}, email={self.email}, name={self.name}, is_active={self.is_active})>"
