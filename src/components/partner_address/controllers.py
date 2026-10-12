from uuid import UUID
from typing import List, Optional

from dependency_injector.wiring import Provide, inject
from fastapi import APIRouter, Body, Depends, Request
from fastapi.encoders import jsonable_encoder
from sqlalchemy.exc import IntegrityError

from src.components.common.constants import CurrentUserMap
from src.components.common.errors import ErrorMsg
from src.components.common.response import (
    BadRequestResponse,
    InternalServerErrorResponse,
    NotFoundResponse,
    ResourceConflictResponse,
    ResourceCreatedResponse,
    SuccessResponse,
    ValidationErrorResponse,
)
from src.components.partner.error import PartnerNotFoundError
from src.components.partner_address.constant import (
    ExceptionMessages,
    PartnerAddressResponseMsg,
)
from src.components.partner_address.error import AddressNotFoundError
from src.components.partner_address.models import PartnerAddress
from src.components.partner_address.schema import (
    Contrasts,
    PartnerAddressResponse,
    UpdatePartnerAddressRequest,
    UpsertPartnerAddressResponse,
)
from src.components.partner_address.services import PartnerAddressService
from src.components.rbac.permission_dependency import PermissionDependency
from src.components.rbac.permission_injector import permission_check
from src.components.user.services import UserService
from src.core.container import Container
from src.exceptions import AddressExistsException, PartnerException
from src.loggers.console_service_logger import ConsoleServiceLogger


class PartnerAddressController:

    partner_address_router = APIRouter()

    @partner_address_router.get(
        "/partner_addresses", response_model=List[PartnerAddressResponse]
    )
    @permission_check(PermissionDependency)
    @inject
    async def get_partner_addresses(
        request: Request,
        address_service: PartnerAddressService = Depends(
            Provide[Container.address_service]
        ),
        console_service_logger: ConsoleServiceLogger = Depends(
            Provide[Container.console_service_logger]
        ),
    ):
        try:
            console_service_logger.info(
                "Fetching all the partner addresses from the database."
            )
            all_addresses = await address_service.get_addresses()
            console_service_logger.info(
                "Fetched all the addresses successfully: {}".format(all_addresses)
            )
            addresses_response = [
                PartnerAddressResponse.model_validate(address)
                for address in all_addresses
            ]
            return SuccessResponse(jsonable_encoder(addresses_response))
        except Exception as e:
            console_service_logger.error("Error fetching addresses {}".format(e))
            return InternalServerErrorResponse(ErrorMsg.INTERNAL_SERVER_ERROR)

    @partner_address_router.get(
        "/partner_address_by_address_id/{address_id}",
        response_model=PartnerAddressResponse,
    )
    @permission_check(PermissionDependency)
    @inject
    async def get_partner_address_by_id(
        request: Request,
        address_id: UUID,
        address_service: PartnerAddressService = Depends(
            Provide[Container.address_service]
        ),
        console_service_logger: ConsoleServiceLogger = Depends(
            Provide[Container.console_service_logger]
        ),
    ):
        try:
            console_service_logger.info("Getting address with id {}".format(address_id))
            address = await address_service.get_by_id(address_id)
            console_service_logger.info(
                "Address fetched successfully:{}".format(address)
            )
            return SuccessResponse(
                jsonable_encoder(PartnerAddressResponse.model_validate(address))
            )
        except AddressNotFoundError as ex:
            console_service_logger.error("Address not found: {}".format(ex))
            return NotFoundResponse(detail=str(ex))
        except PartnerNotFoundError as exec:
            console_service_logger.error("Partner not found: {}".format(exec))
            return NotFoundResponse(detail=str(exec))
        except Exception as exec_info:
            console_service_logger.error("Error fetching address {}".format(exec_info))
            return InternalServerErrorResponse(ErrorMsg.INTERNAL_SERVER_ERROR)

    @partner_address_router.delete("/partner_address/{address_id}")
    @permission_check(PermissionDependency)
    @inject
    async def delete_partner_address_by_id(
        request: Request,
        address_id: UUID,
        address_service: PartnerAddressService = Depends(
            Provide[Container.address_service]
        ),
        console_service_logger: ConsoleServiceLogger = Depends(
            Provide[Container.console_service_logger]
        ),
    ):
        try:
            console_service_logger.info(
                "Attempting to delete the address with id {}".format(address_id)
            )
            await address_service.delete_by_id(address_id)
            console_service_logger.info(
                "address with id {} is now deleted successfully.".format(address_id)
            )
            return SuccessResponse(PartnerAddressResponseMsg.DELETE_ADDRESS_PARTNER)
        except AddressNotFoundError as e:
            console_service_logger.error("Address not found: {}".format(e))
            return NotFoundResponse(detail=str(e))
        except Exception as e:
            console_service_logger.error("Error fetching address {}".format(e))
            return InternalServerErrorResponse(ErrorMsg.INTERNAL_SERVER_ERROR)

    @partner_address_router.get(
        "/partner_address/{partner_id}",
        response_model=list[Contrasts.GetAddressByAddressIdResponse],
    )
    @permission_check(PermissionDependency)
    @inject
    async def get_partner_address_by_partner_id(
        request: Request,
        partner_id: UUID,
        address_service: PartnerAddressService = Depends(
            Provide[Container.address_service]
        ),
        console_service_logger: ConsoleServiceLogger = Depends(
            Provide[Container.console_service_logger]
        ),
    ):
        try:
            console_service_logger.info(
                "Attempting to fetch the partner address by id: {}".format(partner_id)
            )
            partner: list[Contrasts.GetAddressByAddressIdResponse] = (
                await address_service.get_partner_address_by_partner_id(partner_id)
            )
            return SuccessResponse(data=partner)
        except AddressNotFoundError as exec:
            console_service_logger.error(
                "Partner address not found for partner id: {}".format(partner_id)
            )
            return NotFoundResponse(detail=ExceptionMessages.ADDRESS_NOT_FOUND)
        except Exception as exec:
            console_service_logger.error(
                "An unexpected error occured while fetching the user: {}".format(exec)
            )
            return InternalServerErrorResponse()

    @partner_address_router.post(
        "/partner_address", response_model=list[UpsertPartnerAddressResponse]
    )
    @permission_check(PermissionDependency)
    @inject
    async def upsert_partner_address(
        request: Request,
        address_data: UpdatePartnerAddressRequest,
        partner_id: Optional[UUID] = None,
        is_upserting_publisher_address: Optional[bool]=False,
        address_service: PartnerAddressService = Depends(
            Provide[Container.address_service]
        ),
        user_svc: UserService = Depends(Provide[Container.console_service]),
        console_service_logger: ConsoleServiceLogger = Depends(
            Provide[Container.console_service_logger]
        ),
    ):
        try:
            current_user: dict = request.state.user
            user_id: UUID = current_user.get(CurrentUserMap.USER_ID)
            if not is_upserting_publisher_address:
                if not (partner_id and await user_svc.is_user_internal(user_id)):
                    partner_id: UUID = current_user.get(CurrentUserMap.PARTNER_ID)

            console_service_logger.info(
                "trying to update the partner addresses for partner id: {}".format(
                    partner_id
                )
            )
            updated_address: list[UpsertPartnerAddressResponse] = await address_service.upsert_partner_address(
                partner_id, user_id, address_data
            )
            return SuccessResponse(data=updated_address)
        except PartnerException as exec:
            console_service_logger.error(
                "Partner not found error occured: {}".format(exec)
            )
            return NotFoundResponse(detail=str(exec))
        except AddressExistsException as exec:
            console_service_logger.error(
                "Address already exists error occured: {}".format(exec)
            )
            return ResourceConflictResponse(detail=str(exec))
        except Exception as exec:
            console_service_logger.error(
                "An unexpected error occured while updating address"
            )
            return InternalServerErrorResponse()
