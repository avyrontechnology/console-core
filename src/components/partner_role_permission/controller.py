from uuid import UUID
from typing import List, Optional

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
from src.components.partner_role_permission.constant import SuccessResponseMsg
from src.components.partner_role_permission.schema import (
    PartnerPermissionData,
    PartnerRolePermissionResponse,
)
from src.components.partner_role_permission.service import PartnerPermissionService
from src.components.rbac.permission_injector import permission_check
from src.core.container import Container
from src.exceptions import PartnerRolePermissionException, PartnerConfigException
from src.loggers.console_service_logger import ConsoleServiceLogger


class PartnerPermissionController:

    partner_role_permission_router = APIRouter()

    # add mapping partner role permission
    @partner_role_permission_router.post(
        "/partner_role_permission", response_model=PartnerRolePermissionResponse
    )
    @permission_check("console:add_partner_role_permission")
    @inject
    async def add_partner_role_permission(
        request: Request,
        add_data: PartnerPermissionData,
        role_perm_service: PartnerPermissionService = Depends(
            Provide[Container.partner_role_perm_service]
        ),
        console_service_logger: ConsoleServiceLogger = Depends(
            Provide[Container.console_service_logger]
        ),
    ):
        try:
            console_service_logger.info(
                "Attempting to map Partner role permission for partner id: {}".format(
                    add_data.partner_id
                )
            )
            current_user = request.state.user
            result = await role_perm_service.add_partner_permission(
                add_data, current_user
            )
            console_service_logger.info(
                "Successfully inserted mapping in db for partner id {}".format(
                    add_data.partner_id
                )
            )
            return ResourceCreatedResponse(
                jsonable_encoder(PartnerRolePermissionResponse.model_validate(result))
            )
        except PartnerRolePermissionException as ex:
            console_service_logger.error(
                "Unexpected error during map partner role permission{}".format(str(ex))
            )
            return BadRequestResponse(str(ex))
        except Exception as ex:
            console_service_logger.error(
                "Unexpected error during map partner role permission{}".format(str(ex))
            )
            return InternalServerErrorResponse(ErrorMsg.INTERNAL_SERVER_ERROR)

    @partner_role_permission_router.get(
        "/partner_role_permission/partner/",
        response_model=PartnerRolePermissionResponse,
    )
    @permission_check("console:get_prp_by_partner_id")
    @inject
    async def get_prp_by_partner_id(
        request: Request,
        partner_id: UUID = Query(..., description="ID of the partner"),
        role_perm_service: PartnerPermissionService = Depends(
            Provide[Container.partner_role_perm_service]
        ),
        console_service_logger: ConsoleServiceLogger = Depends(
            Provide[Container.console_service_logger]
        ),
    ):
        """get partner role permission mapping by partner id."""
        try:
            console_service_logger.info(
                "Attempting to get mapping  Partner role permission by Partner ID: {}".format(
                    partner_id
                )
            )
            result = await role_perm_service.get_by_partner_id(partner_id)
            console_service_logger.info(
                "successfully retrieved partner role permission by partner id {} {}".format(
                    partner_id, result
                )
            )
            partner_prp = [
                PartnerRolePermissionResponse.model_validate(prp) for prp in result
            ]
            return SuccessResponse(jsonable_encoder(partner_prp))
        except PartnerRolePermissionException as ex:
            console_service_logger.error(
                "Unexpected error during get map partner role permission by partner id{}".format(
                    str(ex)
                )
            )
            return NotFoundResponse(str(ex))
        except Exception as ex:
            console_service_logger.error(
                "Unexpected error during get map partner role permission by partner id{}".format(
                    str(ex)
                )
            )
            return InternalServerErrorResponse(ErrorMsg.INTERNAL_SERVER_ERROR)

    # return partner role permission mapping by id
    @partner_role_permission_router.get(
        "/partner_role_permission/", response_model=PartnerRolePermissionResponse
    )
    @permission_check("console:get_partner_role_permission_by_id")
    @inject
    async def get_partner_role_permission_by_id(
        request: Request,
        id: UUID = Query(..., description="ID of the partner role permission"),
        role_perm_service: PartnerPermissionService = Depends(
            Provide[Container.partner_role_perm_service]
        ),
        console_service_logger: ConsoleServiceLogger = Depends(
            Provide[Container.console_service_logger]
        ),
    ):
        try:
            console_service_logger.info(
                "Attempting to get mapping  Partner role permission by ID: {}".format(
                    id
                )
            )
            result = await role_perm_service.get_partner_role_permission_by_id(id)
            console_service_logger.info(
                "successfully retrieved partner role permission by id  {}".format(
                    result
                )
            )

            return SuccessResponse(
                jsonable_encoder(PartnerRolePermissionResponse.model_validate(result))
            )
        except PartnerRolePermissionException as ex:
            console_service_logger.error(
                "Unexpected error during get map partner role permission by id{}".format(
                    str(ex)
                )
            )
            return NotFoundResponse(str(ex))
        except Exception as ex:
            console_service_logger.error(
                "Unexpected error during get map partner role permission by id{}".format(
                    str(ex)
                )
            )
            return InternalServerErrorResponse(ErrorMsg.INTERNAL_SERVER_ERROR)

    @partner_role_permission_router.delete("/partner_role_permission/{id}")
    @permission_check("console:delete_partner_role_permission")
    @inject
    async def delete_partner_role_permission(
        request: Request,
        id: UUID,
        role_perm_service: PartnerPermissionService = Depends(
            Provide[Container.partner_role_perm_service]
        ),
        console_service_logger: ConsoleServiceLogger = Depends(
            Provide[Container.console_service_logger]
        ),
    ):
        try:
            console_service_logger.info(
                "Attempting to delete Mapping  Partner role permission ID: {}".format(
                    id
                )
            )
            current_user = request.state.user
            await role_perm_service.delete_partner_role_permission(id, current_user)
            console_service_logger.info(
                "successfully deleted partner role permission, id {}".format(id)
            )
            return SuccessNoContentResponse()
        except PartnerRolePermissionException as ex:
            console_service_logger.error(
                "Unexpected error during map partner role permission{}".format(str(ex))
            )
            return NotFoundResponse(str(ex))
        except Exception as ex:
            console_service_logger.error(
                "Unexpected error during delete map partner role permission{}".format(
                    str(ex)
                )
            )
            return InternalServerErrorResponse(ErrorMsg.INTERNAL_SERVER_ERROR)
        
    @partner_role_permission_router.get(
        "/partner_role_permission_matrix/{partner_id}/",
    )
    @permission_check("console:get_partner_role_permissions_matrix")
    @inject
    async def get_partner_role_permissions_matrix(
        request: Request,
        partner_id: UUID,
        role_perm_service: PartnerPermissionService = Depends(
            Provide[Container.partner_role_perm_service]
        ),
        console_service_logger: ConsoleServiceLogger = Depends(
            Provide[Container.console_service_logger]
        ),
    ):
        try:
            console_service_logger.info("Fetching partner role permission matrix for all partners with custom role permissions")
            data: dict = await role_perm_service.get_partner_permissions_matrix_by_config(partner_id)
            return SuccessResponse(
                data=data
            )
        except PartnerRolePermissionException as exec:
            console_service_logger.error(
                "Failed to fetch partner role permission matrix: {}".format(str(exec))
            )
            return NotFoundResponse(str(exec))
        except PartnerConfigException as exec:
            console_service_logger.error(
                "Failed to fetch partner config: {}".format(str(exec))
            )
            return NotFoundResponse(str(exec))
        except Exception as exec:
            console_service_logger.error(
                "Failed to fetch partner role permission matrix: {}".format(str(exec))
            )
            return InternalServerErrorResponse(ErrorMsg.INTERNAL_SERVER_ERROR)
