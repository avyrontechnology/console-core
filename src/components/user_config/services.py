from uuid import UUID
from typing import List, Optional

from dependency_injector.wiring import Provide
from fastapi import Depends
from sqlalchemy.exc import IntegrityError

from src.components.cache import TTL
from src.components.cache import Keys as CacheKeys
from src.components.cache.helper import CacheHelper
from src.components.audit_log.schema import AuditLogSchema
from src.components.audit_log.services import AuditService
from src.components.common.actions import AuditActions
from src.components.common.resources import Resource
from src.components.common.constants import CurrentUserMap
from src.components.user.errors import UserNotFoundError
from src.components.user.models import User
from src.components.user.services import UserService
from src.components.user_config.constants import UserConfigAttributes, UserConfigEnum
from src.components.user_config.models import UserConfig
from src.components.user_config.repositories import UserConfigRepository
from src.components.user_config.schemas import (
    UpdateUserConfigResponse,
    UserConfigBase,
    UserConfigData,
    UserConfigRequest,
    UserConfigResponse,
)
from src.core.redis import RedisCache
from src.exceptions import UserConfigException  # reuse or define UserConfigException
from src.loggers.console_service_logger import ConsoleServiceLogger
from src.components.partner_config.services import PartnerConfigService
from src.components.session_mangement.services import UserSessionService
from src.components.auth.constant import ServiceNames

class UserConfigService:

    def __init__(
        self,
        user_config_repository: UserConfigRepository,
        console_service_logger: ConsoleServiceLogger,
        console_service_cache: CacheHelper,
        user_repository=None,
        audit_service=None,
    ) -> None:
        self.__user_config_repository = user_config_repository
        self.__console_service_logger = console_service_logger
        self.__console_service_cache = console_service_cache
        self.__user_repository = user_repository
        self.__audit_service = audit_service

    async def __assert_can_grant_super_admin(self, granter_id: UUID) -> None:
        """Only an existing super-admin or the system-admin may grant
        is_super_admin. Fail-closed: anything unreadable denies."""
        try:
            cfg = await self.__user_config_repository.get_user_config_by_key(
                granter_id, UserConfigEnum.IS_SUPER_ADMIN.value
            )
            if cfg is not None and getattr(cfg, "value", False) is True:
                return
        except Exception:
            pass
        try:
            if self.__user_repository is not None:
                sys_admin = await self.__user_repository.get_system_admin_user()
                if sys_admin is not None and granter_id == sys_admin.id:
                    return
        except Exception:
            pass
        self.__console_service_logger.error(
            "Refusing is_super_admin grant by non-privileged user: {}".format(
                granter_id
            )
        )
        raise UserConfigException(
            "Only a super-admin or system-admin can grant super-admin."
        )

    async def __audit_grant(
        self, granter_id: UUID, target_id: UUID, granted: bool
    ) -> None:
        """Persist GRANT/REVOKE audit rows for super-admin changes."""
        if self.__audit_service is None:
            return
        try:
            await self.__audit_service.log_action(
                AuditLogSchema(
                    action=AuditActions.grant if granted else AuditActions.revoke,
                    resource=Resource.user,
                    resource_id=target_id,
                    performed_by=granter_id,
                    details="super-admin {} for user {} by {}".format(
                        "granted to" if granted else "revoked from",
                        target_id,
                        granter_id,
                    ),
                )
            )
        except Exception:
            pass

    async def create_user_config(
        self,
        user_config_data: UserConfigRequest,
        current_user: dict,
        user_service: UserService = Depends(Provide["console_service"]),
    ):
        try:
            self.__console_service_logger.info(
                "Trying to create user config for user id: {}".format(
                    user_config_data.user_id
                )
            )
            user_obj = await user_service.get_user_by_id(user_config_data.user_id)
            if not user_obj:
                self.__console_service_logger.error(
                    "User not found with id: {}".format(user_config_data.user_id)
                )
                raise UserNotFoundError(user_config_data.user_id)

            if user_obj.partner_id != current_user.get(CurrentUserMap.PARTNER_ID):
                self.__console_service_logger.error(
                    "The currnet user's and the provided user's partner id is different."
                )
                raise UserConfigException(
                    "cant create the user config for different partner's user"
                )

            if user_config_data.key == UserConfigEnum.IS_SUPER_ADMIN.value:
                await self.__assert_can_grant_super_admin(
                    current_user.get(CurrentUserMap.USER_ID)
                )

            request_data: UserConfigBase = UserConfigBase(
                user_id=user_config_data.user_id,
                key=user_config_data.key,
                value=user_config_data.value,
            )

            user_config: UserConfig = (
                await self.__user_config_repository.create_user_config(request_data)
            )

            user_config_response: UserConfigResponse = (
                UserConfigResponse.model_validate(user_config.__dict__)
            )

            cache_patterns: list = [
                CacheKeys.ALL_USER_CONFIGS.format(user_config_data.user_id),
                CacheKeys.USER_CONFIG.format(
                    user_config_data.key, user_config_data.user_id
                ),
            ]
            await self.__console_service_cache.clear_pattern(
                prefix=RedisCache.KeysPrefix.CONSOLE,
                pattern=cache_patterns,
            )
            if user_config_data.key == UserConfigEnum.IS_SUPER_ADMIN.value:
                # Super-admin flag changed: drop cached permission list.
                try:
                    await self.__console_service_cache.delete_cache(
                        key=CacheKeys.USER_PERMISSIONS.format(user_config_data.user_id)
                    )
                except Exception:
                    pass
                await self.__audit_grant(
                    granter_id=current_user.get(CurrentUserMap.USER_ID),
                    target_id=user_config_data.user_id,
                    granted=bool(user_config_data.value),
                )

            return user_config_response

        except IntegrityError as exec:
            self.__console_service_logger.error(
                "An integrity error occured: {}".format(exec)
            )
            raise exec
        except UserConfigException as exec:
            self.__console_service_logger.error(
                "User config exception occured: {}".format(exec)
            )
            raise exec
        except UserNotFoundError as exec:
            self.__console_service_logger.error(
                "Not found error occured: {}".format(exec)
            )
            raise exec
        except Exception as exec:
            self.__console_service_logger.error(
                "An unexpected error occured: {}".format(exec)
            )
            raise exec

    async def get_user_config_by_key(
        self, user_id: UUID, key: str
    ) -> UserConfigResponse:
        try:
            self.__console_service_logger.info(
                "Trying to get user config for user id: {}".format(user_id)
            )
            cached_data = await self.__console_service_cache.get_cache(
                key=CacheKeys.USER_CONFIG.format(key, user_id)
            )
            if cached_data:
                self.__console_service_logger.info(
                    "Found cached data of user config for user_id: {}".format(user_id)
                )
                return UserConfigResponse.model_validate(cached_data)

            user_config: UserConfig = (
                await self.__user_config_repository.get_user_config_by_key(user_id, key)
            )

            await self.__console_service_cache.set_cache(
                key=CacheKeys.USER_CONFIG.format(key, user_id),
                value=user_config,
                ttl=TTL.ONE_WEEK,
            )

            return user_config and UserConfigResponse.model_validate(user_config)

        except UserConfigException as exec:
            self.__console_service_logger.error(
                "No user config found for user id: {}".format(user_id)
            )
            raise exec
        except Exception as exec:
            self.__console_service_logger.error(
                "An unexpected error occured while getting user config: {}".format(exec)
            )
            raise exec

    async def update_user_config(
        self,
        partner_id: UUID,
        user_ids: List[UUID],
        update_user_config_data: UserConfigData,
        current_user: dict,
        user_service: UserService = Depends(Provide["console_service"]),
        user_session_service: UserSessionService = Depends(Provide["user_session_service"])
    ) -> List[UpdateUserConfigResponse]:
        try:
            current_user_id: UUID = current_user.get(CurrentUserMap.USER_ID)
            current_user_partner_id: UUID = current_user.get(CurrentUserMap.PARTNER_ID)

            if (
                current_user_partner_id != partner_id
                and not await user_service.is_user_internal(current_user_id)
            ):
                self.__console_service_logger.error(
                    "The currnet user's and the provided partner id is different."
                )
                raise UserConfigException(
                    "cant update the user config for different partner's user"
                )

            self.__console_service_logger.info(
                "getting users by user ids to verify their partner id: {}".format(
                    user_ids
                )
            )
            users: List[User] = await user_service.get_users_by_user_ids(
                partner_id, user_ids
            )
            if len(users) != len(user_ids):
                self.__console_service_logger.error(
                    "One or more user ids are invalid or do not belong to the partner id: {}".format(
                        partner_id
                    )
                )
                raise UserConfigException(UserConfigAttributes.INVALID_USER)

            self.__console_service_logger.info(
                "Trying to update user config for user ids: {}".format(user_ids)
            )
            # validate config input

            await self.validate_config_values(partner_id, update_user_config_data)
            if "is_super_admin" in update_user_config_data.model_dump(
                exclude_unset=True
            ):
                await self.__assert_can_grant_super_admin(current_user_id)
            response_data: List[UserConfig] = (
                await self.__user_config_repository.update_user_config(
                    user_ids, update_user_config_data
                )
            )
            validated_responses: List = [
                UserConfigResponse.model_validate(item) for item in response_data
            ]
            for user_id in user_ids:
                cache_patterns: list = [
                    CacheKeys.ALL_USER_CONFIGS.format(user_id),
                    CacheKeys.USER_CONFIG.format("*", user_id),
                ]
                await self.__console_service_cache.clear_pattern(
                    prefix=RedisCache.KeysPrefix.CONSOLE,
                    pattern=cache_patterns,
                )
                # Super-admin flag may have changed: drop permission cache.
                try:
                    await self.__console_service_cache.delete_cache(
                        key=CacheKeys.USER_PERMISSIONS.format(user_id)
                    )
                except Exception:
                    pass
            if "is_super_admin" in update_user_config_data.model_dump(
                exclude_unset=True
            ) and self.__audit_service is not None:
                try:
                    await self.__audit_service.log_action(
                        AuditLogSchema(
                            action=AuditActions.grant,
                            resource=Resource.user,
                            performed_by=current_user_id,
                            details="super-admin bulk update for users {} by {}".format(
                                [str(u) for u in user_ids], current_user_id
                            ),
                        )
                    )
                except Exception:
                    pass
            services_to_deactivate = self._extract_disabled_services(update_user_config_data)
            if services_to_deactivate:
                await user_session_service.deactivate_user_sessions(
                    user_id=user_ids,
                    service_name=services_to_deactivate,
                )
            self.__console_service_logger.info(
                "Configuration setting update successfully for user ids: {}".format(
                    user_ids
                )
            )
            return validated_responses

        except UserConfigException as exec:
            self.__console_service_logger.error(
                "No user config found for user id: {}".format(user_ids)
            )
            raise exec
        except Exception as exec:
            self.__console_service_logger.error(
                "An unexpected error occured while updating user config: {}".format(
                    exec
                )
            )
            raise exec

    async def get_user_configs_by_user_id(
        self,
        user_id: UUID,
    ) -> List[UserConfigResponse]:
        try:
            self.__console_service_logger.info(
                "Trying to get all user configs for user id: {}".format(user_id)
            )

            REQUIRED_KEYS = [
                UserConfigEnum.IS_SUPER_ADMIN,
                UserConfigEnum.IS_TALKO_ENABLED,
                UserConfigEnum.IS_GSM_CALLING_ENABLED,
                UserConfigEnum.IS_MEETING_LOG_ENABLED,
                UserConfigEnum.CAN_VIEW_CONTACT,
                UserConfigEnum.CAN_VIEW_ORGANIZATION,
                UserConfigEnum.IS_OBOTAAI_ENABLED,
                UserConfigEnum.ENABLE_DIALER,
                UserConfigEnum.CAN_VIEW_PRODUCTS,
                UserConfigEnum.CAN_VIEW_INVENTORY,
                # Notification preferences are included here so the legacy
                # user-config listing stays aligned with the new notification
                # preference API and still surfaces user-level state.
                UserConfigEnum.NOTIFICATION_TALKO,
                UserConfigEnum.NOTIFICATION_WHATSAPP,
                UserConfigEnum.NOTIFICATION_OBOTAAI,
                UserConfigEnum.CAN_VIEW_PAYMENT_HISTORY,
                UserConfigEnum.CAN_VIEW_REPORT_MANAGEMENT,
            ]

            response_data: List[UserConfig] = (
                await self.__user_config_repository.get_user_configs_by_user_id(user_id)
            )

            config_dict: dict = {}
            if response_data and not isinstance(response_data[0], str):
                config_dict = {r.key: r for r in response_data}

            validated_responses: List[UserConfigResponse] = []

            for key in REQUIRED_KEYS:
                key_str = key.value
                if key_str in config_dict:
                    response = config_dict[key_str]
                    validated_responses.append(
                        UserConfigResponse(
                            id=response.id,
                            user_id=response.user_id,
                            key=response.key,
                            value=response.value,
                            history=response.history[-5:] if response.history else None,
                            created_at=response.created_at,
                        )
                    )
                else:
                    validated_responses.append(
                        UserConfigResponse(
                            id=None,
                            user_id=user_id,
                            key=key,
                            value=False,
                            history=None,
                            created_at=None,
                        )
                    )

            self.__console_service_logger.info(
                "Configuration settings fetched successfully for user id: {}".format(user_id)
            )
            return validated_responses

        except UserConfigException as exec:
            self.__console_service_logger.error(
                "No user config is available for user id: {}".format(user_id)
            )
            raise exec
        except Exception as exec:
            self.__console_service_logger.error(
                "An unexpected error occured while getting all user configs: {}".format(exec)
            )
            raise exec

    async def validate_config_values(
        self,
        partner_id: UUID,
        update_user_config_data: UserConfigData,
        partner_config_service: PartnerConfigService = Depends(
            Provide["partner_config_service"]
        ),
    ):
        if update_user_config_data.is_meeting_log_enabled:
            result = await partner_config_service.get_partner_config_by_key(
                partner_id=partner_id, key=UserConfigEnum.IS_MEETING_LOG_ENABLED
            )
            if not result or result.value != True:
                raise UserConfigException(
                    "Meeting Log is not enabled at the partner level."
                )


    def _extract_disabled_services(self, dto: UserConfigData) -> list[str]:
        services = []
        USER_CONFIG_TO_SERVICE = {
            "is_talko_enabled": ServiceNames.TALKO.value,
            "is_obotaai_enabled": ServiceNames.OBOTAAI.value,
        }
        for field, service in USER_CONFIG_TO_SERVICE.items():
            value = getattr(dto, field, None)

            if value is False:
                services.append(service)

        return services
