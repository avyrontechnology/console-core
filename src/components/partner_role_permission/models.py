from sqlalchemy import Column, DateTime, ForeignKey, Integer, UniqueConstraint, func
from sqlalchemy.orm import relationship

from src.components.auth.models import Permission, Role
from src.components.database.base_model import MetaData

# from src.components.user.models import User
from src.core.db import Base


class PartnerRolePermission(MetaData):
    __tablename__ = "console_partner_role_permission"

    partner_id = Column(
        Integer,
        ForeignKey("console_partners.id", ondelete="RESTRICT"),
        index=True,
        nullable=False,
    )  # FK
    permission_id = Column(
        Integer,
        ForeignKey("console_permission.id", ondelete="RESTRICT"),
        index=True,
        nullable=False,
    )  # FK
    role_id = Column(
        Integer,
        ForeignKey("console_role.id", ondelete="RESTRICT"),
        index=True,
        nullable=False,
    )  # FK
    created_by = Column(
        Integer, ForeignKey("console_users.id", ondelete="RESTRICT")
    )  # FK

    # unidirectional relation
    permission = relationship("Permission", lazy="select")
    role = relationship("Role", lazy="select")
    creator = relationship("User", foreign_keys=[created_by], lazy="select")
    # Bidirectional relation
    partner = relationship(
        "Partner", back_populates="partner_role_permissions", lazy="select"
    )

    # Define the unique together
    __table_args__ = (
        UniqueConstraint(
            "role_id", "partner_id", "permission_id", name="_role_partner_permission_uc"
        ),
    )

    def __repr__(self):
        return (
            f"<PartnerRolePermission(partner_id={self.partner_id}, "
            f"role_id={self.role_id}, "
            f"permission_id={self.permission_id})>"
        )
