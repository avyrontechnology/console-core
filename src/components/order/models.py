from sqlalchemy import Boolean, Column, Float, ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import JSON
from sqlalchemy.ext.hybrid import hybrid_property
from sqlalchemy.orm import relationship

from src.components.database.base_model import MetaData
from src.components.order.constants import OrderSource, OrderType, PaymentMethod
from src.components.payment.enum import PaymentStatusEnum
from src.components.wallet.enum import Currency


class Order(MetaData):
    """
    Represents a purchase order for base plans or add-ons.
    """

    __tablename__ = "console_orders"

    partner_id = Column(
        Integer, ForeignKey("console_partners.id"), nullable=False, index=True
    )
    plan_id = Column(Integer, ForeignKey("console_plans.id"), nullable=True, index=True)
    add_ons = Column(JSON, nullable=True, default=dict)
    amount = Column(Float, nullable=False)
    currency = Column(String(3), default=Currency.INDIA, nullable=False)
    status = Column(String(50), default=PaymentStatusEnum.PENDING, index=True)
    merchant_transaction_id = Column(
        String(128), unique=True, nullable=True, index=True
    )
    duration = Column(Integer, nullable=False)
    source = Column(String(50), nullable=False, default=OrderSource.CONSOLE)

    is_manually_created = Column(Boolean, default=False, nullable=False, index=True)

    order_type = Column(
        String(20),
        nullable=False,
        default=OrderType.FRESH,
        index=True,
        comment="FRESH | RENEWAL | UPGRADE | DOWNGRADE",
    )

    payment_method = Column(
        String(20),
        nullable=False,
        default=PaymentMethod.GATEWAY,
        index=True,
        comment=(
            "GATEWAY | DIRECT — never null. "
            "Self-serve orders always GATEWAY. "
            "Manual orders: GATEWAY (SDK) or DIRECT (outside system)."
        ),
    )

    original_order_id = Column(
        Integer,
        ForeignKey("console_orders.id"),
        nullable=True,
        index=True,
        comment="Populated for RENEWAL orders; points to the order being renewed.",
    )

    # Relationships
    partner = relationship("Partner", back_populates="orders")
    plan = relationship("Plan", back_populates="orders", lazy="joined")
    entitlements = relationship("Entitlement", back_populates="order")
    payment = relationship("Payment", back_populates="order", uselist=False)

    original_order = relationship(
        "Order",
        foreign_keys=[original_order_id],
        remote_side="Order.id",
        backref="renewals",
    )

    @hybrid_property
    def plan_name(self):
        return self.plan.name if self.plan else None

    def __repr__(self):
        return (
            f"<Order(id={self.id}, partner_id={self.partner_id}, "
            f"plan_id={self.plan_id}, status={self.status}, "
            f"amount={self.amount}, is_manually_created={self.is_manually_created}, "
            f"order_type={self.order_type}, payment_method={self.payment_method})>"
        )
