from sqlalchemy import BigInteger, Boolean, Column, ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import ARRAY, JSON
from sqlalchemy.orm import relationship

from src.components.common.datetime import DateTimeUtil
from src.components.database.base_model import MetaData


class Entitlement(MetaData):
    __tablename__ = "console_entitlements"

    order_id = Column(
        Integer, ForeignKey("console_orders.id"), nullable=False, index=True
    )
    partner_id = Column(
        Integer, ForeignKey("console_partners.id"), nullable=False, index=True
    )

    service_name = Column(String(32), nullable=False, index=True)

    # Aggregated limits (base + add-ons)
    limits = Column(JSON, nullable=False, default=dict)
    modules = Column(ARRAY(String), nullable=True)

    is_manually_deactivated = Column(
        Boolean,
        default=False,
        nullable=False,
        comment="True if deactivated manually due to dispute or other reasons",
    )
    start_date_update_count = Column(Integer, default=0)

    start_date = Column(
        BigInteger,
        default=lambda: int(DateTimeUtil.get_current_time()),
        nullable=False,
        index=True,
    )

    end_date = Column(
        BigInteger,
        default=None,
        nullable=True,
        index=True,
    )
    is_active = Column(Boolean, default=True, index=True)

    # Relationships
    order = relationship("Order", back_populates="entitlements")
    partner = relationship("Partner", back_populates="entitlements")

    def __repr__(self):
        return (
            f"<Entitlement(id={self.id}, partner_id={self.partner_id}, "
            f"service_name={self.service_name}, "
            f"is_active={self.is_active}, end_date={self.end_date})>"
        )
