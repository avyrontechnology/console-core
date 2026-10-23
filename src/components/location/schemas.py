from uuid import UUID
from typing import List, Optional
from pydantic import BaseModel, ConfigDict


class BaseResponse(BaseModel):
    id: UUID
    name: str
    slug: str

    model_config = ConfigDict(
        from_attributes=True,
    )


class CountryResponse(BaseResponse):
    pass


class StateResponse(BaseResponse):
    pass


class CityResponse(BaseResponse):
    pass

class StatePaginatedResponse(BaseModel):
    total_count: int
    limit: Optional[int] = None
    offset: Optional[int] = None
    data: List[StateResponse]


class CityPaginatedResponse(BaseModel):
    total_count: int
    limit: Optional[int] = None
    offset: Optional[int] = None
    data: List[CityResponse]