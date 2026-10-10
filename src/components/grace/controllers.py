"""Grace Period Controller."""
from typing import Any

from dependency_injector.wiring import Provide, inject
from fastapi import APIRouter, Depends, Request

from src.components.auth.constant import TokenKeys
from src.components.common.constants import FieldType
from src.components.common.response import (
    BadRequestResponse,
    ForbiddenResponse,
    InternalServerErrorResponse,
    NotFoundResponse,
    ResourceCreatedResponse,
    SuccessResponse,
)
from src.components.common.utility import SchemaValidator
from src.components.grace.errors import (
    GraceAlreadyActiveError,
    GraceForbiddenError,
    GraceInvalidDaysError,
    GraceMaxAttemptsError,
    GraceNoPriorOrderError,
    GraceNotEligibleError,
)
from src.components.grace.schema import (
    GraceResponse,
    GraceStatusResponse,
    GrantGraceRequest,
)
from src.components.grace.services import GraceService
from src.components.partner.error import PartnerNotFoundError
from src.components.rbac.permission_dependency import PermissionDependency
from src.components.rbac.permission_injector import permission_check
from src.core.container import Container
from src.loggers.console_service_logger import ConsoleServiceLogger


class GraceController:
    """Endpoints for grace period management."""

    grace_router = APIRouter(prefix="/grace", tags=["Grace"])

    @grace_router.post(
        "/grant",
        status_code=201,
        summary="Grant a grace period to a partner",
        description=(
            "Grants a temporary service extension after entitlement expiry. "
            "Only available to users whose partner has is_internal = true. "
            "Grace is only allowed when the partner has no active or scheduled entitlement. "
            "Service names are derived automatically from the partner's last successful order."
        ),
    )
    @permission_check(PermissionDependency)
    @inject
    async def grant_grace(
        request: Request,
        payload: GrantGraceRequest,
        grace_service: GraceService = Depends(Provide[Container.grace_service]),
        logger: ConsoleServiceLogger = Depends(
            Provide[Container.console_service_logger]
        ),
    ):
        try:
            current_user: dict = request.state.user
            is_internal: bool = current_user.get(TokenKeys.IS_INTERNAL, False)

            if not is_internal:
                return ForbiddenResponse(
                    detail="Only internal team members can view grace status."
                )

            logger.info(
                "Controller: grant_grace | partner_id={} by_user={}".format(
                    payload.partner_id,
                    current_user.get("user_id"),
                )
            )

            validated, error = payload.validate_payload()
            if error:
                logger.error(
                    "Controller: grant_grace | validation error | {}".format(error)
                )
                return BadRequestResponse(detail=error)

            result: GraceResponse = await grace_service.grant_grace(
                payload=validated,
                current_user=current_user,
            )

            logger.info(
                "Controller: grant_grace success | grace_id={} partner_id={}".format(
                    result.grace_id, result.partner_id
                )
            )
            return ResourceCreatedResponse(
                data=result.model_dump(),
                message="Grace period granted successfully.",
            )

        except PartnerNotFoundError as exc:
            logger.error(
                "Controller: grant_grace | partner not found or inactive | {}".format(
                    exc
                )
            )
            return NotFoundResponse(detail=str(exc))
        except GraceForbiddenError as exc:
            logger.error("Controller: grant_grace | forbidden | {}".format(exc))
            return ForbiddenResponse(detail=str(exc))

        except GraceNotEligibleError as exc:
            logger.error("Controller: grant_grace | not eligible | {}".format(exc))
            return BadRequestResponse(detail=str(exc))

        except GraceMaxAttemptsError as exc:
            logger.error("Controller: grant_grace | max attempts | {}".format(exc))
            return BadRequestResponse(detail=str(exc))

        except GraceAlreadyActiveError as exc:
            logger.error("Controller: grant_grace | already active | {}".format(exc))
            return BadRequestResponse(detail=str(exc))

        except GraceInvalidDaysError as exc:
            logger.error("Controller: grant_grace | invalid days | {}".format(exc))
            return BadRequestResponse(detail=str(exc))

        except GraceNoPriorOrderError as exc:
            logger.error("Controller: grant_grace | no prior order | {}".format(exc))
            return BadRequestResponse(detail=str(exc))

        except PartnerNotFoundError as exc:
            logger.error("Controller: grant_grace | partner not found | {}".format(exc))
            return NotFoundResponse(detail=str(exc))

        except Exception as exc:
            logger.error(
                "Controller: grant_grace | unexpected error | {}".format(repr(exc))
            )
            return InternalServerErrorResponse(detail="Failed to grant grace period.")

    @grace_router.get(
        "/status",
        summary="Get grace status for a partner",
        description=(
            "Returns current grace state, attempt count, and total consumed days "
            "for the given partner across all services."
        ),
    )
    @permission_check(PermissionDependency)
    @inject
    async def get_grace_status(
        request: Request,
        partner_id: Any,
        grace_service: GraceService = Depends(Provide[Container.grace_service]),
        logger: ConsoleServiceLogger = Depends(
            Provide[Container.console_service_logger]
        ),
    ):
        try:
            current_user: dict = request.state.user
            is_internal: bool = current_user.get(TokenKeys.IS_INTERNAL, False)

            validated, error = SchemaValidator.validate(
                {
                    "partner_id": {
                        "value": partner_id,
                        "required": True,
                        "type": FieldType.INTEGER,
                        "min": 1,
                        "max": 2147483647,
                    },
                }
            )

            if error:
                return BadRequestResponse(detail=error)

            if not is_internal:
                return ForbiddenResponse(
                    detail="Only internal team members can view grace status."
                )

            logger.info(
                "Controller: get_grace_status | partner_id={}".format(
                    validated["partner_id"]
                )
            )

            result: GraceStatusResponse = await grace_service.get_grace_status(
                validated["partner_id"]
            )

            return SuccessResponse(data=result.model_dump())

        except PartnerNotFoundError as exc:
            logger.error(
                "Controller: grant_grace | partner not found or inactive | {}".format(
                    exc
                )
            )
            return NotFoundResponse(detail=str(exc))
        except Exception as exc:
            logger.error(
                "Controller: get_grace_status | unexpected error | {}".format(repr(exc))
            )
            return InternalServerErrorResponse(detail="Failed to fetch grace status.")
