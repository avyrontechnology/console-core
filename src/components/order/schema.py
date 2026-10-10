from typing import Any, Dict, List, Optional, Set, Tuple

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from src.components.common.constants import FieldType, Limits
from src.components.common.utility import SchemaValidator
from src.components.order.constants import OrderSource, OrderType, PaymentMethod
from src.components.plan.constants import PlanCustomLimitKeys
from src.components.wallet.enum import Currency


class ValidatableSchema(BaseModel):
    __validation_rules__: Dict[str, Dict[str, Any]] = {}

    def validate_payload(self) -> Tuple[Dict[str, Any], Optional[str]]:
        rules: Dict[str, Dict[str, Any]] = {}
        for field_name, config in self.__validation_rules__.items():
            rules[field_name] = {**config, "value": getattr(self, field_name, None)}
        return SchemaValidator.validate(rules)


class OrderBase(BaseModel):
    plan_id: Optional[int] = Field(None, ge=0)
    add_ons: Optional[Dict[str, int]] = Field(default_factory=dict)
    amount: float
    currency: str = Field(Currency.INDIA, min_length=3, max_length=3)
    source: Optional[str] = None

    @model_validator(mode="after")
    def validate_add_ons_or_plan(self):
        if not self.plan_id and not self.add_ons:
            raise ValueError("Either plan_id or add_ons is required")

        for key, val in self.add_ons.items():
            if not isinstance(val, int):
                raise ValueError(f"Add-on value for '{key}' must be integer")
        return self

    @field_validator("amount")
    @classmethod
    def validate_amount(cls, amount: float):
        if not (100 <= amount <= 50000000):
            raise ValueError(
                "Amount must be greater than 99 and less than or equal to 50000000"
            )
        return amount

    @model_validator(mode="after")
    def validate_source(self):
        if not self.source:
            raise ValueError("source field required")

        VALID_ORDER_SOURCES: set[str] = {
            value
            for key, value in OrderSource.__dict__.items()
            if key.isupper() and isinstance(value, str)
        }

        if self.source not in VALID_ORDER_SOURCES:
            raise ValueError(
                f"invalid source: {self.source}, "
                f"Valid sources are: {', '.join(sorted(VALID_ORDER_SOURCES))}"
            )

        return self

    @model_validator(mode="after")
    def validate_all(self):
        allowed_limit_keys: Set[str] = {
            value
            for class_value in PlanCustomLimitKeys.__dict__.values()
            if isinstance(class_value, type)
            for attribute_name, value in class_value.__dict__.items()
            if attribute_name.isupper()
        }

        for limit_key, limit_value in self.add_ons.items():
            if limit_key not in allowed_limit_keys:
                raise ValueError(
                    f"Invalid limit key '{limit_key}'. Allowed keys are: "
                    f"{', '.join(sorted(allowed_limit_keys))}"
                )

            if not isinstance(limit_value, int) or limit_value == 0:
                raise ValueError(
                    f"limit value for '{limit_key}' must be a positive/negative integer"
                )
        return self


class OrderValidateRequest(BaseModel):
    order_id: str = Field(..., description="Merchant transaction ID (gateway order ID)")
    payment_id: str = Field(..., description="Gateway payment ID")
    signature: str = Field(..., description="Gateway signature for verification")


class OrderBillingDetailsRequest(BaseModel):
    """
    Order billing details request.

    Rules:
    - Either plan_id or add_ons must be provided
    """

    plan_id: Optional[int] = None
    add_ons: Optional[Dict[str, int]] = Field(default_factory=dict)
    coupon: Optional[str] = None

    @staticmethod
    def _get_allowed_limit_keys() -> Set[str]:
        """Extract allowed limit keys from PlanCustomLimitKeys."""
        return {
            v
            for cls in PlanCustomLimitKeys.__dict__.values()
            if isinstance(cls, type)
            for k, v in cls.__dict__.items()
            if k.isupper()
        }

    def _validate_plan_or_addons(self) -> None:
        """Validate that either plan_id or add_ons is provided."""
        if self.plan_id is None and not self.add_ons:
            raise ValueError("Either plan_id or add_ons must be provided")

    def _validate_add_ons(self, allowed_keys: Set[str]) -> None:
        """Validate add-ons keys and values."""
        if not self.add_ons:
            return

        for key, val in self.add_ons.items():
            if key not in allowed_keys:
                raise ValueError(
                    f"Invalid limit key '{key}'. "
                    f"Allowed keys are: {', '.join(sorted(allowed_keys))}"
                )
            if not isinstance(val, int) or val < 1:
                raise ValueError(f"Add-on '{key}' must be a positive integer")

    @model_validator(mode="after")
    def validate_request(self):
        """Validate the complete request."""
        self._validate_plan_or_addons()
        allowed_limit_keys = self._get_allowed_limit_keys()
        self._validate_add_ons(allowed_limit_keys)
        return self


_VALID_PAYMENT_METHODS: set[str] = {
    value
    for key, value in PaymentMethod.__dict__.items()
    if key.isupper() and isinstance(value, str)
}

_ORDER_TYPE_DESC: str = " | ".join(
    value
    for key, value in OrderType.__dict__.items()
    if key.isupper() and isinstance(value, str)
)


_CURRENCY_TYPE_DESC: str = " | ".join(
    value
    for key, value in Currency.__dict__.items()
    if key.isupper() and isinstance(value, str)
)


class ManualOrderCreateRequest(ValidatableSchema):
    partner_id: Any
    plan_id: Any
    amount: Any
    payment_method: Any
    add_ons: Any = None
    currency: Any = None

    __validation_rules__ = {
        "partner_id": {
            "required": True,
            "type": FieldType.INTEGER,
            "min": 1,
            "max": Limits.MAX_INT,
        },
        "plan_id": {
            "required": True,
            "type": FieldType.INTEGER,
            "min": 1,
            "max": Limits.MAX_INT,
        },
        "amount": {
            "required": True,
            "type": FieldType.INTEGER,
            "min": 100,
            "max": 50000000,
        },
        "payment_method": {
            "required": True,
            "type": FieldType.STRING,
            "values": list(_VALID_PAYMENT_METHODS),
        },
        "currency": {
            "required": False,
            "type": FieldType.STRING,
            "min": 3,
            "max": 3,
            "values": list(_CURRENCY_TYPE_DESC.split(" | ")),
        },
        "add_ons": {
            "required": False,
            "type": FieldType.DICT,
        },
    }

    def validate_payload(self) -> Tuple[Dict[str, Any], Optional[str]]:
        validated, error = super().validate_payload()
        if error:
            return {}, error

        allowed_limit_keys: Set[str] = {
            v
            for cls in PlanCustomLimitKeys.__dict__.values()
            if isinstance(cls, type)
            for k, v in cls.__dict__.items()
            if k.isupper()
        }

        if self.add_ons:
            normalised_addons = {}

            for key, value in self.add_ons.items():

                if key not in allowed_limit_keys:
                    return (
                        {},
                        f"Invalid limit key '{key}'. Allowed keys are: "
                        f"{', '.join(sorted(allowed_limit_keys))}",
                    )

                if not isinstance(value, int) or value < 1:
                    return {}, f"Add-on '{key}' must be a positive integer"

                normalised_addons[key] = value

            validated["add_ons"] = normalised_addons

        else:
            validated["add_ons"] = {}

        return validated, None


class OrderResponse(OrderBase):
    id: int
    status: str
    merchant_transaction_id: Optional[str]
    created_at: Optional[int]
    plan_name: Optional[str] = None
    duration: Optional[int] = None

    model_config = ConfigDict(from_attributes=True)


class OrderHistoryItemResponse(BaseModel):
    # Order details
    order_id: int
    source: str
    order_status: str
    order_currency: str
    merchant_transaction_id: Optional[str] = None
    duration: int

    is_manually_created: bool = False
    order_type: str = Field(default=OrderType.FRESH, description=_ORDER_TYPE_DESC)
    payment_method: Optional[str] = Field(
        default=PaymentMethod.GATEWAY,
        description="GATEWAY | DIRECT",
    )
    original_order_id: Optional[int] = None

    # Partner details
    partner_id: Optional[int] = None
    partner_name: Optional[str] = None
    partner_email: Optional[str] = None
    partner_phone_number: Optional[str] = None
    partner_country: Optional[str] = None
    partner_state: Optional[str] = None
    partner_city: Optional[str] = None
    partner_gst_no: Optional[str] = None
    partner_is_active: Optional[bool] = None

    # Plan details
    plan_id: Optional[int] = None
    plan_name: Optional[str] = None
    plan_type: Optional[str] = None
    plan_duration_months: Optional[int] = None
    duration_in_days: Optional[int] = None
    plan_limits: Dict = Field(default_factory=dict)

    # Addons and pricing
    add_ons: Dict = Field(default_factory=dict)
    plan_price: Optional[float] = None
    plan_discount_percentage: Optional[float] = None
    total_price: float

    # Timestamps
    order_created_at: int
    order_created_by: Optional[int] = None
    order_updated_at: Optional[int] = None
    order_updated_by: Optional[int] = None

    # Entitlement details
    entitlement_start_date: Optional[int] = None
    entitlement_end_date: Optional[int] = None
    entitlement_is_active: Optional[bool] = None

    # Payment details
    payment_gateway: Optional[str] = None
    payment_status: Optional[str] = None
    payment_date: Optional[int] = None
    subscription_status: Optional[str] = None

    class Config:
        from_attributes = True


class OrderHistoryPaginatedResponse(BaseModel):
    total_count: int
    limit: int
    offset: int
    data: List[OrderHistoryItemResponse]

    class Config:
        from_attributes = True
