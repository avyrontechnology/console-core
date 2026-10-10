from typing import List

from dependency_injector.wiring import Provide, inject
from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.encoders import jsonable_encoder

from src.components.auth.util import AuthUtility
from src.components.common.errors import ErrorMsg
from src.components.common.response import (
    BadRequestResponse,
    InternalServerErrorResponse,
    NotFoundResponse,
    ResourceCreatedResponse,
    SuccessNoContentResponse,
    SuccessResponse,
)
from src.components.default_role_permission.schemas import (
    DefaultRolePermissionData,
    DefaultRolePermissionResponse,
    SetRoleActionPermissionsData,
    SetRoleActionPermissionsResponse,
)
from src.components.default_role_permission.services import DefaultRolePermissionService
from src.components.partner_role_permission.constant import SuccessResponseMsg
from src.components.rbac.permission_dependency import PermissionDependency
from src.components.rbac.permission_injector import permission_check
from src.core.container import Container
from src.exceptions import DefaultRolePermissionException
from src.loggers.console_service_logger import ConsoleServiceLogger


class DefaultRolePermissionController:

    default_role_permission_router = APIRouter()

    @default_role_permission_router.post(
        "/default_role_permission", response_model=DefaultRolePermissionResponse
    )
    @permission_check(PermissionDependency)
    @inject
    async def add_default_role_permission(
        request: Request,
        add_data: DefaultRolePermissionData,
        default_role_permission_service: DefaultRolePermissionService = Depends(
            Provide[Container.default_role_permission_service]
        ),
        console_service_logger: ConsoleServiceLogger = Depends(
            Provide[Container.console_service_logger]
        ),
    ):
        try:
            console_service_logger.info(
                "Attempting to map Partner role permission for role id: {} and permission id: {}".format(
                    add_data.role_id, add_data.permission_id
                )
            )
            current_user = request.state.user
            result = await default_role_permission_service.add_default_role_permission(
                add_data, current_user
            )
            console_service_logger.info(
                "Successfully inserted mapping in db for role id {} and permission id {}".format(
                    add_data.role_id, add_data.permission_id
                )
            )
            return ResourceCreatedResponse(
                jsonable_encoder(DefaultRolePermissionResponse.model_validate(result))
            )
        except DefaultRolePermissionException as ex:
            console_service_logger.error(
                "Unexpected error during map partner role permission{}".format(str(ex))
            )
            return BadRequestResponse(str(ex))
        except Exception as ex:
            console_service_logger.error(
                "Unexpected error during map partner role permission{}".format(str(ex))
            )
            return InternalServerErrorResponse(ErrorMsg.INTERNAL_SERVER_ERROR)

    @default_role_permission_router.get(
        "/default_role_permission", response_model=DefaultRolePermissionResponse
    )
    @permission_check(PermissionDependency)
    @inject
    async def get_default_role_permission(
        request: Request,
        default_role_permission_service: DefaultRolePermissionService = Depends(
            Provide[Container.default_role_permission_service]
        ),
        console_service_logger: ConsoleServiceLogger = Depends(
            Provide[Container.console_service_logger]
        ),
    ):
        try:
            console_service_logger.info("Fetching default role permissions...")
            result = await default_role_permission_service.get_default_role_permissons(
                request.state.user
            )
            return SuccessResponse(data=result)
        except Exception as exec:
            console_service_logger.error("An unexpected error occured: {}".format(exec))
            return InternalServerErrorResponse()

    @default_role_permission_router.get(
        "/default_role_permission/{role_id}",
        response_model=DefaultRolePermissionResponse,
    )
    @permission_check(PermissionDependency)
    @inject
    async def get_default_role_permission_by_role_id(
        request: Request,
        role_id: int,
        default_role_permission_service: DefaultRolePermissionService = Depends(
            Provide[Container.default_role_permission_service]
        ),
        console_service_logger: ConsoleServiceLogger = Depends(
            Provide[Container.console_service_logger]
        ),
    ):
        try:
            console_service_logger.info(
                "Fetching default role permissions for role id: {}".format(role_id)
            )
            result = await default_role_permission_service.get_default_role_permissons_by_role_id(
                role_id
            )
            return SuccessResponse(data=result)
        except DefaultRolePermissionException as exec:
            console_service_logger.error(
                "No default role permissions found for role id: {}".format(role_id)
            )
            return NotFoundResponse(str(exec))
        except Exception as exec:
            console_service_logger.error("An unexpected error occured: {}".format(exec))
            return InternalServerErrorResponse()

    @default_role_permission_router.put(
        "/default_role_permission/role/{role_id}/action-permissions",
        response_model=SetRoleActionPermissionsResponse,
    )
    @permission_check(PermissionDependency)
    @inject
    async def set_role_action_permissions(
        request: Request,
        role_id: int,
        set_data: SetRoleActionPermissionsData,
        default_role_permission_service: DefaultRolePermissionService = Depends(
            Provide[Container.default_role_permission_service]
        ),
        console_service_logger: ConsoleServiceLogger = Depends(
            Provide[Container.console_service_logger]
        ),
    ):
        """Bulk toggle a partner-owned role's action-flag buttons (grant/revoke the
        mapped RBAC permissions by slug). Body: ``{partner_id, permissions:{slug:bool}}``."""
        try:
            current_user = request.state.user
            console_service_logger.info(
                "Setting action-flag permissions for role id: {} partner id: {}".format(
                    role_id, set_data.partner_id
                )
            )
            result = await default_role_permission_service.set_role_action_permissions(
                role_id, set_data, current_user
            )
            return SuccessResponse(jsonable_encoder(result))
        except DefaultRolePermissionException as ex:
            console_service_logger.error(
                "Failed to set role action permissions for role {}: {}".format(
                    role_id, str(ex)
                )
            )
            return BadRequestResponse(str(ex))
        except Exception as ex:
            console_service_logger.error(
                "Unexpected error while setting role action permissions: {}".format(
                    str(ex)
                )
            )
            return InternalServerErrorResponse(ErrorMsg.INTERNAL_SERVER_ERROR)

    @default_role_permission_router.delete(
        "/default_role_permission/{default_role_permission_id}"
    )
    @permission_check(PermissionDependency)
    @inject
    async def delete_default_role_permission_by_id(
        request: Request,
        default_role_permission_id: int,
        default_role_permission_service: DefaultRolePermissionService = Depends(
            Provide[Container.default_role_permission_service]
        ),
        console_service_logger: ConsoleServiceLogger = Depends(
            Provide[Container.console_service_logger]
        ),
    ):
        try:
            current_user = request.state.user

            console_service_logger.info(
                "deleting default role permission by id: {}".format(
                    default_role_permission_id
                )
            )
            await default_role_permission_service.delete_default_role_permission(
                default_role_permission_id, current_user
            )
            return SuccessNoContentResponse()
        except DefaultRolePermissionException as exec:
            console_service_logger.error("default role permission doesn't exist for mapping id: {}".format(default_role_permission_id))
            return NotFoundResponse(detail=str(exec))
        except Exception as exec:
            console_service_logger.error(
                "An unexpected error occurred: {}".format(exec)
            )
            return InternalServerErrorResponse()
