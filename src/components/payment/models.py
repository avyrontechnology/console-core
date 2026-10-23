import uuid
from sqlalchemy import JSON, Column, ForeignKey, Numeric, String
from sqlalchemy.orm import relationship
from sqlalchemy.dialects.postgresql import UUID

from src.components.database.base_model import MetaData


class Payment(MetaData):
    """
    Represents a payment transaction made by a partner for a specific entity.
    """

    __tablename__ = "console_payments"

    partner_id = Column(
        UUID(as_uuid=True),
        ForeignKey("console_partners.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    order_id = Column(
        UUID(as_uuid=True),
        ForeignKey("console_orders.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    amount = Column(Numeric(10, 2), nullable=False)
    entity_name = Column(String(50), nullable=False)
    vendor = Column(String(50), nullable=False)
    payment_status = Column(String(50), nullable=False)
    payment_method = Column(String(50), nullable=True)
    merchant_transaction_id = Column(
        String(128), unique=True, nullable=True, index=True
    )
    payment_id = Column(String(128), unique=True, nullable=True, index=True)
    additional_info = Column(JSON, nullable=True)

    partner = relationship("Partner", back_populates="payments")
    order = relationship("Order", back_populates="payment", uselist=False)

    def __repr__(self):
        return (
            "<Payment(order_id={}, amount={}, entity={}, vendor={}, status={})>".format(
                self.order_id,
                self.amount,
                self.entity_name.value,
                self.vendor.value,
                self.payment_status.value,
            )
        )
