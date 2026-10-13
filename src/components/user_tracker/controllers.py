from uuid import UUID
from dependency_injector.wiring import Provide, inject
from fastapi import APIRouter, Body, Depends, Request

from src.components.common.constants import CurrentUserMap
from src.components.common.response import (
    BadRequestResponse,
    ForbiddenResponse,
    InternalServerErrorResponse,
    NotFoundResponse,
    ResourceConflictResponse,
    SuccessResponse,
)
from src.components.rbac.permission_injector import permission_check
from src.components.user_tracker.constants import UserTrackerResponseMsg
from src.components.user_tracker.errors import (
    CustomStatusAlreadyExistsError,
    CustomStatusValidationError,
    InvalidStatusError,
    UnauthorizedCustomStatusAccessError,
    UserTrackerNotFoundError,
)
from src.components.user_tracker.schema import (
    UpdateCustomStatusesRequest,
    UpdateCustomStatusesResponse,
    UpdateUserStatusRequest,
    UpdateUserStatusResponse,
    UserAvailabilityStatusResponse,
)
from src.components.user_tracker.services import UserTrackerService
from src.components.user.repositories import UserRepository
from src.core.container import Container
from src.loggers.console_service_logger import ConsoleServiceLogger


class UserTrackerController:
    user_tracker_router = APIRouter()

    @user_tracker_router.get("/user-tracker/status")
    @permission_check("console:get_user_availability_status")
    @inject
    async def get_user_availability_status(
        request: Request,
        user_tracker_service: UserTrackerService = Depends(
            Provide[Container.user_tracker_service]
        ),
        console_service_logger: ConsoleServiceLogger = Depends(
            Provide[Container.console_service_logger]
        ),
    ):
        """
        All authenticated roles.

        Returns:
          - current_status
          - standard_statuses
          - custom_statuses
        """
        try:
            current_user: dict = request.state.user
            user_id: UUID = current_user.get(CurrentUserMap.USER_ID)
            partner_id: UUID = current_user.get(CurrentUserMap.PARTNER_ID)

            result: UserAvailabilityStatusResponse = (
                await user_tracker_service.get_user_availability_status(
                    user_id, partner_id
                )
            )
            return SuccessResponse(data=result)

        except UserTrackerNotFoundError as exc:
            console_service_logger.error(
                f"[UserTrackerController] User not found: {exc}"
            )
            return NotFoundResponse(detail=str(exc))
        except Exception as exc:
            console_service_logger.error(
                f"[UserTrackerController] Unexpected error on GET /user-tracker/status: {exc}"
            )
            return InternalServerErrorResponse()

    @user_tracker_router.put("/user-tracker/status")
    @permission_check("console:update_user_availability_status")
    @inject
    async def update_user_availability_status(
        request: Request,
        body: UpdateUserStatusRequest = Body(...),
        user_tracker_service: UserTrackerService = Depends(
            Provide[Container.user_tracker_service]
        ),
        console_service_logger: ConsoleServiceLogger = Depends(
            Provide[Container.console_service_logger]
        ),
    ):
        """
        All authenticated roles. User updates their own status only.
        status_icon is only editable for custom statuses — standard statuses'
        icons are fixed and any status_icon value is ignored for them.
        """
        try:
            current_user: dict = request.state.user
            user_id: UUID = current_user.get(CurrentUserMap.USER_ID)
            partner_id: UUID = current_user.get(CurrentUserMap.PARTNER_ID)

            result: UpdateUserStatusResponse = (
                await user_tracker_service.update_user_status(
                    user_id, partner_id, body.status, body.status_icon
                )
            )
            return SuccessResponse(data=result)

        except CustomStatusValidationError as exc:
            console_service_logger.error(
                f"[UserTrackerController] Validation error: {exc}"
            )
            return BadRequestResponse(detail=str(exc))
        except InvalidStatusError as exc:
            console_service_logger.error(
                f"[UserTrackerController] Invalid status: {exc}"
            )
            return NotFoundResponse(detail=str(exc))
        except UserTrackerNotFoundError as exc:
            console_service_logger.error(
                f"[UserTrackerController] User not found: {exc}"
            )
            return NotFoundResponse(detail=str(exc))
        except Exception as exc:
            console_service_logger.error(
                f"[UserTrackerController] Unexpected error on PUT /user-tracker/status: {exc}"
            )
            return InternalServerErrorResponse()

    @user_tracker_router.put("/user-tracker/custom-status")
    @permission_check("console:update_custom_statuses")
    @inject
    async def update_custom_statuses(
        request: Request,
        body: UpdateCustomStatusesRequest = Body(...),
        user_tracker_service: UserTrackerService = Depends(
            Provide[Container.user_tracker_service]
        ),
        user_repository: UserRepository = Depends(
            Provide[Container.user_repository]
        ),
        console_service_logger: ConsoleServiceLogger = Depends(
            Provide[Container.console_service_logger]
        ),
    ):
        """
        Admin role only.
        """
        try:
            current_user: dict = dict(request.state.user)
            user_id: UUID = current_user.get(CurrentUserMap.USER_ID)
            partner_id: UUID = current_user.get(CurrentUserMap.PARTNER_ID)

            # role_hierarchy_level is not carried in the JWT — always resolve the
            # user's current role fresh from the DB by their user_id.
            user_details = await user_repository.get_user_details(user_id)
            current_user[CurrentUserMap.ROLE_HIERARCHY_LEVEL] = (
                user_details.get(CurrentUserMap.ROLE_HIERARCHY_LEVEL) if user_details else None
            )

            result: UpdateCustomStatusesResponse = (
                await user_tracker_service.update_custom_statuses(
                    current_user=current_user,
                    partner_id=partner_id,
                    updated_by=user_id,
                    edit_custom_statuses=body.edit_custom_statuses or {},
                    add_custom_statuses=body.add_custom_statuses or [],
                )
            )
            return SuccessResponse(data=result)

        except CustomStatusValidationError as exc:
            console_service_logger.error(
                f"[UserTrackerController] Validation error: {exc}"
            )
            return BadRequestResponse(detail=str(exc))
        except CustomStatusAlreadyExistsError as exc:
            console_service_logger.error(
                f"[UserTrackerController] Conflict: {exc}"
            )
            return ResourceConflictResponse(detail=str(exc))
        except UnauthorizedCustomStatusAccessError as exc:
            console_service_logger.error(
                f"[UserTrackerController] Forbidden: {exc}"
            )
            return ForbiddenResponse(detail=str(exc))
        except Exception as exc:
            console_service_logger.error(
                f"[UserTrackerController] Unexpected error on PUT /user-tracker/custom-status: {exc}"
            )
            return InternalServerErrorResponse()
