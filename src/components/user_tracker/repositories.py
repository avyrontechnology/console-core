from uuid import UUID
from contextlib import AbstractAsyncContextManager
from typing import Callable, Dict, Optional, Tuple

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from src.components.partner_config.models import PartnerConfig
from src.components.user.models import User
from src.components.user_tracker.constants import (
    StandardStatuses,
    UserTrackerPartnerConfigKey,
)
from src.components.user_tracker.errors import UserTrackerNotFoundError
from src.loggers.console_service_logger import ConsoleServiceLogger


class UserTrackerRepository:

    def __init__(
        self,
        session_factory: Callable[..., AbstractAsyncContextManager[AsyncSession]],
        console_service_logger: ConsoleServiceLogger,
    ) -> None:
        self.__session_factory = session_factory
        self.__console_service_logger = console_service_logger

    # console_users operations

    async def get_user_current_status(
        self, user_id: UUID
    ) -> Tuple[str, Optional[str]]:
        """
        Read User.current_status and the user's own current_status_icon
        override from console_users. Falls back to StandardStatuses.AWAY
        if current_status is NULL.
        """
        async with self.__session_factory() as session:
            try:
                self.__console_service_logger.info(
                    f"[UserTrackerRepository] Fetching current_status for user_id: {user_id}"
                )
                query = select(User).where(
                    User.id == user_id,
                    User.is_active.is_(True),
                )
                result = await session.execute(query)
                user = result.scalar_one_or_none()

                if user is None:
                    raise UserTrackerNotFoundError(user_id)

                return user.current_status or StandardStatuses.AWAY, user.current_status_icon

            except UserTrackerNotFoundError:
                raise
            except SQLAlchemyError as exc:
                self.__console_service_logger.error(
                    f"[UserTrackerRepository] DB error fetching current_status "
                    f"for user_id {user_id}: {exc}"
                )
                raise

    async def update_user_current_status(
        self,
        user_id: UUID,
        status: str,
        status_icon_override: Optional[str] = None,
    ) -> str:
        """
        Write new status (and this user's own icon override, if any) to
        console_users. status_icon_override is per-user — it never touches
        the partner-wide custom status catalog. Returns previous status.
        """
        async with self.__session_factory() as session:
            try:
                self.__console_service_logger.info(
                    f"[UserTrackerRepository] Updating current_status to '{status}' "
                    f"for user_id: {user_id}"
                )
                query = select(User).where(
                    User.id == user_id,
                    User.is_active.is_(True),
                )
                result = await session.execute(query)
                user = result.scalar_one_or_none()

                if user is None:
                    raise UserTrackerNotFoundError(user_id)

                previous_status = user.current_status or StandardStatuses.AWAY
                user.current_status = status
                user.current_status_icon = status_icon_override

                session.add(user)
                await session.commit()

                self.__console_service_logger.info(
                    f"[UserTrackerRepository] current_status updated for user_id {user_id}: "
                    f"'{previous_status}' → '{status}'"
                )
                return previous_status

            except UserTrackerNotFoundError:
                raise
            except SQLAlchemyError as exc:
                self.__console_service_logger.error(
                    f"[UserTrackerRepository] DB error updating current_status "
                    f"for user_id {user_id}: {exc}"
                )
                raise

    # console_partner_config operations

    def __migrate_if_old_format(self, data: dict) -> Dict[str, dict]:
        """
        Handles backward compatibility if DB still has old format:
          Old: {"uuid": "Away"}
          New: {"uuid": {"display_id": "custom_1", "name": "Away"}}
        Converts on the fly. DB updated to new format on next upsert.
        """
        migrated = {}
        counter = 1
        for key, value in data.items():
            if isinstance(value, str):
                # Old format — migrate to new
                migrated[key] = {
                    "display_id": f"custom_{counter}",
                    "name": value,
                }
                counter += 1
            elif isinstance(value, dict):
                # Already new format
                migrated[key] = value
                try:
                    n = int(value.get("display_id", "custom_0").split("_")[1])
                    if n >= counter:
                        counter = n + 1
                except (IndexError, ValueError):
                    pass
        return migrated

    async def get_custom_statuses(self, partner_id: UUID) -> Dict[str, dict]:
        """
        Read partner's custom statuses from console_partner_config.
        Returns {} if no config row exists yet.
        """
        async with self.__session_factory() as session:
            try:
                self.__console_service_logger.info(
                    f"[UserTrackerRepository] Fetching custom statuses for partner_id: {partner_id}"
                )
                query = select(PartnerConfig).where(
                    PartnerConfig.partner_id == partner_id,
                    PartnerConfig.key == UserTrackerPartnerConfigKey.USER_TRACKER_STATUSES,
                    PartnerConfig.is_active.is_(True),
                )
                result = await session.execute(query)
                config = result.scalars().first()

                if config and isinstance(config.value, dict):
                    return self.__migrate_if_old_format(config.value)

                return {}

            except SQLAlchemyError as exc:
                self.__console_service_logger.error(
                    f"[UserTrackerRepository] DB error fetching custom statuses "
                    f"for partner_id {partner_id}: {exc}"
                )
                raise

    async def upsert_custom_statuses(
        self,
        partner_id: UUID,
        custom_statuses: Dict[str, dict],  # {uuid: {display_id, name}}
        updated_by: UUID,
    ) -> Dict[str, dict]:
        """
        Full replace of partner's custom statuses in console_partner_config.
        Calls update_history() before overwriting for audit trail.
        Stores raw structure: {uuid: {display_id: "custom_N", name: "..."}}
        Returns the saved Dict.
        """
        async with self.__session_factory() as session:
            try:
                self.__console_service_logger.info(
                    f"[UserTrackerRepository] Upserting custom statuses for "
                    f"partner_id {partner_id}"
                )
                query = select(PartnerConfig).where(
                    PartnerConfig.partner_id == partner_id,
                    PartnerConfig.key == UserTrackerPartnerConfigKey.USER_TRACKER_STATUSES,
                    PartnerConfig.is_active.is_(True),
                )
                result = await session.execute(query)
                config = result.scalars().first()

                if config:
                    config.update_history(config.value, custom_statuses)
                    config.value = custom_statuses
                    config.updated_by = updated_by
                else:
                    config = PartnerConfig(
                        partner_id=partner_id,
                        key=UserTrackerPartnerConfigKey.USER_TRACKER_STATUSES,
                        value=custom_statuses,
                        is_active=True,
                    )
                    session.add(config)

                await session.commit()
                await session.refresh(config)

                self.__console_service_logger.info(
                    f"[UserTrackerRepository] Custom statuses upserted for partner_id: {partner_id}"
                )
                return config.value

            except SQLAlchemyError as exc:
                self.__console_service_logger.error(
                    f"[UserTrackerRepository] DB error upserting custom statuses "
                    f"for partner_id {partner_id}: {exc}"
                )
                raise