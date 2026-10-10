from typing import ClassVar, List, Optional

from pydantic import BaseModel, ConfigDict, Field

from src.components.team.constants import TeamStrictHierarchyMode


class TeamCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=128)
    partner_id: int = Field(..., ge=1, le=9999999999999)
    description: Optional[str] = Field(default=None, max_length=200)
    parent_team_id: Optional[int] = Field(default=None, ge=1)


class TeamUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=128)
    description: Optional[str] = Field(default=None, max_length=200)
    parent_team_id: Optional[int] = Field(default=None, ge=1)
    is_active: Optional[bool] = None


class TeamResponse(BaseModel):
    id: int
    name: str
    slug: str
    partner_id: int
    parent_team_id: Optional[int] = None
    is_internal: bool
    is_active: bool

    model_config: ClassVar[ConfigDict] = ConfigDict(from_attributes=True)


class TeamMemberCreate(BaseModel):
    user_id: int = Field(..., ge=1, le= 9999999999999)
    # Optional per-team role override; null => use the user's default role.
    role_id: Optional[int] = Field(default=None, ge=1, le = 9999999999999)


class TeamMemberUpdate(BaseModel):
    # Pass null explicitly to clear the per-team role override.
    role_id: Optional[int] = Field(default=None, ge=1, le = 9999999999999)


class TeamMemberResponse(BaseModel):
    id: int
    team_id: int
    user_id: int
    role_id: Optional[int] = None

    model_config: ClassVar[ConfigDict] = ConfigDict(from_attributes=True)


class TeamStrictHierarchyPolicy(BaseModel):
    """Partner-level strict-hierarchy-in-teams policy."""

    mode: TeamStrictHierarchyMode
    # Required only when mode == PARTIAL: the role from which strict starts.
    start_role_id: Optional[int] = Field(default=None, ge=1, le = 9999999999999)


class TeamMembersResponse(BaseModel):
    team_id: int
    members: List[TeamMemberResponse]


class TeamMemberDetailResponse(BaseModel):
    id: int
    team_id: int
    user_id: int
    user_name: Optional[str] = None
    role_id: Optional[int] = None
    role_name: Optional[str] = None

    model_config: ClassVar[ConfigDict] = ConfigDict(from_attributes=True)


class TeamMembersPaginatedResponse(BaseModel):
    total_count: int
    limit: Optional[int] = None
    offset: Optional[int] = None
    data: List[TeamMemberDetailResponse]


class TeamListItemResponse(BaseModel):
    id: int
    name: str
    slug: str
    description: Optional[str] = None
    partner_id: int
    parent_team_id: Optional[int] = None
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
    team_id: int
    name: str
    slug: str
    description: Optional[str] = None
    is_active: bool
    role_id: Optional[int] = None
    team_member_id: int

    model_config: ClassVar[ConfigDict] = ConfigDict(from_attributes=True)


class UserAssociatedTeamsResponse(BaseModel):
    user_id: int
    team_count: int
    teams: List[UserAssociatedTeamItem]

class CurrentUserTeamItem(BaseModel):
    """One team the current user belongs to, with their role in that team."""

    id: int
    name: str
    role_id: Optional[int] = None
    role_name: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)
