"""SQLAlchemy model for Grace Period."""

from sqlalchemy import BigInteger, Column, ForeignKey, Integer, String, Text
from sqlalchemy.orm import relationship

from src.components.database.base_model import MetaData
from src.components.database.model_config import TABLES
from src.components.grace.constants import GraceStatus


class GracePeriod(MetaData):
    """
    Tracks grace periods granted to partners after entitlement expiry.

    Grace allows a partner to continue using services for a limited number
    of days without a live entitlement or new order. It is always granted
    manually by an internal user.

    Key rules:
    - One ACTIVE record per partner + service_name at a time.
    - No existing tables (Order, Entitlement) are modified when grace is active.
    - consumed_days is NULL while ACTIVE; set at settlement or expiry.
    - settled_by_order_id is populated automatically when the partner pays.
    """

    __tablename__ = TABLES.GRACE_PERIODS

    partner_id = Column(
        Integer,
        ForeignKey("console_partners.id"),
        nullable=False,
        index=True,
    )
    service_name = Column(
        String(32),
        nullable=False,
        index=True,
    )
    remark = Column(
        Text,
        nullable=True,
        comment="Reason / notes entered by the sales user",
    )
    granted_days = Column(
        Integer,
        nullable=False,
        comment="Number of days granted (1 to MAX_GRACE_DAYS_PER_ATTEMPT)",
    )
    start_date = Column(
        BigInteger,
        nullable=False,
        comment="Epoch ms — the day grace was granted",
    )
    end_date = Column(
        BigInteger,
        nullable=False,
        comment="Epoch ms — start_date + granted_days * 86400000, auto-calculated",
    )
    consumed_days = Column(
        Integer,
        nullable=True,
        comment="Set at settlement or expiry. NULL while ACTIVE.",
    )
    status = Column(
        String(20),
        nullable=False,
        default=GraceStatus.ACTIVE,
        index=True,
        comment="ACTIVE | EXPIRED | SETTLED",
    )
    attempt_number = Column(
        Integer,
        nullable=False,
        comment="Sequential attempt count per partner + service (1, 2, 3...)",
    )
    settled_at = Column(
        BigInteger,
        nullable=True,
        comment="Epoch ms — when grace was auto-settled on payment",
    )
    settled_by_order_id = Column(
        Integer,
        ForeignKey("console_orders.id"),
        nullable=True,
        index=True,
        comment="Order that triggered settlement",
    )

    # ── Relationships ─────────────────────────────────────────────────────────
    partner = relationship("Partner", foreign_keys=[partner_id])
    settled_by_order = relationship("Order", foreign_keys=[settled_by_order_id])
    created_by_user = relationship(
        "User",
        foreign_keys="GracePeriod.created_by",
        primaryjoin="GracePeriod.created_by == User.id",
        lazy="selectin",
    )

    @property
    def granted_by_name(self) -> str:
        """
        Human-readable name of the internal user who granted this grace period.
        Sourced from the User relationship on created_by (MetaData base field).
        Returns empty string if relationship not loaded or user has no name.
        """
        if self.created_by_user and self.created_by_user.name:
            return self.created_by_user.name
        return ""

    def __repr__(self) -> str:
        return (
            "<GracePeriod(id={}, partner_id={}, service={}, "
            "status={}, granted_days={}, attempt={})>".format(
                self.id,
                self.partner_id,
                self.service_name,
                self.status,
                self.granted_days,
                self.attempt_number,
            )
        )
