from typing import Dict, List, Optional, Type, Union

from sqlalchemy import update
from sqlalchemy.engine.result import ScalarResult
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm import joinedload
from sqlalchemy.sql.selectable import Select

from src.components.db_constants.models import (
    ConstantsBase,
    GlobalMediaConstants,
    MediaConstants,
)
from src.components.db_constants.schema import ConstantResponseSchema
from src.components.digital_assets.models import DigitalAssets
from src.loggers.console_service_logger import ConsoleServiceLogger


class ConstantsRepository:
    def __init__(
        self,
        session_factory: AsyncSession,
        console_service_logger: ConsoleServiceLogger,
    ):
        self.session_factory = session_factory
        self.console_service_logger = console_service_logger

    async def fetch_constant_by_type(
        self, constant_model: type[ConstantsBase]
    ) -> List[ConstantResponseSchema]:
        """
        Fetch constants based on the type provided by the user. The type maps to a specific model.
        Returns the constants as a list of ConstantResponseSchema instances.
        """
        async with self.session_factory() as session:
            try:
                self.console_service_logger.info(
                    "Fetching constants for model type: {}".format(constant_model)
                )
                media_models: bool = constant_model in [
                    MediaConstants,
                    GlobalMediaConstants,
                ]
                stmt: Select[Type[ConstantsBase]] = (
                    select(constant_model).options(joinedload(constant_model.media))
                    if media_models
                    else select(constant_model)
                )
                result: ScalarResult[ConstantsBase] = await session.execute(stmt)
                constants: List[ConstantsBase] = result.scalars().all()

                constants_schema: List[ConstantResponseSchema] = [
                    ConstantResponseSchema(
                        id=constant.id,
                        name=constant.name,
                        value=(
                            constant.media.name
                            if media_models and constant.media
                            else constant.value
                        ),
                        description=constant.description,
                        version=constant.version,
                        updated_by=constant.updated_by,
                        updated_at=constant.updated_at,
                        additional_info=(
                            await self.update_additional_info_for_media_constants(
                                constant.additional_info
                            )
                            if media_models and constant.additional_info
                            else constant.additional_info
                        ),
                    )
                    for constant in constants
                ]
                return constants_schema
            except Exception as e:
                self.console_service_logger.error(
                    "Error fetching constants for type {}: {}".format(constant_model, e)
                )
                raise e

    async def update_additional_info_for_media_constants(
        self, additional_info: Dict[str, Union[int, str]]
    ) -> Dict[str, Union[int, str]]:
        """
        Fetch media names for foreign key values in additional_info.
        """
        asset_ids: set[int] = {
            value for value in additional_info.values() if isinstance(value, int)
        }

        try:
            async with self.session_factory() as session:
                media_results: ScalarResult[DigitalAssets] = await session.execute(
                    select(DigitalAssets.id, DigitalAssets.name).filter(
                        DigitalAssets.id.in_(asset_ids)
                    )
                )
                media_objects: Dict[int, str] = {
                    media.id: media.name for media in media_results.all()
                }

            return {
                key: media_objects.get(value, value)
                for key, value in additional_info.items()
            }
        except Exception as e:
            self.console_service_logger.error(f"Error fetching media: {e}")
            return additional_info

    async def get_constant_by_id(
        self, constant_model: type[ConstantsBase], id: int
    ) -> List[ConstantResponseSchema]:
        """
        Retrieve a constant by its ID from the database.
        """
        async with self.session_factory() as session:
            try:
                self.console_service_logger.info(
                    "Fetching constant with ID: {} for model type: {}".format(
                        id, constant_model
                    )
                )
                stmt: Select[Type[ConstantsBase]] = select(constant_model).where(
                    constant_model.id == id
                )
                result: ScalarResult[ConstantsBase] = await session.execute(stmt)
                constant: Optional[ConstantsBase] = result.scalar_one_or_none()

                return constant
            except Exception as e:
                self.console_service_logger.error(
                    "Error fetching constant with ID {} for type {}: {}".format(
                        id, constant_model, e
                    )
                )
                raise e

    async def update_constant(
        self,
        id: int,
        constant_model: Type[ConstantsBase],
        value: object,
        version: int,
        additional_info: Dict[str, Union[int, str]],
        user_id: int = int,
        description: Optional[str] = None,
    ) -> List[ConstantResponseSchema]:
        """
        Update the constant value, description, and increment version.
        Store the previous version in additional_info.
        """
        async with self.session_factory() as session:
            try:
                self.console_service_logger.info(
                    "Updating constant with ID: {} for type: {}".format(
                        id, constant_model
                    )
                )
                stmt = (
                    update(constant_model)
                    .where(constant_model.id == id)
                    .values(
                        value=value,
                        description=description,
                        version=version,
                        additional_info=additional_info,
                        updated_by=user_id,
                        created_by=(
                            user_id
                            if not constant_model.created_by
                            else constant_model.created_by
                        ),
                    )
                )

                await session.execute(stmt)
                await session.commit()

                updated_constant: Type[ConstantsBase] = await session.get(
                    constant_model, id
                )

                self.console_service_logger.info(
                    "Successfully updated constant with ID: {} for type {}".format(
                        id, constant_model
                    )
                )
                return updated_constant
            except Exception as e:
                self.console_service_logger.error(
                    "Error updating constant with ID {} for type {}: {}".format(
                        id, constant_model, e
                    )
                )
                raise e

    async def rollback_version(
        self,
        id: int,
        constant_model: Type[ConstantsBase],
        value: object,
        version: int,
        user_id: int,
        additional_info: Dict[str, Union[int, str]],
    ) -> List[ConstantResponseSchema]:
        """
        Rollback the constant to the specified version by updating its value and version.
        """
        async with self.session_factory() as session:
            try:
                self.console_service_logger.info(
                    "Rolling back constant with ID: {} to version: {} for type: {}".format(
                        id, version, constant_model
                    )
                )

                stmt = (
                    update(constant_model)
                    .where(constant_model.id == id)
                    .values(
                        value=value,
                        version=version,
                        additional_info=additional_info,
                        updated_by=user_id,
                    )
                )

                await session.execute(stmt)
                await session.commit()

                updated_constant: Type[ConstantsBase] = await session.get(
                    constant_model, id
                )

                self.console_service_logger.info(
                    "Successfully rolled back constant with ID: {} to version: {}".format(
                        id, version
                    )
                )
                return updated_constant

            except Exception as e:
                self.console_service_logger.error(
                    "An error occured while rolling back constant with ID {} to version {} for type {}: {}".format(
                        id, version, constant_model, e
                    )
                )
                raise e
