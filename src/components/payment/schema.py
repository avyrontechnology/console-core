from uuid import UUID
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, model_validator


class InitiateOrderRequest(BaseModel):
    partner_id: UUID
    amount: float
    currency: str = Field("INR", min_length=3, max_length=3)
    entity_name: str
    notes: Optional[Dict[str, Any]] = None
    order_id: Optional[UUID] = None

    @model_validator(mode="after")
    def check_amount_positive(self):
        if self.amount <= 0:
            raise ValueError("Amount must be positive")
        return self


class ValidateOrderRequest(BaseModel):
    order_id: str
    payment_id: str
    signature: str


class PaymentHistoryPaginatedResponse(BaseModel):
    total_count: int
    limit: int
    offset: int
    data: List[Dict[str, Any]]
