from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, HttpUrl
from src.components.digital_assets.constants import DigitalAssetEnum


class DigitalAssetResponse(BaseModel):
    id: int
    name: str
    partner_id: int
    version: int
    url: Optional[HttpUrl] = None
    asset_type: DigitalAssetEnum
    additional_info: Optional[dict] = None
    created_by: Optional[int] = None
    updated_by: Optional[int] = None

    model_config = ConfigDict(
        from_attributes=True,
    )


class UploadDigitalAssetResponse(BaseModel):
    """
    Response schema for uploading a digital asset.
    """

    id: int = Field(..., description="ID of uploaded DA")
    file_name: str = Field(
        ..., description="The name of the uploaded file in the storage."
    )
    url: str = Field(..., description="The URL of the uploaded digital asset.")
