from uuid import UUID
from pydantic import BaseModel, ConfigDict


class PartnerPermissionData(BaseModel):
    role_id: UUID
    permission_id: UUID
    partner_id: UUID


class PartnerRolePermissionResponse(BaseModel):
    id: UUID
    partner_id: UUID
    permission_id: UUID
    role_id: UUID

    model_config = ConfigDict(
        from_attributes=True,
    )
