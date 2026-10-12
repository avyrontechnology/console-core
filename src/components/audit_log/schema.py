from uuid import UUID
from typing import Any, Optional

from pydantic import BaseModel, Field, field_validator


class AuditLogSchema(BaseModel):
    action: str
    resource: str
    resource_id: Optional[str] = None
    performed_by: Optional[UUID] = None
    resource_previous_state: Optional[str] = None
    resource_current_state: Optional[str] = None
    details: Optional[str] = None

    @field_validator("resource_id", mode="before")
    @classmethod
    def _stringify_resource_id(cls, v: Any) -> Any:
        # Callers pass UUID objects; the column is String(36).
        if v is None:
            return None
        return v if isinstance(v, str) else str(v)
