from uuid import UUID
import json
from typing import List

from dependency_injector.wiring import Provide, inject
from fastapi import APIRouter, Body, Depends, Query, Request, status
from sqlalchemy.exc import IntegrityError

from src.components.common.errors import ErrorMsg
from src.components.common.response import (
    APIResponse,
    BadRequestResponse,
    InternalServerErrorResponse,
    NotFoundResponse,
    ResourceConflictResponse,
    ResourceCreatedResponse,
    SuccessResponse,
    UnauthorizedResponse,
)
from src.components.partner import messages
from src.components.partner.constant import (
    DashboardFilters,
    PaginationConstants,
    PartnerResponseData,
)
from src.components.partner.error import PartnerNotFoundError
from src.components.partner.schema import (
    BasePartnerData,
    ChangePartnerStatusRequest,
    ChangePartnerStatusResponse,
    PartnerCreateResponse,
    PartnerFilterRequest,
    PartnerOnboardingDetails,
    PartnerOnboardingResponse,
    PartnerProfileResponse,
    PartnerResponse,
    TogglePartnerActivation,
    TogglePartnerActivationResponse,
    UpdatePartnerRequest,
)
from src.components.partner.services import PartnerService
from src.components.rbac.permission_dependency import PermissionDependency
from src.components.rbac.permission_injector import permission_check
from src.core.container import Container
from src.exceptions import (
    AuthException,
    PartnerException,
    PartnerStatusUnchangedException,
)
from src.loggers.console_service_logger import ConsoleServiceLogger


class PartnerController:

    partner_router = APIRouter()

    @partner_router.post("/partners", response_model=List[PartnerResponse])
    @permission_check(PermissionDependency)
    @inject
    async def get_all_partners(
        request: Request,
        filter_request: PartnerFilterRequest = Body(...),
        partner_service: PartnerService = Depends(Provide[Container.partner_service]),
        console_service_logger: ConsoleServiceLogger = Depends(
            Provide[Container.console_service_logger]
        ),
    ):
        try:
            current_user = request.state.user
            console_service_logger.info("Getting all the partners from database")
            all_partners: List[PartnerResponse] = (
                await partner_service.enlist_partners_dynamically(
                    current_user, filter_request
                )
            )
            console_service_logger.info(
                "Fetched all the partners: {}".format(all_partners)
            )

            return SuccessResponse(all_partners)
        except AuthException:
            return UnauthorizedResponse(detail="User is not internal.")
        except PartnerException as exec:
            console_service_logger.error("Partner exception occured: {}".format(exec))
            return BadRequestResponse(detail=str(exec))
        except Exception as e:
            console_service_logger.error(
                "An unexpected error occurred: {}".format(str(e))
            )
            return InternalServerErrorResponse(ErrorMsg.INTERNAL_SERVER_ERROR)

    @partner_router.get("/partner/{partner_id}", response_model=PartnerResponse)
    @permission_check(PermissionDependency)
    @inject
    async def get_partners_by_id(
        request: Request,
        partner_id: UUID,
        partner_service: PartnerService = Depends(Provide[Container.partner_service]),
        console_service_logger: ConsoleServiceLogger = Depends(
            Provide[Container.console_service_logger]
        ),
    ):
        try:
            console_service_logger.info("Getting partner by id: {}".format(partner_id))
            fetched_partner = await partner_service.get_partner_by_id(partner_id)
            console_service_logger.info(
                "Partner fetched successfully: {}".format(fetched_partner)
            )
            return SuccessResponse(PartnerResponse.model_validate(fetched_partner))
        except PartnerException as ex:
            console_service_logger.error(
                "Partner with id {} is not found in database".format(partner_id)
            )
            return NotFoundResponse(str(ex))
        except Exception as e:
            console_service_logger.error(
                "An unexpected error occurred: {}".format(str(e))
            )
            return InternalServerErrorResponse(ErrorMsg.INTERNAL_SERVER_ERROR)

    @partner_router.post("/create_partner", response_model=PartnerCreateResponse)
    @inject
    async def add_partner(
        partner_data: BasePartnerData = Body(...),
        partner_service: PartnerService = Depends(Provide[Container.partner_service]),
        console_service_logger: ConsoleServiceLogger = Depends(
            Provide[Container.console_service_logger]
        ),
    ):
        try:
            console_service_logger.info(
                "Received the partner data :{}".format(partner_data)
            )
            created_partner = await partner_service.create_partner(partner_data)
            console_service_logger.info(
                "Partner created successfully: {}".format(created_partner)
            )

            return ResourceCreatedResponse(
                {
                    **PartnerCreateResponse.model_validate(
                        created_partner
                    ).model_dump(),
                }
            )
        except PartnerException as ex:
            console_service_logger.error(
                "Partner/Publisher already exists while creating partner: {}".format(
                    repr(ex)
                )
            )
            content = {
                "status": "error",
                "error_code": "RESOURCE_CONFLICT_REQUEST",
                "detail": str(ex.message) if ex.message else None,
                "id": ex.id if ex.id else None,
            }
            return APIResponse(
                content=json.dumps(content),
                status_code=409,
                media_type="application/json",
            )
        except Exception as ex:
            console_service_logger.error("Error creating partner: {}".format(repr(ex)))
            return InternalServerErrorResponse(ErrorMsg.INTERNAL_SERVER_ERROR)

    @partner_router.delete(
        "/partner/{partner_id}", status_code=status.HTTP_204_NO_CONTENT
    )
    @permission_check(PermissionDependency)
    @inject
    async def delete_partner(
        request: Request,
        partner_id: UUID,
        partner_service: PartnerService = Depends(Provide[Container.partner_service]),
        console_service_logger: ConsoleServiceLogger = Depends(
            Provide[Container.console_service_logger]
        ),
    ):
        try:
            console_service_logger.info(
                "Deleting partner with id: {}".format(partner_id)
            )
            current_user: dict = request.state.user
            await partner_service.delete_partner_by_id(partner_id, current_user)
            console_service_logger.info(
                "Partner with id {} is now deleted.".format(partner_id)
            )
            return SuccessResponse(PartnerResponseData.DELETE_PARTNER)

        except PartnerException as ex:
            console_service_logger.error(
                "The partner with id {} is not found in the database.".format(
                    partner_id
                )
            )
            return NotFoundResponse(str(ex))
        except Exception as e:
            console_service_logger.error(
                "An unexpected error occurred: {}".format(str(e))
            )
            return InternalServerErrorResponse(ErrorMsg.INTERNAL_SERVER_ERROR)

    @partner_router.patch(
        "/partner/{partner_id}",
        response_model=PartnerResponse,
        status_code=status.HTTP_200_OK,
    )
    @permission_check(PermissionDependency)
    @inject
    async def update_partner(
        request: Request,
        partner_id: UUID,
        partner_data: UpdatePartnerRequest = Body(...),
        partner_service: PartnerService = Depends(Provide[Container.partner_service]),
        console_service_logger: ConsoleServiceLogger = Depends(
            Provide[Container.console_service_logger]
        ),
    ):
        try:
            console_service_logger.info(
                "Received update request for partner id {} with data: {}".format(
                    partner_id, partner_data
                )
            )
            current_user: dict = request.state.user

            updated_partner = await partner_service.update_partner(
                partner_id, partner_data, current_user
            )
            console_service_logger.info(
                "Partner updated successfully: {}".format(updated_partner)
            )

            return SuccessResponse(
                {**PartnerResponse.model_validate(updated_partner).model_dump()}
            )
        except PartnerNotFoundError as ex:
            console_service_logger.error("Partner not found: {}".format(repr(ex)))
            return NotFoundResponse(str(ex))

        except PartnerException as ex:
            console_service_logger.error(
                "Unexpected error while updating partner: {}".format(repr(ex))
            )
            return BadRequestResponse(PartnerResponseData.PARTNER_EXIST)

        except Exception as ex:
            console_service_logger.error("Error updating partner: {}".format(repr(ex)))
            return InternalServerErrorResponse(ErrorMsg.INTERNAL_SERVER_ERROR)

    @partner_router.get("/get_partner_statuses")
    @permission_check(PermissionDependency)
    @inject
    async def get_partner_statuses(
        request: Request,
        partner_service: PartnerService = Depends(Provide[Container.partner_service]),
        console_service_logger: ConsoleServiceLogger = Depends(
            Provide[Container.console_service_logger]
        ),
    ):
        """SuccessResponse[List[str]]
        Get the list of all partner statuses.

        Args:
            partner_service: Service for handling partner-related logic.
            console_service_logger: Logger instance for service logging.

        Returns:
            SuccessResponse: A response containing the list of partner statuses.
        """
        try:
            current_user: dict = request.state.user
            current_user_id: UUID = current_user.get("user_id")
            console_service_logger.info(
                "Received request to get partner statuses by user id: {}".format(
                    current_user_id
                )
            )
            statuses = partner_service.get_partner_statuses()
            return SuccessResponse(data=statuses)
        except Exception as exc:
            console_service_logger.error(
                f"Unexpected error while getting partner statuses by user_id: {current_user_id}, error: {exc}"
            )
            return InternalServerErrorResponse()

    @partner_router.put(
        "/change_partner_status", response_model=ChangePartnerStatusResponse
    )
    @permission_check(PermissionDependency)
    @inject
    async def change_partner_status(
        request: Request,
        status_data: ChangePartnerStatusRequest,
        partner_service: PartnerService = Depends(Provide[Container.partner_service]),
        console_service_logger: ConsoleServiceLogger = Depends(
            Provide[Container.console_service_logger]
        ),
    ):
        """
        Change the status and/or is_feedback_enabled flag of a partner.

        Args:
            request: The incoming HTTP request.
            status_data: Request body containing partner_id, status, and is_feedback_enabled.
            partner_service: Service for handling partner-related logic.
            console_service_logger: Logger instance for service logging.

        Returns:
            SuccessResponse: A response containing the updated partner details.
        """
        try:
            console_service_logger.info(
                f"Received request to change partner status for partner_id={status_data.partner_id}, "
                f"status={status_data.status}, is_feedback_enabled={status_data.is_feedback_enabled}"
            )
            updated_partner = await partner_service.change_partner_status(
                status_data.partner_id,
                status_data.status,
                status_data.is_feedback_enabled,
            )
            return SuccessResponse(data=updated_partner)

        except PartnerStatusUnchangedException as ex:
            console_service_logger.info(
                "Partner id: {} status remins unchanged due to same status: {}".format(
                    status_data.partner_id, ex
                )
            )
            return ResourceConflictResponse(detail=messages.PARTNER_STATUS_UNCHANGED)
        except PartnerException as ex:
            console_service_logger.error(
                "The partner with id {} is not found in the database.".format(
                    status_data.partner_id
                )
            )
            return NotFoundResponse(str(ex))
        except Exception as exc:
            console_service_logger.error(
                f"Unexpected error while changing partner status for partner_id={status_data.partner_id}: {exc}"
            )
            return InternalServerErrorResponse()

    @partner_router.post("/onboard_partner", response_model=PartnerOnboardingResponse)
    @inject
    async def onboard_partner(
        request: Request,
        partner_data: PartnerOnboardingDetails = Body(...),
        partner_service: PartnerService = Depends(Provide[Container.partner_service]),
        console_service_logger: ConsoleServiceLogger = Depends(
            Provide[Container.console_service_logger]
        ),
    ):
        try:
            console_service_logger.info(
                "Attempting to onboard free trial partner{}".format(
                    partner_data.partner_details
                )
            )
            created_partner: PartnerOnboardingResponse = (
                await partner_service.onboard_partner(request, partner_data)
            )
            return ResourceCreatedResponse(created_partner)
        except PartnerException as exc:
            console_service_logger.error(
                "Error occurred while onboarding free trial partner, error: {}.".format(
                    str(exc)
                )
            )
            return BadRequestResponse(str(exc))
        except Exception as ex:
            console_service_logger.error("Error creating partner: {}".format(repr(ex)))
            return InternalServerErrorResponse(ErrorMsg.INTERNAL_SERVER_ERROR)

    @partner_router.patch(
        "/partner/{partner_id}/toggle_activation",
        response_model=TogglePartnerActivationResponse,
    )
    @permission_check(PermissionDependency)
    @inject
    async def toggle_partner_activation(
        request: Request,
        partner_id: UUID,
        partner_data: TogglePartnerActivation = Body(...),
        partner_service: PartnerService = Depends(Provide[Container.partner_service]),
        console_service_logger: ConsoleServiceLogger = Depends(
            Provide[Container.console_service_logger]
        ),
    ):
        try:
            console_service_logger.info(
                "Received update request for partner id {} with data: {}".format(
                    partner_id, partner_data
                )
            )
            current_user: dict = request.state.user
            partner_status: TogglePartnerActivationResponse = (
                await partner_service.toggle_partner_activation(
                    current_user, partner_id, partner_data
                )
            )
            console_service_logger.info(
                "Partner updated successfully: {}".format(partner_status)
            )
            return SuccessResponse(data=partner_status)

        except PartnerNotFoundError as ex:
            console_service_logger.error("Partner not found: {}".format(repr(ex)))
            return NotFoundResponse(str(ex))

        except PartnerException as exec:
            console_service_logger.error(
                "Partner exception occured: {}".format(str(exec))
            )
            return BadRequestResponse(detail=str(exec))

        except Exception as ex:
            console_service_logger.error("Error updating partner: {}".format(repr(ex)))
            return InternalServerErrorResponse(ErrorMsg.INTERNAL_SERVER_ERROR)
