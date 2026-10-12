from uuid import UUID
from typing import Any, Dict, List, Optional

import httpx
from dependency_injector.wiring import Provide
from fastapi import Depends
from sqlalchemy.exc import IntegrityError

from src.components.auth.repositories import AuthRepository
from src.components.cache import TTL
from src.components.cache import Keys as CacheKeys
from src.components.cache.helper import CacheHelper
from src.components.common.constants import CurrentUserMap
from src.components.entitlement.models import Entitlement
from src.components.entitlement.repositories import EntitlementRepository
from src.components.notifications.services import NotificationRepository
from src.components.partner.models import Partner
from src.components.partner.repositories import PartnerRepository
from src.components.partner_config.constants import (
    PartnerConfigEnum,
    SubscriptionModeEnum,
)
from src.components.partner_config.errors import (
    PartnerConfigKeyError,
    PartnerConfigValidationError,
    PartnerNotFoundError,
)
from src.components.partner_config.models import PartnerConfig
from src.components.partner_config.repositories import PartnerConfigRepository
from src.components.partner_config.schemas import (
    PartnerConfigBase,
    PartnerConfigData,
    PartnerConfigRequest,
    PartnerConfigResponse,
    UpdatePartnerConfigResponse,
)
from src.components.session_mangement.services import UserSessionService
from src.components.user.models import User
from src.components.user.repositories import UserRepository
from src.components.user.services import UserService
from src.components.user_config.constants import UserConfig
from src.components.user_config.repositories import UserConfigRepository
from src.components.wallet.services import WalletService  # noqa: F401 (DI wiring)
from src.core.environment import ENV
from src.core.redis import RedisCache
from src.exceptions import (
    AuthException,
    PartnerActiveSubscriptionException,
    PartnerConfigException,
    TeamException,
)
from src.loggers.console_service_logger import ConsoleServiceLogger


class PartnerConfigService:

    def __init__(
        self,
        partner_config_repository: PartnerConfigRepository,
        console_service_logger: ConsoleServiceLogger,
        console_service_cache: CacheHelper,
    ) -> None:
        self.__partner_config_repository: PartnerConfigRepository = (
            partner_config_repository
        )
        self.__console_service_logger: ConsoleServiceLogger = console_service_logger
        self.__console_service_cache: CacheHelper = console_service_cache

    async def create_partner_config(
        self,
        partner_config_data: PartnerConfigRequest,
        partner_id: UUID,
    ):
        try:

            self.__console_service_logger.info(
                "Trying to create partner config for partner id: {}".format(partner_id)
            )
            request_data: PartnerConfigBase = PartnerConfigBase(
                key=partner_config_data.key,
                value=partner_config_data.value,
            )

            partner_config: PartnerConfig = (
                await self.__partner_config_repository.create_partner_config(
                    request_data, partner_id
                )
            )
            self.__console_service_logger.info(
                "Configuration  created successfully for partner with id: {}".format(
                    partner_id
                )
            )

            partner_config_response: PartnerConfigResponse = (
                PartnerConfigResponse.model_validate(partner_config.__dict__)
            )

            cache_patterns: list = [
                CacheKeys.ALL_PARTNER_CONFIGS.format(partner_id),
                CacheKeys.PARTNER_CONFIG.format(partner_config_data.key, partner_id),
            ]
            await self.__console_service_cache.clear_pattern(
                prefix=RedisCache.KeysPrefix.CONSOLE,
                pattern=cache_patterns,
            )

            return partner_config_response

        except IntegrityError as exec:
            self.__console_service_logger.error(
                "An integrity error occured: {}".format(exec)
            )
            raise exec

        except Exception as exec:
            self.__console_service_logger.error(
                "An unexpected error occured while creating partner config: {}".format(
                    exec
                )
            )
            raise exec

    async def get_partner_config_by_key(
        self, partner_id: UUID | list[UUID], key: str
    ) -> PartnerConfigResponse | list[PartnerConfigResponse] | None:
        try:
            is_single = not isinstance(partner_id, list)

            partner_ids = partner_id if isinstance(partner_id, list) else [partner_id]

            self.__console_service_logger.info(
                "Trying to get partner config for partner id(s): {}".format(partner_ids)
            )

            if is_single:
                cached_data = await self.__console_service_cache.get_cache(
                    key=CacheKeys.PARTNER_CONFIG.format(key, partner_id)
                )
                if cached_data:
                    self.__console_service_logger.info(
                        "Returning cached config for partner_id: {}".format(partner_id)
                    )
                    return PartnerConfigResponse.model_validate(cached_data)

            configs: List[PartnerConfig] = (
                await self.__partner_config_repository.get_partner_config_by_key(
                    partner_ids, key
                )
            )

            response_list = [
                PartnerConfigResponse.model_validate(cfg) for cfg in configs
            ]

            if is_single:
                if response_list:
                    await self.__console_service_cache.set_cache(
                        key=CacheKeys.PARTNER_CONFIG.format(key, partner_id),
                        value=response_list[0],
                        ttl=TTL.ONE_WEEK,
                    )

                    return response_list[0]

                return None

            return response_list

        except PartnerConfigException as exec:
            self.__console_service_logger.error(
                "No partner config found for partner id(s): {}".format(partner_id)
            )
            raise exec

        except Exception as exec:
            self.__console_service_logger.error(
                "Unexpected error occurred while getting partner config: {}".format(
                    exec
                )
            )
            raise exec

    async def update_partner_config(
        self,
        partner_id: UUID,
        update_partner_config_data: PartnerConfigData,
        current_user: dict,
        user_service: UserService = Provide["console_service"],
        user_session_service: UserSessionService = Provide["user_session_service"],
        entitlement_repo: EntitlementRepository = Depends(
            Provide["entitlement_repository"]
        ),
        notification_repo: NotificationRepository = Depends(
            Provide["notification_repository"]
        )
    ) -> List[UpdatePartnerConfigResponse]:
        try:
            current_user_id: UUID = current_user.get(CurrentUserMap.USER_ID)
            current_user_partner_id: UUID = current_user.get(CurrentUserMap.PARTNER_ID)
            if (
                partner_id != current_user_partner_id
                and not await user_service.is_user_internal(current_user_id)
            ):
                raise AuthException(
                    "You are not authorized to update this partner config."
                )
            self.__console_service_logger.info(
                "Fetching partner sources mapped to current user partner id: {}".format(
                    partner_id
                )
            )

            self.__console_service_logger.info(
                "Trying to update partner config for partner id: {}".format(partner_id)
            )

            if update_partner_config_data.is_partner_custom_roles_enabled is False:
                if await self.__partner_config_repository.has_users_on_partner_roles(partner_id):
                    raise TeamException(
                        "Cannot disable custom roles while users are assigned to partner-specific roles. "
                        "Please reassign all users to default (global) roles first."
                    )

            if update_partner_config_data.subscription_mode is not None:
                active_entitlements: List[Entitlement] = (
                    await entitlement_repo.get_all_active_entitlements(partner_id)
                )
                if active_entitlements:
                    raise PartnerActiveSubscriptionException(
                        "subscription_mode cannot be changed while partner {} "
                        "has an active subscription. ".format(partner_id)
                    )
                self.__console_service_logger.info(
                    "subscription_mode update allowed | partner_id={} no active entitlements".format(
                        partner_id
                    )
                )

            await notification_repo.unsubscribe_all_users_from_partner(partner_id=partner_id)

            response_data: List[PartnerConfig] = (
                await self.__partner_config_repository.update_partner_config(
                    partner_id, update_partner_config_data, current_user_id
                )
            )

            # Logout/Expire session of every user for that partner
            await user_session_service.deactivate_all_sessions_by_partner_id(
                partner_id, None
            )

            validated_responses: List = [
                PartnerConfigResponse.model_validate(item) for item in response_data
            ]
            cache_patterns: list = [
                CacheKeys.ALL_PARTNER_CONFIGS.format(partner_id),
                CacheKeys.PARTNER_CONFIG.format("*", partner_id),
            ]
            await self.__console_service_cache.clear_pattern(
                prefix=RedisCache.KeysPrefix.CONSOLE,
                pattern=cache_patterns,
            )
            self.__console_service_logger.info(
                "Configuration setting update successfully for service board with id: {}".format(
                    partner_id
                )
            )
            return validated_responses
        except PartnerConfigException as exec:
            self.__console_service_logger.error(
                "No partner config found for partner id: {}".format(partner_id)
            )
            raise exec
        except AuthException as exec:
            self.__console_service_logger.error(
                "Unauthorized access attempt by user id: {} for partner id: {}".format(
                    current_user.get(CurrentUserMap.USER_ID), partner_id
                )
            )
            raise exec
        except Exception as exec:
            self.__console_service_logger.error(
                "An unexpected error occured while updating partner config: {}".format(
                    exec
                )
            )
            raise exec

    async def get_partner_configs_by_partner_id(
        self,
        partner_id: UUID,
    ) -> List[PartnerConfigResponse]:
        try:
            self.__console_service_logger.info(
                "Trying to get all partner configs for partner id: {}".format(
                    partner_id
                )
            )

            REQUIRED_KEYS = [
                PartnerConfigEnum.IS_CUSTOM_ROLE_PERMISSION_ENABLED,
                PartnerConfigEnum.IS_OTP_ENABLED,
                PartnerConfigEnum.IS_TALKO_ENABLED,
                PartnerConfigEnum.SEND_USER_CREDENTIALS,
                PartnerConfigEnum.IS_EMAIL_VERIFICATION_ENABLED,
                PartnerConfigEnum.IS_PHONE_NUMBER_VERIFICATION_ENABLED,
                PartnerConfigEnum.CAN_CREATE_DEALS,
                PartnerConfigEnum.CAN_ADD_WORKFLOW,
                PartnerConfigEnum.CAN_VIEW_WORKFLOW,
                PartnerConfigEnum.IS_WALLET_ENABLED,
                PartnerConfigEnum.EMAIL_CONFIG_KEY,
                PartnerConfigEnum.SMTP_USERNAME,
                PartnerConfigEnum.SMTP_PASSWORD,
                PartnerConfigEnum.FROM_EMAIL,
                PartnerConfigEnum.IS_MAILER_ENABLED,
                PartnerConfigEnum.IS_GSM_CALLING_ENABLED,
                PartnerConfigEnum.CAN_VIEW_TASK_MANAGEMENT,
                PartnerConfigEnum.IS_MEETING_LOG_ENABLED,
                PartnerConfigEnum.SUBSCRIPTION_MODE,
                PartnerConfigEnum.IS_RULE_BASED_ASSIGNMENT_ENABLED,
                PartnerConfigEnum.CAN_VIEW_PIPELINE_MANAGEMENT,
                PartnerConfigEnum.CAN_VIEW_CONTACT,
                PartnerConfigEnum.CAN_VIEW_ORGANIZATION,
                PartnerConfigEnum.IS_OBOTAAI_ENABLED,
                PartnerConfigEnum.ENABLE_DIALER,
                PartnerConfigEnum.IS_BULK_WORKFLOW_ENABLED,
                PartnerConfigEnum.CAN_VIEW_MVIEW_MANAGEMENT,
                PartnerConfigEnum.IS_ADVANCE_FILTER_ENABLED,
                PartnerConfigEnum.CAN_VIEW_TEMPLATE_MANAGEMENT,
                PartnerConfigEnum.CAN_VIEW_PRODUCT_MANAGEMENT,
                PartnerConfigEnum.CAN_VIEW_FINANCE_MANAGEMENT,
                PartnerConfigEnum.CAN_VIEW_CSF_LEAD_LISTING,
                PartnerConfigEnum.IS_ADD_NUMBER_ENABLED,
                PartnerConfigEnum.CAN_VIEW_PRODUCTS,
                PartnerConfigEnum.CAN_VIEW_INVENTORY,
                PartnerConfigEnum.CAN_VIEW_ORDER_MANAGEMENT,
                PartnerConfigEnum.IS_PARTNER_CUSTOM_ROLES_ENABLED,
                PartnerConfigEnum.IS_USER_TRACKER_ENABLED,
                PartnerConfigEnum.CAN_VIEW_PAYMENT_HISTORY,
                PartnerConfigEnum.IS_REENQUIRY_CHAIN_ENABLED,
                PartnerConfigEnum.CAN_VIEW_REPORT_MANAGEMENT,
                PartnerConfigEnum.CAN_VIEW_HELPDESK_MANAGEMENT,
                PartnerConfigEnum.CAN_DOWNLOAD_CALL_LOGS,
                PartnerConfigEnum.IS_INBOX_ENABLED,
                PartnerConfigEnum.IS_FIELD_TRACKING_ENABLED,
                PartnerConfigEnum.CAN_VIEW_INACTIVE_AGENTS,
                PartnerConfigEnum.IS_AGENT_AVAILABILITY_BASED_ASSIGNMENT_ENABLED,
                PartnerConfigEnum.IS_STICKY_DIDS_ENABLED,
                PartnerConfigEnum.CAN_ADD_ADDRESS_WITH_GOOGLE_PLACES,
                PartnerConfigEnum.IS_ASSIGNEE_SYNC_ENABLED,
            ]

            response_data: List[PartnerConfig] = (
                await self.__partner_config_repository.get_partner_configs_by_partner_id(
                    partner_id
                )
            )

            config_dict: dict = {}
            if response_data and not isinstance(response_data[0], str):
                config_dict = {r.key: r for r in response_data}

            validated_responses: List[PartnerConfigResponse] = []

            for key in REQUIRED_KEYS:
                key_str = key.value
                if key_str in config_dict:
                    response = config_dict[key]
                    validated_responses.append(
                        PartnerConfigResponse(
                            id=response.id,
                            partner_id=response.partner_id,
                            key=response.key,
                            value=response.value,
                            history=response.history[-5:] if response.history else None,
                            created_at=response.created_at,
                        )
                    )
                else:
                    # Default value depends on the key type
                    if key == PartnerConfigEnum.SUBSCRIPTION_MODE:
                        default_value = SubscriptionModeEnum.SELF_SERVED
                    else:
                        default_value = False

                    validated_responses.append(
                        PartnerConfigResponse(
                            id=None,
                            partner_id=partner_id,
                            key=key,
                            value=default_value,
                            history=None,
                            created_at=None,
                        )
                    )
                    
            await self.__console_service_cache.set_cache(
                key=CacheKeys.ALL_PARTNER_CONFIGS.format(partner_id),
                value=validated_responses,
                ttl=TTL.ONE_WEEK,
            )

            self.__console_service_logger.info(
                "Configuration settings fetched successfully for service board with id: {}".format(
                    partner_id
                )
            )
            return validated_responses
        except Exception as exec:
            self.__console_service_logger.error(
                "An unexpected error occured while getting all partner configs: {}".format(
                    exec
                )
            )
            raise exec

    async def custom_role_permission_check(
        self,
        user_id: UUID,
        auth_repo: AuthRepository = Provide["auth_repository"],
        user_service: UserService = Provide["console_service"],
        user_config_repo: UserConfigRepository = Provide["user_config_repository"],
        user_repo: UserRepository = Provide["user_repository"],
    ) -> list[str]:
        try:

            self.__console_service_logger.info("Checking for Super Admin User")

            user_config: UserConfig = await user_config_repo.get_user_config_by_key(
                user_id, "is_super_admin"
            )
            if getattr(user_config, "value", False):
                permissions = await auth_repo.get_all_permission()
                return [permission.slug for permission in permissions]

            # Bypass permissions for system admin
            sys_admin: Optional[User] = await user_repo.get_system_admin_user()
            if sys_admin is not None and user_id == sys_admin.id:
                permissions = await auth_repo.get_all_permission()
                return [permission.slug for permission in permissions]

            self.__console_service_logger.info(
                "Getting user object to get partner id..."
            )
            user: User = await user_service.get_user_by_id(user_id)
            partner_id: UUID = user.partner_id
            self.__console_service_logger.info(
                "checking the custom role permission value for partner id: {}".format(
                    partner_id
                )
            )
            key = PartnerConfigEnum.IS_CUSTOM_ROLE_PERMISSION_ENABLED
            is_custom_role_permission_enabled: PartnerConfigResponse = (
                await self.__partner_config_repository.get_partner_config_by_key(
                    partner_id, key
                )
            )
            default_permission_list: list[str] = (
                await auth_repo.get_default_role_permission_for_user(user_id)
            )
            cfg_list = is_custom_role_permission_enabled

            if isinstance(cfg_list, list):
                cfg = cfg_list[0] if len(cfg_list) > 0 else None
            else:
                cfg = cfg_list

            if cfg and getattr(cfg, "value", False) == True:
                partner_permission_list: list[str] = (
                    await auth_repo.get_user_permission(user_id)
                )
                user_permission_list: list[str] = list(
                    set(partner_permission_list + default_permission_list)
                )

                if user.is_internal:
                    return user_permission_list

                internal_permission_list: list = (
                    await auth_repo.get_internal_permissions()
                )

                return list(set(user_permission_list) - set(internal_permission_list))

            return default_permission_list
        except Exception as exec:
            self.__console_service_logger.error(
                "An unexpected error occured while custom role permission check: {}".format(
                    exec
                )
            )
            raise exec


    async def role_permission_check(
        self,
        role_id: UUID,
        auth_repo: AuthRepository = Provide["auth_repository"],
    ) -> list[str]:
        """Configured permission slugs granted to a specific role (no user).

        The role's default-role permissions, unioned with its partner-custom
        permissions when the role belongs to a partner that has custom-role
        permissions enabled. Powers the ``GetRolePermissions`` RPC / the home
        role-permission-keys view. A system default role (``partner_id`` NULL)
        has only default permissions.
        """
        try:
            role = await auth_repo.get_role_by_id(role_id)

            default_permissions = (
                await auth_repo.get_default_role_permissions_by_role_id(role_id)
            )
            default_permission_list: list[str] = [
                permission.slug for permission in default_permissions
            ]

            partner_id: Optional[UUID] = getattr(role, "partner_id", None)
            if partner_id is None:
                # System default role -> default permissions only.
                return default_permission_list

            key = PartnerConfigEnum.IS_CUSTOM_ROLE_PERMISSION_ENABLED
            cfg_list = (
                await self.__partner_config_repository.get_partner_config_by_key(
                    partner_id, key
                )
            )
            if isinstance(cfg_list, list):
                cfg = cfg_list[0] if len(cfg_list) > 0 else None
            else:
                cfg = cfg_list

            if cfg and getattr(cfg, "value", False) == True:
                partner_permissions = (
                    await auth_repo.get_partner_role_permissions_by_partner_and_role(
                        partner_id, role_id
                    )
                )
                partner_permission_list: list[str] = [
                    permission.slug for permission in partner_permissions
                ]
                return list(set(partner_permission_list + default_permission_list))

            return default_permission_list
        except Exception as exec:
            self.__console_service_logger.error(
                "An unexpected error occurred while role permission check: {}".format(
                    exec
                )
            )
            raise exec

