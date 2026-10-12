from uuid import UUID
from collections import defaultdict
from typing import Any, Iterator, Optional

from dependency_injector.wiring import Provide
from fastapi import Depends, HTTPException, status

from src.components.audit_log.schema import AuditLogSchema
from src.components.audit_log.services import AuditService
from src.components.auth.constant import PermissionAttributes
from src.components.auth.service import AuthService
from src.components.auth.models import Role
from src.components.common.actions import AuditActions
from src.components.common.constants import CurrentUserMap
from src.components.common.resources import Resource
from src.components.partner.services import PartnerService
from src.components.partner.models import Partner
from src.components.partner_config.constants import PartnerConfigEnum
from src.components.partner_config.schemas import PartnerConfigResponse
from src.components.partner_config.services import PartnerConfigService
from src.components.partner_role_permission.constant import ExceptionMsg
from src.components.partner_role_permission.models import PartnerRolePermission
from src.components.partner_role_permission.repositories import (
    PartnerPermissionRepository,
)
from src.components.partner_role_permission.schema import PartnerPermissionData
from src.exceptions import (
    AuthException,
    PartnerConfigException,
    PartnerException,
    PartnerRolePermissionException,
)
from src.loggers.console_service_logger import ConsoleServiceLogger


class PartnerPermissionService:

    def __init__(
        self,
        audit_service: AuditService,
        console_service_logger: ConsoleServiceLogger,
        partner_perm_repository: PartnerPermissionRepository,
    ):
        self.__audit_service: AuditService = audit_service
        self.__console_service_logger: ConsoleServiceLogger = console_service_logger
        self.__partner_perm_repository: PartnerPermissionRepository = (
            partner_perm_repository
        )

    async def add_partner_permission(
        self,
        add_data: PartnerPermissionData,
        current_user: dict,
        partner_config_service: PartnerConfigService = Depends(
            Provide["partner_config_service"]
        ),
        partner_service: PartnerService = Depends(Provide["partner_service"]),
        role_service: AuthService = Depends(Provide["auth_service"]),
    ) -> PartnerRolePermission:
        try:
            self.__console_service_logger.info(
                "Inserting new entry in Partner Role Permission table for partner_id: {}".format(
                    add_data.partner_id
                )
            )
            partner_object: Partner = await partner_service.get_partner_by_id(
                add_data.partner_id
            )
            role_object: Role = await role_service.get_role_by_id(add_data.role_id)

            if partner_object.is_internal != role_object.is_internal:
                self.__console_service_logger.error(
                    "Can't create partner role permission if one of them is internal"
                )
                raise PartnerRolePermissionException(
                    ExceptionMsg.CANT_CREATE_IF_ONE_IS_INTERNAL
                )

            user_id: UUID = current_user.get(CurrentUserMap.USER_ID)
            partner_id: UUID = current_user.get(CurrentUserMap.PARTNER_ID)
            key = PartnerConfigEnum.IS_CUSTOM_ROLE_PERMISSION_ENABLED
            is_custom_role_permission_enabled: PartnerConfigResponse = (
                await partner_config_service.get_partner_config_by_key(partner_id, key)
            )
            if (
                is_custom_role_permission_enabled
                and is_custom_role_permission_enabled.value == False
            ):
                self.__console_service_logger.error(
                    "Can't create partner role permission if the is custom role permission value is false"
                )
                raise PartnerRolePermissionException(
                    ExceptionMsg.IS_CUSTOM_PERMISSION_FALSE
                )
            result = await self.__partner_perm_repository.add_partner_permission(
                add_data, user_id
            )
            self.__console_service_logger.info(
                "Successfully inserted mapping in db for partner id {}".format(
                    add_data.partner_id
                )
            )
            log_entry = AuditLogSchema(
                action=AuditActions.create,
                resource=Resource.partner_role_permission,
                resource_id=result.id,
                resource_previous_state=None,
                resource_current_state=str(add_data),
                performed_by=user_id,
                details="Partner role permission created with id: {}".format(result.id),
            )
            await self.__audit_service.log_action(log_entry)
            return result
        except PartnerRolePermissionException as ex:
            self.__console_service_logger.error(
                "error occurred while inserting new entry in Partner Role Permission table{}".format(
                    str(ex)
                )
            )
            raise ex

        except PartnerException as exec:
            self.__console_service_logger.error(
                "Partner not found while inserting new entry in Partner Role Permission table: {}".format(
                    str(exec)
                )
            )
            raise PartnerRolePermissionException(ExceptionMsg.PARTNER_NOT_FOUND)

        except AuthException as exec:
            self.__console_service_logger.error(
                "Role not found while inserting new entry in Partner Role Permission table: {}".format(
                    str(exec)
                )
            )
            raise PartnerRolePermissionException(ExceptionMsg.ROLE_NOT_FOUND)

        except Exception as ex:
            self.__console_service_logger.error(
                "error occurred while inserting new entry in Partner Role Permission table{}".format(
                    str(ex)
                )
            )
            raise ex

    async def get_partner_role_permission(self) -> Iterator[PartnerRolePermission]:
        try:
            self.__console_service_logger.info(
                "Getting all partner role permission table mapping"
            )
            partner_role_permission = (
                await self.__partner_perm_repository.get_all_partner_role_permission()
            )
            self.__console_service_logger.info(
                "Fetched all partner role permission successfully: {}".format(
                    partner_role_permission
                )
            )
            return partner_role_permission
        except Exception as ex:
            self.__console_service_logger.error(
                "error occurred while getting in Partner Role Permission table{}".format(
                    str(ex)
                )
            )
            raise ex

    async def get_partner_role_permission_by_id(self, id: UUID) -> PartnerRolePermission:
        try:
            self.__console_service_logger.info(
                "Attempting get Partner Role Permission by ID: {}".format(id)
            )
            partner_role_permission = (
                await self.__partner_perm_repository.get_partner_role_permission_by_id(
                    id
                )
            )
            self.__console_service_logger.info(
                "successfully retrieved partner role permission by id  {}".format(
                    partner_role_permission
                )
            )

            return partner_role_permission
        except PartnerRolePermissionException as ex:
            self.__console_service_logger.error(
                "error occurred while  get Partner Role Permission{}".format(str(ex))
            )
            raise ex
        except Exception as ex:
            self.__console_service_logger.error(
                "error occurred while  get Partner Role Permission{}".format(str(ex))
            )
            raise ex

    async def get_by_partner_id(self, id: UUID) -> Iterator[PartnerRolePermission]:
        try:
            self.__console_service_logger.info(
                "Attempting get Partner Role Permission by Partner ID: {}".format(id)
            )
            partner_role_permission = (
                await self.__partner_perm_repository.get_by_partner_id(id)
            )
            self.__console_service_logger.info(
                "successfully retrieved partner role permission by partner id {} {}".format(
                    id, partner_role_permission
                )
            )
            return partner_role_permission
        except PartnerRolePermissionException as ex:
            self.__console_service_logger.error(
                "error occurred while  get Partner Role Permission by Partner ID:{}".format(
                    str(ex)
                )
            )
            raise ex
        except Exception as ex:
            self.__console_service_logger.error(
                "error occurred while  get Partner Role Permission by Partner ID:{}".format(
                    str(ex)
                )
            )
            raise ex

    async def delete_partner_role_permission(self, id: UUID, current_user: dict) -> None:
        try:
            self.__console_service_logger.info(
                "Attempting delete Partner Role Permission ID {}".format(id)
            )
            result = (
                await self.__partner_perm_repository.delete_partner_role_permission(id)
            )
            user_id = current_user.get(CurrentUserMap.USER_ID)
            log_entry = AuditLogSchema(
                action=AuditActions.delete,
                resource=Resource.partner_role_permission,
                resource_id=id,
                resource_previous_state=None,
                resource_current_state=None,
                performed_by=user_id,
                details="Partner role permission with id: {} is deleted successfully.".format(
                    id
                ),
            )
            await self.__audit_service.log_action(log_entry)
            self.__console_service_logger.info(
                "successfully deleted partner role permission, id {}".format(id)
            )
            return result
        except PartnerRolePermissionException as ex:
            raise ex
        except Exception as ex:
            self.__console_service_logger.error(
                "error occurred while delete  entry in Partner Role Permission table{}".format(
                    str(ex)
                )
            )
            raise ex

    async def get_partner_permissions_matrix_by_config(
        self,
        partner_id: UUID,
        partner_config_service: PartnerConfigService = Depends(
            Provide["partner_config_service"]
        ),
        partner_service: PartnerService = Depends(Provide["partner_service"]),
    ) -> dict:
        try:
            self.__console_service_logger.info(
                "Building permission matrix for partners having custom role permissions enabled"
            )
            partner_object: Partner = await partner_service.get_partner_by_id(
                partner_id
            )
            is_internal_partner: bool = False
            if partner_object.is_internal:
                is_internal_partner: bool = True
                
            partner_config = await partner_config_service.get_partner_config_by_key(
                partner_id, PartnerConfigEnum.IS_CUSTOM_ROLE_PERMISSION_ENABLED.value
            )

            if not partner_config or not partner_config.value:
                self.__console_service_logger.error(
                    "Partner config for custom role permissions is not enabled for partner_id: {}".format(
                        partner_id
                    )
                )
                raise PartnerConfigException(
                    "Custom role permissions are not enabled for this partner."
                )
            config_key = PartnerConfigEnum.IS_CUSTOM_ROLE_PERMISSION_ENABLED.value

            permission_matrix: Any = (
                await self.__partner_perm_repository.get_partner_role_permission_matrix(
                    key=config_key,
                    partner_id=partner_id,
                    is_internal_partner=is_internal_partner,
                )
            )

            matrix: defaultdict[Any, dict] = defaultdict(dict)

            for row in permission_matrix:
                partner = row.partner_name
                role = row.role_name
                category = row.category
                slug = row.slug

                if role not in matrix[partner]:
                    matrix[partner][role] = {}

                if category not in matrix[partner][role]:
                    matrix[partner][role][category] = {}

                matrix[partner][role][category][slug] = {
                    PermissionAttributes.ID: row.permission_id,
                    PermissionAttributes.CREATED_AT: row.created_at,
                    PermissionAttributes.DESCRIPTION: row.description,
                    PermissionAttributes.DISPLAY_TEXT: row.display_text,
                    PermissionAttributes.IS_ACTIVE: row.is_partner,
                }

            response: defaultdict[Any, dict] = matrix
            self.__console_service_logger.info(
                "Successfully built partner permissions matrix: {}".format(response)
            )
            return response
        except PartnerRolePermissionException as exec:
            self.__console_service_logger.error(
                "Error fetching partner permissions matrix: {}".format(exec)
            )
            raise exec

        except PartnerConfigException as exec:
            self.__console_service_logger.error(
                "Error fetching partner config: {}".format(exec)
            )
            raise exec
        
        except PartnerException as exec:
            self.__console_service_logger.error(
                "Error fetching partner details: {}".format(exec)
            )
            raise PartnerRolePermissionException(ExceptionMsg.PARTNER_NOT_FOUND)

        except Exception as exec:
            self.__console_service_logger.error(
                "Error fetching partner permissions: {}".format(exec)
            )
            raise exec
