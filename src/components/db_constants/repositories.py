from uuid import UUID
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
                result: ScalarResult[ConstantsBase] = await session.execute(
                    select(constant_model)
                )
                constants: List[ConstantsBase] = result.scalars().all()

                constants_schema: List[ConstantResponseSchema] = [
                    ConstantResponseSchema(
                        id=constant.id,
                        name=constant.name,
                        value=constant.value,
                        description=constant.description,
                        version=constant.version,
                        updated_by=constant.updated_by,
                        updated_at=constant.updated_at,
                        additional_info=constant.additional_info,
                    )
                    for constant in constants
                ]
                return constants_schema
            except Exception as e:
                self.console_service_logger.error(
                    "Error fetching constants for type {}: {}".format(constant_model, e)
                )
                raise e

    async def get_constant_by_id(
        self, constant_model: type[ConstantsBase], id: UUID
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
        id: UUID,
        constant_model: Type[ConstantsBase],
        value: object,
        version: int,
        additional_info: Dict[str, Union[int, str]],
        user_id: UUID = int,
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
        id: UUID,
        constant_model: Type[ConstantsBase],
        value: object,
        version: int,
        user_id: UUID,
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
