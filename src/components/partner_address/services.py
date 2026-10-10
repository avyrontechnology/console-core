from typing import Dict, Iterator

from dependency_injector.wiring import Provide
from fastapi import Depends
from sqlalchemy.exc import IntegrityError
from src.components.cache import Keys as CacheKeys
from src.core.redis import RedisCache

from src.components.audit_log.schema import AuditLogSchema
from src.components.audit_log.services import AuditService
from src.components.common.actions import AuditActions
from src.components.common.resources import Resource
from src.components.partner.models import Partner
from src.components.partner.services import PartnerService
from src.components.partner_address.error import AddressNotFoundError
from src.components.partner_address.models import PartnerAddress
from src.components.partner_address.repositories import AddressRepository
from src.components.partner_address.schema import (
    Contrasts,
    UpdatePartnerAddressRequest,
    UpsertPartnerAddressResponse,
)
from src.components.cache.helper import CacheHelper
from src.exceptions import AddressExistsException, PartnerException
from src.loggers.console_service_logger import ConsoleServiceLogger


class PartnerAddressService:

    def __init__(
        self,
        address_repository: AddressRepository,
        audit_service: AuditService,
        console_service_logger: ConsoleServiceLogger,
        partner_address_service_cache: CacheHelper,
    ) -> None:
        self.__repository: AddressRepository = address_repository
        self.__logger: AuditService = console_service_logger
        self.__audit_service: ConsoleServiceLogger = audit_service
        self.__partner_address_service_cache: CacheHelper = partner_address_service_cache

    async def partner_exists(self, partner_id: int) -> bool:
        try:
            return await self.__repository.partner_exists(partner_id)
        except Exception as e:
            self.__logger.error("Error checking if partner exists: {}".format(e))
            raise

    async def get_addresses(self) -> Iterator[PartnerAddress]:
        try:
            self.__logger.info("Getting all the addresses stored in database.")
            all_addresses = await self.__repository.get_all()
            self.__logger.info(
                "Fetched all addresses successfully: {}".format(all_addresses)
            )
            return all_addresses
        except Exception as e:
            self.__logger.error("Error retriving addresses.{}".format(e))
            raise

    async def get_by_id(self, address_id) -> PartnerAddress:
        try:
            self.__logger.info("getting address with id : {}".format(address_id))
            address = await self.__repository.get_by_id(address_id)
            # checking if partner is active or not
            partner_exists = await self.__repository.partner_exists(address.partner_id)
            if not partner_exists:
                self.__logger.error(
                    "The partner with id {} is deleted or is not active".format(
                        address.partner_id
                    )
                )
                raise AddressNotFoundError(address_id)
            self.__logger.info(
                "Address fetched successfully. {}".format(address.__dict__)
            )
            return address
        except AddressNotFoundError as e:
            self.__logger.error(str(e))
            raise
        except Exception as e:
            self.__logger.error("error getting partner {}".format(e))
            raise

    async def delete_by_id(self, address_id) -> None:
        try:
            self.__logger.info("deleting address with id : {}".format(address_id))
            deleted_address: PartnerAddress = await self.__repository.delete_by_id(address_id)

            self.__logger.info(
                "address with id: {} is now deleted from the database".format(
                    address_id
                )
            )

            log_entry = AuditLogSchema(
                action=AuditActions.delete,
                resource=Resource.partner_address,
                resource_id=address_id,
                resource_previous_state=None,
                resource_current_state=None,
                performed_by=address_id,
                details="Partner address with address id: {} is deleted successfully".format(
                    address_id
                ),
            )
            await self.__audit_service.log_action(log_entry)

            await self.__partner_address_service_cache.clear_pattern(
                prefix=RedisCache.KeysPrefix.MAGLO,
                pattern=CacheKeys.GRPC_GET_PUBLISHER_DATA.format(deleted_address.partner_id),
            )
        except AddressNotFoundError as e:
            self.__logger.error(str(e))
            raise
        except Exception as e:
            self.__logger.error("error deleting partner {}".format(e))
            raise

    async def get_partner_address_by_partner_id(
        self, partner_id: int
    ) -> Contrasts.GetAddressByAddressIdResponse:
        try:
            self.__logger.info(
                "Fetching partner address by partner id: {}".format(partner_id)
            )
            addresses: PartnerAddress = (
                await self.__repository.get_partner_address_by_partner_id(partner_id)
            )
            response: list[Contrasts.GetAddressByAddressIdResponse] = [
                Contrasts.GetAddressByAddressIdResponse.model_validate(addr)
                for addr in addresses
            ]
            return response
        except AddressNotFoundError as exec:
            self.__logger.error(
                "Partner address not found for the partner id: {}".format(partner_id)
            )
            raise exec
        except Exception as exec:
            self.__logger.error(
                "An error occured while fetching the user: {}".format(exec)
            )
            raise exec

    async def upsert_partner_address(
        self,
        partner_id: int,
        user_id: int,
        update_data: UpdatePartnerAddressRequest,
        partner_service: PartnerService = Depends(Provide["partner_service"]),
    ) -> list[UpsertPartnerAddressResponse]:
        try:
            self.__logger.info(
                "Updating addresses for partner id {}".format(partner_id)
            )
            partner: Partner = await partner_service.get_partner_by_id(partner_id)
            if not partner:
                raise PartnerException(
                    "Partner with id {} not found".format(partner_id)
                )

            addresses: Dict[str, PartnerAddress | None] = (
                await self.__repository.upsert_partner_address(
                    partner_id, user_id, update_data
                )
            )
            result: list[UpsertPartnerAddressResponse] = [
                UpsertPartnerAddressResponse.model_validate(addr)
                for addr in addresses
                if addr
            ]

            await self.__partner_address_service_cache.clear_pattern(
                prefix=RedisCache.KeysPrefix.MAGLO,
                pattern=CacheKeys.GRPC_GET_PUBLISHER_DATA.format(partner_id),
            )

            return result
        except PartnerException as exec:
            self.__logger.error("Partner not found: {}".format(str(exec)))
            raise exec
        except IntegrityError as exec:
            self.__logger.error(
                "Integrity error while updating address: {}".format(str(exec))
            )
            raise AddressExistsException(str(exec))
        except Exception as exec:
            self.__logger.error(
                "Unexpected error while updating address: {}".format(exec)
            )
            raise exec
