from typing import Dict, List, Optional, Union, Tuple

from sqlalchemy.exc import IntegrityError

from src.components.cache.helper import CacheHelper
from src.components.session_mangement.errors import UserSessionNotFoundError
from src.components.session_mangement.models import UserSession
from src.components.session_mangement.repositories import UserSessionRepository
from src.loggers.console_service_logger import ConsoleServiceLogger
from src.components.session_mangement.constants import SessionResponse
from src.components.common.datetime import DateTimeUtil

class UserSessionService:
    """Service layer for managing user sessions."""

    def __init__(
        self,
        user_session_repository: UserSessionRepository,
        console_service_logger: ConsoleServiceLogger,
        user_session_service_cache: CacheHelper,
    ) -> None:

        self.__user_session_repository: UserSessionRepository = user_session_repository
        self.__console_service_logger: ConsoleServiceLogger = console_service_logger
        self.__user_session_service_cache: CacheHelper = user_session_service_cache

    async def create_user_session(self, session_data: Dict) -> UserSession:
        """
        Create a new user session.
        """
        try:
            self.__console_service_logger.info(
                f"Creating user session with data: {session_data}"
            )
            user_session: UserSession = (
                await self.__user_session_repository.create_user_session(**session_data)
            )
            self.__console_service_logger.info(
                f"User session created successfully with ID: {user_session.session_id}"
            )
            return user_session

        except IntegrityError as integrity_error:
            self.__console_service_logger.error(
                f"Error occurred while creating user session: {str(integrity_error)}"
            )
        except Exception as exc:
            self.__console_service_logger.error(
                f"Error occurred while creating user session: {str(exc)}"
            )
            raise exc

    async def get_user_session(self, session_id: str) -> Optional[UserSession]:
        """
        Retrieve a user session by session ID.
        """
        try:
            self.__console_service_logger.info(
                f"Getting user session with ID: {session_id}"
            )
            user_session: UserSession = (
                await self.__user_session_repository.get_user_session(session_id)
            )
            if not user_session:
                raise UserSessionNotFoundError(entity_id=session_id)

            self.__console_service_logger.info(
                f"User session retrieved successfully with ID: {session_id}"
            )
            return user_session

        except UserSessionNotFoundError as session_not_found_exc:
            self.__console_service_logger.error(
                f"User session not found with ID: {session_id}"
            )
            raise session_not_found_exc
        except Exception as exc:
            self.__console_service_logger.error(
                f"Error occurred while retrieving user session with ID: {session_id} Error: {str(exc)}"
            )
            raise exc

    async def update_user_session(
        self, session_id: str, update_data: Dict
    ) -> Optional[UserSession]:
        """
        Update attributes of a user session.
        """
        try:
            updated_session: UserSession = (
                await self.__user_session_repository.update_user_session(
                    session_id, update_data
                )
            )
            if not updated_session:
                raise UserSessionNotFoundError(entity_id=session_id)
            self.__console_service_logger.info(
                f"User session with ID {session_id} updated successfully."
            )
            return updated_session

        except UserSessionNotFoundError as not_found_exc:
            self.__console_service_logger.error(
                f"User session not found: {not_found_exc}"
            )
            raise not_found_exc
        except Exception as exc:
            self.__console_service_logger.error(
                f"Error occurred while updating user session with ID: {session_id} Error: {str(exc)}"
            )
            raise exc

    async def deactivate_user_sessions(self, user_id: int | list[int], service_name: str | list[str] | None = None,) -> int:
        """
        Deactivate all active sessions for a user.
        """
        try:
            self.__console_service_logger
            deactivated_count: int = (
                await self.__user_session_repository.deactivate_all_sessions_by_user_id(
                    user_id, service_name
                )
            )
            self.__console_service_logger.info(
                f"Deactivated: {deactivated_count} sessions for user ID: {user_id}."
            )
            return deactivated_count
        except Exception as exc:
            self.__console_service_logger.error(
                f"Error occurred while deactivating sessions for user ID {user_id}: {str(exc)}"
            )
            raise exc

    async def deactivate_all_sessions_by_partner_id(
        self, partner_id: int, config: Optional[bool], service_name: Optional[str]=None
    ) -> int:
        """
        Deactivate all user sessions for a specific partner and update UserConfig.
        """
        try:
            self.__console_service_logger.info(
                f"Deactivating all sessions for partner_id: {partner_id}"
            )

            deactivated_count, user_ids = (
                await self.__user_session_repository.deactivate_all_sessions_by_partner_id(
                    partner_id, service_name
                )
            )

            if not user_ids:
                self.__console_service_logger.info(
                    f"No active sessions found for partner_id: {partner_id}"
                )
                return 0

            if config is not None:
                config_count = await self.__user_session_repository.deactivate_or_create_user_configs_by_user_ids(
                    user_ids, config
                )
                self.__console_service_logger.info(
                    f"{config_count} UserConfig records for partner_id: {partner_id}"
                )

            self.__console_service_logger.info(
                f"Successfully deactivated {deactivated_count} sessions and updated/created "
            )

            return

        except Exception as e:
            self.__console_service_logger.error(
                f"Error deactivating sessions for partner_id {partner_id}: {e}"
            )
            raise


    async def deactivate_all_sessions_by_service_name(
        self,
        service_name: str,
    ) -> str:
        """
        Deactivate all active user sessions for a specific service.
        """
        try:
            self.__console_service_logger.info(
                f"Deactivating all sessions for service_name: {service_name}"
            )

            deactivated_count: int = (
                await self.__user_session_repository
                .deactivate_all_sessions_by_service_name(service_name)
            )

            self.__console_service_logger.info(
                f"Successfully deactivated {deactivated_count} sessions "
                f"for service_name: {service_name}"
            )

            return SessionResponse.SESSIONS_DEACTIVATED.format(deactivated_count)

        except Exception as e:
            self.__console_service_logger.error(
                f"Error deactivating sessions for service_name {service_name}: {e}"
            )
            raise

    async def has_active_session(
            self, 
            user_id: int,
            service_name: str
        ) -> bool:
        """
        Check if a user has an active session for a specific service.
        """
        try:
            self.__console_service_logger.info(
                f"Checking active session for user_id: {user_id}, service_name: {service_name}"
            )
            current_time = DateTimeUtil.get_current_time()
            has_active: bool = (
                await self.__user_session_repository.has_active_session(
                    user_id, current_time, service_name
                )
            )
            return has_active

        except Exception as e:
            self.__console_service_logger.error(
                f"Error checking active session for user_id {user_id}, service_name {service_name}: {e}"
            )
            raise