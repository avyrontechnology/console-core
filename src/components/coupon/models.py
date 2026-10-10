from sqlalchemy import Boolean, Column, Float, String, BigInteger
from sqlalchemy.dialects.postgresql import ARRAY

from sqlalchemy.orm import relationship

from src.components.database.base_model import MetaData


class Coupon(MetaData):

    __tablename__ = "console_coupons"

    name = Column(String(100), nullable=False, unique=True)
    plans = Column(ARRAY(int), nullabe=False)
    start_date = Column(
        BigInteger,
        nullable=False,
        index=True,
    )

    end_date = Column(
        BigInteger,
        nullable=False,
        index=True,
    )
    discount_percentage = Column(Float, nullable=False, default=0.0)

    is_active = Column(Boolean, default=True)

    # Relationships
    orders = relationship("Order", back_populates="coupon")

    def __repr__(self) -> str:
        return (
            f"<Coupon id={self.id} name={self.name} "
            f"discount={self.discount_percentage}% active={self.is_active}>"
        )
