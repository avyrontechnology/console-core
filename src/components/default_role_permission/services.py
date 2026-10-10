from typing import Iterator, Optional

from fastapi import HTTPException, status, Depends
from dependency_injector.wiring import Provide

from src.components.audit_log.schema import AuditLogSchema
from src.components.audit_log.services import AuditService
from src.components.auth.service import AuthService
from src.components.auth.models import Role, Permission
from src.components.cache.helper import CacheHelper
from src.components.common.actions import AuditActions
from src.components.common.constants import CurrentUserMap
from src.components.common.resources import Resource
from src.components.default_role_permission.models import DefaultRolePermission
from src.components.default_role_permission.repositories import (
    DefaultRolePermissionRepository,
)
from src.components.default_role_permission.schemas import (
    DefaultRolePermissionData,
    DefaultRolePermissionResponse,
    SetRoleActionPermissionsData,
    SetRoleActionPermissionsResponse,
)
from src.components.partner_config.constants import PartnerConfigEnum
from src.components.partner_config.services import PartnerConfigService
from src.exceptions import DefaultRolePermissionException, AuthException
from src.loggers.console_service_logger import ConsoleServiceLogger


class DefaultRolePermissionService:

    def __init__(
        self,
        audit_service: AuditService,
        console_service_logger: ConsoleServiceLogger,
        default_role_permission_repository: DefaultRolePermissionRepository,
        partner_config_service: PartnerConfigService,
        cache_helper: CacheHelper,
    ):
        self.__audit_service: AuditService = audit_service
        self.__console_service_logger: ConsoleServiceLogger = console_service_logger
        self.__default_role_permission_repository: DefaultRolePermissionRepository = (
            default_role_permission_repository
        )
        self.__partner_config_service: PartnerConfigService = partner_config_service
        self.__cache: CacheHelper = cache_helper

    async def add_default_role_permission(
        self, add_data: DefaultRolePermissionData, current_user: dict, auth_service: AuthService = Depends(Provide["auth_service"])
    ) -> DefaultRolePermission:
        try:
            self.__console_service_logger.info(
                "Inserting new entry in Default Role Permission table for role id: {} and permission id: {}".format(
                    add_data.role_id, add_data.permission_id
                )
            )
            role_object: Role = await auth_service.get_role_by_id(add_data.role_id)
            permission_object: Permission = await auth_service.get_permission_by_id(add_data.permission_id)
            if not role_object.is_internal and permission_object.is_internal:
                raise DefaultRolePermissionException(
                    "can't map internal permission to external role"
                )
            user_id = current_user.get(CurrentUserMap.USER_ID)
            result = await self.__default_role_permission_repository.add_default_role_permission(
                add_data, user_id
            )
            self.__console_service_logger.info(
                "Successfully inserted mapping in db for role id: {} and permission id: {}".format(
                    add_data.role_id, add_data.permission_id
                )
            )
            log_entry = AuditLogSchema(
                action=AuditActions.create,
                resource=Resource.default_role_permission,
                resource_id=result.id,
                resource_previous_state=None,
                resource_current_state=str(add_data),
                performed_by=user_id,
                details="Partner role permission created with id: {}".format(result.id),
            )
            await self.__audit_service.log_action(log_entry)
            # Baseline grant changes the RBAC set maglo caches per user.
            await self.__cache.invalidate_user_permissions_cache()
            return result
        except AuthException as exec:
            self.__console_service_logger.error(
                "Error occurred while fetching role or permission: {}".format(str(exec))
            )
            raise DefaultRolePermissionException(str(exec))
        except DefaultRolePermissionException as ex:
            self.__console_service_logger.error(
                "error occurred while inserting new entry in Partner Role Permission table{}".format(
                    str(ex)
                )
            )
            raise ex
        except Exception as ex:
            self.__console_service_logger.error(
                "error occurred while inserting new entry in Partner Role Permission table{}".format(
                    str(ex)
                )
            )
            raise ex

    async def get_default_role_permissons(self, current_user: dict) -> list:
        try:
            self.__console_service_logger.info("Fetching default role permissions...")
            partner_id: int = current_user.get(CurrentUserMap.PARTNER_ID)
            config = await self.__partner_config_service.get_partner_config_by_key(
                partner_id, PartnerConfigEnum.IS_PARTNER_CUSTOM_ROLES_ENABLED.value
            )
            filter_partner_id: Optional[int] = (
                partner_id if (config and config.value == True) else None
            )
            default_role_permissions = (
                await self.__default_role_permission_repository.get_default_role_permissions(
                    partner_id=filter_partner_id
                )
            )
            response = [
                DefaultRolePermissionResponse.model_validate(item)
                for item in default_role_permissions
            ]
            return response
        except Exception as exec:
            self.__console_service_logger.error(
                "An error occured while fetching default role permissions: {}".format(
                    exec
                )
            )
            raise exec

    async def get_default_role_permissons_by_role_id(self, role_id: int):
        try:
            self.__console_service_logger.info(
                "Fetching default role permissions by role id: {}".format(role_id)
            )
            default_role_permissions = await self.__default_role_permission_repository.get_default_role_permissions_by_role_id(
                role_id
            )
            response = [
                DefaultRolePermissionResponse.model_validate(item)
                for item in default_role_permissions
            ]
            return response
        except DefaultRolePermissionException as exec:
            self.__console_service_logger.error("No default role permissions found for role id: {}".format(role_id))
            raise exec
        except Exception as exec:
            self.__console_service_logger.error(
                "An error occured while fetching default role permissions: {}".format(
                    exec
                )
            )
            raise exec

    async def set_role_action_permissions(
        self,
        role_id: int,
        set_data: SetRoleActionPermissionsData,
        current_user: dict,
        auth_service: AuthService = Depends(Provide["auth_service"]),
    ) -> SetRoleActionPermissionsResponse:
        """Bulk enable/disable a partner-owned role's action-flag permissions by slug.

        Guards that the role belongs to ``set_data.partner_id`` (a materialised,
        partner-owned role) so a partner can never edit a global default role
        (``partner_id IS NULL``) — that would leak across every partner. Enable →
        insert into the role's ``DefaultRolePermission`` baseline; disable → delete it
        (and any partner-custom grant). maglo caches each user's resolved RBAC set
        (``GRPC_GET_USER_PERMISSIONS``, ONE_WEEK), so the changed slugs are busted
        below to make the effect immediate.
        """
        try:
            self.__console_service_logger.info(
                "set_role_action_permissions requested role_id={} partner_id={}".format(
                    role_id, set_data.partner_id
                )
            )
            role_object: Role = await auth_service.get_role_by_id(role_id)

            # Ownership guard: only a role OWNED by this partner may be edited here.
            if role_object is None or getattr(role_object, "partner_id", None) is None:
                raise DefaultRolePermissionException(
                    "Only a partner-owned (materialised) role can be edited; "
                    "global default roles are not editable."
                )
            if role_object.partner_id != set_data.partner_id:
                raise DefaultRolePermissionException(
                    "Role {} does not belong to partner {}.".format(
                        role_id, set_data.partner_id
                    )
                )

            requested_slugs = list(set_data.permissions.keys())
            slug_to_id: dict = (
                await self.__default_role_permission_repository.get_permission_ids_by_slugs(
                    requested_slugs
                )
            )
            unknown_slugs = [s for s in requested_slugs if s not in slug_to_id]

            enable_ids = {
                slug_to_id[s]
                for s, enabled in set_data.permissions.items()
                if enabled and s in slug_to_id
            }
            disable_ids = {
                slug_to_id[s]
                for s, enabled in set_data.permissions.items()
                if not enabled and s in slug_to_id
            }

            granted_ids, revoked_ids = (
                await self.__default_role_permission_repository.set_role_action_permissions(
                    role_id=role_id,
                    partner_id=set_data.partner_id,
                    enable_ids=enable_ids,
                    disable_ids=disable_ids,
                    user_id=current_user.get(CurrentUserMap.USER_ID),
                )
            )

            id_to_slug = {v: k for k, v in slug_to_id.items()}
            granted = [id_to_slug[i] for i in granted_ids if i in id_to_slug]
            revoked = [id_to_slug[i] for i in revoked_ids if i in id_to_slug]
            changed = set(granted) | set(revoked)
            unchanged = [
                s for s in requested_slugs if s in slug_to_id and s not in changed
            ]

            log_entry = AuditLogSchema(
                action=AuditActions.update,
                resource=Resource.default_role_permission,
                resource_id=role_id,
                resource_previous_state=None,
                resource_current_state=str(
                    {"granted": granted, "revoked": revoked}
                ),
                performed_by=current_user.get(CurrentUserMap.USER_ID),
                details="Set action-flag permissions for role {} (partner {})".format(
                    role_id, set_data.partner_id
                ),
            )
            await self.__audit_service.log_action(log_entry)

            if changed:
                await self.__cache.invalidate_user_permissions_cache()

            return SetRoleActionPermissionsResponse(
                role_id=role_id,
                partner_id=set_data.partner_id,
                granted=granted,
                revoked=revoked,
                unchanged=unchanged,
                unknown_slugs=unknown_slugs,
            )
        except DefaultRolePermissionException as exec:
            self.__console_service_logger.error(str(exec))
            raise exec
        except Exception as exec:
            self.__console_service_logger.error(
                "An error occurred while setting role action permissions: {}".format(
                    str(exec)
                )
            )
            raise exec

    async def delete_default_role_permission(
        self, default_role_permission_id: int, current_user: dict
    ):
        try:
            self.__console_service_logger.info(
                "Deleting default role permission with id: {}".format(
                    default_role_permission_id
                )
            )
            result = await self.__default_role_permission_repository.delete_default_role_permission(
                default_role_permission_id
            )
            log_entry = AuditLogSchema(
                action=AuditActions.delete,
                resource=Resource.default_role_permission,
                resource_id=default_role_permission_id,
                resource_previous_state=None,
                resource_current_state=None,
                performed_by=current_user.get(CurrentUserMap.USER_ID),
                details="Default role permission deleted with id: {}".format(
                    default_role_permission_id
                ),
            )
            await self.__audit_service.log_action(log_entry)
            # Revoking a baseline grant changes the RBAC set maglo caches per user.
            await self.__cache.invalidate_user_permissions_cache()
            return {"message": "Default role permission deleted successfully."}
        except DefaultRolePermissionException as exec:
            self.__console_service_logger.error(str(exec))
            raise exec
        except Exception as exec:
            self.__console_service_logger.error(
                "An error occurred while deleting default role permission: {}".format(
                    str(exec)
                )
            )
            raise exec
