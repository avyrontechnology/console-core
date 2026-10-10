from enum import Enum
from typing import Optional

from pydantic import BaseModel, ConfigDict


class AddressType(str, Enum):
    BILLING = "Billing"
    COMMUNICATION = "Communication"
    COMMUNICATION_AND_BILLING = "Billing and Communication"


class Contrasts:
    class AddressData(BaseModel):
        address_1: str
        address_2: Optional[str] = None
        address_type: AddressType
        city: str
        state: str
        country: str
        pincode: str
        partner_id: int
        is_address_same: bool = False

    class GetAddressByAddressIdResponse(AddressData):
        is_address_same: Optional[bool] = False
        id: int

        model_config = ConfigDict(
            from_attributes=True,
        )


class UpdatePartnerAddressData(BaseModel):
    address_1: Optional[str] = None
    address_2: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    country: Optional[str] = None
    pincode: Optional[str] = None


class UpdatePartnerAddressRequest(BaseModel):
    is_address_same: Optional[bool] = True
    billing_address: Optional[UpdatePartnerAddressData] = None
    communication_address: Optional[UpdatePartnerAddressData] = None


class PartnerAddressResponse(BaseModel):
    id: int
    address_1: str
    address_2: Optional[str]
    address_type: AddressType
    city: str
    state: str
    country: str
    pincode: str
    partner_id: int

    model_config = ConfigDict(
        from_attributes=True,
    )


class UpsertPartnerAddressResponse(BaseModel):
    id: int
    address_1: str
    address_2: Optional[str]
    city: str
    state: str
    country: str
    pincode: str
    address_type: AddressType
    partner_id: int
    is_address_same: Optional[bool] = False
    created_at: Optional[int] = None
    created_by: Optional[int] = None

    model_config = ConfigDict(
        from_attributes=True,
    )
