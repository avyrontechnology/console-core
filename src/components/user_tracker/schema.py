from typing import Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

from src.components.user_tracker.constants import UserTrackerValidation



class StandardStatusItem(BaseModel):
    name: str
    status_icon: Optional[str] = None


class CustomStatusItem(BaseModel):
    name: str
    status_icon: Optional[str] = None


class UserAvailabilityStatusResponse(BaseModel):

    current_status: str
    current_status_icon: Optional[str] = None
    standard_statuses: List[StandardStatusItem]
    custom_statuses: Dict[str, CustomStatusItem]     # {display_id: {name, status_icon}}

    model_config = ConfigDict(from_attributes=True)



class UpdateUserStatusRequest(BaseModel):
    """Request body for PUT /user-tracker/status."""
    status: str = Field(..., max_length=UserTrackerValidation.STATUS_MAX_LENGTH)
    status_icon: Optional[str] = Field(
        default=None, max_length=UserTrackerValidation.ICON_MAX_LENGTH
    )   # if provided, sets/updates the icon for `status`

    @field_validator("status")
    def strip_status(cls, value: str) -> str:
        return value.strip() if value else value

    @field_validator("status_icon")
    def strip_status_icon(cls, value: Optional[str]) -> Optional[str]:
        return value.strip() if value else value


class UpdateUserStatusResponse(BaseModel):
    """Response for PUT /user-tracker/status."""
    previous_status: str
    updated_status: str
    status_icon: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)



class CustomStatusEditItem(BaseModel):
    """name='' soft-deletes the status. name=None leaves the name untouched (icon-only edit)."""
    name: Optional[str] = Field(default=None, max_length=UserTrackerValidation.STATUS_MAX_LENGTH)
    status_icon: Optional[str] = Field(
        default=None, max_length=UserTrackerValidation.ICON_MAX_LENGTH
    )

    @field_validator("name")
    def strip_name(cls, value: Optional[str]) -> Optional[str]:
        return value.strip() if value else value

    @field_validator("status_icon")
    def strip_status_icon(cls, value: Optional[str]) -> Optional[str]:
        return value.strip() if value else value

    @property
    def is_soft_delete(self) -> bool:
        return self.name == ""

    @property
    def is_rename(self) -> bool:
        return self.name is not None and self.name != ""


class CustomStatusAddItem(BaseModel):
    name: str = Field(..., max_length=UserTrackerValidation.STATUS_MAX_LENGTH)
    status_icon: Optional[str] = Field(
        default=None, max_length=UserTrackerValidation.ICON_MAX_LENGTH
    )

    @field_validator("name")
    def strip_name(cls, value: str) -> str:
        return value.strip() if value else value

    @field_validator("status_icon")
    def strip_status_icon(cls, value: Optional[str]) -> Optional[str]:
        return value.strip() if value else value


class UpdateCustomStatusesRequest(BaseModel):

    edit_custom_statuses: Optional[Dict[str, CustomStatusEditItem]] = Field(default_factory=dict)
    add_custom_statuses: Optional[List[CustomStatusAddItem]] = Field(default_factory=list)


class UpdateCustomStatusesResponse(BaseModel):

    message: str
    custom_statuses: Dict[str, CustomStatusItem]     # {display_id: {name, status_icon}} after update

    model_config = ConfigDict(from_attributes=True)