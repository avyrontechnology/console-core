"""
Pydantic schemas for partner database configuration.
"""

from typing import Optional

from pydantic import BaseModel, ConfigDict, field_validator


class PartnerDBConfigRequest(BaseModel):
    """Schema for creating/updating a partner's dedicated database config."""

    db_host: str
    db_port: int = 5432
    db_name: str
    db_user: str
    db_password: str
    ssl_required: bool = True

    model_config = ConfigDict(from_attributes=True)

    @field_validator("db_port")
    @classmethod
    def validate_port(cls, v: int) -> int:
        if not (1 <= v <= 65535):
            raise ValueError("db_port must be between 1 and 65535")
        return v

    @field_validator("db_host")
    @classmethod
    def validate_host(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("db_host must not be empty")
        return v

    @field_validator("db_name")
    @classmethod
    def validate_db_name(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("db_name must not be empty")
        return v

    @field_validator("db_user")
    @classmethod
    def validate_db_user(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("db_user must not be empty")
        return v


class PartnerDBConfigResponse(BaseModel):
    """Response schema — password is always masked."""

    partner_id: int
    db_host: str
    db_port: int
    db_name: str
    db_user: str
    db_password: str = "********"
    ssl_required: bool = True

    model_config = ConfigDict(from_attributes=True)


class PartnerDBConfigInternalResponse(BaseModel):
    """
    Internal-only response that includes the decrypted password.
    Used by maglo-service via the internal API — never exposed to end users.
    """

    partner_id: int
    db_host: str
    db_port: int
    db_name: str
    db_user: str
    db_password: str
    ssl_required: bool = True

    model_config = ConfigDict(from_attributes=True)
