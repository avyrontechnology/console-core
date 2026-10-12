from uuid import UUID
from contextlib import AbstractContextManager
from typing import Callable, List

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from src.components.api_key.models import ApiKey
from src.loggers.console_service_logger import ConsoleServiceLogger


class ApiKeyRepository:
    def __init__(
        self,
        session_factory: Callable[..., AbstractContextManager[AsyncSession]],
        console_service_logger: ConsoleServiceLogger,
    ) -> None:
        self.__session_factory: Callable[..., AbstractContextManager[AsyncSession]] = (
            session_factory
        )
        self.__console_service_logger: ConsoleServiceLogger = console_service_logger

    async def generate_api_key(
        self,
        partner_id: UUID,
        current_user_id: UUID,
        scopes: list | None = None,
        user_context: dict | None = None,
    ):
        """
        Generate and insert a new API key for a partner.
        """
        try:
            async with self.__session_factory() as session:
                self.__console_service_logger.info(
                    f"Attempting to generate API key for partner_id: {partner_id}"
                )

                api_key = ApiKey(
                    partner_id=partner_id,
                    is_active=True,
                    created_by=current_user_id,
                    scopes=scopes,
                    user_context=user_context,
                )

                session.add(api_key)
                await session.commit()
                await session.refresh(api_key)

                self.__console_service_logger.info(
                    f"API key generated successfully for partner_id: {partner_id}"
                )

                return api_key

        except Exception as ex:
            self.__console_service_logger.error(
                f"Error generating API key for partner_id={partner_id}: {str(ex)}"
            )
            raise

    async def validate_api_key(self, key: str):
        """
        Validate if the provided API key is valid (exists and active).
        If valid, return the API key details; otherwise, return None.
        """
        try:
            async with self.__session_factory() as session:
                self.__console_service_logger.info(
                    f"Validating API key: {key[:10]}..."  # log partially for safety
                )

                # Fetch the API key and ensure it’s active and not deleted
                result = await session.execute(
                    select(ApiKey).where(ApiKey.key == key, ApiKey.is_active == True)
                )
                api_key_obj = result.scalars().first()

                return api_key_obj

        except Exception as ex:
            self.__console_service_logger.error(
                f"Unexpected error while validating API key={key[:10]}...: {str(ex)}"
            )
            raise

    async def get_active_api_key(self, partner_id: UUID) -> ApiKey:
        """
        Retrieve the active API key for the given partner.
        Returns the ApiKey ORM object if found, otherwise None.
        """
        try:
            async with self.__session_factory() as session:
                self.__console_service_logger.info(
                    f"Attempting to fetch active API key for partner_id: {partner_id}"
                )

                result = await session.execute(
                    select(ApiKey).where(
                        ApiKey.partner_id == partner_id,
                        ApiKey.is_active == True,
                    )
                )

                api_key_obj = result.scalars().first()

                self.__console_service_logger.info(
                    f"Successfully fetched active API key for partner_id: {partner_id}"
                )
                return api_key_obj

        except Exception as ex:
            self.__console_service_logger.error(
                f"Error fetching API key for partner_id={partner_id}: {str(ex)}"
            )
            raise

    async def inactivate_api_key(self, partner_id: UUID, current_user_id: UUID) -> bool:
        """
        Mark the given API key as inactive (soft delete style) and record who updated it.
        """
        try:
            async with self.__session_factory() as session:
                self.__console_service_logger.info(
                    f"Attempting to inactivate API key for partner_id={partner_id} by user_id={current_user_id}"
                )

                # Update query
                stmt = (
                    update(ApiKey)
                    .where(ApiKey.partner_id == partner_id, ApiKey.is_active.is_(True))
                    .values(is_active=False, updated_by=current_user_id)
                    .returning(ApiKey)
                )

                result = await session.execute(stmt)
                api_key = result.scalar_one_or_none()

                if not api_key:
                    self.__console_service_logger.warning(
                        f"No active API key found for partner_id={partner_id}"
                    )
                    return False

                await session.commit()

                self.__console_service_logger.info(
                    f"API key for partner_id={partner_id} successfully inactivated by user_id={current_user_id}"
                )

                return True
        except Exception as ex:
            self.__console_service_logger.error(
                f"Unexpected error while inactivating API key for partner_id={partner_id}: {str(ex)}"
            )
            raise

    async def update_active_api_key_metadata(
        self,
        partner_id: UUID,
        current_user_id: UUID | None,
        scopes: list | None = None,
        user_context: dict | None = None,
    ):
        """
        Update ``scopes`` / ``user_context`` on the partner's active API key
        in place (no rotation). A field passed as ``None`` is left untouched;
        pass ``[]`` / ``{}`` to clear it.

        Returns the updated ApiKey row, or ``None`` if there is no active key.
        """
        try:
            async with self.__session_factory() as session:
                self.__console_service_logger.info(
                    f"Attempting to update API key metadata for partner_id={partner_id}"
                )

                values: dict = {"updated_by": current_user_id}
                if scopes is not None:
                    values["scopes"] = scopes
                if user_context is not None:
                    values["user_context"] = user_context

                stmt = (
                    update(ApiKey)
                    .where(ApiKey.partner_id == partner_id, ApiKey.is_active.is_(True))
                    .values(**values)
                    .returning(ApiKey)
                )

                result = await session.execute(stmt)
                api_key = result.scalar_one_or_none()

                if not api_key:
                    self.__console_service_logger.warning(
                        f"No active API key found for partner_id={partner_id}"
                    )
                    return None

                await session.commit()
                # ``expire_on_commit`` is on, so re-populate the instance while
                # it is still bound to the session — otherwise the caller hits
                # DetachedInstanceError when serialising it after the session
                # closes (same pattern as ``generate_api_key``).
                await session.refresh(api_key)

                self.__console_service_logger.info(
                    f"API key metadata updated for partner_id={partner_id}"
                )
                return api_key
        except Exception as ex:
            self.__console_service_logger.error(
                f"Unexpected error while updating API key metadata for "
                f"partner_id={partner_id}: {str(ex)}"
            )
            raise

    async def generated_api_key_while_partner_onboarding(
        self,
        partner_id: UUID,
    ):
        """
        Generate and insert a new API key for a partner.
        """
        try:
            async with self.__session_factory() as session:
                self.__console_service_logger.info(
                    f"Attempting to generate API key for partner_id: {partner_id}"
                )

                api_key = ApiKey(
                    partner_id=partner_id,
                    is_active=True,
                )

                session.add(api_key)
                await session.commit()
                await session.refresh(api_key)

                self.__console_service_logger.info(
                    f"API key generated successfully for partner_id: {partner_id}"
                )

                return api_key

        except Exception as ex:
            self.__console_service_logger.error(
                f"Error generating API key for partner_id={partner_id}: {str(ex)}"
            )
