"""Controller module."""

import csv
import io
from dependency_injector.wiring import Provide, inject
from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse

from src.components.common.constants import CurrentUserMap
from src.components.user.bulk_upload_utils import build_bulk_upload_headers
from src.components.user.constants import FileContent

from typing import List, Optional, Dict, Any
import base64
import uuid
from uuid import UUID
from src.components.user.helpers import validate_csv_content
from src.components.user.constants import ValidationMsg
from src.components.user.helpers import validate_bulk_upload_data_rows
from src.components.user.helpers import validate_bulk_upload_file
from src.components.user.helpers import validate_bulk_upload_headers
from fastapi import APIRouter, Body, Depends, Header, HTTPException, Query, Request
from fastapi import status
from fastapi import status as http_status, UploadFile, File
from celery.result import AsyncResult
from fastapi.encoders import jsonable_encoder
from pydantic import EmailStr
from src.components.partner.error import PartnerNotFoundError
from src.components.partner.repositories import PartnerRepository

from src.components.user.tasks import create_bulk_users
from src.components.user.constants import FileContent, TextPrompt
from src.components.user.schema import TaskStartResponse
from src.components.user.repositories import UserRepository

from src.components.auth.constant import TokenKeys
from src.components.auth.error import RoleNotFoundError
from src.components.auth.schema import UserDataResponse, UserNewResponse
from src.components.common.errors import ErrorMsg
from src.components.common.response import (
    BadRequestResponse,
    ForbiddenResponse,
    InternalServerErrorResponse,
    NotFoundResponse,
    ResourceConflictResponse,
    SuccessResponse,
    ValidationErrorResponse,
    UnauthorizedResponse,
    InvalidFileFormat,
    InvalidPartnerResponse,
)
from src.components.location.errors import (
    CityNotFoundError,
    CountryNotFoundError,
    StateNotFoundError,
)
from src.components.rbac.constant import PermissionErrorText
from src.components.rbac.permission_injector import permission_check
from src.components.user.constants import PaginationConstants, UserResponseMsg
from src.components.user.errors import UserNotFoundError
from src.components.user.schema import (
    BulkUserCreateRequest,
    Contrasts,
    PaginatedUserRoleResponse,
    UserRoleFilterRequest,
)
from src.components.user.services import ApiKeyNotFoundError, User, UserService
from src.components.user_tracker.errors import InvalidStatusError
from src.components.filters.criteria import BaseFilterCriteria
from src.core.container import Container
from src.exceptions import AuthException, UserException
from src.loggers.console_service_logger import ConsoleServiceLogger


class UserController:
    # User controller, all user related endpoints will be in this class.
    user_router = APIRouter()

    @user_router.get("/users", response_model=List[UserDataResponse])
    @permission_check("console:get_all_users")
    @inject
    async def get_all_users(
        request: Request,
        offset: int = Query(
            PaginationConstants.offset,
            ge=PaginationConstants.offset,
            description="Page number for pagination",
        ),
        limit: int = Query(
            PaginationConstants.limit,
            ge=PaginationConstants.offset,
            le=PaginationConstants.LIMIT_MAX,
            description="Number of items per page",
        ),
        filter_by_fields: List[str] = Query(
            default=[],
            description=(
                "User Listing column to filter on. Repeat once per filter, "
                "lining up positionally with operators and values. Supported: "
                "status/is_active, role/role_id/role_name, "
                "availability/current_status, created_at, updated_at, and the "
                "other listing columns."
            ),
        ),
        operators: List[str] = Query(
            default=[],
            description=(
                "Operator for the filter at the same position. Words or symbols: "
                "EQUALS (=), NOT_EQUALS (!=), BEFORE (<), AFTER (>), <=, >=, "
                "LIKE, IN, BETWEEN."
            ),
        ),
        values: List[str] = Query(
            default=[],
            description=(
                "Value for the filter at the same position. Dates accept epoch "
                "milliseconds or YYYY-MM-DD / DD-MMM-YYYY, and a date without a "
                "time covers the whole day. BETWEEN takes two comma separated "
                "values, e.g. values=2026-08-01,2026-08-10."
            ),
        ),
        console_service: UserService = Depends(Provide[Container.console_service]),
        console_service_logger: ConsoleServiceLogger = Depends(
            Provide[Container.console_service_logger]
        ),
    ):
        """
        Get paginated users under the current user's hierarchy.

        Filters are optional and combine with AND; sending none returns the
        existing full authorized listing unchanged.

        Args:
            request: FastAPI request with user auth details.
            offset: Pagination start (default: 0).
            limit: Users per page (default: 10, max: 100).
            filter_by_fields: Listing columns to filter on.
            operators: Operator per filter, positionally aligned.
            values: Value per filter, positionally aligned.
            console_service: User service instance.
            console_service_logger: Logger instance.

        Returns:
            SuccessResponse: List of user data.

        Raises:
            HTTPException: 403 for permission errors.
            Exception: 500 for other errors.
        """
        try:
            console_service_logger.info("Getting all the users from database")
            current_user = request.state.user
            current_user_id = current_user.get(TokenKeys.USER_ID)

            try:
                filter_criteria = BaseFilterCriteria.from_query_params(
                    filter_by_fields, operators, values
                )
            except ValueError as invalid_filters:
                console_service_logger.error(
                    "Invalid filter parameters: {}".format(invalid_filters)
                )
                return BadRequestResponse(detail=str(invalid_filters))

            all_users = await console_service.get_users(
                current_user_id, limit, offset, filter_criteria=filter_criteria
            )
            console_service_logger.info(
                "Fetched all users under user: {}".format(current_user_id)
            )
            return SuccessResponse(all_users)

        except HTTPException as http_exc:
            if http_exc.status_code == 403:
                console_service_logger.error(
                    f"Forbidden (403) error: {http_exc.detail}"
                )
                return ForbiddenResponse(detail=PermissionErrorText.PERMISSION_DENIED)

        except UserException as user_exc:
            console_service_logger.error(f"User exception occurred: {user_exc}")
            if filter_by_fields:
                return BadRequestResponse(detail=str(user_exc))
            return NotFoundResponse(detail=str(user_exc))

        except Exception as e:
            console_service_logger.error("Error fetching users {}".format(e))
            return InternalServerErrorResponse(
                PermissionErrorText.INTERNAL_SERVER_ERROR
            )

    @user_router.get("/get_users_by_partner", response_model=UserNewResponse)
    @permission_check("console:get_users_by_partner_id")
    @inject
    async def get_users_by_partner_id(
        request: Request,
        partner_id: UUID = Query(..., description="ID of the Partner"),
        console_service: UserService = Depends(Provide[Container.console_service]),
        console_service_logger: ConsoleServiceLogger = Depends(
            Provide[Container.console_service_logger]
        ),
    ):
        try:
            console_service_logger.info(
                "Attempting to get users for partner: {}".format(partner_id)
            )
            users: dict = await console_service.get_users_by_partner_id(partner_id)
            user_response = [UserNewResponse(**user) for user in users]
            return SuccessResponse(jsonable_encoder(user_response))
        except PartnerNotFoundError as ex:
            console_service_logger.error(
                "Partner not found: {}, error: {}".format(partner_id, repr(ex))
            )
            return NotFoundResponse(str(ex))
        except Exception as ex:
            console_service_logger.error(
                "Unexpected error during get users by partner id: {}".format(repr(ex))
            )
            return InternalServerErrorResponse(ErrorMsg.INTERNAL_SERVER_ERROR)

    @user_router.delete("/user/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
    @permission_check("console:delete_user")
    @inject
    async def delete_user(
        request: Request,
        user_id: UUID,
        console_service: UserService = Depends(Provide[Container.console_service]),
        console_service_logger: ConsoleServiceLogger = Depends(
            Provide[Container.console_service_logger]
        ),
    ):
        try:
            console_service_logger.info("Deleting user with id: {}".format(user_id))
            await console_service.delete_user_by_id(request, user_id)
            console_service_logger.info(
                "user with id {} is now deleted.".format(user_id)
            )
            return SuccessResponse(UserResponseMsg.DELETE_USER)
        except UserException as exc:
            console_service_logger.error(
                "Error occurred while deleting user: {}".format(exc)
            )
            return ValidationErrorResponse(detail=str(exc))
        except UserNotFoundError as e:
            console_service_logger.error("User not found: {}".format(e))
            return NotFoundResponse(detail=str(e))
        except Exception as e:
            console_service_logger.error("Error deleting user {}".format(e))
            return InternalServerErrorResponse(ErrorMsg.INTERNAL_SERVER_ERROR)

    @user_router.patch(
        "/user/{user_id}",
        response_model=UserDataResponse,
        status_code=status.HTTP_200_OK,
    )
    @permission_check("console:update_user")
    @inject
    async def update_user(
        request: Request,
        user_id: UUID,
        user_data: Contrasts.UpdateUserData = Body(...),
        console_service: UserService = Depends(Provide[Container.console_service]),
        console_service_logger: ConsoleServiceLogger = Depends(
            Provide[Container.console_service_logger]
        ),
    ):
        try:
            console_service_logger.info(
                "Received update request for user id {} with data: {}".format(
                    user_id, user_data
                )
            )
            current_user: Dict = request.state.user

            updated_user = await console_service.update_user(
                user_id, current_user, user_data
            )
            console_service_logger.info(
                "User updated successfully: {}".format(updated_user)
            )

            return SuccessResponse(
                jsonable_encoder(UserDataResponse.model_validate(updated_user))
            )
        except AuthException as ex:
            console_service_logger.error(
                "Unexpected error during signup: {}".format(str(ex))
            )
            return ResourceConflictResponse(str(ex))
        except PartnerNotFoundError as exc:
            console_service_logger.error(
                "Partner not found while creating new user: {}".format(str(exc))
            )
            return NotFoundResponse(str(exc))
        except RoleNotFoundError as exc:
            console_service_logger.error(
                "Role not found while creating new user: {}".format(str(exc))
            )
            return NotFoundResponse(str(exc))
        except CountryNotFoundError as exc:
            console_service_logger.error(
                "Country not found while creating new user: {}".format(str(exc))
            )
            return NotFoundResponse(str(exc))
        except StateNotFoundError as exc:
            console_service_logger.error(
                "State not found while creating new user: {}".format(str(exc))
            )
            return NotFoundResponse(str(exc))
        except CityNotFoundError as exc:
            console_service_logger.error(
                "City not found while creating new user: {}".format(str(exc))
            )
            return NotFoundResponse(str(exc))
        except UserException as exec:
            console_service_logger.error(
                "User exception occurred while updating new user: {}".format(str(exec))
            )
            return ResourceConflictResponse(detail=str(exec))
        except UserNotFoundError as e:
            console_service_logger.error("User not found: {}".format(e))
            return NotFoundResponse(detail=str(e))
        except InvalidStatusError as exc:
            console_service_logger.error(
                "Invalid current_status while updating user: {}".format(str(exc))
            )
            return NotFoundResponse(detail=str(exc))
        except Exception as e:
            console_service_logger.error("Error updating user {}".format(e))
            return InternalServerErrorResponse(ErrorMsg.INTERNAL_SERVER_ERROR)

    @user_router.get(
        "/user/get_by_id/{user_id}", response_model=Contrasts.GetUserDetailResponse
    )
    @permission_check("console:get_user_by_user_id")
    @inject
    async def get_user_by_user_id(
        request: Request,
        user_id: UUID,
        console_service: UserService = Depends(Provide[Container.console_service]),
        console_service_logger: ConsoleServiceLogger = Depends(
            Provide[Container.console_service_logger]
        ),
    ):
        try:
            current_user: dict = request.state.user
            current_user_partner_id: UUID = current_user.get(CurrentUserMap.PARTNER_ID)
            console_service_logger.info(
                "Attempting to fetch the user by id: {}".format(user_id)
            )
            user: Contrasts.GetUserDetailResponse = (
                await console_service.get_user_by_user_id(
                    user_id, current_user_partner_id
                )
            )
            return SuccessResponse(data=user)
        except UserNotFoundError as exec:
            console_service_logger.error(
                "User not found for user with id: {}".format(user_id)
            )
            return NotFoundResponse(detail=UserResponseMsg.USER_NOT_FOUND)
        except Exception as exec:
            console_service_logger.error(
                "An unexpected error occured while fetching the user: {}".format(exec)
            )
            return InternalServerErrorResponse()

    @user_router.get(
        "/user/get_by_partner_id/{partner_id}",
        response_model=Contrasts.GetUserDetailResponse,
    )
    @permission_check("console:get_admin_details_by_partner_id")
    @inject
    async def get_admin_details_by_partner_id(
        request: Request,
        partner_id: UUID,
        console_service: UserService = Depends(Provide[Container.console_service]),
        console_service_logger: ConsoleServiceLogger = Depends(
            Provide[Container.console_service_logger]
        ),
    ):
        try:
            console_service_logger.info(
                "Attempting to fetch the admin user by partner id: {}".format(
                    partner_id
                )
            )
            user: Contrasts.GetUserDetailResponse = (
                await console_service.get_admin_details_by_partner_id(partner_id)
            )
            return SuccessResponse(data=user)
        except UserException as exec:
            console_service_logger.error(
                "User exception occurred while fetching the user: {}".format(str(exec))
            )
            return NotFoundResponse(detail=str(exec))
        except Exception as exec:
            console_service_logger.error(
                "An unexpected error occured while fetching the user: {}".format(exec)
            )
            return InternalServerErrorResponse()

    @user_router.post(
        "/enlist_users_dynamically", response_model=PaginatedUserRoleResponse
    )
    @permission_check("console:enlist_users_dynamically")
    @inject
    async def enlist_users_dynamically(
        request: Request,
        filter_request: UserRoleFilterRequest = Body(...),
        console_service: UserService = Depends(Provide[Container.console_service]),
        console_service_logger: ConsoleServiceLogger = Depends(
            Provide[Container.console_service_logger]
        ),
    ):
        try:
            console_service_logger.info(
                "Attempting to get users for partner: {}".format(
                    filter_request.partner_id
                )
            )
            current_user: dict = request.state.user

            users: dict = await console_service.enlist_users_dynamically(
                current_user, filter_request
            )

            return SuccessResponse(users)
        except PartnerNotFoundError as ex:
            console_service_logger.error(
                "Partner not found: {}, error: {}".format(
                    filter_request.partner_id, repr(ex)
                )
            )
            return NotFoundResponse(str(ex))
        except UserException as user_exc:
            console_service_logger.error(
                "User exception occurred while getting users by partner_id: {}".format(
                    str(user_exc)
                )
            )
            return BadRequestResponse(detail=str(user_exc))
        except Exception as ex:
            console_service_logger.error(
                "Unexpected error during get users by partner id: {}".format(repr(ex))
            )
            return InternalServerErrorResponse(ErrorMsg.INTERNAL_SERVER_ERROR)

    @user_router.get("/{partner_id}/user/{ivr_phone}/get_user_details_by_ivr")
    @inject
    async def get_user_details_by_ivr(
        request: Request,
        ivr_phone: str,
        partner_id: UUID,
        console_service: UserService = Depends(Provide[Container.console_service]),
        console_service_logger: ConsoleServiceLogger = Depends(
            Provide[Container.console_service_logger]
        ),
        x_api_key: Optional[str] = Header(default=None),
    ):
        try:
            if partner_id is None or ivr_phone is None:
                return BadRequestResponse(
                    detail="partner_id or ivr_number not provided"
                )

            user_info: dict = await console_service.get_agent_details_by_IVR(
                partner_id=partner_id, ivr_phone=ivr_phone, api_key=x_api_key
            )
            return SuccessResponse(data=user_info)

        except ApiKeyNotFoundError as apiexc:
            console_service_logger.error("invalid API_KEY given")
            return NotFoundResponse(detail="API_KEY is not valid")

        except UserNotFoundError as exc:
            console_service_logger.error(
                "User not found while getting user deails for ivr_phone: {}".format(
                    ivr_phone
                )
            )
            return NotFoundResponse(detail=UserResponseMsg.USER_NOT_FOUND)
        except Exception as exp:
            return InternalServerErrorResponse()

    # =========================================================
    # BULK USER UPLOAD
    # =========================================================
    @user_router.post(
        "/users/bulk_upload",
        response_model=TaskStartResponse,
        status_code=status.HTTP_202_ACCEPTED,
    )
    @permission_check("console:bulk_upload_users")
    @inject
    async def bulk_upload_users(
        request: Request,
        input_file: UploadFile = File(..., description="File to be processed"),
        console_service_logger: ConsoleServiceLogger = Depends(
            Provide[Container.console_service_logger]
        ),
        user_repository: UserRepository = Depends(
            Provide[Container.user_repository]
        ),
        partner_repository: PartnerRepository = Depends(
            Provide[Container.partner_repository]
        ),
        console_service: UserService = Depends(
            Provide[Container.console_service]
        ),
    ) -> TaskStartResponse:
        try:
            current_user: Optional[Dict[str, Any]] = getattr(request.state, "user", None)

            if not current_user:
                console_service_logger.error(
                    "Unauthorized request - user missing in state"
                )
                return UnauthorizedResponse("User not authenticated")

            user_id: UUID = current_user.get(CurrentUserMap.USER_ID)
            partner_id: UUID = current_user.get(CurrentUserMap.PARTNER_ID)

            if not partner_id:
                return InvalidPartnerResponse("Partner is not found")

            # Get hierarchy
            current_user_hierarchy: Optional[int] = current_user.get(
                CurrentUserMap.ROLE_HIERARCHY_LEVEL
            )

            if current_user_hierarchy is None:
                user = await user_repository.get_user_details(user_id)
                   
                if not user :
                    console_service_logger.error(
                        "User not found for user_id=%s", user_id
                    )
                    return UnauthorizedResponse("User not found")
                
                # Safe handling
                current_user_hierarchy: Optional[int] = user.get("role_hierarchy_level")   
                
                if current_user_hierarchy is None:  
                    console_service_logger.error(
                        "Role not found for user_id=%s", user_id
                    )
                    return UnauthorizedResponse("User role not found")
            
            # Authorization check 
            allowed_hierarchy = {
                CurrentUserMap.SUPER_ADMIN_ROLE_HIERARCHY_LEVEL,  # 0
                CurrentUserMap.ADMIN_ROLE_HIERARCHY_LEVEL,        # 1
                CurrentUserMap.MAINTAINER_ROLE_HIERARCHY_LEVEL,   # 3
            }

            if current_user_hierarchy not in allowed_hierarchy:
                console_service_logger.error(
                    "Unauthorized bulk upload attempt by user_id=%s with hierarchy=%s",
                    user_id, current_user_hierarchy,
                )
                return UnauthorizedResponse(
                    "Only Super Admin, Admin and Maintainer can upload users"
                )
            # =========================
            # Validate file type (CSV only)
            # =========================
            allowed_types: List[str] = FileContent.FILE_CONTENT_TYPE
            filename: str = (input_file.filename or "").lower()
            
            is_valid_type: bool = input_file.content_type in allowed_types
            is_valid_extension = filename.endswith(".csv") or filename.endswith(".xlsx")


            if not (is_valid_type and is_valid_extension):
                console_service_logger.warning(
                    "Invalid file type uploaded by user_id=%s content_type=%s filename=%s",
                    user_id, input_file.content_type, filename,
                )
                return BadRequestResponse(detail=ValidationMsg.ONLY_CSV_SUPPORTED)

            # =========================
            # Read file (ONLY ONCE)
            # =========================
            file_bytes: bytes = await input_file.read()

            if not file_bytes or not file_bytes.strip():
                return BadRequestResponse(detail=TextPrompt.FILE_EMPTY)

            # =========================
            # Validate partner_id exists FIRST
            # (feature-flag lookup below needs a real partner)
            # =========================
            try:
                await partner_repository.get_by_id(partner_id)
            except PartnerNotFoundError:
                console_service_logger.warning(
                    "Invalid partner_id=%s provided by user_id=%s", partner_id, user_id
                )
                return InvalidPartnerResponse()

            # =========================
            # Fetch partner feature flags (teams / custom roles)
            # =========================
            flags: dict = await console_service.get_bulk_upload_feature_flags(partner_id)

            # =========================
            # Validate CSV headers / content (flag-aware)
            # =========================
            try:
                validate_csv_content(file_bytes, filename)
                validate_bulk_upload_headers(file_bytes, filename, flags)
                validate_bulk_upload_data_rows(file_bytes, filename)

            except ValueError as exc:
                return BadRequestResponse(detail=str(exc))

            
            # =========================
            # File size validation 
            # =========================
            MAX_BULK_UPLOAD_BYTES = 5 * 1024 * 1024  # 5MB

            if len(file_bytes) > MAX_BULK_UPLOAD_BYTES:
                console_service_logger.warning(
                    "File too large uploaded by user_id=%s size=%s", user_id, len(file_bytes)
                )
                return BadRequestResponse(
                    detail="File too large; max allowed is %s MB"
                    % (MAX_BULK_UPLOAD_BYTES // (1024 * 1024))
                )

            # Convert file bytes to base64 — no shared folder needed
            file_data_b64: str = base64.b64encode(file_bytes).decode("utf-8")

            console_service_logger.info(
                "File read successfully size=%s bytes user_id=%s", len(file_bytes), user_id
            )

            # Call Celery
            task = create_bulk_users.apply_async(
                kwargs={
                    "current_user": current_user,
                    "file_data_b64": file_data_b64,
                    "partner_id": partner_id,
                    "filename": filename,
                }
            )
            console_service_logger.info(
                "Task triggered successfully task_id=%s by user_id=%s", task.id, user_id
            )

            return TaskStartResponse(
                task_id=task.id,
                message="User creation process started.",
            )

        except ValueError as exc:
            console_service_logger.error("Error while processing file: %s", exc)
            return BadRequestResponse(str(exc))

        except Exception as exc:
            console_service_logger.error("Unexpected error in bulk upload: %s", repr(exc))
            return InternalServerErrorResponse()

    @user_router.post(
        "/users/bulk_create",
        include_in_schema=False,
    )
    @permission_check("console:bulk_create_users")
    @inject
    async def bulk_create_users(
        request: Request,
        body: BulkUserCreateRequest,
        user_service: UserService = Depends(Provide[Container.console_service]),
        console_service_logger: ConsoleServiceLogger = Depends(
            Provide[Container.console_service_logger]
        ),
    ):
        """
        Create a batch of users in a single atomic transaction.

        Request body: BulkUserCreateRequest
        - users: list of user dicts (sequence, name, email, phone, password,
                role_id, partner_id, optional fields…)
        - parent_resolution: list of {sequence, parent_sequence} entries
                covering every user in the batch.

        Response: {message, data: {created_users: [{sequence, user_id, email}], total}}
        """

        try:
            # Partner comes from the authenticated token, never from headers
            # or body — every created user lands in the caller's partner.
            token_partner_id = request.state.user.get(CurrentUserMap.PARTNER_ID)
            result = await user_service.bulk_create(
                body, requesting_partner_id=token_partner_id
            )
        except ValueError as exc:
            raise HTTPException(
                status_code=http_status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=str(exc),
            ) from exc
        except Exception as exc:
            console_service_logger.error(
                "Unexpected error in bulk_create_users for partner={}: {}".format(
                    partner_id, exc
                )
            )
            raise HTTPException(
                status_code=http_status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="An unexpected error occurred. Please try again.",
            ) from exc

        return {
            "message": "Users created successfully.",
            "data": result,
        }
        
    # =========================================================
    # BULK UPLOAD RESULT 
    # =========================================================
    @user_router.get("/users/bulk_upload/result/{task_id}")
    @permission_check("console:get_bulk_upload_result")
    @inject
    async def get_bulk_upload_result(
        request: Request,
        task_id: str,
        console_service_logger: ConsoleServiceLogger = Depends(
            Provide[Container.console_service_logger]
        ),
    )-> SuccessResponse:
        """
        Get bulk upload result by task_id.
 
        Returns:
        - status: processing / completed / failed
        - total_success_count
        - total_failed_count
        - failed_reasons: list of failed rows with row_number, email, name, reason
        """
        try:
            # =========================
            # Validate task_id
            # =========================
            if not task_id or not task_id.strip():
                return BadRequestResponse("task_id is required")
            try:
                uuid.UUID(task_id.strip())
            except ValueError:
                console_service_logger.warning(
                    "Invalid task_id format provided: %s", task_id
                )
                return BadRequestResponse(detail="Invalid task_id format")


            task = AsyncResult(task_id)
 
            # Still running
            if task.state == "PENDING":
                return SuccessResponse({
                    "task_id": task_id,
                    "status": "processing",
                    "total_success_count": None,
                    "total_failed_count": None,
                    "download_url": None,
                })
 
            # Celery level failure
            if task.state == "FAILURE":
                console_service_logger.error(
                    "Bulk upload task failed at celery level task_id=%s", task_id
                )
                return SuccessResponse({
                    "task_id": task_id,
                    "status": "failed",
                    "total_success_count": 0,
                    "total_failed_count": 0,
                    "download_url": None,
                })
            # Task completed
            if task.state == "SUCCESS":
                result: Any = task.result

                console_service_logger.info(
                    "Bulk upload result fetched task_id=%s success=%s failed=%s",
                    task_id,
                    result.get("total_success_count"),
                    result.get("total_failed_count"),
                )

                return SuccessResponse({
                    "task_id": task_id,
                    "status": "completed",
                    "total_success_count": result.get("total_success_count", 0),
                    "total_failed_count": result.get("total_failed_count", 0),
                })
 
            return SuccessResponse({
                "task_id": task_id,
                "status": task.state.lower(),
                "total_success_count": None,
                "total_failed_count": None,
                "download_url": None,
            })
 
        except Exception as exc:
            console_service_logger.error(
                "Error fetching bulk upload result task_id=%s error=%s",
                task_id, repr(exc),
            )
            return InternalServerErrorResponse()

    # =========================================================
    # BULK UPLOAD REFERENCE FILE (no request body — GET only)
    # =========================================================
    @user_router.get("/users/bulk_upload/reference-file")
    @permission_check("console:download_bulk_upload_reference_file")
    @inject
    async def download_bulk_upload_reference_file(
        request: Request,
        console_service: UserService = Depends(Provide[Container.console_service]),
        console_service_logger: ConsoleServiceLogger = Depends(
            Provide[Container.console_service_logger]
        ),
    ):
        try:
            headers: list[str] = await console_service.download_bulk_upload_reference_file(
                current_user=request.state.user
            )
            return SuccessResponse(data=headers)
        except Exception as exc:
            console_service_logger.error(
                "Error building bulk upload reference file: %s", repr(exc)
            )
            return InternalServerErrorResponse()
        
