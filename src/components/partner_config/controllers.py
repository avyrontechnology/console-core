from typing import List

from dependency_injector.wiring import Provide, inject
from fastapi import APIRouter, Body, Depends, Request
from sqlalchemy.exc import IntegrityError

from src.components.common.constants import CurrentUserMap
from src.components.common.response import (
    BadRequestResponse,
    InternalServerErrorResponse,
    NotFoundResponse,
    ResourceConflictResponse,
    ResourceCreatedResponse,
    SuccessResponse,
    UnauthorizedResponse,
)
from src.components.partner_config.constants import (
    PartnerConfigAttributes,
    PartnerConfigEnum,
)
from src.components.partner_config.errors import (
    PartnerConfigKeyError,
    PartnerConfigMailMGError,
    PartnerConfigValidationError,
    PartnerNotFoundError,
)
from src.components.partner_config.schemas import (
    EmailConfigUpsertSchema,
    PartnerConfigData,
    PartnerConfigRequest,
    PartnerConfigResponse,
    UpdatePartnerConfigResponse,
)
from src.components.partner_config.services import PartnerConfigService
from src.components.rbac.permission_dependency import PermissionDependency
from src.components.rbac.permission_injector import permission_check
from src.components.user.services import UserService
from src.core.container import Container
from src.exceptions import (
    AuthException,
    PartnerActiveSubscriptionException,
    PartnerConfigException,
    TeamException,
    UnauthorisedException,
)
from src.loggers.console_service_logger import ConsoleServiceLogger


class PartnerConfigController:

    partner_config_router = APIRouter()

    @partner_config_router.post("/partner-config", response_model=PartnerConfigResponse)
    @permission_check(PermissionDependency)
    @inject
    async def create_partner_config(
        request: Request,
        partner_config_data: PartnerConfigRequest = Body(
            ..., description="Partner Config data."
        ),
        console_service_logger: ConsoleServiceLogger = Depends(
            Provide[Container.console_service_logger]
        ),
        partner_config_service: PartnerConfigService = Depends(
            Provide[Container.partner_config_service]
        ),
    ):
        try:

            key: str = partner_config_data.key
            if PartnerConfigEnum(key) not in PartnerConfigEnum.__members__.values():
                return BadRequestResponse(detail=f"Invalid Config Key: {key}")
            current_user: dict = request.state.user
            partner_id: int = current_user.get(CurrentUserMap.PARTNER_ID)

            console_service_logger.info(
                "Attempting to create partner config for partner id: {}".format(
                    partner_id
                )
            )
            partner_config: PartnerConfigResponse = (
                await partner_config_service.create_partner_config(
                    partner_config_data, partner_id
                )
            )
            console_service_logger.info(
                "partner config created successfully for partner id: {} : {}".format(
                    partner_id, partner_config
                )
            )
            return ResourceCreatedResponse(data=partner_config)

        except ValueError as value_error:
            console_service_logger.error(
                f"Invalid Key while creating Partner Config with key: {key}"
            )
            return BadRequestResponse(
                detail=str(f"Invalid Key while creating Partner Config with key: {key}")
            )
        except UnauthorisedException as exec:
            console_service_logger.error(
                "An Unauthorised error occured: {}".format(exec)
            )
            return UnauthorizedResponse(detail=str(exec))
        except IntegrityError as exec:
            console_service_logger.error("Integrity error occured: {}".format(exec))
            return ResourceConflictResponse(
                detail=PartnerConfigAttributes.KEY_CONFLICT.format(
                    partner_config_data.key
                )
            )
        except Exception as exec:
            console_service_logger.error("An Unexpected error occured: {}".format(exec))
            return InternalServerErrorResponse()

    @partner_config_router.get("/partner-config", response_model=PartnerConfigResponse)
    @permission_check(PermissionDependency)
    @inject
    async def get_partner_config_by_key(
        request: Request,
        key: str,
        console_service_logger: ConsoleServiceLogger = Depends(
            Provide[Container.console_service_logger]
        ),
        partner_config_service: PartnerConfigService = Depends(
            Provide[Container.partner_config_service]
        ),
    ):
        try:
            current_user: dict = request.state.user
            partner_id: int = current_user.get(CurrentUserMap.PARTNER_ID)
            console_service_logger.info(
                "Attempting to fetch partner config for partner id: {}".format(
                    partner_id
                )
            )
            partner_config: PartnerConfigResponse = (
                await partner_config_service.get_partner_config_by_key(partner_id, key)
            )
            console_service_logger.info(
                "partner config fetched successfully for partner id: {} : {}".format(
                    partner_id, partner_config
                )
            )
            return SuccessResponse(data=partner_config)
        except ValueError as value_error:
            console_service_logger.error(
                f"Value Error while getting SBConfig: {value_error}"
            )
            return BadRequestResponse(detail=str(value_error))
        except PartnerConfigException as exec:
            console_service_logger.error(
                "Partner config not found for partner id: {}".format(partner_id)
            )
            return NotFoundResponse(
                detail=PartnerConfigAttributes.PARTNER_CONFIG_NOT_FOUND.format(
                    partner_id
                )
            )
        except Exception as exec:
            console_service_logger.error("An Unexpected error occured: {}".format(exec))
            return InternalServerErrorResponse()

    @partner_config_router.patch(
        "/partner-configs/{partner_id}", response_model=UpdatePartnerConfigResponse
    )
    @permission_check(PermissionDependency)
    @inject
    async def upsert_partner_config(
        request: Request,
        partner_id: int,
        update_partner_config_data: PartnerConfigData = Body(
            ..., description="New value for the configuration."
        ),
        console_service_logger: ConsoleServiceLogger = Depends(
            Provide[Container.console_service_logger]
        ),
        partner_config_service: PartnerConfigService = Depends(
            Provide[Container.partner_config_service]
        ),
    ):
        try:
            current_user: dict = request.state.user
            console_service_logger.info(
                "Attempting to update partner config for partner id: {}".format(
                    partner_id
                )
            )

            partner_config: List[UpdatePartnerConfigResponse] = (
                await partner_config_service.update_partner_config(
                    partner_id, update_partner_config_data, current_user
                )
            )
            console_service_logger.info(
                "partner config updated successfully for partner id: {} : {}".format(
                    partner_id, partner_config
                )
            )
            return SuccessResponse(data=partner_config)
        except PartnerConfigKeyError as exc:
            console_service_logger.error(
                f"Service board config key does not found:{ exc}"
            )
            return BadRequestResponse(exc)
        except AuthException as exec:
            console_service_logger.error(
                "Unauthorized access attempt by user id: {} for partner id: {}".format(
                    current_user.get(CurrentUserMap.USER_ID), partner_id
                )
            )
            return UnauthorizedResponse(detail=str(exec))
        except PartnerActiveSubscriptionException as exc:
            console_service_logger.error(
                f"Subscription mode change not allowed due to active subscription: {exc}"
            )
            return BadRequestResponse(
                detail="Subscription mode change not allowed due to active subscription"
            )
        except PartnerConfigException as exec:
            console_service_logger.error(
                "Partner config not found for partner id: {}".format(partner_id)
            )
            return NotFoundResponse(
                detail=PartnerConfigAttributes.PARTNER_CONFIG_NOT_FOUND.format(
                    partner_id
                )
            )
        except TeamException as exec:
            console_service_logger.error(
                "Cannot disable custom roles while users are assigned to partner-specific roles for partner id: {}".format(
                    partner_id
                )
            )
            return BadRequestResponse(
                detail=str(exec)
            )
        except Exception as exec:
            console_service_logger.error("Unexpected error occured: {}".format(exec))
            return InternalServerErrorResponse()

    @partner_config_router.get(
        "/partner-configs/{partner_id}", response_model=List[PartnerConfigResponse]
    )
    @permission_check(PermissionDependency)
    @inject
    async def get_partner_configs_by_partner_id(
        request: Request,
        partner_id: int,
        console_service_logger: ConsoleServiceLogger = Depends(
            Provide[Container.console_service_logger]
        ),
        partner_config_service: PartnerConfigService = Depends(
            Provide[Container.partner_config_service]
        ),
        user_svc: UserService = Depends(Provide[Container.console_service]),
    ):
        try:
            current_user: dict = request.state.user
            if partner_id and await user_svc.is_user_internal(
                current_user.get(CurrentUserMap.USER_ID)
            ):
                pass

            elif partner_id != current_user.get(CurrentUserMap.PARTNER_ID):
                raise PartnerConfigException(
                    "current user doesn't belongs to partner id:{}".format(partner_id)
                )
            console_service_logger.info(
                "Attempting to fetch partner configs for partner id: {}".format(
                    partner_id
                )
            )
            partner_configs: List[PartnerConfigResponse] = (
                await partner_config_service.get_partner_configs_by_partner_id(
                    partner_id
                )
            )
            console_service_logger.info(
                "partner configs fetched successfully for partner id: {} : {}".format(
                    partner_id, partner_configs
                )
            )
            return SuccessResponse(data=partner_configs)

        except PartnerConfigException as exec:
            console_service_logger.error(
                "No partner is not available for partner id: {}: {}".format(
                    partner_id, exec
                )
            )
            return NotFoundResponse(detail=str(exec))
        except UnauthorisedException as exec:
            console_service_logger.error("Unauthorised error occured: {}".format(exec))
            return UnauthorizedResponse(detail=str(exec))
        except Exception as exec:
            console_service_logger.error("Unexpected error occured: {}".format(exec))
            return InternalServerErrorResponse()

    @partner_config_router.post("/upsert-email-config")
    @permission_check(PermissionDependency)
    @inject
    async def upsert_email_config(
        request: Request,
        email_config_data: EmailConfigUpsertSchema,
        console_service_logger: ConsoleServiceLogger = Depends(
            Provide[Container.console_service_logger]
        ),
        partner_config_service: PartnerConfigService = Depends(
            Provide[Container.partner_config_service]
        ),
    ):
        try:
            current_user: dict = request.state.user
            response = await partner_config_service.upsert_email_config(
                current_user, email_config_data
            )
            return SuccessResponse(
                data=response, message="Email config key generated successfully"
            )

        except PartnerConfigValidationError as exc:
            console_service_logger.error("Validation error: {}".format(str(exc)))
            return BadRequestResponse(detail=str(exc))

        except (PartnerNotFoundError, PartnerConfigKeyError) as exc:
            console_service_logger.error("Not found error: {}".format(str(exc)))
            return NotFoundResponse(detail=str(exc))

        except PartnerConfigMailMGError as exc:
            console_service_logger.error("MailMG API error: {}".format(str(exc)))
            return InternalServerErrorResponse(detail=str(exc))

        except Exception as exc:
            console_service_logger.error("Unexpected error: {}".format(str(exc)))
            return InternalServerErrorResponse(detail=str(exc))
