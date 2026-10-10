from typing import Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field


class DefaultRolePermissionData(BaseModel):
    role_id: int
    permission_id: int


class SetRoleActionPermissionsData(BaseModel):
    """Bulk toggle a partner-owned role's action-flag permissions.

    ``permissions`` maps a permission *slug* (e.g. ``"maglo:delete_lead"``) to the
    desired state: True → granted (button visible), False → revoked. Only the slugs
    present in the payload are touched; anything omitted is left untouched. The role
    must belong to ``partner_id`` (a materialised, partner-owned role) — global
    default roles cannot be edited through this endpoint.
    """

    partner_id: int
    permissions: Dict[str, bool] = Field(default_factory=dict)


class SetRoleActionPermissionsResponse(BaseModel):
    role_id: int
    partner_id: int
    granted: List[str] = Field(default_factory=list)
    revoked: List[str] = Field(default_factory=list)
    unchanged: List[str] = Field(default_factory=list)
    unknown_slugs: List[str] = Field(default_factory=list)


class DefaultRolePermissionResponse(BaseModel):
    id: int
    permission_id: int
    role_id: int
    permission_name: Optional[str] = None

    model_config = ConfigDict(
        from_attributes=True,
    )
