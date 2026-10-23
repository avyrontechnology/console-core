from uuid import UUID
from typing import Optional

from pydantic import BaseModel, ConfigDict


class UserDetails(BaseModel):
    """Pydantic model for user."""

    id: UUID
    name: str
    designation: Optional[str] = None
    email: Optional[str] = None

    model_config = ConfigDict(
        from_attributes=True,
    )


class RoleActionFlagResponse(BaseModel):
    can_view_dashboard: Optional[bool] = False
    can_view_partners: Optional[bool] = False
    can_view_permissions: Optional[bool] = False
    can_view_users: Optional[bool] = False
    can_view_configurations: Optional[bool] = False
    can_view_add_permissions: Optional[bool] = False
    can_view_partner_info: Optional[bool] = False
    can_view_internal_roles: Optional[bool] = False
    can_edit_internal_roles: Optional[bool] = False
    can_view_partner_config: Optional[bool] = False
    can_assume_user: Optional[bool] = False
    can_view_plans: Optional[bool] = False
    can_view_order_history: Optional[bool] = False
    can_view_api_admin: Optional[bool] = False

    model_config = ConfigDict(
        from_attributes=True,
    )


class SusbscribedServices(BaseModel):
    is_talko_enabled: Optional[bool] = False
    is_obotaai_enabled: Optional[bool] = False
    is_add_number_enabled: Optional[bool] = False

    class Config:
        from_attributes = True


class ParnterInfo(BaseModel):
    partner_id: UUID
    partner_name: Optional[str] = None
    subscription_mode: Optional[str] = None
    subscription_status: Optional[dict] = None

    class Config:
        from_attributes = True


class UserEntityData(BaseModel):
    user_info: UserDetails
    partner_info: ParnterInfo
    user_permissions: RoleActionFlagResponse
    services_info: SusbscribedServices

    model_config = ConfigDict(
        from_attributes=True,
    )
