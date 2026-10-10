"""
REST controllers for partner database configuration.

All endpoints are guarded by:
  1. PermissionDependency (RBAC)
  2. is_user_internal check (super-admin only)
"""

from dependency_injector.wiring import Provide, inject
from fastapi import APIRouter, Body, Depends, Request

from src.components.common.constants import CurrentUserMap
from src.components.common.response import (
    BadRequestResponse,
    InternalServerErrorResponse,
    NotFoundResponse,
    SuccessResponse,
    UnauthorizedResponse,
)
from src.components.partner_db_config.schemas import (
    PartnerDBConfigRequest,
    PartnerDBConfigResponse,
)
from src.components.partner_db_config.services import PartnerDBConfigService
from src.components.rbac.permission_dependency import PermissionDependency
from src.components.rbac.permission_injector import permission_check
from src.components.user.services import UserService
from src.core.container import Container
from src.loggers.console_service_logger import ConsoleServiceLogger


class PartnerDBConfigController:

    partner_db_config_router = APIRouter()

    # ------------------------------------------------------------------
    # UPSERT  —  POST /partner-db-config/{partner_id}
    # ------------------------------------------------------------------
    @partner_db_config_router.post(
        "/partner-db-config/{partner_id}",
        response_model=PartnerDBConfigResponse,
    )
    @permission_check(PermissionDependency)
    @inject
    async def upsert_partner_db_config(
        request: Request,
        partner_id: int,
        config_data: PartnerDBConfigRequest = Body(
            ..., description="Partner database connection credentials"
        ),
        console_service_logger: ConsoleServiceLogger = Depends(
            Provide[Container.console_service_logger]
        ),
        partner_db_config_service: PartnerDBConfigService = Depends(
            Provide[Container.partner_db_config_service]
        ),
        user_svc: UserService = Depends(Provide[Container.console_service]),
    ):
        try:
            current_user: dict = request.state.user
            current_user_id: int = current_user.get(CurrentUserMap.USER_ID)

            # Super-admin guard
            if not await user_svc.is_user_internal(current_user_id):
                return UnauthorizedResponse(
                    detail="Only super-admin users can manage partner DB configs"
                )

            result = await partner_db_config_service.upsert_db_config(
                partner_id=partner_id,
                config_data=config_data,
                current_user_id=current_user_id,
            )
            return SuccessResponse(data=result)

        except ValueError as exc:
            console_service_logger.error(
                "Validation error for partner DB config: {}".format(exc)
            )
            return BadRequestResponse(detail=str(exc))
        except Exception as exc:
            console_service_logger.error(
                "Unexpected error upserting partner DB config: {}".format(exc)
            )
            return InternalServerErrorResponse()

    # ------------------------------------------------------------------
    # GET  —  GET /partner-db-config/{partner_id}
    # ------------------------------------------------------------------
    @partner_db_config_router.get(
        "/partner-db-config/{partner_id}",
        response_model=PartnerDBConfigResponse,
    )
    @permission_check(PermissionDependency)
    @inject
    async def get_partner_db_config(
        request: Request,
        partner_id: int,
        console_service_logger: ConsoleServiceLogger = Depends(
            Provide[Container.console_service_logger]
        ),
        partner_db_config_service: PartnerDBConfigService = Depends(
            Provide[Container.partner_db_config_service]
        ),
        user_svc: UserService = Depends(Provide[Container.console_service]),
    ):
        try:
            current_user: dict = request.state.user
            current_user_id: int = current_user.get(CurrentUserMap.USER_ID)

            if not await user_svc.is_user_internal(current_user_id):
                return UnauthorizedResponse(
                    detail="Only super-admin users can view partner DB configs"
                )

            result = await partner_db_config_service.get_db_config(partner_id)
            if result is None:
                return NotFoundResponse(
                    detail="No DB config found for partner_id={}".format(partner_id)
                )
            return SuccessResponse(data=result)

        except Exception as exc:
            console_service_logger.error(
                "Unexpected error fetching partner DB config: {}".format(exc)
            )
            return InternalServerErrorResponse()

    # ------------------------------------------------------------------
    # INTERNAL GET  —  GET /internal/partner-db-config/{partner_id}
    # (service-to-service, returns decrypted credentials)
    # ------------------------------------------------------------------
    @partner_db_config_router.get(
        "/internal/partner-db-config/{partner_id}",
    )
    @inject
    async def get_partner_db_config_internal(
        request: Request,
        partner_id: int,
        console_service_logger: ConsoleServiceLogger = Depends(
            Provide[Container.console_service_logger]
        ),
        partner_db_config_service: PartnerDBConfigService = Depends(
            Provide[Container.partner_db_config_service]
        ),
    ):
        """
        Internal endpoint for maglo-service to resolve partner DB credentials.
        Returns decrypted password.
        """
        try:
            result = await partner_db_config_service.get_db_config_internal(
                partner_id
            )
            if result is None:
                return NotFoundResponse(
                    detail="No DB config found for partner_id={}".format(partner_id)
                )
            return SuccessResponse(data=result)

        except Exception as exc:
            console_service_logger.error(
                "Unexpected error fetching internal partner DB config: {}".format(exc)
            )
            return InternalServerErrorResponse()

    # ------------------------------------------------------------------
    # DELETE  —  DELETE /partner-db-config/{partner_id}
    # ------------------------------------------------------------------
    @partner_db_config_router.delete(
        "/partner-db-config/{partner_id}",
    )
    @permission_check(PermissionDependency)
    @inject
    async def delete_partner_db_config(
        request: Request,
        partner_id: int,
        console_service_logger: ConsoleServiceLogger = Depends(
            Provide[Container.console_service_logger]
        ),
        partner_db_config_service: PartnerDBConfigService = Depends(
            Provide[Container.partner_db_config_service]
        ),
        user_svc: UserService = Depends(Provide[Container.console_service]),
    ):
        try:
            current_user: dict = request.state.user
            current_user_id: int = current_user.get(CurrentUserMap.USER_ID)

            if not await user_svc.is_user_internal(current_user_id):
                return UnauthorizedResponse(
                    detail="Only super-admin users can delete partner DB configs"
                )

            deleted = await partner_db_config_service.delete_db_config(partner_id)
            if not deleted:
                return NotFoundResponse(
                    detail="No DB config found for partner_id={}".format(partner_id)
                )
            return SuccessResponse(
                data={"partner_id": partner_id},
                message="Partner DB config deleted successfully",
            )

        except Exception as exc:
            console_service_logger.error(
                "Unexpected error deleting partner DB config: {}".format(exc)
            )
            return InternalServerErrorResponse()
