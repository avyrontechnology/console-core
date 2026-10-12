from uuid import UUID
from typing import Optional

from pydantic import BaseModel, ConfigDict


class UserMetadataSchema(BaseModel):
    id: UUID
    meta_key: str
    meta_value: str

    model_config = ConfigDict(
        from_attributes=True,
    )


class UserMetadataResponse(UserMetadataSchema):
    id: UUID
    meta_key: str

    model_config = ConfigDict(
        from_attributes=True,
    )


class CreateUserMetaDataSchema(BaseModel):
    meta_value: str


class UpdateUserMetadataSchema(BaseModel):
    meta_value: Optional[str] = None

    model_config = ConfigDict(
        from_attributes=True,
    )
