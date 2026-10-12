import json
import uuid
from uuid import UUID
from collections import defaultdict
from datetime import timedelta
from typing import Any, Dict, List, Optional, Union

from dependency_injector.wiring import Provide
from fastapi import APIRouter, Depends, Request
from sqlalchemy.exc import IntegrityError

from src.components.audit_log.schema import AuditLogSchema
from src.components.audit_log.services import AuditService
from src.components.auth.constant import (
    AuthExceptionMsg,
    AuthSuccessMsg,
    OtpConstants,
    OtpType,
    PermissionAttributes,
    ServiceNames,
    SignupConfigKeys,
    SvcFlagMap,
    TokenKeys,
    UserHierarchyLevel,
    config_keys,
    ServiceKeys,
)
from src.components.auth.dto import ServiceAccessDTO
from src.components.auth.error import (
    OtpMediumMissing,
    PermissionNotFoundError,
    RoleNotFoundError,
    UserCreatedButEmailFailedError, 
)
from src.components.auth.models import OTP, Permission, Role
from src.components.auth.permission_mapper import PermissionCategories
from src.components.auth.repositories import AuthRepository
from src.components.auth.schema import (
    InternalUserData,
    LoginData,
    OtpValidateRequest,
    PermissionData,
    ResetPasswordRequest,
    RoleData,
    RolePermissionCombined,
    RoleResponse,
    UpdatePermissionResponse,
    UpdatePermissionRquest,
    UpdateRoleRequest,
    UserData,
)
from src.components.auth.util import AuthUtility
from src.components.cache import Keys as CacheKeys
from src.components.cache.helper import CacheHelper
from src.components.common.actions import AuditActions
from src.components.common.constants import CurrentUserMap, UserAttributes
from src.components.common.datetime import DateTimeUtil
from src.components.common.resources import Resource
from src.components.location.errors import (
    CityNotFoundError,
    CountryNotFoundError,
    StateNotFoundError,
)
from src.components.location.services import LocationService
from src.components.partner.error import PartnerNotFoundError
from src.components.partner.models import Partner
from src.components.partner.repositories import PartnerRepository
from src.components.partner.services import PartnerService
from src.components.partner_config.constants import (
    PartnerConfigEnum,
    SubscriptionModeEnum,
)
from src.components.partner_config.schemas import PartnerConfigResponse
from src.components.partner_config.services import PartnerConfigService
from src.components.partner_meta_data.models import PartnerMetaData
from src.components.partner_meta_data.services import PartnerMetaDataServices
from src.components.session_mangement.errors import UserSessionNotFoundError
from src.components.session_mangement.models import UserSession
from src.components.session_mangement.services import UserSessionService
from src.components.user.errors import UserNotFoundError
from src.components.user.models import User
from src.components.user.repositories import UserRepository
from src.components.user.schema import Contrasts
from src.components.user.services import UserService
from src.components.user_config.schemas import UserConfigResponse
from src.components.user_config.services import UserConfigService
from src.core.environment import ENV
from src.core.redis import RedisCache
from src.exceptions import AuthException, PartnerException
from src.loggers.console_service_logger import ConsoleServiceLogger


class AuthService:

    def __init__(
        self,
        auth_repository: AuthRepository,
        auth_service_logger: ConsoleServiceLogger,
        auth_service_cache: CacheHelper,
        auth_service_utility: AuthUtility,
        audit_service: AuditService,
        user_session_service: UserSessionService,
    ) -> None:
        self.__auth_repository: AuthRepository = auth_repository
        self.__auth_service_logger: ConsoleServiceLogger = auth_service_logger
        self.__auth_service_cache: CacheHelper = auth_service_cache
        self.__auth_service_utility: AuthUtility = auth_service_utility
        self.__audit_service: AuditService = audit_service
        self.__user_session_service: UserSessionService = user_session_service
        self.__is_wallet_enabled: bool = True
        self.__is_obotaai_enabled: bool = False

    auth_router = APIRouter()

    async def get_token(
        self,
        request: Request,
        login_data: LoginData = None,
        svc_name: str = "console",
        is_assume_user: bool = False,
        user_id: UUID = None,
        user_config_service: UserConfigService = Depends(
            Provide["user_config_service"]
        ),
        partner_config_service: PartnerConfigService = Depends(
            Provide["partner_config_service"]
        ),
        partner_service: PartnerService = Depends(Provide["partner_service"]),
        partner_meta_data_service: PartnerMetaDataServices = Depends(
            Provide["partner_meta_data_service"]
        ),
    ) -> dict:
        """
        This function create Token for authentication and authorization for user
        and used user_repository class for user data
        """

        try:
            validate_password: bool = not (
                is_assume_user or (login_data and login_data.is_verify)
            )

            user: User = await self._get_user(
                login_data=login_data,
                is_assume_user=is_assume_user,
                user_id=user_id,
                validate_password=validate_password,
            )
            self.__auth_service_logger.info(
                "Verifying if partner is active or not id: {}".format(user.partner_id)
            )
            await partner_service.get_partner_by_id(user.partner_id)
            user_config = await user_config_service.get_user_configs_by_user_id(user.id)
            config_map: dict[str, bool] = self.__extract_config_flags(
                user_config, config_keys
            )
            trial_expiry = None

            partner_config: List[PartnerConfigResponse] = await partner_config_service.get_partner_configs_by_partner_id(user.partner_id)
            partner_config_map = self._get_partner_config_map(partner_config)

            service_access_dto = ServiceAccessDTO(
                user=user,
                svc_name=svc_name,
                config_map=config_map,
                partner_config_map=partner_config_map,
                is_assume_user=is_assume_user,
                trial_expiry=trial_expiry,
            )


            # validate the service access and update the DTO
            await self.validate_service_access(
                service_access_dto,
                partner_config_service=partner_config_service,
                partner_meta_data_service=partner_meta_data_service,
                user_config_service=user_config_service,
            )

            if not is_assume_user:
                is_otp_enabled: PartnerConfigResponse = (
                    await partner_config_service.get_partner_config_by_key(
                        partner_id=user.partner_id,
                        key=PartnerConfigEnum.IS_OTP_ENABLED.value,
                    )
                )
                requires_otp = (
                    login_data.is_verify  # always true for verification flows
                    or (is_otp_enabled and is_otp_enabled.value and not is_assume_user)
                )

                if requires_otp:
                    if not (login_data.send_mail_otp or login_data.send_whatsapp_otp):
                        raise OtpMediumMissing("OTP Medium is missing")

                    otp_type: str = (
                        (
                            OtpType.EMAIL.value
                            if login_data.send_mail_otp
                            else OtpType.PHONE_NUMBER.value
                        )
                        if login_data.is_verify
                        else OtpType.LOGIN.value
                    )

                    additional_info = {
                        "service_name": svc_name,
                        "trial_expiry": trial_expiry,
                    }

                    otp_entry: OTP = await self.__auth_repository.create_otp(
                        user_id=user.id,
                        otp_type=otp_type,
                        additional_info=additional_info,
                    )

                    if login_data.send_mail_otp:
                        await self.__send_email_otp(user.email, otp_entry.otp)
                    if login_data.send_whatsapp_otp:
                        # Retired channel removed — fail closed (never claim sent without sending)
                        # (never claim "OTP sent" without sending).
                        raise OtpMediumMissing(
                            "WhatsApp OTP is unavailable (channel removed)"
                        )

                    self.__auth_service_logger.info(
                        f"OTP generated and sent for user {user.email} (id={user.id})"
                    )
                    return {"message": "OTP sent successfully"}

            partner_config: PartnerConfigResponse = (
                await partner_config_service.get_partner_config_by_key(
                    partner_id=user.partner_id,
                    key=PartnerConfigEnum.IS_WALLET_ENABLED.value,
                )
            )

            obotaai_config: PartnerConfigResponse = (
                await partner_config_service.get_partner_config_by_key(
                    partner_id=user.partner_id,
                    key=PartnerConfigEnum.IS_OBOTAAI_ENABLED.value,
                )
            )

            subscription_mode: PartnerConfigResponse = (
                await partner_config_service.get_partner_config_by_key(
                    partner_id=user.partner_id,
                    key=PartnerConfigEnum.SUBSCRIPTION_MODE.value,
                )
            )
            self.__is_wallet_enabled = partner_config.value if partner_config else True
            self.__is_obotaai_enabled = obotaai_config.value if obotaai_config else False

            await self.resolve_user_walkthrough_key(user.id, user.partner_id)

            return await self.__create_session_and_token(
                request,
                user,
                config_map,
                svc_name,
                service_access_dto.trial_expiry,
                subscription_mode,
                partner_config_map,
            )

        except UserNotFoundError as exc:
            self.__auth_service_logger.error(
                "User not found error occurred while creating token: {}".format(exc)
            )
            raise exc
        except PartnerException as exec:
            self.__auth_service_logger.error(
                "Can't log in as the partner is deactivated."
            )
            raise AuthException(AuthExceptionMsg.RESTRICT_LOGIN)
        except AuthException as ex:
            self.__auth_service_logger.error("Unexpected error: {}".format(str(ex)))
            raise ex
        except OtpMediumMissing as exc:
            self.__auth_service_logger.error(
                f"OTP medium missing while logging out. Error: {exc}"
            )
            raise exc
        except Exception as ex:
            self.__auth_service_logger.error("Unexpected error: {}".format(str(ex)))
            raise ex

    async def logout(self, token: str) -> bool:
        try:
            is_token_expired: bool = False
            self.__auth_service_logger.debug(f"Logging out with token: {token}")
            payload: dict = self.__auth_service_utility.decode_access_token(token)
            if not payload:
                is_token_expired = True
                # need to decode token get session id without verifying expiration
                payload: dict = (
                    self.__auth_service_utility.decode_access_token_without_exp(token)
                )
                if not payload:
                    raise AuthException(AuthExceptionMsg.UNSUCCESSFULL_LOGOUT)

            self.__auth_service_logger.info(
                f"Access token decoded sucessfully & Got the payload: {payload}"
            )
            user_session_id = payload.get("user_session_id")
            partner_id: UUID = payload.get("partner_id")

            # Invalidating  cache for user's issued token
            self.__auth_service_logger.debug(
                f"Invalidating cache during user logout with token: {token}"
            )
            if not await self.__auth_service_cache.delete_cache(
                CacheKeys.TOKEN.format(partner_id, token)
            ):
                self.__auth_service_logger.info(
                    f"Cache Miss.. could not find any cache with key: {token}"
                )
            else:
                self.__auth_service_logger.debug(
                    f"Successfully Invalidated the cache with key: {token}"
                )

            # deactivating session for user
            self.__auth_service_logger.debug(
                f"Deactivating the user session with ID: {user_session_id}"
            )
            user_session: UserSession = (
                await self.__user_session_service.get_user_session(user_session_id)
            )
            if user_session.is_active:
                updated_user_session: UserSession = (
                    await self.__user_session_service.update_user_session(
                        user_session_id, {"is_active": False}
                    )
                )

                if updated_user_session:
                    self.__auth_service_logger.info(
                        f"Sucessfully deactivated the session ID: {user_session_id} Updated Session status: {updated_user_session.is_active}"
                    )
                else:
                    raise AuthException(AuthExceptionMsg.SESSION_NOT_FOUND)

                self.__auth_service_logger.info(
                    f"User successfully logged out with session_id: {user_session_id}"
                )
            else:
                is_token_expired = True
            return is_token_expired

        except UserSessionNotFoundError:
            raise AuthException(AuthExceptionMsg.SESSION_NOT_FOUND)
        except Exception as exc:
            self.__auth_service_logger.error(
                f"Got an unexpeced error while logging out Error: {exc}"
            )
            raise exc

    async def sing_up(
        self,
        user_data: UserData,
        services: Optional[SignupConfigKeys] = None,
        user_repository: UserRepository = Depends(Provide["user_repository"]),
        partner_repository: PartnerRepository = Depends(Provide["partner_repository"]),
        location_service: LocationService = Depends(Provide["location_service"]),
        partner_config_service: PartnerConfigService = Depends(
            Provide["partner_config_service"]
        ),
    ):
        try:
            self.__auth_service_logger.info("Attempting to create new user")
            partner_object: Partner = await partner_repository.get_by_id(
                user_data.partner_id
            )
            user_data_extended: dict = user_data.model_dump()
            user_data_extended["is_internal"] = partner_object.is_internal

            # Validate against the internal schema
            user_data: InternalUserData = InternalUserData.model_validate(
                user_data_extended
            )

            if user_data.country_id or user_data.state_id or user_data.city_id:
                await location_service.validate_location_hierarchy(
                    user_data.country_id,
                    user_data.state_id,
                    user_data.city_id,
                )

            # Extract and validate user data
            phone_number = user_data.phone_number
            name = user_data.name
            password: str = user_data.password
            user_data.password = await self.__auth_service_utility.get_password_hash(
                user_data.password
            )  # convert plainpassword to hash password
            email = user_data.email
            partner_id = user_data.partner_id
            role_id = user_data.role_id
            parent_id = user_data.parent_id

            # Prefer partner-owned copy of role when catalog is materialized
            if role_id:
                custom_roles_cfg = await partner_config_service.get_partner_config_by_key(
                    partner_id, PartnerConfigEnum.IS_PARTNER_CUSTOM_ROLES_ENABLED.value
                )
                if custom_roles_cfg and custom_roles_cfg.value == True:
                    role_id = await self.__auth_repository.resolve_role_for_partner(
                        role_id, partner_id
                    )
                    user_data.role_id = role_id

            if parent_id in (0, "0", "", None):
                parent_id = None
                user_data.parent_id = None
            self.__auth_service_logger.info(
                "Extracted user data: name={}, email={}, phone_number={}, name={}".format(
                    name, email, phone_number, name
                )
            )

            # check partner and role are present
            if partner_id or role_id:
                partner = await partner_repository.get_by_id(partner_id)
                user_role = await self.__auth_repository.get_role_by_id(role_id)

                # check for admin exist for partner
                if (
                    user_role.hierarchy == UserHierarchyLevel.ADMIN_LEVEL_HIERARCHY
                    and (
                        await user_repository.is_admin_exists(partner_id, user_role.id)
                    )
                ):
                    raise AuthException(AuthExceptionMsg.ADMIN_EXIST)

                partner_limit = await user_repository.partner_user_limit(partner_id)
                if partner_limit >= partner.active_license:
                    raise AuthException(
                        AuthExceptionMsg.PARTNER_LIMIT.format(partner.active_license)
                    )

            # check parent role hierarchy is must less than current user role hierarchy
            if parent_id:
                parent_role = await user_repository.get_user_with_role(parent_id)

                if not partner_object.is_internal and user_role.hierarchy <= parent_role.hierarchy:
                    raise AuthException(AuthExceptionMsg.PARENT_VALIDATION)

                if partner_object.is_internal and user_role.hierarchy >= parent_role.hierarchy:
                    raise AuthException(AuthExceptionMsg.PARENT_VALIDATION)
  
            user = await user_repository.add_user(
                user_data=user_data, services=services
            )

            # Log the successful creation of the user
            self.__auth_service_logger.info(
                "User created successfully: {}".format(user)
            )

            send_user_credentials: PartnerConfigResponse = (
                await partner_config_service.get_partner_config_by_key(
                    partner_id=user.partner_id,
                    key=PartnerConfigEnum.SEND_USER_CREDENTIALS.value,
                )
            )
            if send_user_credentials and send_user_credentials.value:
                raise UserCreatedButEmailFailedError(
                    "User created but credentials email unavailable (mailer removed)"
                )

            log_entry = AuditLogSchema(
                action=AuditActions.create,
                resource=Resource.user,
                resource_id=user.id,
                resource_previous_state=None,
                resource_current_state=str(user_data),
                performed_by=user.id,
                details="User created with id :{}".format(user.id),
            )
            await self.__audit_service.log_action(log_entry)

            return user

        except CountryNotFoundError as exec:
            self.__auth_service_logger.error(
                "Country not find while create user: {}".format(str(exec))
            )
            raise exec
        except StateNotFoundError as exec:
            self.__auth_service_logger.error(
                "State not find while create user: {}".format(str(exec))
            )
            raise exec
        except CityNotFoundError as exec:
            self.__auth_service_logger.error(
                "City not find while create user: {}".format(str(exec))
            )
            raise exec
        except UserNotFoundError as ex:
            self.__auth_service_logger.error(
                "Parent not find while create user: {}".format(str(ex))
            )
            raise AuthException("Parent not found")
        except PartnerNotFoundError as ex:
            self.__auth_service_logger.error(
                "Partner not find while create user: {}".format(str(ex))
            )
            raise AuthException(ex)
        except RoleNotFoundError as ex:
            self.__auth_service_logger.error(
                "Role not find while create user: {}".format(str(ex))
            )
            raise AuthException(ex)
        except IntegrityError as err:
            if UserAttributes.EMAIL in str(err.orig):
                self.__auth_service_logger.error(
                    "{} : {}".format(AuthExceptionMsg.EMAIL_EXIST, email)
                )
                raise AuthException("{}".format(AuthExceptionMsg.EMAIL_EXIST))
            elif UserAttributes.PHONE_NUMBER in str(err.orig):
                self.__auth_service_logger.error(
                    "{} : {}".format(AuthExceptionMsg.PHONE_NUMBER_EXIST, phone_number)
                )
                raise AuthException("{}".format(AuthExceptionMsg.PHONE_NUMBER_EXIST))
            else:
                self.__auth_service_logger.error("Integrity error: {}".format(str(err)))
                raise AuthException(str(err))
        except Exception as ex:
            self.__auth_service_logger.error(
                "Failed to create user: {}".format(repr(ex))
            )
            raise ex

    async def add_role(
        self,
        role_data: RoleData,
        current_user: dict,
    ) -> Role:
        try:
            self.__auth_service_logger.info("Attempting to create new role")
            user_id: UUID = current_user.get(CurrentUserMap.USER_ID)
            role = await self.__auth_repository.add_role(role_data, user_id)
            log_entry = AuditLogSchema(
                action=AuditActions.create,
                resource=Resource.role,
                resource_id=role.id,
                resource_previous_state=None,
                resource_current_state=str(role_data),
                performed_by=user_id,
                details="Role created successfully with role id {}".format(role.id),
            )
            await self.__audit_service.log_action(log_entry)
            return role
        except AuthException as ex:
            self.__auth_service_logger.error(
                "Integrity error during role creation: ".format(repr(ex))
            )
            raise ex
        except Exception as ex:
            self.__auth_service_logger.error(
                "Failed to create role: {}".format(repr(ex))
            )
            raise ex

    async def get_all_role(
        self,
        partner_id: UUID,
        partner_service: PartnerService = Depends(Provide["partner_service"]),
        partner_config_service: PartnerConfigService = Depends(
            Provide["partner_config_service"]
        ),
    ) -> List[Role]:
        try:
            self.__auth_service_logger.info("Checking if partner is internal or not...")
            partner_object: Partner = await partner_service.get_partner_by_id(
                partner_id
            )
            is_internal_partner: bool = False
            if partner_object.is_internal:
                is_internal_partner: bool = True

            custom_roles_cfg = await partner_config_service.get_partner_config_by_key(
                partner_id, PartnerConfigEnum.IS_PARTNER_CUSTOM_ROLES_ENABLED.value
            )
            filter_partner_id: Optional[UUID] = (
                partner_id if (custom_roles_cfg and custom_roles_cfg.value == True) else None
            )

            self.__auth_service_logger.info("Attempting to getting all roles")
            return await self.__auth_repository.get_all_role(
                is_internal_partner, filter_partner_id
            )
        except Exception as ex:
            self.__auth_service_logger.error(
                "Unexpected error during getting roles: {}".format(repr(ex))
            )
            raise ex

    async def get_role_by_id(self, id: UUID) -> Role:
        try:
            self.__auth_service_logger.info("Attempting to get role{}".format(id))
            return await self.__auth_repository.get_role_by_id(id)
        except RoleNotFoundError as ex:
            self.__auth_service_logger.error(
                "Unexpected error during get role by id: {}".format(str(ex))
            )
            raise AuthException(str(ex))
        except Exception as ex:
            self.__auth_service_logger.error(
                "Unexpected error during get role: {}".format(str(ex))
            )
            raise ex

    async def delete_role(
        self,
        id: UUID,
        current_user: dict,
    ) -> Role:
        try:
            self.__auth_service_logger.info("Attempting to delete role{}".format(id))
            user_id: UUID = current_user.get(CurrentUserMap.USER_ID)
            deleted_roles = await self.__auth_repository.delete_role(id, user_id)
            log_entry = AuditLogSchema(
                action=AuditActions.delete,
                resource=Resource.role,
                resource_id=id,
                resource_previous_state=None,
                resource_current_state=None,
                performed_by=user_id,
                details="Role with role id: {} is deleted successfully".format(id),
            )
            await self.__audit_service.log_action(log_entry)

            return deleted_roles
        except RoleNotFoundError as ex:
            self.__auth_service_logger.error(
                "Unexpected error during delete role by id: {}".format(str(ex))
            )
            raise AuthException(str(ex))
        except Exception as ex:
            self.__auth_service_logger.error(
                "Unexpected error during delete role: {}", format(repr(ex))
            )
            raise ex

    async def create_permission(
        self, user_permission: PermissionData, current_user: dict
    ) -> Permission:
        try:
            self.__auth_service_logger.info(
                "Attempting to create permission: {}".format(user_permission.title)
            )
            user_id: UUID = current_user.get(CurrentUserMap.USER_ID)
            permission = await self.__auth_repository.add_permission(
                user_permission, user_id
            )
            log_entry = AuditLogSchema(
                action=AuditActions.create,
                resource=Resource.permission,
                resource_id=permission.id,
                resource_previous_state=None,
                resource_current_state=str(user_permission),
                performed_by=user_id,
                details="Permission with permission id: {} is created successfully".format(
                    permission.id
                ),
            )
            await self.__audit_service.log_action(log_entry)
            return permission
        except AuthException as ex:
            self.__auth_service_logger.error(
                "Integrity error during permission creation: ".format(repr(ex))
            )
            raise AuthException(str(ex))
        except Exception as ex:
            self.__auth_service_logger.error(
                "Failed to create permission: {}".format(repr(ex))
            )
            raise ex

    async def get_all_permission(
        self,
    ) -> List[Permission]:
        try:
            self.__auth_service_logger.info("Attempting to getting all permissions")
            return await self.__auth_repository.get_all_permission()
        except Exception as ex:
            self.__auth_service_logger.error(
                "Unexpected error during getting permission: {}".format(repr(ex))
            )
            raise ex

    async def get_permission_by_id(
        self,
        id: UUID,
    ):
        try:
            self.__auth_service_logger.info(
                "Attempting to get permission {}".format(id)
            )
            return await self.__auth_repository.get_permission_by_id(id)
        except PermissionNotFoundError as ex:
            self.__auth_service_logger.error(
                "Unexpected error during get permission: {}".format(repr(ex))
            )
            raise AuthException(str(ex))
        except Exception as ex:
            self.__auth_service_logger.error(
                "Unexpected error during get permission: {}".format(repr(ex))
            )
            raise ex

    async def delete_permission(
        self,
        id: UUID,
        current_user: dict,
    ) -> Permission:
        try:
            self.__auth_service_logger.info(
                "Attempting to delete permission {}".format(id)
            )
            user_id: UUID = current_user.get(CurrentUserMap.USER_ID)
            deleted_permission = await self.__auth_repository.delete_permission(
                id, user_id
            )
            log_entry = AuditLogSchema(
                action=AuditActions.delete,
                resource=Resource.permission,
                resource_id=id,
                resource_previous_state=None,
                resource_current_state=None,
                performed_by=user_id,
                details="Permission with permission id: {} is deleted successfully".format(
                    id
                ),
            )
            await self.__audit_service.log_action(log_entry)
            # A deleted permission drops out of every user's resolved RBAC set,
            # which downstream caches per user (GRPC_GET_USER_PERMISSIONS, ONE_WEEK).
            return deleted_permission

        except PermissionNotFoundError as ex:
            self.__auth_service_logger.error(
                "Unexpected error during delete permission: {}".format(repr(ex))
            )
            raise AuthException(str(ex))
        except Exception as ex:
            self.__auth_service_logger.error(
                "Unexpected error during delete permission: {}".format(repr(ex))
            )
            raise ex

    async def get_user_permission(
        self,
        user_id: UUID,
    ) -> List[str]:
        try:
            self.__auth_service_logger.info(
                "Attempting to get permissions for user {}".format(user_id)
            )
            user_permissions = await self.__auth_repository.get_user_permission(user_id)
            return user_permissions
        except Exception as ex:
            self.__auth_service_logger.error(f"Unexpected error: {str(ex)}")
            raise ex

    async def get_role_by_user_id(
        self,
        user_id: UUID,
    ) -> dict:
        try:
            self.__auth_service_logger.info(
                "Attempting to get role for user {}".format(user_id)
            )
            user_role = await self.__auth_repository.get_role_by_user_id(user_id)
            return user_role
        except Exception as ex:
            self.__auth_service_logger.error(f"Unexpected error: {str(ex)}")
            raise ex

    async def reset_password(
        self,
        current_user: dict,
        reset_password_request: ResetPasswordRequest,
        user_service: UserService = Depends(Provide["console_service"]),
        user_session_service: UserSessionService = Depends(
            Provide["user_session_service"]
        ),
    ) -> str:
        try:
            self.__auth_service_logger.info(
                "Attempting to reset password for user: {}".format(
                    reset_password_request.email
                )
            )
            user: User = await user_service.get_user_by_field(
                field_name=CurrentUserMap.EMAIL, value=reset_password_request.email
            )
            if not user or not user.is_active:
                self.__auth_service_logger.warning(
                    "User not found {}".format(reset_password_request.email)
                )
                raise AuthException(AuthExceptionMsg.USER_NOT_FOUND)

            # get current user details
            current_user_id: UUID = current_user.get(CurrentUserMap.USER_ID)
            user_details: dict = await user_service.get_user_details(current_user_id)
            current_user_partner_id: UUID = user_details.get(CurrentUserMap.PARTNER_ID)
            current_user_role_hierarchy: int = user_details.get(
                CurrentUserMap.ROLE_HIERARCHY_LEVEL
            )
            if current_user_role_hierarchy >= CurrentUserMap.ADMIN_ROLE_HIERARCHY_LEVEL:
                current_user_email: int = user_details.get(CurrentUserMap.EMAIL)
                if user.partner_id != current_user_partner_id or (
                    current_user_role_hierarchy
                    > CurrentUserMap.MAINTAINER_ROLE_HIERARCHY_LEVEL
                    and user.email != current_user_email
                ):
                    raise AuthException(AuthExceptionMsg.USER_NOT_FOUND)

                if (
                    current_user_role_hierarchy
                    > CurrentUserMap.MAINTAINER_ROLE_HIERARCHY_LEVEL
                    and not reset_password_request.current_password
                ):
                    raise AuthException(AuthExceptionMsg.PASSWORD_REQUIRED)

                # if current user not a admin so verify current password
                if (
                    current_user_role_hierarchy
                    > CurrentUserMap.MAINTAINER_ROLE_HIERARCHY_LEVEL
                    and not await self.__auth_service_utility.verify_password(
                        reset_password_request.current_password, user.hashed_password
                    )
                ):
                    raise AuthException(AuthExceptionMsg.INCORRECT_PWD)
            if await self.__auth_service_utility.verify_password(
                reset_password_request.new_password, user.hashed_password
            ):
                self.__auth_service_logger.warning(
                    "New password cannot be the same as the existing password"
                )
                raise AuthException(AuthExceptionMsg.EXISTING_PASSWORD_WARNING)
            hashed_password = await self.__auth_service_utility.get_password_hash(
                reset_password_request.new_password
            )
            await self.__auth_repository.reset_password(hashed_password, user)
            await user_session_service.deactivate_user_sessions(user.id)
            return AuthSuccessMsg.PASSWORD_RESET_SUCCESSFULLY
        except Exception as exc:
            self.__auth_service_logger.error(
                "Unexpected error occurred while reset password: {}".format(str(exc))
            )
            raise exc

    async def get_parent_users_by_role_id(
        self, role_id: UUID, partner_id: UUID
    ) -> list[Contrasts.ParentUserResponse]:
        try:
            self.__auth_service_logger.info(
                "Attempting to get parents by role id: {}".format(role_id)
            )
            parents: list[User] = (
                await self.__auth_repository.get_parent_users_by_role_id(
                    role_id, partner_id
                )
            )
            parent_response: list[Contrasts.ParentUserResponse] = [
                Contrasts.ParentUserResponse.model_validate(parent)
                for parent in parents
            ]
            return parent_response
        except RoleNotFoundError as exec:
            self.__auth_service_logger.error("Role not found: {}".format(str(exec)))
            raise exec
        except Exception as exec:
            self.__auth_service_logger.error(
                "An unexpected error: {}".format(str(exec))
            )
            raise exec

    async def get_role_permissions_matrix(
        self,
        user_id: UUID,
        is_internal_permission: Optional[bool],
        filter_partner_id: Optional[UUID] = None,
        user_service: UserService = Depends(Provide["console_service"]),
    ) -> dict:
        try:
            self.__auth_service_logger.info("Fetching role permissions matrix")
            if is_internal_permission and not await user_service.is_user_internal(
                user_id
            ):
                self.__auth_service_logger.error(
                    "Only internal user can see the internal permissions"
                )
                raise AuthException("Current user can't view internal permissions.")

            permission_data: list[RolePermissionCombined] = (
                await self.__auth_repository.get_default_role_permission_matrix(
                    is_internal_permission, filter_partner_id=filter_partner_id
                )
            )

            default_response = defaultdict(lambda: defaultdict(dict))

            for item in permission_data:
                base_permission = {
                    PermissionAttributes.CREATED_AT: item.created_at,
                    PermissionAttributes.DESCRIPTION: item.description,
                    PermissionAttributes.DISPLAY_TEXT: item.display_text,
                    PermissionAttributes.ID: item.permission_id,
                }

                default_response[item.role_name][item.category][item.slug] = {
                    **base_permission,
                    PermissionAttributes.IS_ACTIVE: item.is_default,
                }

            return {
                PermissionAttributes.DEFAULT_ROLE_PERMISSION: default_response,
            }

        except Exception as exec:
            self.__auth_service_logger.error(
                "Unexpected error in get_role_permissions_matrix: {}".format(exec)
            )
            raise exec

    async def update_permission(
        self, permission_id: UUID, permission_data: UpdatePermissionRquest
    ):
        try:
            self.__auth_service_logger.info(
                "Attempting to update permission with id: {}".format(permission_id)
            )
            updated_permission = await self.__auth_repository.update_permission(
                permission_id, permission_data
            )
            self.__auth_service_logger.info(
                "Permission with id: {} updated successfully".format(permission_id)
            )
            response = UpdatePermissionResponse.model_validate(updated_permission)
            # Editing a permission (e.g. its slug) changes the strings downstream
            # per-user RBAC set resolves to (GRPC_GET_USER_PERMISSIONS, ONE_WEEK).
            return response
        except PermissionNotFoundError as exec:
            self.__auth_service_logger.error(
                "Permission not found during updating permission: {}".format(repr(exec))
            )
            raise exec
        except AuthException as exec:
            self.__auth_service_logger.error(
                "Auth error during updating permission: {}".format(repr(exec))
            )
            raise exec
        except Exception as exec:
            self.__auth_service_logger.error(
                "Unexpected error during updating permission: {}".format(repr(exec))
            )
            raise exec

    async def assume_user(
        self,
        request: Request,
        user_id: UUID,
        svc_name: str = "console",
        console_service: UserService = Depends(Provide["console_service"]),
        partner_config_service: PartnerConfigService = Depends(
            Provide["partner_config_service"]
        ),
        user_config_service: UserConfigService = Depends(  
           Provide["user_config_service"]
        ),
    ) -> dict:
        try:
            current_user: dict = request.state.user
            current_user_id = current_user.get(CurrentUserMap.USER_ID)

            self.__auth_service_logger.info(
                f"Attempting to assume user: {user_id} by {current_user_id} for service: {svc_name}"
            )
            # Get user
            user = await console_service.get_user_by_id(user_id)
           
            # Extract partner_id
            partner_id: Optional[UUID] = getattr(user, "partner_id", None)
            if not partner_id:
                raise AuthException("Partner ID not found for user")

            # Fetch partner config
            partner_config = await partner_config_service.get_partner_configs_by_partner_id(
                partner_id
            )
            if not partner_config:
                raise AuthException(
                        f"Partner config not found for partner_id: {partner_id}"
                )
            
            # Convert partner_config list → dict
            services = {}

            for config in partner_config:
                if config.key.startswith("is_") and config.key.endswith("_enabled"):
                    service_name = config.key.replace("is_", "").replace("_enabled", "")
                    services[service_name] = config.value
            
            user_config = await user_config_service.get_user_configs_by_user_id(user_id)
            
            if not user_config:
                raise AuthException(
                    f"User config not found for user_id: {user_id}"
                )
            user_services = {}
            
            for config in user_config:
                if config.key.startswith("is_") and config.key.endswith("_enabled"):
                    service_name = config.key.replace("is_", "").replace("_enabled", "")
                    user_services[service_name] = config.value
            
            # -------------------------------
            # FINAL VALIDATION 
            # -------------------------------
            partner_enabled = services.get(svc_name)
            user_enabled = user_services.get(svc_name)

            # service not found
            if partner_enabled is None or user_enabled is None:
                self.__auth_service_logger.error(
                   f"Service {svc_name} not configured in partner/user config for user_id: {user_id}"
                )
                raise AuthException(f"Invalid service name: {svc_name}")

            # partner check
            if not partner_enabled:
                self.__auth_service_logger.error(
                    f"Service {svc_name} is disabled for partner_id: {partner_id}"
                )
                raise AuthException(
                    f"{svc_name} service is disabled for this partner"
                )

            # user check
            if not user_enabled:
                self.__auth_service_logger.error(
                    f"Service {svc_name} is disabled for user_id: {user_id}"
                )
                raise AuthException(
                    f"{svc_name} service is disabled for this user"
                )
              
            token: dict = await self.get_token(
                request=request,
                is_assume_user=True,
                user_id=user_id,
                svc_name=svc_name,   
            )

            return token

        except UserNotFoundError as exc:
            self.__auth_service_logger.error(
               f"User not found while assuming user: {user_id}, error: {str(exc)}"
            )
            raise exc


        except PartnerException:
            self.__auth_service_logger.error(
                "Can't log in as the partner is deactivated."
            )
            raise AuthException(AuthExceptionMsg.RESTRICT_LOGIN)

        except Exception as exc:
            self.__auth_service_logger.error(
                f"Unexpected error while assuming user: {user_id}, error: {str(exc)}"
            )
            raise exc


    async def _get_user(
        self,
        login_data,
        is_assume_user,
        user_id,
        validate_password: Optional[bool] = True,
        user_service: UserService = Depends(Provide["console_service"]),
    ):
        if not is_assume_user:
            if login_data.email:
                field_name, value = UserAttributes.EMAIL, login_data.email
            elif login_data.phone_number:
                field_name, value = UserAttributes.PHONE_NUMBER, login_data.phone_number
            else:
                raise ValueError("Either email or phone_number must be provided")
            self.__auth_service_logger.info(f"Fetching user by {field_name}: {value}")
            user = await user_service.get_user_by_field(field_name, value)

            if not user:
                self.__auth_service_logger.warning(f"User not found: {value}")
                raise AuthException(AuthExceptionMsg.USER_NOT_FOUND)

            if validate_password:
                self.__auth_service_logger.info(f"Verifying password for {value}")
                if not await self.__auth_service_utility.verify_password(
                    login_data.password, user.hashed_password
                ):
                    self.__auth_service_logger.warning("Incorrect password")
                    raise AuthException(AuthExceptionMsg.INCORRECT_PWD)

        else:
            self.__auth_service_logger.info(f"Assuming user by ID: {user_id}")
            user = await user_service.get_user_by_id(user_id)
            if user.is_internal:
                self.__auth_service_logger.warning("Cannot assume internal user")
                raise UserNotFoundError(user_id)

        return user

    def get_categories(self) -> dict[str, list[str]]:
        try:
            self.__auth_service_logger.info("getting categories name...")
            console_categories: list[str] = list(
                PermissionCategories.CONSOLE_PERMISSIONS.keys()
            )
            talko_categories: list[str] = list(
                PermissionCategories.TALKO_PERMISSIONS.keys()
            )
            response = {
                "console": console_categories,
                "talko": talko_categories,
            }
            self.__auth_service_logger.info("Fetched all the categories ")
            return response
        except Exception as exec:
            self.__auth_service_logger.error(
                "An error occured while geting categories: {}".format(exec)
            )
            raise exec

    def get_permission_title_by_category_name(
        self, category_name: str, service_name: str
    ) -> list[str]:
        category_name = category_name.strip().lower()
        self.__auth_service_logger.info(
            "Attempting to get permission titles by category name: {}".format(
                category_name
            )
        )

        try:
            if service_name == ServiceNames.CONSOLE:
                permission = PermissionCategories.CONSOLE_PERMISSIONS
            elif service_name == ServiceNames.TALKO:
                permission = PermissionCategories.TALKO_PERMISSIONS

            all_permissions: dict = {**{k.lower(): permission[k] for k in permission}}

            permission_entries = all_permissions.get(category_name, [])

            if (
                permission_entries
                and isinstance(permission_entries[0], (list, tuple))
                and len(permission_entries[0]) == 2
            ):
                permission_titles: list = [item[0] for item in permission_entries]
            else:
                permission_titles: list = permission_entries

            self.__auth_service_logger.info(
                "Fetched permission titles for category {}: {}".format(
                    category_name, permission_titles
                )
            )
            return permission_titles

        except Exception as exec:
            self.__auth_service_logger.error(
                "Error fetching permission titles for {}: {}".format(
                    category_name, exec
                )
            )
            raise exec

    async def update_role(
        self,
        role_id: UUID,
        role_data: UpdateRoleRequest,
    ):
        try:
            self.__auth_service_logger.info(
                "Attempting to update the role with id: {}".format(role_id)
            )
            role_data = role_data.model_dump(exclude_unset=True)
            update_role: Role = await self.__auth_repository.update_role(
                role_id, **role_data
            )
            response = RoleResponse.model_validate(update_role)
            return response
        except RoleNotFoundError as exec:
            self.__auth_service_logger.error(
                "Role not found during updating role: {}".format(repr(exec))
            )
            raise exec
        except AuthException as exec:
            self.__auth_service_logger.error(
                "Auth error during updating role: {}".format(repr(exec))
            )
            raise exec
        except Exception as exec:
            self.__auth_service_logger.error(
                "Unexpected error during updating role: {}".format(repr(exec))
            )
            raise exec

    async def get_role_by_hierarchy(self, hierarchy: int) -> Role:
        try:
            self.__auth_service_logger.info(
                "Attempting to get role details by hierarchy number: {}".format(
                    hierarchy
                )
            )
            response: Role = await self.__auth_repository.get_role_by_hierarchy(
                hierarchy
            )
            return response
        except Exception as exc:
            self.__auth_service_logger.error(
                "Unexpected error occurred while get role details by hierarchy: {}, error: {}".format(
                    hierarchy, exc
                )
            )
            raise exc

    def __extract_config_flags(
        self, user_config_list: list, keys: list
    ) -> dict[str, bool]:
        """
        Converts a list of config dicts or objects into a {key: value} dict for given keys.
        Handles both types by introspection.
        """
        config_map: dict[str, bool] = {}
        for item in user_config_list:
            if isinstance(item, dict):
                key, value = item.get("key"), item.get("value")
            else:
                # Handles Pydantic, dataclasses, or ORM model objects
                key, value = getattr(item, "key", None), getattr(item, "value", None)
            if key in keys:
                config_map[key] = value
        return config_map

    async def __create_session_and_token(
        self,
        request: Request,
        user: User,
        config_map: dict,
        service_name: str = "console",
        trial_expiry: int | None = None,
        subscription_mode: PartnerConfigResponse | None = None,
        partner_config_map: dict = {},
    ) -> dict:
        """Handles session + token creation (existing flow)."""
        try:
            ACCESS_TOKEN_EXPIRE_MINUTES: int = int(ENV.ACCESS_TOKEN_EXPIRE_MINUTES)

            # create user session
            user_session_id: str = str(uuid.uuid4())
            self.__auth_service_logger.debug(
                f"Creating user session for user ID: {user.id} session Id: {user_session_id}"
            )

            device_info: str = request.headers.get("User-Agent", "Unknown")
            ip_address: str = request.client.host if request.client else "Unknown"
            expiry_time : int = int(DateTimeUtil.get_current_time() + (ACCESS_TOKEN_EXPIRE_MINUTES * 60 * 1000))
            
            user_session: UserSession = (
                await self.__user_session_service.create_user_session(
                    {
                        "user_id": user.id,
                        "session_id": user_session_id,
                        "device_info": device_info,
                        "ip_address": ip_address,
                        "service_name": service_name,
                        "expiry_time": expiry_time,
                    }
                )
            )
            access_token_expires: timedelta = timedelta(
                minutes=ACCESS_TOKEN_EXPIRE_MINUTES
            )

            token_data: dict = {
                TokenKeys.IS_ACTIVE: user_session.is_active,
                TokenKeys.USER_SESSION_ID: user_session_id,
                TokenKeys.USER_ID: user.id,
                TokenKeys.NAME: user.name,
                TokenKeys.PARTNER: user.partner_id,
            }

            token_data.update(
                {
                    TokenKeys.IS_TALKO_ENABLED: (
                        config_map.get(ServiceKeys.IS_TALKO_ENABLED, False)
                        and partner_config_map.get(ServiceKeys.IS_TALKO_ENABLED, False)
                    ),
                    TokenKeys.IS_INTERNAL: user.is_internal,
                    TokenKeys.IS_WALLET_ENABLED: self.__is_wallet_enabled,
                    TokenKeys.IS_OBOTAAI_ENABLED: self.__is_obotaai_enabled,
                    TokenKeys.SUBSCRIPTION_MODE: (
                        subscription_mode.value
                        if subscription_mode
                        else SubscriptionModeEnum.SELF_SERVED
                    ),
                }
            )

            access_token: str = await self.__auth_service_utility.create_access_token(
                token_data, expires_delta=access_token_expires
            )

            # Cache token data
            self.__auth_service_logger.debug(
                f"Caching..  the token data:{token_data} with token:{access_token}"
            )

            if access_token:
                await self.__auth_service_cache.set_cache(
                    key=CacheKeys.TOKEN.format(user.partner_id, access_token),
                    value=json.dumps(token_data, default=str),
                    ttl=access_token_expires,
                )
                self.__auth_service_logger.info(
                    f"Access token successfully cached with token as key for User: {user.id}"
                )

            # Log audit
            log_entry = AuditLogSchema(
                action=AuditActions.create,
                resource=Resource.authentication,
                resource_id=None,
                resource_previous_state=None,
                resource_current_state=None,
                performed_by=user.id,
                details="Token created successfully",
            )
            await self.__audit_service.log_action(log_entry)

            return {"access_token": access_token, "token_type": TokenKeys.TOKEN_TYPE}
        except Exception as exc:
            self.__auth_service_logger.error(
                f"Error during session/token creation for user {user.id}: {repr(exc)}"
            )
            raise AuthException("Failed to create session and token") from exc

        
    async def validate_otp(
        self,
        request: Request,
        payload: OtpValidateRequest,
        user_config_service: UserConfigService = Depends(
            Provide["user_config_service"]
        ),
        user_repository: UserRepository = Depends(Provide["user_repository"]),
        partner_config_service: PartnerConfigService = Depends(
            Provide["partner_config_service"]
        ),
    ) -> dict:
        """
        Validate OTP and generate token if valid.
        """
        try:
            # Step 1: Fetch user
            user: User = await self._get_user(
                login_data=payload,
                is_assume_user=False,
                user_id=None,
                validate_password=False,
            )

            user_config: List[UserConfigResponse] = (
                await user_config_service.get_user_configs_by_user_id(user.id)
            )
            config_map: dict[str, bool] = self.__extract_config_flags(
                user_config, config_keys
            )

            partner_config: List[PartnerConfigResponse] = await partner_config_service.get_partner_configs_by_partner_id(user.partner_id)

            partner_config_map: dict = self._get_partner_config_map(partner_config)
            otp_type: OtpType = (
                (OtpType.EMAIL if payload.email else OtpType.PHONE_NUMBER)
                if payload.is_verify
                else OtpType.LOGIN
            )

            # Step 2: Fetch OTP record
            otp_entry: Union[OTP, None] = await self.__auth_repository.get_active_otp(
                user_id=user.id,
                otp_type=otp_type,
                otp=payload.otp,
            )

            # Validate OTP existence
            if not otp_entry:
                self.__auth_service_logger.warning(
                    f"Invalid OTP attempt for user {user.email}"
                )
                raise AuthException("Invalid OTP")

            # Step 3: Mark OTP as used
            otp_entry.is_used = True
            await self.__auth_repository.update_otp(otp_entry)
            # fetch additional details of otp
            additional_info: dict = otp_entry.additional_info

            update_data = {}
            if payload.email:
                if not user.is_email_verified:
                    update_data["is_email_verified"] = True
            else:
                if not user.is_phone_number_verified:
                    update_data["is_phone_number_verified"] = True

            if update_data:
                if not user.is_email_verified:
                    await user_repository.update_user(
                        user_id=user.id, current_user_id=user.id, **update_data
                    )
            if payload.is_verify:
                self.__auth_service_logger.info(
                    f"OTP successfully verified for user {payload.credential}"
                )
                return {
                    "message": f"OTP successfully verified for {payload.credential}"
                }
            service_name: str = additional_info.get("service_name", "console")
            trial_expiry: int = additional_info.get("trial_expiry", None)

            token: dict = await self.__create_session_and_token(
                request, user, config_map, service_name, trial_expiry, partner_config_map
            )

            self.__auth_service_logger.info(
                f"OTP validated, token generated for user {user.email}"
            )
            return token
        except UserNotFoundError as exc:
            self.__auth_service_logger.error(
                f"User not found during OTP validation: {repr(exc)}"
            )
            raise AuthException("User not found") from exc

        except AuthException as exc:
            self.__auth_service_logger.warning(
                f"Auth exception during OTP validation: {repr(exc)}"
            )
            raise exc

        except Exception as exc:
            self.__auth_service_logger.error(
                f"Unexpected error during OTP validation for user {payload.email or payload.phone_number}: {repr(exc)}"
            )
            raise AuthException("Internal server error") from exc

    async def __send_email_otp(
        self,
        email: str,
        otp: str,
    ):
        """
        Email OTP retired with the mailer — fail closed (never claim sent).
        """
        raise OtpMediumMissing("Email OTP is unavailable (mailer removed)")

    async def resolve_user_walkthrough_key(
        self,
        user_id: UUID,
        partner_id: UUID,
        user_service: UserService = Depends(Provide["console_service"]),
    ) -> None:
        try:
            self.__auth_service_logger.info("Attempting to resolve user walktrough key")
            await user_service.resolve_user_walkthrough_key(user_id, partner_id)
        except Exception as exec:
            self.__auth_service_logger.error(
                "An unexpected error occured while resolving the user walkthrough key: {}".format(
                    exec
                )
            )
            raise exec

    async def validate_service_access(
        self,
        service_access_dto: ServiceAccessDTO,
        partner_config_service: PartnerConfigService,
        partner_meta_data_service: PartnerMetaDataServices,
        user_config_service: UserConfigService = Depends(Provide["user_config_service"]),
    ) -> None:
        """
        This method will validate user service access and update the DTO.
        """
        partner_flag_key = SvcFlagMap.get(service_access_dto.svc_name)
        partner_service_enabled = service_access_dto.partner_config_map.get(partner_flag_key, False)
        if service_access_dto.svc_name != ServiceNames.CONSOLE and not partner_service_enabled:
            raise AuthException(
                AuthExceptionMsg.PARTNER_SERVICE_NOT_ENABLED.format(
                    service_access_dto.svc_name,
                )
            )
        # Verify if user is enbaled for coming login request for a service(talko)
        if (
            service_access_dto.svc_name != ServiceNames.CONSOLE
            and not service_access_dto.is_assume_user
            and not service_access_dto.config_map.get(
                SvcFlagMap.get(service_access_dto.svc_name), False
            )
        ):
            raise AuthException(
                AuthExceptionMsg.SVC_NOT_ENABLED.format(
                    service_access_dto.svc_name, service_access_dto.user.id
                )
            )


    def _get_partner_config_map(
        self,
        partner_configs   
    ) -> Dict[str, object]:
        """
        return them as a key-value map.
        """

        return {
            config.key: config.value
            for config in partner_configs
            if config.key is not None
        }