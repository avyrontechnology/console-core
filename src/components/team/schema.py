from uuid import UUID
from typing import ClassVar, List, Optional

from pydantic import BaseModel, ConfigDict, Field

from src.components.team.constants import TeamStrictHierarchyMode


class TeamCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=128)
    partner_id: UUID = Field(...)
    description: Optional[str] = Field(default=None, max_length=200)
    parent_team_id: Optional[UUID] = Field(default=None)


class TeamUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=128)
    description: Optional[str] = Field(default=None, max_length=200)
    parent_team_id: Optional[UUID] = Field(default=None)
    is_active: Optional[bool] = None


class TeamResponse(BaseModel):
    id: UUID
    name: str
    slug: str
    partner_id: UUID
    parent_team_id: Optional[UUID] = None
    is_internal: bool
    is_active: bool

    model_config: ClassVar[ConfigDict] = ConfigDict(from_attributes=True)


class TeamMemberCreate(BaseModel):
    user_id: UUID = Field(...)
    # Optional per-team role override; null => use the user's default role.
    role_id: Optional[UUID] = Field(default=None)


class TeamMemberUpdate(BaseModel):
    # Pass null explicitly to clear the per-team role override.
    role_id: Optional[UUID] = Field(default=None)


class TeamMemberResponse(BaseModel):
    id: UUID
    team_id: UUID
    user_id: UUID
    role_id: Optional[UUID] = None

    model_config: ClassVar[ConfigDict] = ConfigDict(from_attributes=True)


class TeamStrictHierarchyPolicy(BaseModel):
    """Partner-level strict-hierarchy-in-teams policy."""

    mode: TeamStrictHierarchyMode
    # Required only when mode == PARTIAL: the role from which strict starts.
    start_role_id: Optional[UUID] = Field(default=None)


class TeamMembersResponse(BaseModel):
    team_id: UUID
    members: List[TeamMemberResponse]


class TeamMemberDetailResponse(BaseModel):
    id: UUID
    team_id: UUID
    user_id: UUID
    user_name: Optional[str] = None
    role_id: Optional[UUID] = None
    role_name: Optional[str] = None

    model_config: ClassVar[ConfigDict] = ConfigDict(from_attributes=True)


class TeamMembersPaginatedResponse(BaseModel):
    total_count: int
    limit: Optional[int] = None
    offset: Optional[int] = None
    data: List[TeamMemberDetailResponse]


class TeamListItemResponse(BaseModel):
    id: UUID
    name: str
    slug: str
    description: Optional[str] = None
    partner_id: UUID
    parent_team_id: Optional[UUID] = None
    is_internal: bool
    is_active: bool
    created_at: Optional[int] = None
    updated_at: Optional[int] = None
    member_count: int

    model_config: ClassVar[ConfigDict] = ConfigDict(from_attributes=True)


class TeamPaginatedResponse(BaseModel):
    total_count: int
    total_active: int
    total_inactive: int
    limit: Optional[int] = None
    offset: Optional[int] = None
    data: List[TeamListItemResponse]


class UserAssociatedTeamItem(BaseModel):
    team_id: UUID
    name: str
    slug: str
    description: Optional[str] = None
    is_active: bool
    role_id: Optional[UUID] = None
    team_member_id: UUID

    model_config: ClassVar[ConfigDict] = ConfigDict(from_attributes=True)


class UserAssociatedTeamsResponse(BaseModel):
    user_id: UUID
    team_count: int
    teams: List[UserAssociatedTeamItem]

class CurrentUserTeamItem(BaseModel):
    """One team the current user belongs to, with their role in that team."""

    id: UUID
    name: str
    role_id: Optional[UUID] = None
    role_name: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)
