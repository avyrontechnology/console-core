from contextlib import AbstractContextManager
from typing import Callable, Dict, Iterator, Optional
from unittest import result

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.future import select
from sqlalchemy.orm import Session

from src.components.partner.models import Partner
from src.components.partner_address.error import AddressNotFoundError
from src.components.partner_address.models import PartnerAddress
from src.components.partner_address.schema import (
    AddressType,
    Contrasts,
    UpdatePartnerAddressData,
    UpdatePartnerAddressRequest,
)
from src.exceptions import AddressExistsException
from src.loggers.console_service_logger import ConsoleServiceLogger


class AddressRepository:

    def __init__(
        self,
        session_factory: Callable[..., AbstractContextManager[Session]],
        console_service_logger: ConsoleServiceLogger,
    ) -> None:
        self.__session_factory: Callable[..., AbstractContextManager[Session]] = (
            session_factory
        )
        self.__console_service_logger: ConsoleServiceLogger = console_service_logger

    async def partner_exists(self, partner_id: int) -> bool:
        async with self.__session_factory() as session:
            try:
                self.__console_service_logger.info(
                    f"Checking existence of partner with id {partner_id}"
                )
                result = await session.execute(
                    select(Partner).filter(
                        Partner.id == partner_id, Partner.is_active == True
                    )
                )
                partner = result.scalars().first()
                return partner is not None
            except Exception as ex:
                self.__console_service_logger.error("unexpected error {}".format(ex))
                raise ex

    async def get_all(self) -> Iterator[PartnerAddress]:
        async with self.__session_factory() as session:
            try:
                self.__console_service_logger.info(
                    "Fetching all the addresses from the database"
                )
                # creating a subquery to get the active partners from partner id
                active_partner_subquery = (
                    select(Partner.id).filter(Partner.is_active == True).subquery()
                )
                all_addresses = (
                    (
                        await session.execute(
                            select(PartnerAddress).where(
                                PartnerAddress.partner_id.in_(
                                    active_partner_subquery.select()
                                )
                            )
                        )
                    )
                    .scalars()
                    .all()
                )
                self.__console_service_logger.info(
                    "Fetched all the addresses successfully: {}".format(all_addresses)
                )
                return all_addresses
            except Exception as ex:
                self.__console_service_logger.error("unexpected error {}".format(ex))
                raise ex

    async def get_by_id(self, id: str) -> PartnerAddress:
        async with self.__session_factory() as session:
            try:
                self.__console_service_logger.info(
                    "getting address with id {}".format(id)
                )
                address = await session.get(PartnerAddress, id)
                if not address:
                    self.__console_service_logger.error(
                        "address not found : id {}".format(id)
                    )
                    raise AddressNotFoundError(id)
                return address
            except AddressNotFoundError as e:
                self.__console_service_logger.error(str(e))
                raise
            except Exception as ex:
                self.__console_service_logger.error("unexpected error {}".format(ex))
                raise ex

    async def delete_by_id(self, address_id) -> PartnerAddress:
        async with self.__session_factory() as session:
            try:
                self.__console_service_logger.info(
                    "deleting address with id {} from the database".format(address_id)
                )
                entity: PartnerAddress = await session.get(PartnerAddress, address_id)
                if not entity:
                    self.__console_service_logger.error(
                        "address not found id: {}".format(address_id)
                    )
                    raise AddressNotFoundError(address_id)
                await session.delete(entity)
                self.__console_service_logger.info(
                    "Address deleted succsessfully, id: {}".format(address_id)
                )
                await session.commit()
                return entity
            except AddressNotFoundError as e:
                self.__console_service_logger.error(str(e))
                raise
            except Exception as ex:
                self.__console_service_logger.error("unexpected error {}".format(ex))
                raise ex

    async def get_partner_address_by_partner_id(self, partner_id) -> PartnerAddress:
        try:
            async with self.__session_factory() as session:
                self.__console_service_logger.info(
                    "Fetching partner address by partner id: {}".format(partner_id)
                )
                query = select(PartnerAddress).where(
                    PartnerAddress.partner_id == partner_id
                )

                result = await session.execute(query)
                response = result.scalars().all()
                self.__console_service_logger.info(
                    "Partner address fetched successfully: {}".format(response)
                )
                return response
        except AddressNotFoundError as exec:
            self.__console_service_logger.error(
                "Partner not found for partner id: {}".format(partner_id)
            )
            raise exec
        except Exception as exec:
            self.__console_service_logger.error(
                "An error occured while fetching the user: {}".format(exec)
            )
            raise exec

    async def upsert_partner_address(
        self,
        partner_id: int,
        user_id: int,
        update_data: UpdatePartnerAddressRequest,
    ) -> list[PartnerAddress]:
        async with self.__session_factory() as session:
            try:
                self.__console_service_logger.info(
                    "Attempting to upsert addresses for partner id {}".format(
                        partner_id
                    )
                )

                address_map: dict = await self._get_existing_addresses(session, partner_id)

                if update_data.is_address_same:
                    updated_addresses = await self._handle_combined_address(
                        session, partner_id, user_id, update_data, address_map
                    )
                else:
                    updated_addresses: list[PartnerAddress] = await self._handle_separate_addresses(
                        session, partner_id, user_id, update_data, address_map
                    )

                self.__console_service_logger.info(
                    "Partner addresses upserted successfully for partner id {}: {}".format(
                        partner_id, updated_addresses
                    )
                )
                return updated_addresses

            except Exception as exec:
                self.__console_service_logger.error(
                    "An error occurred while upserting partner address for partner id {}: {}".format(
                        partner_id, exec
                    )
                )
                raise exec

    async def _get_existing_addresses(self, session, partner_id: int) -> dict:
        self.__console_service_logger.info(
            "Fetching existing addresses for partner id: {}".format(partner_id)
        )
        query = select(PartnerAddress).where(PartnerAddress.partner_id == partner_id)
        result = await session.execute(query)
        addresses = result.scalars().all()
        return {addr.address_type: addr for addr in addresses}

    async def _handle_combined_address(
        self,
        session,
        partner_id: int,
        user_id: int,
        update_data: UpdatePartnerAddressRequest,
        address_map: dict,
    ) -> list[PartnerAddress]:

        self.__console_service_logger.info(
            "is_address_same is True for partner id {}, merging addresses.".format(
                partner_id
            )
        )

        for addr_type in [AddressType.BILLING, AddressType.COMMUNICATION]:
            if addr_type in address_map:
                self.__console_service_logger.info(
                    "Deleting {} address for partner id {}".format(
                        addr_type.value, partner_id
                    )
                )
                await session.delete(address_map[addr_type])
        preferred_address: UpdatePartnerAddressRequest = (
            update_data.billing_address or update_data.communication_address
        )
        if AddressType.COMMUNICATION_AND_BILLING in address_map:
            addr_obj = address_map[AddressType.COMMUNICATION_AND_BILLING]
            new_data: dict = preferred_address.model_dump(exclude_unset=True)
            for key, value in new_data.items():
                setattr(addr_obj, key, value)

            self.__console_service_logger.info(
                "Updating existing COMMUNICATION_AND_BILLING address for partner id {}".format(
                    partner_id
                )
            )
        else:
            address_data: dict = preferred_address.model_dump(exclude_unset=True)
            addr_obj: PartnerAddress = PartnerAddress(
                **address_data,
                address_type=AddressType.COMMUNICATION_AND_BILLING,
                partner_id=partner_id,
                created_by=user_id,
                is_address_same=True,
            )
            session.add(addr_obj)
            self.__console_service_logger.info(
                "Creating new COMMUNICATION_AND_BILLING address for partner id {}".format(
                    partner_id
                )
            )

        await session.commit()
        await session.refresh(addr_obj)
        return [addr_obj]

    async def _handle_separate_addresses(
        self,
        session,
        partner_id: int,
        user_id: int,
        update_data: UpdatePartnerAddressRequest,
        address_map: dict,
    ) -> list[PartnerAddress]:

        self.__console_service_logger.info(
            "is_address_same is False for partner id {}, updating or creating billing and communication addresses.".format(
                partner_id
            )
        )

        updated_addresses: list = []

        if AddressType.COMMUNICATION_AND_BILLING in address_map:
            self.__console_service_logger.info(
                "Deleting existing COMMUNICATION_AND_BILLING address for partner id {}".format(
                    partner_id
                )
            )
            await session.delete(address_map[AddressType.COMMUNICATION_AND_BILLING])

        if update_data.billing_address:
            billing_data = update_data.billing_address.model_dump(exclude_unset=True)
            updated_addresses.append(
                self._upsert_address(
                    session,
                    billing_data,
                    address_map,
                    AddressType.BILLING,
                    partner_id,
                    user_id,
                    is_same=False,
                )
            )

        if update_data.communication_address:
            communication_data: dict = update_data.communication_address.model_dump(
                exclude_unset=True
            )
            updated_addresses.append(
                self._upsert_address(
                    session,
                    communication_data,
                    address_map,
                    AddressType.COMMUNICATION,
                    partner_id,
                    user_id,
                    is_same=False,
                )
            )

        await session.commit()
        for addr in updated_addresses:
            await session.refresh(addr)
        return updated_addresses

    def _upsert_address(
        self,
        session,
        data: dict,
        address_map: dict,
        addr_type: AddressType,
        partner_id: int,
        user_id: int,
        is_same: bool,
    ) -> PartnerAddress:

        if addr_type in address_map:
            addr_obj: PartnerAddress = address_map[addr_type]
            for key, value in data.items():
                setattr(addr_obj, key, value)
            self.__console_service_logger.info(
                "Updating existing {} address for partner id {}".format(
                    addr_type.value, partner_id
                )
            )
        else:
            addr_obj: PartnerAddress = PartnerAddress(
                **data,
                address_type=addr_type,
                partner_id=partner_id,
                created_by=user_id,
                is_address_same=is_same,
            )
            session.add(addr_obj)
            self.__console_service_logger.info(
                "Creating new {} address for partner id {}".format(
                    addr_type.value, partner_id
                )
            )
        return addr_obj
