from datetime import datetime
from typing import Any, Dict, Optional

from pydantic import BaseModel, ConfigDict, Field


class ConstantResponseSchema(BaseModel):
    id: Optional[int] = Field(None, description="Unique identifier")
    name: str = Field(
        ..., max_length=100, description="Name of the constant or variable"
    )
    value: Optional[str | int] = Field(
        ..., description="Value of the constant or variable"
    )
    description: Optional[str] = Field(
        None, description="Description of the constant or variable"
    )
    version: int = Field(..., description="Version number")
    updated_by: Optional[int] = Field(None, description="User ID of the last updater")
    updated_at: Optional[datetime] = Field(
        None, description="Timestamp of the last update"
    )
    additional_info: Optional[Dict[str, Any]] = Field(
        None, description="Additional information about the constant"
    )

    model_config = ConfigDict(
        from_attributes=True,
    )


class NavbarMarqueeResponseSchema(BaseModel):
    is_enabled: bool = Field(
        ..., description="Whether the navbar marquee is currently launched"
    )
    message: Optional[str] = Field(
        None, description="Marquee text to display; null/omitted when disabled"
    )

    model_config = ConfigDict(
        from_attributes=True,
    )
