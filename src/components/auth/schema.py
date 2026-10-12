from uuid import UUID
import re
from dataclasses import dataclass
from typing import List, Optional, Any

from pydantic import (
    BaseModel,
    ConfigDict,
    EmailStr,
    Field,
    TypeAdapter,
    ValidationError,
    field_validator,
    model_validator,
)

from src.components.auth.constant import AuthExceptionMsg, UserNameLength

email_adapter = TypeAdapter(EmailStr)


class UserBase(BaseModel):
    name: str = Field(
        ...,
        min_length=UserNameLength.NAME_MIN_LENGTH,
        max_length=UserNameLength.NAME_MAX_LENGTH,
    )
    email: EmailStr
    designation: Optional[str] = None
    phone_number: str
    parent_id: Optional[UUID] = None
    partner_id: Optional[UUID] = None
    role_id: Optional[UUID] = None
    country_id: Optional[UUID] = None
    state_id: Optional[UUID] = None
    city_id: Optional[UUID] = None
    alternate_phone_number: Optional[str] = None
    cloud_agent_number: Optional[str] = None

    @model_validator(mode="after")
    def remove_prefix_from_phone(self) -> "User":
        if self.phone_number:
            self.phone_number = self.phone_number.removeprefix("tel:")
        return self

    @field_validator("name")
    def validate_name(cls, value):
        value = value.strip()
        # Regex for valid name (allow spaces, hyphens, and apostrophes)
        if not re.match(r"^[A-Za-z]+([ ]?[A-Za-z]+)*$", value):
            raise ValueError("Name contains invalid characters")
        return value
    
    @field_validator("cloud_agent_number")
    def validate_cloud_agent_number(cls, value)-> Any:
        if value is None:
            return value
        return value


class UserData(UserBase):
    phone_number: str
    alternate_phone_number: Optional[str] = None
    partner_id: UUID
    password: str = Field(..., min_length=8)

    @field_validator("password")
    def validate_password(cls, password: str) -> str:
        regex = r"^(?=.*[A-Z])(?=.*[a-z])(?=.*\d)(?=.*[!@#$%^&*(),.?\":{}|<>]).{8,}$"
        if not re.match(regex, password):
            raise ValueError(AuthExceptionMsg.PASSWORD_NOT_STRONG)
        return password

    @field_validator("phone_number", "alternate_phone_number")
    def validate_international_phone(cls, value):
        if value is None:
            return value
        pattern = r"^\+[1-9]\d{7,14}$"
        if not re.match(pattern, value):
            raise ValueError("Enter a valid phone number (e.g., +919988776655).")
        return value


class InternalUserData(UserData):
    is_internal: Optional[bool] = False


class LoginData(BaseModel):
    credential: str = Field(..., min_length=1)
    password: Optional[str] = None
    send_mail_otp: Optional[bool] = False
    send_whatsapp_otp: Optional[bool] = False
    is_verify: Optional[bool] = False

    @property
    def email(self) -> Optional[str]:
        try:
            return email_adapter.validate_python(self.credential)
        except ValidationError:
            return None

    @property
    def phone_number(self) -> Optional[str]:
        return None if self.email else self.credential

    @model_validator(mode="after")
    def validate_logic(self):
        """
        Validation rules:
        1. If 'is_verify' is True → password not required.
        2. If 'is_verify' is False or missing → password required.
        3. If 'is_verify' is True → OTP type must match credential type.
        """
        if self.is_verify:
            # Check if at least one OTP flag is True
            if not (self.send_mail_otp or self.send_whatsapp_otp):
                raise ValueError(
                    "At least one of 'send_mail_otp' or 'send_whatsapp_otp' must be True when 'is_verify' is True."
                )

            # If credential is an email → only email OTP allowed
            if self.email:
                if self.send_whatsapp_otp:
                    raise ValueError(
                        "Cannot send WhatsApp OTP for email credentials. Use 'send_mail_otp=True' instead."
                    )
                if not self.send_mail_otp:
                    raise ValueError(
                        "For email verification, 'send_mail_otp' must be True."
                    )

            # If credential is phone → WhatsApp OTP was the only channel,
            # removed. Fail closed with a clear message.
            else:
                raise ValueError(
                    "Phone verification is unavailable (WhatsApp channel removed)."
                )

            # Password should not be required in verification mode
            self.password = None

        else:
            # If not verification → password required
            if not self.password:
                raise ValueError("'password' is required for login.")
        return self


class RoleData(BaseModel):
    name: str = Field(..., min_length=1)
    slug: str = Field(..., min_length=1)
    hierarchy: int
    description: str
    is_internal: Optional[bool] = False


class PermissionData(BaseModel):
    title: str = Field(..., min_length=1)
    slug: str = Field(..., min_length=1)
    description: Optional[str] = None
    category: Optional[str] = None
    display_text: Optional[str] = None
    is_internal: Optional[bool] = False


class UserDataResponse(UserBase):
    phone_number: Optional[str] = None
    is_internal: Optional[bool] = False
    updated_by: Optional[UUID] = None
    is_walkthrough_completed: Optional[bool] = False
    current_status: Optional[str] = None
    is_active: Optional[bool] = None
    id: UUID

    model_config = ConfigDict(
        from_attributes=True,
    )


class TokenResponse(BaseModel):
    access_token: str
    token_type: str

    model_config = ConfigDict(
        from_attributes=True,
    )


class RoleResponse(BaseModel):
    id: UUID
    name: str
    slug: str
    hierarchy: Optional[int] = None
    description: Optional[str] = None
    is_active: bool
    is_deleted: bool
    created_by: Optional[UUID] = None
    updated_by: Optional[UUID] = None
    deleted_by: Optional[UUID] = None
    is_internal: Optional[bool] = False

    model_config = ConfigDict(
        from_attributes=True,
    )


class PermissionResponse(BaseModel):
    id: UUID
    title: str
    description: Optional[str] = None
    slug: str
    category: Optional[str] = None
    display_text: Optional[str] = None
    is_active: bool
    is_deleted: bool
    created_by: Optional[UUID] = None
    updated_by: Optional[UUID] = None
    deleted_by: Optional[UUID] = None

    model_config = ConfigDict(
        from_attributes=True,
    )


class ResetPasswordRequest(BaseModel):
    email: EmailStr
    current_password: Optional[str] = None
    new_password: str

    @field_validator("new_password")
    def validate_password(cls, new_password: str) -> str:
        regex = r"^(?=.*[A-Z])(?=.*[a-z])(?=.*\d)(?=.*[!@#$%^&*(),.?\":{}|<>]).{8,}$"
        if not re.match(regex, new_password):
            raise ValueError(AuthExceptionMsg.PASSWORD_NOT_STRONG)
        return new_password


class AllUsersDataResponse(UserBase):
    phone_number: Optional[str] = None
    alternate_phone_number: Optional[str] = None
    id: UUID
    country_name: Optional[str] = None
    role_name: Optional[str] = None
    parent_name: Optional[str] = None
    is_active: bool
    current_status: Optional[str] = None

    model_config = ConfigDict(
        from_attributes=True,
    )


class PaginatedAllUsersDataResponse(BaseModel):
    total_count: int
    limit: int
    offset: int
    users_data: List[AllUsersDataResponse]


class UpdatePermissionRquest(BaseModel):
    title: Optional[str] = None
    slug: Optional[str] = None
    description: Optional[str] = None
    category: Optional[str] = None
    display_text: Optional[str] = None
    is_internal: Optional[bool] = None


class UpdatePermissionResponse(BaseModel):
    id: UUID
    title: Optional[str] = None
    category: Optional[str] = None
    description: Optional[str] = None
    slug: Optional[str] = None
    display_text: Optional[str] = None
    is_internal: Optional[bool] = None

    model_config = ConfigDict(
        from_attributes=True,
    )


@dataclass
class RolePermissionCombined:
    role_name: str
    category: str
    slug: str
    is_active: bool
    created_at: int
    description: str
    display_text: str
    permission_id: UUID


class UserNewResponse(BaseModel):
    id: UUID
    name: str
    email: str
    phone_number: str
    role: str
    role_hierarchy: int


class UpdateRoleRequest(BaseModel):
    name: Optional[str] = None
    slug: Optional[str] = None
    hierarchy: Optional[int] = None
    description: Optional[str] = None
    is_internal: Optional[bool] = False

    model_config = ConfigDict(
        from_attributes=True,
    )


class OtpValidateRequest(BaseModel):
    credential: str = Field(..., min_length=1)
    otp: str = Field(..., min_length=6, max_length=6)
    is_verify: Optional[bool] = False

    @property
    def email(self) -> Optional[str]:
        try:
            return email_adapter.validate_python(self.credential)
        except ValidationError:
            return None

    @property
    def phone_number(self) -> Optional[str]:
        return None if self.email else self.credential
