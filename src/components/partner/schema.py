from uuid import UUID
import re
from typing import Any, Dict, List, Optional

from pydantic import (
    BaseModel,
    ConfigDict,
    EmailStr,
    Field,
    field_validator,
    model_validator,
)

from src.components.auth.constant import AuthExceptionMsg
from src.components.partner.constant import DashboardFilters, PartnerStatus
from src.components.partner_config.constants import SubscriptionModeEnum
from src.components.payment.enum import PaymentBillingCycle


class BasePartnerData(BaseModel):
    name: str = Field(max_length=128)
    company_legal_name: str = Field(max_length=128)
    gst_no: Optional[str] = None
    cin_no: Optional[str] = None
    active_license: Optional[int] = 3
    description: Optional[str] = Field(default=None, max_length=256)
    is_free_trail_enabled: Optional[bool] = False
    is_email_verification_enabled: Optional[bool] = False
    is_phone_number_verification_enabled: Optional[bool] = False
    subscription_mode: Optional[str] = SubscriptionModeEnum.SELF_SERVED.value

    @field_validator("gst_no")
    def validate_gst_no(cls, value):
        if value and not re.match(
            r"^[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z]{1}[1-9A-Z]{1}Z[0-9A-Z]{1}$", value
        ):
            raise ValueError("Invalid GST number")
        return value

    @field_validator("cin_no")
    def validate_cin_no(cls, value):
        if value and not re.match(
            r"^[A-Z]{1}[0-9]{5}[A-Z]{2}[0-9]{4}[A-Z]{3}[0-9]{6}$", value
        ):
            raise ValueError("Invalid CIN number")
        return value

    @model_validator(mode="after")
    def set_license_for_trial(self):
        if self.is_free_trail_enabled:
            self.active_license = 3
        return self

    @field_validator("subscription_mode")
    def validate_subscription_mode(cls, value):
        if value not in [e.value for e in SubscriptionModeEnum]:
            allowed = ", ".join([e.value for e in SubscriptionModeEnum])
            raise ValueError(f"subscription_mode must be one of: {allowed}")
        return value


class PartnerResponse(BaseModel):
    name: str
    company_legal_name: str
    gst_no: Optional[str] = None
    cin_no: Optional[str] = None
    active_license: Optional[int] = 0
    description: Optional[str] = None
    email: Optional[EmailStr] = None
    phone_number: Optional[str] = None
    is_active: Optional[bool] = None
    is_partner_paid: bool | None = None
    is_free_trial_enabled: bool | None = None
    active_talko_users: int | None = 0
    id: UUID

    model_config = ConfigDict(
        from_attributes=True,
    )


class PartnerCreateResponse(BaseModel):
    name: str
    company_legal_name: str
    gst_no: Optional[str] = None
    cin_no: Optional[str] = None
    active_license: Optional[int] = 0
    description: Optional[str] = None
    id: UUID

    model_config = ConfigDict(
        from_attributes=True,
    )


class PartnerProfileResponse(BaseModel):
    message: str
    partner_logo_url: Optional[str] = None


class ChangePartnerStatusRequest(BaseModel):
    partner_id: UUID
    status: Optional[str] = None
    is_feedback_enabled: Optional[bool] = None

    @field_validator("status")
    def validate_status(cls, value):
        if value is not None and value not in PartnerStatus.choices():
            raise ValueError(
                f"Invalid status: {value}. Must be one of {PartnerStatus.choices()}"
            )
        return value

    @model_validator(mode="after")
    def check_at_least_one(self):
        if self.status is None and self.is_feedback_enabled is None:
            raise ValueError(
                "At least one of 'status' or 'is_feedback_enabled' must be provided"
            )
        return self

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "partner_id": 12,
                "status": "ACTIVE",
                "is_feedback_enabled": True,
            }
        }
    )


class ChangePartnerStatusResponse(BaseModel):
    id: UUID
    name: str
    partner_status: str
    is_feedback_enabled: bool

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "id": 12,
                "name": "Affinity education",
                "partner_status": "ACTIVE",
                "is_feedback_enabled": True,
            }
        }
    )


class UpdatePartnerRequest(BasePartnerData):
    name: Optional[str] = Field(default=None, max_length=128)
    company_legal_name: Optional[str] = Field(default=None, max_length=128)
    billing_cycle: Optional[str] = None

    model_config = ConfigDict(
        from_attributes=True,
    )

    @field_validator("billing_cycle")
    def validate_billing_cycle(cls, v):
        if v is None:
            return v
        allowed = {
            value
            for key, value in vars(PaymentBillingCycle).items()
            if not key.startswith("__")
        }
        if v not in allowed:
            raise ValueError(f"Billing_cycle must be one of {allowed}")
        return v


class PartnerDetails(BaseModel):
    name: str
    company_legal_name: str
    gst_no: Optional[str] = None
    cin_no: Optional[str] = None

    @field_validator("gst_no")
    def validate_gst_no(cls, value):
        if value and not re.match(r"^\d{2}[A-Z]{5}\d{4}[A-Z][1-9A-Z]Z[\dA-Z]$", value):
            raise ValueError("Invalid GST number")
        return value

    @field_validator("cin_no")
    def validate_cin_no(cls, value):
        if value and not re.match(r"^[A-Z]\d{5}[A-Z]{2}\d{4}[A-Z]{3}\d{6}$", value):
            raise ValueError("Invalid CIN number")
        return value

    model_config = ConfigDict(extra="allow")


class PartnerMetaDataDetails(BaseModel):
    is_talko_free_trial__enabled: Optional[bool] = False
    is_email_verification_enabled: Optional[bool] = True
    is_phone_number_verification_enabled: Optional[bool] = False
    subscription_mode: Optional[str] = SubscriptionModeEnum.SELF_SERVED.value

    model_config = ConfigDict(extra="allow")

    @field_validator("subscription_mode")
    def validate_subscription_mode(cls, value):
        if value not in [e.value for e in SubscriptionModeEnum]:
            allowed = ", ".join([e.value for e in SubscriptionModeEnum])
            raise ValueError(f"subscription_mode must be one of: {allowed}")
        return value


class UserDetails(BaseModel):
    name: str
    email: EmailStr
    phone_number: str
    password: str

    def format_number(self, phone_number: str) -> str:
        return phone_number.removeprefix("tel:").replace("-", "").strip()

    @field_validator("password")
    def validate_password(cls, password: str) -> str:
        regex = r"^(?=.*[A-Z])(?=.*[a-z])(?=.*\d)(?=.*[!@#$%^&*(),.?\":{}|<>]).{8,}$"
        if not re.match(regex, password):
            raise ValueError(AuthExceptionMsg.PASSWORD_NOT_STRONG)
        return password

    @field_validator("name")
    def validate_name(cls, value):
        value = value.strip()
        # Regex for valid name (allow spaces, hyphens, and apostrophes)
        if not re.match(r"^[A-Za-z]+([ ]?[A-Za-z]+)*$", value):
            raise ValueError("Name contains invalid characters")
        return value

    @field_validator("phone_number")
    @classmethod
    def normalize_phone_number(cls, value: any) -> str:
        value = str(value)
        value = (
            value.removeprefix("tel:")
            .replace("-", "")
            .replace("(", "")
            .replace(" ", "")
            .replace(")", "")
            .strip()
        )
        if not value.startswith("+91"):
            value = "+91" + value.lstrip("0")
        pattern = r"^\+[1-9]\d{7,14}$"
        if not re.match(pattern, value):
            raise ValueError("Enter a valid phone number (e.g., +919988776655).")
        return value

    model_config = ConfigDict(extra="allow")


class PartnerOnboardingDetails(BaseModel):
    partner_details: PartnerDetails
    partner_meta_data: PartnerMetaDataDetails
    user_details: UserDetails


class PartnerOnboardingResponse(PartnerCreateResponse):
    user_login_token: Optional[str] = None


class PartnerFilterRequest(BaseModel):

    is_custom_role_permission_enabled: Optional[bool] = Field(
        default=False,
        description="it will filter the partners with is custom role permission value true if the value set to true.",
    )

    dashboard_filters: Optional[DashboardFilters] = None

    filters: Optional[List[Dict[str, Any]]] = Field(
        default=[],
        description="List of filter criteria. Example: [{'field': 'user_active', 'operator': '=', 'value': 'true'}]",
        examples=[[{"field": "", "operator": "", "value": ""}]],
    )

    order_by: Optional[List[Dict[str, str]]] = Field(
        default=[],
        description="List of ordering criteria. Example: [{'field': 'user_name', 'direction': 'ASC'}]",
        examples=[[{"field": "", "direction": ""}]],
    )

    limit: Optional[int] = Field(
        default=100,
        ge=1,
        le=500,
        description="Maximum number of records to return (1-1000)",
    )

    offset: Optional[int] = Field(
        default=0,
        ge=0,
        description="Number of records to skip for pagination (0 for first page)",
    )

    @field_validator("filters")
    def validate_id_field(cls, filters):
        MAX_INT = 2147483647
        for f in filters or []:
            if isinstance(f, dict) and f.get("field") == "id":
                value = f.get("value")
                try:
                    value_int = int(value)
                except (TypeError, ValueError):
                    raise ValueError("Please enter a valid numeric ID")

                if value_int > MAX_INT:
                    raise ValueError("ID exceeds maximum limit")
                if value_int < 0:
                    raise ValueError("ID cannot be negative")
        return filters

    model_config = ConfigDict(from_attributes=True)


class PaginatedPartnerResponse(BaseModel):

    total_count: int
    limit: int
    offset: int
    partners_data: List[PartnerResponse]

    model_config = ConfigDict(from_attributes=True)


class TogglePartnerActivation(BaseModel):
    is_active: Optional[bool] = False


class TogglePartnerActivationResponse(BaseModel):
    is_active: bool

    model_config = ConfigDict(from_attributes=True)


class ApiKeyOnboarding(BaseModel):
    partner_id: UUID
    is_active: bool
    created_by: Optional[UUID] = None
