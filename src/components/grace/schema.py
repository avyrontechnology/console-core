"""Pydantic schemas for the Grace Period feature."""

from uuid import UUID
from typing import Any, Dict, Optional, Tuple

from pydantic import BaseModel

from src.components.common.constants import FieldType, Limits
from src.components.common.utility import SchemaValidator
from src.components.db_constants.loader.constant import DbConstants


class ValidatableSchema(BaseModel):
    __validation_rules__: Dict[str, Dict[str, Any]] = {}

    def validate_payload(self) -> Tuple[Dict[str, Any], Optional[str]]:
        rules: Dict[str, Dict[str, Any]] = {}
        for field_name, config in self.__validation_rules__.items():
            resolved = {
                k: (
                    v() if callable(v) else v
                )  # lazily resolve callables at validation time
                for k, v in config.items()
            }
            resolved["value"] = getattr(self, field_name, None)
            rules[field_name] = resolved
        return SchemaValidator.validate(rules)


class GrantGraceRequest(ValidatableSchema):
    partner_id: Any
    granted_days: Any
    remark: Any

    @staticmethod
    def get_max_grace_days_per_attempt():
        return DbConstants.MAX_GRACE_DAYS_PER_ATTEMPT

    __validation_rules__ = {
        "partner_id": {
            "required": True,
            "type": FieldType.UUID,
        },
        "granted_days": {
            "required": True,
            "type": FieldType.INTEGER,
            "min": 1,
            "max": get_max_grace_days_per_attempt,  # callable — resolved lazily at validation time
        },
        "remark": {
            "required": True,
            "type": FieldType.STRING,
            "min": 1,
            "max": 500,
        },
    }

    def validate_payload(self) -> Tuple[Dict[str, Any], Optional[str]]:
        validated, error = super().validate_payload()
        if error:
            return {}, error
        return validated, None


class GraceResponse(BaseModel):
    grace_id: UUID
    partner_id: UUID
    service_name: str
    granted_days: int
    attempt_number: int
    start_date: int
    end_date: int
    status: str
    remark: Optional[str] = None
    consumed_days: Optional[int] = None
    settled_at: Optional[int] = None
    settled_by_order_id: Optional[UUID] = None
    created_by: Optional[UUID] = None
    created_at: Optional[int] = None
    granted_by_name: Optional[str] = None

    class Config:
        from_attributes = True


class GraceStatusResponse(BaseModel):
    partner_id: UUID
    service_name: str
    has_active_grace: bool
    current_grace: Optional[GraceResponse] = None
    total_attempts_used: int
    attempts_remaining: int
    total_consumed_days: int
    created_by: Optional[UUID] = None
    created_at: Optional[int] = None
    granted_by_name: Optional[str] = None
