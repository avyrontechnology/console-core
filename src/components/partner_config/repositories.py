from contextlib import AbstractAsyncContextManager
from typing import Callable, List

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from src.components.auth.models import Role
from src.components.common.constants import CurrentUserMap
from src.components.partner_config.constants import PartnerConfigEnum
from src.components.user.models import User
from src.components.partner_config.models import PartnerConfig
from src.components.partner_config.schemas import PartnerConfigBase, PartnerConfigData
from src.loggers.console_service_logger import ConsoleServiceLogger


class PartnerConfigRepository:                                                                      

    def __init__(
        self,
        session_factory: Callable[..., AbstractAsyncContextManager[AsyncSession]],
        console_service_logger: ConsoleServiceLogger,
    ) -> None:
        self.__session_factory: Callable[
            ..., AbstractAsyncContextManager[AsyncSession]
        ] = session_factory
        self.__console_service_logger: ConsoleServiceLogger = console_service_logger

    async def create_partner_config(
        self, partner_config_data: PartnerConfigBase, partner_id: int
    ):
        try:
            async with self.__session_factory() as session:

                self.__console_service_logger.info(
                    "Creating partner config with current user partner id: {} and key {}".format(
                        partner_id, partner_config_data.key
                    )
                )
                partner_config = PartnerConfig(
                    key=partner_config_data.key,
                    value=partner_config_data.value,
                    partner_id=partner_id,
                )
                session.add(partner_config)

                await session.commit()
                await session.refresh(partner_config)

            return partner_config

        except IntegrityError as exec:
            self.__console_service_logger.error(
                "Integrity error occured: {}".format(exec)
            )
            raise exec
        except Exception as exec:
            self.__console_service_logger.error(
                "Unexpected error occured while creating partner config: {}".format(
                    exec
                )
            )
            raise exec

    async def get_partner_config_by_key(
        self, partner_id: int | list[int], key: str
    ) -> PartnerConfig | Exception:
        try:
            async with self.__session_factory() as session:
                self.__console_service_logger.info(
                    "Checking Partner Lead Sources Associated to current partner: {}".format(
                        partner_id
                    )
                )
                if isinstance(partner_id, int):
                    partner_id = [partner_id]

                self.__console_service_logger.info(
                    "getting partner config for partner id: {}".format(partner_id)
                )
                query = select(PartnerConfig).filter(
                    PartnerConfig.partner_id.in_(partner_id),
                    PartnerConfig.key == key,
                    PartnerConfig.is_active == True,
                )
                partner_config = await session.execute(query)
                result = partner_config.scalars().all()
                return result

        except Exception as exec:
            self.__console_service_logger.error(
                "Unexpected error occured while getting partner config: {}".format(exec)
            )
            raise exec

    async def update_partner_config(
        self,
        partner_id: int,
        update_partner_config_data: PartnerConfigData,
        current_user_id: int,
    ) -> PartnerConfig:
        try:
            async with self.__session_factory() as session:
                self.__console_service_logger.info(
                    "Validating current user partner id with partner lead source partner id: {}".format(
                        partner_id
                    )
                )
                self.__console_service_logger.info(
                    "updating partner config for partner id: {}".format(partner_id)
                )
                update_data = update_partner_config_data.model_dump(exclude_unset=True)
                keys_to_update = list(update_data.keys())

                # 2. Fetch existing PartnerConfig entries for all valid sources and keys
                query = select(PartnerConfig).where(
                    PartnerConfig.partner_id == partner_id,
                    PartnerConfig.key.in_(keys_to_update),
                )
                result = await session.execute(query)
                existing_configs = result.scalars().all()

                # 3. Map: {(key) -> PartnerConfig}
                existing_map = {(config.key): config for config in existing_configs}

                updated_configs: List = []

                for key, new_value in update_data.items():
                    config_key = key

                    if config_key in existing_map:
                        config = existing_map[config_key]
                        if new_value is not None:
                            old_value = config.value
                            config.update_history(old_value, new_value)
                            config.value = new_value
                            config.updated_by = current_user_id
                        updated_configs.append(config)
                    else:
                        # Insert only if new_value is provided
                        if new_value is not None:
                            new_config = PartnerConfig(
                                partner_id=partner_id,
                                key=key,
                                value=new_value,
                            )
                            session.add(new_config)
                            updated_configs.append(new_config)

                await session.commit()

                # Optional: Refresh if required
                for config in updated_configs:
                    await session.refresh(config)

            return updated_configs

        except Exception as exec:
            self.__console_service_logger.error(
                "Unexpected error occured while updating partner config: {}".format(
                    exec
                )
            )
            raise exec

    async def get_partner_configs_by_partner_id(self, partner_id: int):
        try:
            async with self.__session_factory() as session:
                self.__console_service_logger.info(
                    "Validating current user partner id with partner lead source partner id: {}".format(
                        partner_id
                    )
                )

                self.__console_service_logger.info(
                    "getting all partner configs for partner id: {}".format(partner_id)
                )
                query = select(PartnerConfig).filter(
                    PartnerConfig.partner_id == partner_id,
                    PartnerConfig.is_active == True,
                )
                result = await session.execute(query)
                result = result.scalars().all()
                if not result:
                    partner_config_keys: List[str] = [
                        item.value for item in PartnerConfigEnum
                    ]
                    return partner_config_keys
                return result
        except Exception as exec:
            self.__console_service_logger.error(
                "Unexpected error occured while getting all partner configs: {}".format(
                    exec
                )
            )
            raise exec

    async def upsert_partner_config(self, current_user: dict, key: str, value: str):
        """Create or Update partner config key."""

        async with self.__session_factory() as session:
            try:
                current_user_id: int = current_user.get(CurrentUserMap.PARTNER_ID)
                partner_id: int = current_user.get(CurrentUserMap.PARTNER_ID)

                # Check existing
                query = select(PartnerConfig).filter(
                    PartnerConfig.partner_id == partner_id,
                    PartnerConfig.key == key,
                )

                result = await session.execute(query)
                existing = result.scalars().first()

                if existing:
                    # UPDATE
                    existing.value = value
                    existing.updated_by = current_user_id
                    existing.is_active = True 
                else:
                    # CREATE
                    config = PartnerConfig(
                        partner_id=partner_id,
                        key=key,
                        value=value,
                        is_active=True,
                        created_by=current_user_id,
                    )
                    session.add(config)

                await session.commit()
                return True

            except Exception as exc:
                self.__console_service_logger.error(
                    f"Error during upsert_partner_config: {exc}"
                )
                raise exc

    async def has_users_on_partner_roles(self, partner_id: int) -> bool:
        """True if any active user of this partner is assigned to a partner-owned role."""
        async with self.__session_factory() as session:
            result = await session.execute(
                select(func.count())
                .select_from(User)
                .join(Role, Role.id == User.role_id)
                .where(
                    User.partner_id == partner_id,
                    Role.partner_id == partner_id,
                    User.is_active == True,    # noqa: E712
                    User.is_deleted == False,  # noqa: E712
                )
            )
            return (result.scalar() or 0) > 0
            
    async def delete_partner_config_by_key(self, partner_id: int, key: str):
        """Soft delete a partner config by key."""
        try:
            async with self.__session_factory() as session:
                self.__console_service_logger.info(
                    "Soft deleting partner config for partner_id={} and key={}".format(
                        partner_id, key
                    )
                )

                # 1. Look for the active record specifically
                query = select(PartnerConfig).filter(
                    PartnerConfig.partner_id == partner_id,
                    PartnerConfig.key == key,
                    PartnerConfig.is_active == True
                )

                result = await session.execute(query)
                existing = result.scalars().first()

                if existing:
                    # 2. Update the flag instead of session.delete(existing)
                    existing.is_active = False 
                    await session.commit()
                    
                    self.__console_service_logger.info(
                        "Successfully soft deleted partner config for partner_id={} and key={}".format(
                            partner_id, key
                        )
                    )
                else:
                    self.__console_service_logger.warning(
                        "No active partner config found for partner_id={} and key={}".format(
                            partner_id, key
                        )
                    )

        except Exception as exc:
            self.__console_service_logger.error(
                f"Error during delete_partner_config_by_key: {exc}"
            )
            raise exc