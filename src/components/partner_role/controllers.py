from uuid import UUID
from typing import Any, Dict, Optional

from dependency_injector.wiring import Provide, inject
from fastapi import APIRouter, Depends, Query, Request
from fastapi.encoders import jsonable_encoder

from src.components.auth.models import Role
from src.components.common.response import (
    APIResponse,
    BadRequestResponse,
    NotFoundResponse,
    ResourceCreatedResponse,
    SuccessNoContentResponse,
    SuccessResponse,
)
from src.components.partner_role.error import (
    PartnerRoleException,
    PartnerRoleNotFoundError,
)
from src.components.partner_role.schema import (
    CreatePartnerRole,
    MaterializePartnerRoles,
    PartnerRolePaginatedResponse,
    PartnerRoleResponse,
    UpdatePartnerRole,
)
from src.components.partner_role.service import PartnerRoleService
from src.components.rbac.permission_injector import permission_check
from src.core.container import Container
from src.loggers.console_service_logger import ConsoleServiceLogger


class PartnerRoleController:

    partner_role_router: APIRouter = APIRouter()

    @partner_role_router.post("/partner_role/materialize")
    @permission_check("console:materialize_partner_roles")
    @inject
    async def materialize_partner_roles(
        request: Request,
        data: MaterializePartnerRoles,
        partner_role_service: PartnerRoleService = Depends(
            Provide[Container.partner_role_service]
        ),
        console_service_logger: ConsoleServiceLogger = Depends(
            Provide[Container.console_service_logger]
        ),
    ) -> APIResponse:
        try:
            current_user: Dict[str, Any] = request.state.user
            await partner_role_service.ensure_partner_catalog(
                data.partner_id, current_user
            )
            return SuccessResponse({"detail": "Partner role catalog materialized"})
        except PartnerRoleException as ex:
            console_service_logger.error(
                "Materialize catalog failed: {}".format(str(ex))
            )
            return BadRequestResponse(str(ex))

    @partner_role_router.post("/partner_role", response_model=PartnerRoleResponse)
    @permission_check("console:create_partner_role")
    @inject
    async def create_partner_role(
        request: Request,
        data: CreatePartnerRole,
        partner_role_service: PartnerRoleService = Depends(
            Provide[Container.partner_role_service]
        ),
        console_service_logger: ConsoleServiceLogger = Depends(
            Provide[Container.console_service_logger]
        ),
    ) -> APIResponse:
        try:
            current_user: Dict[str, Any] = request.state.user
            role: Role = await partner_role_service.create_partner_role(
                data, current_user
            )
            return ResourceCreatedResponse(
                jsonable_encoder(PartnerRoleResponse.model_validate(role))
            )
        except PartnerRoleException as ex:
            console_service_logger.error(
                "Create partner role failed: {}".format(str(ex))
            )
            return BadRequestResponse(str(ex))

    @partner_role_router.get("/partner_roles", response_model=PartnerRolePaginatedResponse)
    @permission_check("console:get_partner_roles")
    @inject
    async def get_partner_roles(
        request: Request,
        limit: Optional[int] = Query(
            None, description="number of records per page", ge=1
        ),
        offset: Optional[int] = Query(
            None, description="zero-based page offset", ge=0
        ),
        partner_role_service: PartnerRoleService = Depends(
            Provide[Container.partner_role_service]
        ),
    ) -> APIResponse:
        if (limit is None) != (offset is None):
            return BadRequestResponse(
                detail="Both 'limit' and 'offset' must be provided together for pagination."
            )

        try:
            current_user: Dict[str, Any] = request.state.user
            result: PartnerRolePaginatedResponse = (
                await partner_role_service.list_partner_roles(current_user, limit, offset)
            )
            return SuccessResponse(
                data=jsonable_encoder(result.data),
                pagination={
                    "total_count": result.total_count,
                    "total_active": result.total_active,
                    "total_inactive": result.total_inactive,
                    "limit": result.limit,
                    "offset": result.offset,
                },
            )
        except PartnerRoleException as ex:
            return BadRequestResponse(str(ex))

    @partner_role_router.patch("/partner_role/{role_id}")
    @permission_check("console:update_partner_role")
    @inject
    async def update_partner_role(
        request: Request,
        role_id: UUID,
        data: UpdatePartnerRole,
        partner_role_service: PartnerRoleService = Depends(
            Provide[Container.partner_role_service]
        ),
    ) -> APIResponse:
        try:
            current_user: Dict[str, Any] = request.state.user
            role: Role = await partner_role_service.update_partner_role(
                role_id, data, current_user
            )
            return SuccessResponse(
                jsonable_encoder(PartnerRoleResponse.model_validate(role))
            )
        except PartnerRoleNotFoundError as ex:
            return NotFoundResponse(str(ex))
        except PartnerRoleException as ex:
            return BadRequestResponse(str(ex))

    @partner_role_router.delete("/partner_role/{role_id}")
    @permission_check("console:delete_partner_role")
    @inject
    async def delete_partner_role(
        request: Request,
        role_id: UUID,
        partner_role_service: PartnerRoleService = Depends(
            Provide[Container.partner_role_service]
        ),
    ) -> APIResponse:
        try:
            current_user: Dict[str, Any] = request.state.user
            await partner_role_service.delete_partner_role(role_id, current_user)
            return SuccessNoContentResponse()
        except PartnerRoleNotFoundError as ex:
            return NotFoundResponse(str(ex))
        except PartnerRoleException as ex:
            return BadRequestResponse(str(ex))
