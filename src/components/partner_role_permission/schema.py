from pydantic import BaseModel, ConfigDict


class PartnerPermissionData(BaseModel):
    role_id: int
    permission_id: int
    partner_id: int


class PartnerRolePermissionResponse(BaseModel):
    id: int
    partner_id: int
    permission_id: int
    role_id: int

    model_config = ConfigDict(
        from_attributes=True,
    )
