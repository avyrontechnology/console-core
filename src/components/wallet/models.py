import uuid
from sqlalchemy import JSON, Column, Enum, ForeignKey, Numeric, String
from sqlalchemy.orm import relationship
from sqlalchemy.dialects.postgresql import UUID

from src.components.database.base_model import MetaData
from src.components.partner.models import Partner
from src.components.wallet.enum import Currency, ServiceName, TransactionType


class Wallet(MetaData):
    """
    Wallet is associated with a Partner.
    It tracks available and frozen balances in INR.
    """

    __tablename__ = "console_wallets"

    partner_id = Column(
        UUID(as_uuid=True),
        ForeignKey("console_partners.id", ondelete="CASCADE"),
        unique=True,
        nullable=False,
    )
    balance = Column(Numeric(12, 2), default=0, nullable=False)
    frozen_balance = Column(Numeric(12, 2), default=0, nullable=False)
    currency = Column(String(6), default=Currency.INDIA, nullable=False)

    # Relationships
    partner = relationship("Partner", back_populates="wallet")
    transactions = relationship(
        "WalletTransaction", back_populates="wallet", cascade="all, delete-orphan"
    )

    @property
    def available_balance(self):
        """
        Returns the spendable (available) balance for the wallet.
        """
        return (self.balance or 0) - (self.frozen_balance or 0)

    def __repr__(self):
        return (
            f"<Wallet(id={self.id}, partner_id={self.partner_id}, "
            f"balance={self.balance}, frozen_balance={self.frozen_balance})>"
        )


class WalletTransaction(MetaData):
    """
    Stores transaction history for each Partner wallet.
    """

    __tablename__ = "console_wallet_transactions"

    wallet_id = Column(
        UUID(as_uuid=True), ForeignKey("console_wallets.id", ondelete="CASCADE"), nullable=False
    )
    transaction_type = Column(Enum(TransactionType), nullable=False)
    service_name = Column(Enum(ServiceName), nullable=False)
    description = Column(String(255), nullable=True)
    amount = Column(Numeric(12, 2), nullable=False)
    remaining_balance = Column(Numeric(12, 2), nullable=False)
    previous_balance = Column(Numeric(12, 2), nullable=False)
    attributes = Column(
        JSON,
        nullable=True,
        comment="Stores dynamic fields like campaign_id, phone_number_id, etc.",
    )

    wallet = relationship("Wallet", back_populates="transactions")

    def __repr__(self):
        return (
            f"<WalletTransaction(wallet_id={self.wallet_id}, "
            f"type={self.transaction_type.name}, amount={self.amount})>"
        )
