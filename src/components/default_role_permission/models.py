from sqlalchemy import Column, DateTime, ForeignKey, Integer, UniqueConstraint, func
from sqlalchemy.orm import relationship

from src.components.auth.models import Permission, Role
from src.components.database.base_model import MetaData

# from src.components.user.models import User
from src.core.db import Base


class DefaultRolePermission(MetaData):
    __tablename__ = "console_default_role_permission"

    role_id = Column(
        Integer,
        ForeignKey("console_role.id", ondelete="RESTRICT"),
        index=True,
        nullable=False,
    )  # FK
    permission_id = Column(
        Integer,
        ForeignKey("console_permission.id", ondelete="RESTRICT"),
        index=True,
        nullable=False,
    )  # FK
    created_by = Column(Integer, ForeignKey("console_users.id", ondelete="RESTRICT"))

    # Relations
    role = relationship("Role", lazy="select")
    permission = relationship("Permission", lazy="select")
    creator = relationship("User", foreign_keys=[created_by], lazy="select")

    __table_args__ = (
        UniqueConstraint(
            "role_id", "permission_id", name="_default_role_permission_uc"
        ),
    )

    def __repr__(self):
        return (
            f"<DefaultRolePermission(role_id={self.role_id}, "
            f"permission_id={self.permission_id})>"
        )
