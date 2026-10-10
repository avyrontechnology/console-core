from typing import Optional

from pydantic import BaseModel, Field


class AuditLogSchema(BaseModel):
    action: str
    resource: str
    resource_id: Optional[int] = None
    performed_by: Optional[int] = None
    resource_previous_state: Optional[str] = None
    resource_current_state: Optional[str] = None
    details: Optional[str] = None
