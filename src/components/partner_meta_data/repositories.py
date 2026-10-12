from uuid import UUID
from contextlib import AbstractContextManager
from typing import Callable, Iterator

from fastapi import HTTPException, status
from sqlalchemy import exists, select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from src.components.partner.models import Partner
from src.components.partner_meta_data.constant import PartnerMetaDataExceptionMsg
from src.components.partner_meta_data.error import PartnerMetaDataNotFoundError
from src.components.partner_meta_data.models import PartnerMetaData
from src.components.partner_meta_data.schema import (
    PartnerMetadata,
    UpdatePartnerMetaData,
)
from src.exceptions import PartnerMetaDataException
from src.loggers.console_service_logger import ConsoleServiceLogger


class PartnerMetaDataRepository:

    def __init__(
        self,
        session_factory: Callable[..., AbstractContextManager[Session]],
        console_service_logger: ConsoleServiceLogger = ConsoleServiceLogger(),
    ) -> None:
        self.__session_factory: Callable[..., AbstractContextManager[Session]] = (
            session_factory
        )
        self.__console_service_logger: ConsoleServiceLogger = console_service_logger

    async def is_partner_exists(self, partner_id: UUID) -> bool:
        try:
            async with self.__session_factory() as session:
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
        except SQLAlchemyError as e:
            self.__console_service_logger.error(
                "Database error while fetching partner, id: {}".format(partner_id)
            )
            raise e

    async def is_partner_meta_data_exists(self, session: AsyncSession, partner_id: UUID):
        self.__console_service_logger.info(
            "Checking if partner meta data already exists or not, partner id: {}".format(
                partner_id
            )
        )
        result = await session.execute(
            select(PartnerMetaData).where(
                PartnerMetaData.partner_id == partner_id, Partner.is_active == True
            )
        )
        return result.scalars().first() is not None

    async def add_partner_metadata_repository(
        self, partner_id: UUID, partner_meta_data: PartnerMetadata
    ):
        """
        This function called by partner service function whenever new partner will create
        """
        try:
            async with self.__session_factory() as session:
                self.__console_service_logger.info(
                    "Attempting insert partner metadata for partner id: {}".format(
                        partner_id
                    )
                )
                self.__console_service_logger.info(
                    "Checking whether the partner metadata is already available or not for partner_id: {}".format(
                        partner_id
                    )
                )

                if await self.is_partner_meta_data_exists(session, partner_id):
                    raise PartnerMetaDataException(
                        "Meta data for partner id: {} is already exists, you can update it if needed.".format(
                            partner_id
                        )
                    )

                partner_meta_data_dict = partner_meta_data.model_dump(
                    exclude_unset=True
                )
                partner_meta_data_dict.update({"partner_id": partner_id})
                partner_property = PartnerMetaData(**partner_meta_data_dict)
                session.add(partner_property)
                await session.commit()
                await session.refresh(partner_property)
                self.__console_service_logger.info(
                    "Successfully insert partner metadata for partner id: {}".format(
                        partner_id
                    )
                )
                return partner_property
        except IntegrityError as exec:
            self.__console_service_logger.error(
                "Integrity error occurred while inserting partner metadata for partner id: '{}' error: {}".format(
                    partner_id, exec
                )
            )
            raise PartnerMetaDataException(
                PartnerMetaDataExceptionMsg.EMAIL_ALREADY_EXISTS
            )
        except PartnerMetaDataException as exec:
            raise exec
        except Exception as ex:
            self.__console_service_logger.error(
                "Error occurred while inserting partner metadata for partner id: '{}' error: {}".format(
                    partner_id, ex
                )
            )
            raise ex

    async def get_all_partner_meta_data(self) -> Iterator[PartnerMetaData]:
        try:
            async with self.__session_factory() as session:
                self.__console_service_logger.info(
                    "Attempting get all partner metadata"
                )

                query = select(PartnerMetaData).filter(
                    exists()
                    .where(Partner.id == PartnerMetaData.partner_id)
                    .where(Partner.is_deleted == False)
                )
                all_partner_meta_data = (await session.execute(query)).scalars().all()
                self.__console_service_logger.info(
                    "Successfully fetched all partner metadata: {}".format(
                        all_partner_meta_data
                    )
                )
                return all_partner_meta_data
        except Exception as ex:
            self.__console_service_logger.error(
                "Error occurred while getting all partner metadata {}".format(str(ex))
            )
            raise ex

    async def update_partner_meta_data(
        self,
        partner_id: UUID,
        update_data: UpdatePartnerMetaData,
    ) -> PartnerMetaData:
        try:
            async with self.__session_factory() as session:
                self.__console_service_logger.info(
                    "Attempting update partner metadata for partner id: {}".format(
                        partner_id
                    )
                )
                query = (
                    select(PartnerMetaData)
                    .filter(PartnerMetaData.partner_id == partner_id)
                    .filter(
                        exists()
                        .where(Partner.id == partner_id)
                        .where(Partner.is_deleted == False)
                    )
                )

                result = await session.execute(query)
                partner_metadata = result.scalars().one_or_none()
                if not partner_metadata:
                    self.__console_service_logger.error(
                        "Error occurred while update partner metadata for partner_id {} not found".format(
                            partner_id
                        )
                    )
                    raise PartnerMetaDataNotFoundError(partner_id)

                for field, value in update_data.model_dump(exclude_unset=True).items():
                    setattr(partner_metadata, field, value)

                # Commit the changes to the database
                await session.commit()
                await session.refresh(partner_metadata)
                self.__console_service_logger.info(
                    "Partner metadata updated successfully: {}".format(result)
                )

                return partner_metadata
        except Exception as ex:
            self.__console_service_logger.error(
                "Error occurred while update partner metadata for partner_id {}".format(
                    ex
                )
            )
            raise

    async def get_partner_meta_data_by_partner_id(
        self, partner_id: UUID
    ) -> PartnerMetaData | None:
        try:
            async with self.__session_factory() as session:
                self.__console_service_logger.info(
                    "Attempting to get partner metadata by partner_id {}".format(
                        partner_id
                    )
                )

                query = (
                    select(PartnerMetaData)
                    .filter(PartnerMetaData.partner_id == partner_id)
                    .filter(
                        exists()
                        .where(Partner.id == partner_id)
                        .where(Partner.is_deleted == False)
                    )
                )

                result = await session.execute(query)
                partner_metadata = result.scalars().one_or_none()
                if not partner_metadata:
                    self.__console_service_logger.error(
                        "Error occurred while get partner metadata by partner_id"
                    )
                    return None
                self.__console_service_logger.info(
                    "Successfully fetched partner metadata by partner_id {} {}".format(
                        partner_id, partner_metadata
                    )
                )
                return partner_metadata
        except PartnerMetaDataNotFoundError as ex:
            self.__console_service_logger.error(
                "Error occurred while get partner metadata by partner_id {}".format(ex)
            )
            raise PartnerMetaDataException(ex)
        except Exception as ex:
            self.__console_service_logger.error(
                "Error occurred while get partner metadata by partner_id {}".format(ex)
            )
            raise

    async def get_partner_meta_data_by_partner_ids(
        self, partner_ids: list[int]
    ) -> list[PartnerMetaData]:
        try:
            async with self.__session_factory() as session:
                self.__console_service_logger.info(
                    "Attempting to get partner metadata by partner_ids {}".format(
                        partner_ids
                    )
                )

                query = select(PartnerMetaData).filter(
                    PartnerMetaData.partner_id.in_(partner_ids)
                )

                result = await session.execute(query)
                partner_metadata_list = result.scalars().all()
                self.__console_service_logger.info(
                    "Successfully fetched partner metadata by partner_ids {} {}".format(
                        partner_ids, partner_metadata_list
                    )
                )
                return partner_metadata_list
        except Exception as exec:
            self.__console_service_logger.error(
                "Error occurred while get partner metadata by partner_ids {}".format(
                    exec
                )
            )
            raise exec
