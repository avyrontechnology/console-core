from uuid import UUID
from typing import Any, List

from dependency_injector.wiring import Provide, inject
from fastapi import APIRouter, Depends, Query, Request

from src.components.auth.constant import TokenKeys
from src.components.common.constants import FieldType
from src.components.common.response import (
    BadRequestResponse,
    ForbiddenResponse,
    InternalServerErrorResponse,
    NotFoundResponse,
    SuccessResponse,
)
from src.components.common.utility import SchemaValidator
from src.components.entitlement.errors import (
    EntitlementNotEligibleForStartDateUpdateError,
    EntitlementNotFoundError,
    EntitlementStartDateUpdateLimitExceededError,
    EntitlementStartDateUpdateWindowExpiredError,
    NoPermissionToUpdateEntitlementError,
    OrderNotFoundForEntitlementError,
)
from src.components.entitlement.messages import POPUP_DISMISSED_SUCCESSFULLY
from src.components.entitlement.models import Entitlement
from src.components.entitlement.schema import (
    UpdateEntitlementStartDateRequest,
    UpdateEntitlementStartDateResponse,
)
from src.components.entitlement.services import EntitlementService
from src.components.plan.constants import Platform
from src.components.rbac.permission_dependency import PermissionDependency
from src.components.rbac.permission_injector import permission_check
from src.core.container import Container
from src.loggers.console_service_logger import ConsoleServiceLogger


class EntitlementController:
    entitlement_router = APIRouter(prefix="/entitlements", tags=["Entitlements"])

    @entitlement_router.patch(
        "/update-start-date",
    )
    @permission_check(PermissionDependency)
    @inject
    async def update_entitlement_start_date(
        request: Request,
        update_request: UpdateEntitlementStartDateRequest,
        entitlement_service: EntitlementService = Depends(
            Provide[Container.entitlement_service]
        ),
        logger: ConsoleServiceLogger = Depends(
            Provide[Container.console_service_logger]
        ),
    ):
        """
        Update the start date of an entitlement.

        This endpoint allows updating the start date of a fresh entitlement within
        the configured time window and update limit.

        - **order_id**: ID of the order associated with the entitlement
        - **start_date**: New start date timestamp in milliseconds (must be in future)

        The end date is automatically calculated based on the order's duration.
        """
        try:
            current_user: dict = request.state.user
            partner_id: UUID = current_user.get(TokenKeys.PARTNER_ID)

            logger.info(
                "Controller: update_entitlement_start_date started for partner_id={}, order_id={}".format(
                    partner_id, update_request.order_id
                )
            )

            updated_entitlements: List[Entitlement] = (
                await entitlement_service.update_entitlement_start_date(
                    payload_data=update_request,
                    current_user=current_user,
                )
            )

            response_data = [
                UpdateEntitlementStartDateResponse.model_validate(ent)
                for ent in updated_entitlements
            ]

            logger.info(
                "Controller: Entitlement start date updated successfully. order_id={}".format(
                    update_request.order_id
                )
            )

            return SuccessResponse(
                data=response_data,
                message="Entitlement start date updated successfully",
            )

        except OrderNotFoundForEntitlementError as exc:
            logger.error(
                "Controller: Order not found for entitlement. order_id={}, error={}".format(
                    update_request.order_id, str(exc)
                )
            )
            return NotFoundResponse(detail=str(exc))

        except EntitlementNotFoundError as exc:
            logger.error(
                "Controller: Entitlement not found. order_id={}, error={}".format(
                    update_request.order_id, str(exc)
                )
            )
            return NotFoundResponse(detail=str(exc))

        except EntitlementNotEligibleForStartDateUpdateError as exc:
            logger.warning(
                "Controller: Entitlement not eligible for start date update. order_id={}, error={}".format(
                    update_request.order_id, str(exc)
                )
            )
            return BadRequestResponse(detail=str(exc))

        except EntitlementStartDateUpdateLimitExceededError as exc:
            logger.warning(
                "Controller: Start date update limit exceeded. order_id={}, error={}".format(
                    update_request.order_id, str(exc)
                )
            )
            return BadRequestResponse(detail=str(exc))

        except NoPermissionToUpdateEntitlementError as exc:
            logger.warning(
                "Controller: No permission to update entitlement. order_id={}, error={}".format(
                    update_request.order_id, str(exc)
                )
            )
            return ForbiddenResponse(detail=str(exc))

        except EntitlementStartDateUpdateWindowExpiredError as exc:
            logger.warning(
                "Controller: Start date update window expired. order_id={}, error={}".format(
                    update_request.order_id, str(exc)
                )
            )
            return BadRequestResponse(detail=str(exc))

        except ValueError as exc:
            logger.error(
                "Controller: Validation error. order_id={}, error={}".format(
                    update_request.order_id, str(exc)
                )
            )
            return BadRequestResponse(detail=str(exc))

        except Exception as exc:
            logger.error(
                "Controller: Unexpected error in update_entitlement_start_date. order_id={}, error={}".format(
                    update_request.order_id, repr(exc)
                )
            )
            return InternalServerErrorResponse(
                detail="Failed to update entitlement start date"
            )

    @entitlement_router.patch(
        "/dismiss-popup",
    )
    @permission_check(PermissionDependency)
    @inject
    async def dismiss_popup(
        request: Request,
        service_name: Any = Query(None),
        entitlement_service: EntitlementService = Depends(
            Provide[Container.entitlement_service]
        ),
        logger: ConsoleServiceLogger = Depends(
            Provide[Container.console_service_logger]
        ),
    ):
        """
        Called when user closes the popup.
        Updates popup_last_closed[service_name] = now on User.additional_info.
        Only meaningful for ACTIVE and GRACE statuses
        should call this for those two statuses.
        """
        try:
            current_user: dict = request.state.user
            user_id: UUID = current_user.get(TokenKeys.USER_ID)

            validated, error = SchemaValidator.validate(
                {
                    "service_name": {
                        "value": service_name,
                        "required": True,
                        "type": FieldType.STRING,
                        "min": 1,
                        "max": 100,
                        "values": [
                            getattr(Platform, k) for k in Platform.__annotations__
                        ],
                    }
                }
            )

            if error:
                return BadRequestResponse(detail=error)

            await entitlement_service.dismiss_popup(
                user_id=user_id,
                service_name=validated["service_name"],
            )
            return SuccessResponse(
                message=POPUP_DISMISSED_SUCCESSFULLY, data=POPUP_DISMISSED_SUCCESSFULLY
            )

        except Exception as exc:
            logger.error("Controller: dismiss_popup error | error={}".format(repr(exc)))
            return InternalServerErrorResponse(detail="Failed to dismiss popup")
