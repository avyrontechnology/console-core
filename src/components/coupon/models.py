import uuid
from sqlalchemy import Boolean, Column, Float, String, BigInteger
from sqlalchemy.dialects.postgresql import ARRAY, UUID

from src.components.database.base_model import MetaData


class Coupon(MetaData):

    __tablename__ = "console_coupons"

    name = Column(String(100), nullable=False, unique=True)
    plans = Column(ARRAY(UUID(as_uuid=True)), nullable=False)
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

    def __repr__(self) -> str:
        return (
            f"<Coupon id={self.id} name={self.name} "
            f"discount={self.discount_percentage}% active={self.is_active}>"
        )
