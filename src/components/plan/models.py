"""SQLAlchemy Plan model."""

from sqlalchemy import Boolean, Column, Float, Integer, String
from sqlalchemy.dialects.postgresql import ARRAY, JSON
from sqlalchemy.orm import relationship

from src.components.database.base_model import MetaData
from src.components.plan.constants import PlanType, Platform
from src.components.wallet.enum import Currency


class Plan(MetaData):
    """
    Represents a subscription Plan in the console.
    """

    __tablename__ = "console_plans"

    name = Column(String(100), nullable=False)
    description = Column(String(500), nullable=True)

    modules = Column(ARRAY(String), nullable=True)

    price = Column(Float, nullable=True)
    discount_percentage = Column(Float, nullable=True, default=0.0)

    currency = Column(String(3), default=str(Currency.INDIA))

    limits = Column(JSON, nullable=True, default=dict)

    is_active = Column(Boolean, default=True)

    plan_type = Column(
        String(20), nullable=False, default=PlanType.STANDARD, index=True
    )

    hierarchy = Column(Integer, nullable=False, unique=True)

    duration = Column(Integer, nullable=False)

    tag = Column(String(30), nullable=False, index=True)

    service_name = Column(
        String(100), nullable=False, index=True, default=str(Platform.CONSOLE)
    )

    is_free_trial = Column(Boolean, default=False)

    otc_charge = Column(Float, nullable=True, default=0.0)

    # Relationships
    orders = relationship("Order", back_populates="plan")

    def __repr__(self) -> str:
        return (
            f"<Plan(id={self.id}, name='{self.name}', price={self.price}, "
            f"currency='{self.currency}')>"
        )
