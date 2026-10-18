from uuid import UUID
from contextlib import AbstractAsyncContextManager
from typing import AsyncIterator, Callable, List, Union, Optional

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from src.components.user_config.models import UserConfig
from src.components.user_config.schemas import (
    UserConfigBase,
    UserConfigData,
    UserConfigRequest,
)
from src.exceptions import (
    PartnerConfigException,
)  # You can create a UserConfigException if preferred
from src.loggers.console_service_logger import ConsoleServiceLogger


class UserConfigRepository:

    def __init__(
        self,
        session_factory: Callable[..., AbstractAsyncContextManager[AsyncSession]],
        console_service_logger: ConsoleServiceLogger,
    ) -> None:
        self.__session_factory = session_factory
        self.__console_service_logger = console_service_logger

    async def create_user_config(self, user_config_data: UserConfigBase):
        try:
            async with self.__session_factory() as session:
                self.__console_service_logger.info(
                    "Creating user config with current user id: {} and key {}".format(
                        user_config_data.user_id, user_config_data.key
                    )
                )
                user_config = UserConfig(
                    key=user_config_data.key,
                    value=user_config_data.value,
                    user_id=user_config_data.user_id,
                )
                session.add(user_config)
                await session.commit()
                await session.refresh(user_config)
            return user_config

        except IntegrityError as exec:
            self.__console_service_logger.error(
                "Integrity error occured: {}".format(exec)
            )
            raise exec
        except Exception as exec:
            self.__console_service_logger.error(
                "Unexpected error occured while creating user config: {}".format(exec)
            )
            raise exec

    async def get_user_config_by_key(
        self, user_id: UUID, key: str
    ) -> UserConfig | Exception:
        try:
            async with self.__session_factory() as session:
                self.__console_service_logger.info(
                    "getting user config for user id: {}".format(user_id)
                )
                query = select(UserConfig).filter(
                    UserConfig.user_id == user_id,
                    UserConfig.key == key,
                    UserConfig.is_active == True,
                )
                result = await session.execute(query)
                return result.scalar_one_or_none()

        except Exception as exec:
            self.__console_service_logger.error(
                "Unexpected error occured while getting user config: {}".format(exec)
            )
            raise exec

    async def update_user_config(
        self, user_ids: List[UUID], update_user_config_data: UserConfigData
    ) -> List[UserConfig]:
        try:
            async with self.__session_factory() as session:
                self.__console_service_logger.info(
                    "updating user config for user ids: {}".format(user_ids)
                )
                update_data = update_user_config_data.model_dump(exclude_unset=True)
                keys_to_update = list(update_data.keys())

                # Fetch existing configs for all user_ids and all relevant keys
                query = select(UserConfig).where(
                    UserConfig.user_id.in_(user_ids),
                    UserConfig.key.in_(keys_to_update),
                )
                result = await session.execute(query)
                existing_configs = result.scalars().all()
                # Map by (user_id, key)
                existing_map = {
                    (config.user_id, config.key): config for config in existing_configs
                }

                updated_configs: List[UserConfig] = []
                for user_id in user_ids:
                    for key, new_value in update_data.items():
                        if new_value is not None:
                            config = existing_map.get((user_id, key))
                            if config:
                                old_value = config.value
                                config.update_history(old_value, new_value)
                                config.value = new_value
                                updated_configs.append(config)
                            else:
                                new_config = UserConfig(
                                    user_id=user_id,
                                    key=key,
                                    value=new_value,
                                )
                                session.add(new_config)
                                updated_configs.append(new_config)

                await session.commit()
                # Refresh to get updated state from DB
                for config in updated_configs:
                    await session.refresh(config)
            return updated_configs
        except Exception as exec:
            self.__console_service_logger.error(
                "Unexpected error occurred while updating user config: {}".format(exec)
            )
            raise exec

    async def get_user_configs_by_user_id(self, user_id: UUID):
        try:
            async with self.__session_factory() as session:
                self.__console_service_logger.info(
                    "getting all user configs for user id: {}".format(user_id)
                )
                query = select(UserConfig).filter(
                    UserConfig.user_id == user_id,
                    UserConfig.is_active == True,
                )
                result = await session.execute(query)
                rows = result.scalars().all()
                return rows

        except PartnerConfigException as exec:
            self.__console_service_logger.error(
                "No user config is available for user id: {} ".format(user_id)
            )
            raise exec
        except Exception as exec:
            self.__console_service_logger.error(
                "Unexpected error occured while getting all user configs: {}".format(
                    exec
                )
            )
            raise exec
