from uuid import UUID
from typing import Optional, Union
from pydantic import BaseModel, ConfigDict


class UserConfigBase(BaseModel):
    user_id: UUID
    key: str
    value: Optional[Union[int, str, dict, list, bool]] = None

    model_config = ConfigDict(from_attributes=True)


class UserConfigRequest(BaseModel):
    user_id: UUID
    key: str
    value: Optional[Union[int, str, dict, list, bool]] = None

    model_config = ConfigDict(from_attributes=True)


class UserConfigResponse(BaseModel):
    id: Optional[UUID] = None
    key: Optional[str] = None
    value: Optional[Union[int, str, dict, list, bool]] = None
    user_id: Optional[UUID] = None
    created_at: Optional[int] = None
    history: Optional[list] = None

    model_config = ConfigDict(from_attributes=True)


class UpdateUserConfigResponse(UserConfigResponse):
    updated_at: int
    updated_by: UUID

    model_config = ConfigDict(from_attributes=True)


class UserConfigUpdateRequest(BaseModel):
    new_value: Optional[Union[int, str, dict, list, bool]] = None


class UserConfigData(BaseModel):
    is_super_admin: Optional[bool] = False
    is_talko_enabled: Optional[bool] = False
    is_gsm_calling_enabled: Optional[bool] = False
    is_meeting_log_enabled: Optional[bool] = False
    can_view_contact: Optional[bool] = False
    can_view_organization: Optional[bool] = False
    is_obotaai_enabled: Optional[bool] = False
    enable_dialer: Optional[bool] = False
    can_view_products: Optional[bool] = False
    can_view_inventory: Optional[bool] = False
    can_view_payment_history: Optional[bool] = False
    can_view_report_management: Optional[bool] = False
