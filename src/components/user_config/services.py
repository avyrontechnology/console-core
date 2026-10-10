from typing import List, Optional

from dependency_injector.wiring import Provide
from fastapi import Depends
from sqlalchemy.exc import IntegrityError

from src.components.cache import TTL
from src.components.cache import Keys as CacheKeys
from src.components.cache.helper import CacheHelper
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
    ) -> None:
        self.__user_config_repository = user_config_repository
        self.__console_service_logger = console_service_logger
        self.__console_service_cache = console_service_cache

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
        self, user_id: int, key: str
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
        partner_id: int,
        user_ids: List[int],
        update_user_config_data: UserConfigData,
        current_user: dict,
        user_service: UserService = Depends(Provide["console_service"]),
        user_session_service: UserSessionService = Depends(Provide["user_session_service"])
    ) -> List[UpdateUserConfigResponse]:
        try:
            current_user_id: int = current_user.get(CurrentUserMap.USER_ID)
            current_user_partner_id: int = current_user.get(CurrentUserMap.PARTNER_ID)

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

                await self.__console_service_cache.clear_pattern(
                    prefix=RedisCache.KeysPrefix.MAGLO,
                    pattern=CacheKeys.GRPC_GET_USER_DETAILS.format("*", user_id),
                )
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
        user_id: int,
    ) -> List[UserConfigResponse]:
        try:
            self.__console_service_logger.info(
                "Trying to get all user configs for user id: {}".format(user_id)
            )

            REQUIRED_KEYS = [
                UserConfigEnum.IS_SUPER_ADMIN,
                UserConfigEnum.IS_MAGLO_ENABLED,
                UserConfigEnum.IS_BABBLER_ENABLED,
                UserConfigEnum.IS_TALKO_ENABLED,
                UserConfigEnum.IS_MAGLO_APP_ENABLED,
                UserConfigEnum.IS_GSM_CALLING_ENABLED,
                UserConfigEnum.IS_MEETING_LOG_ENABLED,
                UserConfigEnum.CAN_VIEW_CONTACT,
                UserConfigEnum.CAN_VIEW_ORGANIZATION,
                UserConfigEnum.IS_OBOTAAI_ENABLED,
                UserConfigEnum.ENABLE_DIALER,
                UserConfigEnum.IS_BABBLER_APP_ENABLED,
                UserConfigEnum.CAN_VIEW_PRODUCTS,
                UserConfigEnum.CAN_VIEW_INVENTORY,
                # Notification preferences are included here so the legacy
                # user-config listing stays aligned with the new notification
                # preference API and still surfaces user-level state.
                UserConfigEnum.NOTIFICATION_MAGLO,
                UserConfigEnum.NOTIFICATION_MAGLO_LEAD_ASSIGNED,
                UserConfigEnum.NOTIFICATION_MAGLO_BULK_LEAD_ASSIGNED,
                UserConfigEnum.NOTIFICATION_MAGLO_FOLLOWUP,
                UserConfigEnum.NOTIFICATION_MAGLO_APP,
                UserConfigEnum.NOTIFICATION_BABBLER,
                UserConfigEnum.NOTIFICATION_BABBLER_APP,
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

    async def update_is_maglo_app_config(
        self, user_id: int, is_maglo_app_enabled: Optional[bool]
    ) -> UserConfigResponse:
        KEY = "is_maglo_app_enabled"

        try:
            self.__console_service_logger.info(
                f"Trying to update '{KEY}' for user id: {user_id}"
            )

            updated_data = (
                await self.__user_config_repository.update_is_maglo_app_config(
                    user_id=user_id, is_maglo_app_enabled=is_maglo_app_enabled
                )
            )

            # Prepare service-level response
            response = UserConfigResponse(
                id=updated_data.id,
                user_id=updated_data.user_id,
                key=updated_data.key,
                value=updated_data.value,
                history=updated_data.history[-5:] if updated_data.history else None,
                created_at=updated_data.created_at,
            )

            self.__console_service_logger.info(
                f"'{KEY}' updated successfully for user id: {user_id}"
            )

            return response

        except Exception as exec:
            self.__console_service_logger.error(
                f"Unexpected error while updating '{KEY}' for user id {user_id}: {exec}"
            )
            raise exec

    async def validate_config_values(
        self,
        partner_id: int,
        update_user_config_data: UserConfigData,
        partner_config_service: PartnerConfigService = Depends(
            Provide["partner_config_service"]
        ),
    ):
        if update_user_config_data.is_maglo_app_enabled:
            result = await partner_config_service.get_partner_config_by_key(partner_id=partner_id, key="is_maglo_app_enabled")
            if not result or result.value != True:
                raise UserConfigException("Maglo App is not enabled.")
        
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
            "is_maglo_enabled": ServiceNames.MAGLO.value,
            "is_maglo_app_enabled": ServiceNames.MAGLO_APP.value,
            "is_babbler_enabled": ServiceNames.BABBLER.value,
            "is_talko_enabled": ServiceNames.TALKO.value,
            "is_obotaai_enabled": ServiceNames.OBOTAAI.value,
            "is_babbler_app_enabled": ServiceNames.BABBLER_APP.value,
        }
        for field, service in USER_CONFIG_TO_SERVICE.items():
            value = getattr(dto, field, None)

            if value is False:
                services.append(service)

        return services
