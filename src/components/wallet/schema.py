from decimal import Decimal
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, field_validator

from src.components.wallet.enum import MAX_WALLET_NUMERIC, ServiceName, TransactionType


class WalletTransactionRequest(BaseModel):
    partner_id: Optional[int] = None

    transaction_type: TransactionType = Field(
        ...,
        description="Transaction type is required",
    )

    debit_from_wallet: Optional[bool] = False

    amount: float = Field(
        ...,
        description="Amount is required",
    )

    service_name: ServiceName = Field(
        ...,
        description="Service Name is required",
    )

    description: Optional[str] = Field(
        None,
        max_length=255,
        description="Description should not exceed 255 characters",
    )

    attributes: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Optional metadata like campaign_id, phone_number_id, etc.",
    )

    class Config:
        json_schema_extra = {
            "example": {
                "partner_id": 12,
                "transaction_type": "CREDIT",
                "amount": 1500.00,
                "service_name": "Maglo",
                "description": "Wallet top-up",
                "attributes": {"campaign_id": "CMP1234"},
                "debit_from_wallet":False,
            }
        }

    @field_validator("amount", mode="before")
    def validate_amount_before(cls, value):
        """Override generic parsing error: invalid number"""
        try:
            float(value)
        except Exception:
            raise ValueError("Invalid amount: must be a number")
        return value

    @field_validator("amount")
    def validate_amount(cls, value):
        """Business rules after parsing"""
        if value <= 0:
            raise ValueError("Invalid amount: must be a positive number")

        if value > MAX_WALLET_NUMERIC:
            raise ValueError(f"Invalid amount: must not exceed {MAX_WALLET_NUMERIC}")
        return value

    @field_validator("service_name", mode="before")
    def validate_service_name_before(cls, value):
        """Override default enum parse error"""
        try:
            ServiceName(value)
        except Exception:
            raise ValueError(
                "Invalid Service Name: must be from existing Product (Maglo, Babbler, or Talko)"
            )
        return value

    @field_validator("transaction_type", mode="before")
    def validate_transaction_type_before(cls, value):
        """Override default enum parse error"""
        try:
            TransactionType(value)
        except Exception:
            raise ValueError(
                "Invalid Transaction Type: must be from existing type (CREDIT, DEBIT, FREEZE, or UNFREEZE)"
            )
        return value

    @field_validator("description", mode="before")
    def validate_description_before(cls, value):
        """Override default too-long error"""
        if value is not None and len(str(value)) > 255:
            raise ValueError("Description should not exceed 255 characters")
        return value


class WalletResponse(BaseModel):
    """Schema for wallet details response."""

    partner_id: int
    balance: Decimal
    frozen_balance: Decimal
    currency: str

    class Config:
        from_attributes = True

class WalletRPCResponse(BaseModel):
    """Schema for wallet details response in gRPC."""

    id: Optional[int] = None
    partner_id: Optional[int] = None
    balance: Optional[Decimal] = None
    currency: Optional[str] = None
    frozen_balance: Optional[Decimal] = None
    is_active: Optional[bool] = False
    is_wallet_enabled: Optional[bool] = False
    created_at: Optional[int] = None
    updated_at: Optional[int] = None

class WalletTransactionResponse(BaseModel):
    """Schema for individual wallet transaction."""

    id: int
    wallet_id: int
    transaction_type: str = Field(...)
    service_name: str = Field(...)
    previous_balance: Decimal = Field(...)
    amount: Decimal = Field(...)
    remaining_balance: Decimal = Field(...)
    description: Optional[str] = Field(None)
    attributes: Optional[Dict[str, Any]] = Field(None)
    status: str
    created_at: int
    additional_info: Any

    class Config:
        from_attributes = True


class WalletTransactionListResponse(BaseModel):
    """Schema for paginated wallet transactions response."""

    total_count: int
    limit: int
    offset: int
    transactions: List[WalletTransactionResponse]
