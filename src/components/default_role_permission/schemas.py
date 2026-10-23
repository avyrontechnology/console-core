from uuid import UUID
from typing import Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field


class DefaultRolePermissionData(BaseModel):
    role_id: UUID
    permission_id: UUID


class SetRoleActionPermissionsData(BaseModel):
    """Bulk toggle a partner-owned role's action-flag permissions.

    ``permissions`` maps a permission *slug* (e.g. ``"talko:delete_lead"``) to the
    desired state: True → granted (button visible), False → revoked. Only the slugs
    present in the payload are touched; anything omitted is left untouched. The role
    must belong to ``partner_id`` (a materialised, partner-owned role) — global
    default roles cannot be edited through this endpoint.
    """

    partner_id: UUID
    permissions: Dict[str, bool] = Field(default_factory=dict)


class SetRoleActionPermissionsResponse(BaseModel):
    role_id: UUID
    partner_id: UUID
    granted: List[str] = Field(default_factory=list)
    revoked: List[str] = Field(default_factory=list)
    unchanged: List[str] = Field(default_factory=list)
    unknown_slugs: List[str] = Field(default_factory=list)


class DefaultRolePermissionResponse(BaseModel):
    id: UUID
    permission_id: UUID
    role_id: UUID
    permission_name: Optional[str] = None

    model_config = ConfigDict(
        from_attributes=True,
    )
