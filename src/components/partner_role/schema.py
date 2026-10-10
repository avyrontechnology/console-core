from typing import ClassVar, List, Optional

from pydantic import BaseModel, ConfigDict, Field

from src.components.partner_role.constants import DataScope, RolePlacement


class MaterializePartnerRoles(BaseModel):
    partner_id: int = Field(..., ge=1, le=9999999999999)


class CreatePartnerRole(BaseModel):
    name: str = Field(..., min_length=1, max_length=56)
    description: Optional[str] = Field(default=None, max_length=200)
    data_scope: DataScope = DataScope.SUBTREE
    # Position: place the new role above/below this reference role.
    reference_role_id: int
    placement: RolePlacement
    # Permission source: the new role is seeded with this base role's
    # permissions at creation. May differ from reference_role_id.
    base_role_id: int


class UpdatePartnerRole(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=56)
    description: Optional[str] = Field(default=None, max_length=200)
    data_scope: Optional[DataScope] = None
    is_active: Optional[bool] = None


class PartnerRoleResponse(BaseModel):
    id: int
    name: str
    slug: str
    hierarchy: int
    partner_id: Optional[int] = None
    data_scope: Optional[str] = None
    base_role_id: Optional[int] = None
    is_internal: bool
    is_active: bool
    description: Optional[str] = None
    created_at: Optional[int] = None
    updated_at: Optional[int] = None

    model_config: ClassVar[ConfigDict] = ConfigDict(from_attributes=True)


class PartnerRolePaginatedResponse(BaseModel):
    total_count: int
    total_active: int
    total_inactive: int
    limit: Optional[int] = None
    offset: Optional[int] = None
    data: List[PartnerRoleResponse]
