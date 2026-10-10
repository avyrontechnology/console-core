from typing import Any, Dict, List, Optional

from pydantic import BaseModel, field_validator

# PostgreSQL INTEGER (int4) maximum value: 2,147,483,647
# Reference: Signed 32-bit integer range
MAX_INT_32 = 2_147_483_647


class UpdateEntitlementStartDateRequest(BaseModel):
    """
    Request schema for updating entitlement start date.
    Custom errors only. DB-safe validation.
    """

    order_id: Any
    start_date: Any

    @field_validator("order_id")
    @classmethod
    def validate_order_id(cls, v):
        if v is None:
            raise ValueError("order_id is required")

        if not isinstance(v, int):
            raise ValueError("order_id must be an integer")

        if v <= 0:
            raise ValueError("order_id must be a positive integer")

        if v > MAX_INT_32:
            raise ValueError("order_id exceeds maximum allowed value")

        return v

    @field_validator("start_date")
    @classmethod
    def validate_start_date(cls, v):
        if v is None:
            raise ValueError("start_date is required and cannot be null")

        if not isinstance(v, int):
            raise ValueError("start_date must be an integer timestamp in milliseconds")

        if v <= 0:
            raise ValueError("start_date must be a positive integer timestamp")

        if len(str(v)) != 13:
            raise ValueError(
                "start_date must be a 13-digit epoch timestamp in milliseconds"
            )

        return v


class EntitlementCreate(BaseModel):
    order_id: int
    partner_id: int
    service_name: str  # console / babbler / maglo etc.
    modules: List[str]
    limits: Dict
    created_by: Optional[int] = None
    end_date: int


class EntitlementUpdate(BaseModel):
    modules: Optional[List[str]] = None
    limits: Optional[Dict] = None
    start_date: Optional[int] = None
    end_date: Optional[int] = None
    is_active: Optional[bool] = None
    updated_by: Optional[int] = None


class EntitlementResponse(BaseModel):
    id: int
    order_id: int
    partner_id: int
    service_name: str
    modules: List[str]
    limits: Dict
    start_date: int
    end_date: int
    is_active: bool

    class Config:
        from_attributes = True


class UpdateEntitlementStartDateResponse(BaseModel):
    id: int
    order_id: int
    partner_id: int
    service_name: str
    start_date: int
    end_date: int
    is_active: bool
    start_date_update_count: int

    class Config:
        from_attributes = True
