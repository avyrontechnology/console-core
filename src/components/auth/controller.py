from uuid import UUID
from typing import List, Optional

from dependency_injector.wiring import Provide, inject
from fastapi import APIRouter, Body, Depends, Path, Query, Request, status
from fastapi.encoders import jsonable_encoder
from sqlalchemy.exc import IntegrityError

from src.components.auth.constant import (
    AuthExceptionMsg,
    AuthSuccessMsg,
    ServiceNames,
    SignupConfigKeys,
)
from src.components.auth.error import (
    OtpMediumMissing,
    OtpTemplateNotFound,
    PermissionNotFoundError,
    RoleNotFoundError,
)
from src.components.auth.schema import (
    LoginData,
    OtpValidateRequest,
    PermissionData,
    PermissionResponse,
    ResetPasswordRequest,
    RoleData,
    RoleResponse,
    TokenResponse,
    UpdatePermissionResponse,
    UpdatePermissionRquest,
    UpdateRoleRequest,
    UserData,
    UserDataResponse,
)
from src.components.auth.service import AuthService
from src.components.common.constants import CurrentUserMap
from src.components.partner_config.constants import PartnerConfigEnum
from src.components.partner_config.services import PartnerConfigService
from src.components.common.errors import ErrorMsg
from src.components.common.response import (
    BadRequestResponse,
    InternalServerErrorResponse,
    NotFoundResponse,
    ResourceConflictResponse,
    ResourceCreatedResponse,
    SuccessResponse,
    UnauthorizedResponse,
)
from src.components.location.errors import (
    CityNotFoundError,
    CountryNotFoundError,
    StateNotFoundError,
)
from src.components.rbac.permission_injector import permission_check
from src.components.user.errors import UserNotFoundError
from src.components.user.models import User
from src.components.user.schema import Contrasts
from src.components.user.services import UserService
from src.core.container import Container
from src.exceptions import AuthException
from src.loggers.console_service_logger import ConsoleServiceLogger


class AuthController:

    auth_router = APIRouter()

    @auth_router.post("/do_login")
    @inject
    async def do_login(
        login_data: LoginData,
        svc_name: ServiceNames,
        request: Request,
        auth_service: AuthService = Depends(Provide[Container.auth_service]),
        console_service_logger: ConsoleServiceLogger = Depends(
            Provide[Container.console_service_logger]
        ),
    ):
        try:
            console_service_logger.info(
                "Attempting login in svc:{} for user: {}".format(
                    svc_name, login_data.credential
                )
            )
            token = await auth_service.get_token(
                request=request, login_data=login_data, svc_name=svc_name.value
            )
            if "message" in token:
                console_service_logger.info(
                    "OTP sent to user: {}".format(login_data.email)
                )
                return SuccessResponse(token)

            # If normal token flow
            console_service_logger.info(
                "Token generated successfully for user: {}".format(
                    login_data.credential
                )
            )
            token_data = TokenResponse(**token)
            return SuccessResponse(jsonable_encoder(token_data))
        except AuthException as ex:
            console_service_logger.error(
                "Unexpected error during login: {}".format(repr(ex))
            )
            return UnauthorizedResponse(str(ex))
        except OtpMediumMissing as exc:
            console_service_logger.error(
                "OTP medium missing during login for user: {}. Error: {}".format(
                    login_data.credential, exc
                )
            )
            return BadRequestResponse(detail=str(exc))
        except OtpTemplateNotFound as exc:
            console_service_logger.error(
                "OTP template not found or not approved during login for user: {}. Error: {}".format(
                    login_data.credential, exc
                )
            )
            return BadRequestResponse(detail=str(exc))
        except Exception as ex:
            console_service_logger.error(
                "Unexpected error during login: {}".format(repr(ex))
            )
            return InternalServerErrorResponse(ErrorMsg.INTERNAL_SERVER_ERROR)

    @auth_router.post("/logout")
    @inject
    async def logout(
        request: Request,
        auth_service: AuthService = Depends(Provide[Container.auth_service]),
        console_service_logger: ConsoleServiceLogger = Depends(
            Provide[Container.console_service_logger]
        ),
    ):
        try:
            token: str = request.state.token
            await auth_service.logout(token)
            return SuccessResponse(AuthSuccessMsg.SUCCESSFULL_LOGOUT)
        except AuthException:
            console_service_logger.error(
                f"Unsuccessfull atempt for logout with token: {token}"
            )
            return UnauthorizedResponse(
                detail=AuthExceptionMsg.TOKEN_EXPIRED_OR_INVALID
            )
        except Exception as exc:
            console_service_logger.error(
                f"Got unexpectd error while logout Error: {exc}"
            )
            return InternalServerErrorResponse()

    @auth_router.post(
        "/do_signup",
        response_model=UserDataResponse,
        status_code=status.HTTP_201_CREATED,
    )
    @inject
    async def do_signup(
        user_data: UserData,
        services: Optional[SignupConfigKeys] = None,
        auth_service: AuthService = Depends(Provide[Container.auth_service]),
        console_service_logger: ConsoleServiceLogger = Depends(
            Provide[Container.console_service_logger]
        ),
    ):
        try:
            console_service_logger.info(
                "Attempting to create new user with email: {}".format(user_data.email)
            )
            user = await auth_service.sing_up(user_data, services)
            return ResourceCreatedResponse(
                jsonable_encoder(UserDataResponse.model_validate(user))
            )
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
        except IntegrityError as exc:
            console_service_logger.error(
                "Email or phone already exists while creating new user: {}".format(
                    str(exc)
                )
            )
            return ResourceConflictResponse(AuthExceptionMsg.USER_EXIST)
        except AuthException as ex:
            console_service_logger.error(
                "Unexpected error during signup: {}".format(str(ex))
            )
            return ResourceConflictResponse(str(ex))
        except Exception as ex:
            console_service_logger.error(
                "Unexpected error during signup: {}".format(repr(ex))
            )
            return InternalServerErrorResponse(ErrorMsg.INTERNAL_SERVER_ERROR)

    @auth_router.post(
        "/role",
        response_model=RoleResponse,
    )
    @permission_check("console:create_role")
    @inject
    async def create_role(
        request: Request,
        role: RoleData,
        auth_service: AuthService = Depends(Provide[Container.auth_service]),
        console_service_logger: ConsoleServiceLogger = Depends(
            Provide[Container.console_service_logger]
        ),
    ):
        try:
            console_service_logger.info(
                "Attempting to create new role: {}".format(role.name)
            )
            current_user: dict = request.state.user
            result = await auth_service.add_role(role, current_user)
            return ResourceCreatedResponse(
                jsonable_encoder(RoleResponse.model_validate(result))
            )
        except AuthException as ex:
            console_service_logger.error(
                "Unexpected error during create new role: {}".format(repr(ex))
            )
            return BadRequestResponse(str(ex))
        except Exception as ex:
            console_service_logger.error(
                "Unexpected error during create new role: {}".format(repr(ex))
            )
            return InternalServerErrorResponse(ErrorMsg.INTERNAL_SERVER_ERROR)

    @auth_router.get("/role", response_model=List[RoleResponse])
    @permission_check("console:get_roles")
    @inject
    async def get_roles(
        request: Request,
        auth_service: AuthService = Depends(Provide[Container.auth_service]),
        console_service_logger: ConsoleServiceLogger = Depends(
            Provide[Container.console_service_logger]
        ),
    ):
        try:
            current_user: dict = request.state.user
            partner_id: UUID = current_user.get(CurrentUserMap.PARTNER_ID)
            console_service_logger.info("Attempting to get roles...")
            roles = await auth_service.get_all_role(partner_id)
            console_service_logger.info(
                "Fetched all the roles successfully: {}".format(roles)
            )

            roles_response = [RoleResponse.model_validate(role) for role in roles]
            return SuccessResponse(jsonable_encoder(roles_response))
        except AuthException as ex:
            console_service_logger.error(
                "Unexpected error during getting roles: {}".format(repr(ex))
            )
            return NotFoundResponse(str(ex))
        except Exception as ex:
            console_service_logger.error(
                "Unexpected error during getting roles: {}".format(repr(ex))
            )
            return InternalServerErrorResponse(ErrorMsg.INTERNAL_SERVER_ERROR)

    @auth_router.get("/role/{id}", response_model=RoleResponse)
    @permission_check("console:get_role_by_id")
    @inject
    async def get_role_by_id(
        request: Request,
        id: UUID,
        auth_service: AuthService = Depends(Provide[Container.auth_service]),
        console_service_logger: ConsoleServiceLogger = Depends(
            Provide[Container.console_service_logger]
        ),
    ):
        try:
            console_service_logger.info("Attempting to get role by id {}".format(id))
            role = await auth_service.get_role_by_id(id)
            return SuccessResponse(jsonable_encoder(RoleResponse.model_validate(role)))
        except AuthException as ex:
            console_service_logger.error(
                "Unexpected error during get role by id: {}".format(str(ex))
            )
            return NotFoundResponse(str(ex))
        except Exception as ex:
            console_service_logger.error(
                "Unexpected error during get role by id: {}".format(repr(ex))
            )
            return InternalServerErrorResponse(ErrorMsg.INTERNAL_SERVER_ERROR)

    # soft delete role change is_activate=false and is_delete=true
    @auth_router.delete("/role/{id}")
    @permission_check("console:delete_roles")
    @inject
    async def delete_roles(
        request: Request,
        id: UUID,
        auth_service: AuthService = Depends(Provide[Container.auth_service]),
        console_service_logger: ConsoleServiceLogger = Depends(
            Provide[Container.console_service_logger]
        ),
    ):
        try:
            console_service_logger.info("Attempting to delete role {}".format(id))
            current_user: dict = request.state.user
            await auth_service.delete_role(id, current_user)
            return SuccessResponse(AuthSuccessMsg.ROLE_DELETE)
        except AuthException as ex:
            console_service_logger.error(
                "Unexpected error during delete roles: {}".format(repr(ex))
            )
            return NotFoundResponse(str(ex))
        except Exception as ex:
            console_service_logger.error(
                "Unexpected error during delete roles: {}".format(repr(ex))
            )
            return InternalServerErrorResponse(ErrorMsg.INTERNAL_SERVER_ERROR)

    @auth_router.post(
        "/permission",
        response_model=PermissionResponse,
        status_code=status.HTTP_201_CREATED,
    )
    @permission_check("console:create_permission")
    @inject
    async def create_permission(
        request: Request,
        user_permission: PermissionData,
        auth_service: AuthService = Depends(Provide[Container.auth_service]),
        console_service_logger: ConsoleServiceLogger = Depends(
            Provide[Container.console_service_logger]
        ),
    ):
        try:
            console_service_logger.info(
                "Attempting to create new permission: {}".format(user_permission.title)
            )
            current_user: dict = request.state.user
            permission = await auth_service.create_permission(
                user_permission, current_user
            )
            return ResourceCreatedResponse(
                jsonable_encoder(PermissionResponse.model_validate(permission))
            )
        except AuthException as ex:
            console_service_logger.error(
                "Unexpected error during create permission:{}".format(repr(ex))
            )
            return BadRequestResponse(str(ex))
        except Exception as ex:
            console_service_logger.error(
                "Unexpected error during create permission:{}".format(repr(ex))
            )
            return InternalServerErrorResponse(ErrorMsg.INTERNAL_SERVER_ERROR)

    @auth_router.get("/permission", response_model=List[PermissionResponse])
    @permission_check("console:get_all_permission")
    @inject
    async def get_all_permission(
        request: Request,
        auth_service: AuthService = Depends(Provide[Container.auth_service]),
        console_service_logger: ConsoleServiceLogger = Depends(
            Provide[Container.console_service_logger]
        ),
        user_service: UserService = Depends(Provide[Container.console_service]),
    ):
        try:
            console_service_logger.info("checking is user is internal or not")
            current_user: dict = request.state.user
            user_id: UUID = current_user.get(CurrentUserMap.USER_ID)
            if not await user_service.is_user_internal(user_id):
                console_service_logger.warning(
                    "User with id {} is not an internal user, cannot fetch internal permissions.".format(
                        user_id
                    )
                )
                raise AuthException(
                    "Current user is not an internal user, can't fetch permissions."
                )
            console_service_logger.info("Attempting to getting permission")
            permissions = await auth_service.get_all_permission()

            permissions_response = [
                PermissionResponse.model_validate(permission)
                for permission in permissions
            ]
            return SuccessResponse(jsonable_encoder(permissions_response))
        except AuthException as ex:
            console_service_logger.error(
                "Unexpected error during getting permission: {}".format(repr(ex))
            )
            return BadRequestResponse(str(ex))
        except Exception as ex:
            console_service_logger.error(
                "Unexpected error during getting permission: {}".format(repr(ex))
            )
            return InternalServerErrorResponse(ErrorMsg.INTERNAL_SERVER_ERROR)

    @auth_router.get("/permission/{id}", response_model=PermissionResponse)
    @permission_check("console:get_permission_by_id")
    @inject
    async def get_permission_by_id(
        request: Request,
        id: UUID,
        auth_service: AuthService = Depends(Provide[Container.auth_service]),
        console_service_logger: ConsoleServiceLogger = Depends(
            Provide[Container.console_service_logger]
        ),
    ):
        try:
            console_service_logger.info("Attempting to get permission")
            permission = await auth_service.get_permission_by_id(id)
            return SuccessResponse(
                jsonable_encoder(PermissionResponse.model_validate(permission))
            )
        except AuthException as ex:
            console_service_logger.warning(
                "Get permission failed: permission not found: {id}, error: {ex}".format(
                    id=id, ex=repr(ex)
                )
            )
            return NotFoundResponse(str(ex))
        except Exception as ex:
            console_service_logger.error(
                "Unexpected error during get permission: {}".format(repr(ex))
            )
            return InternalServerErrorResponse(ErrorMsg.INTERNAL_SERVER_ERROR)

    # soft delete permission change is_activate=false and is_delete=true
    @auth_router.delete("/permission/{id}")
    @permission_check("console:delete_permission")
    @inject
    async def delete_permission(
        request: Request,
        id: UUID,
        auth_service: AuthService = Depends(Provide[Container.auth_service]),
        console_service_logger: ConsoleServiceLogger = Depends(
            Provide[Container.console_service_logger]
        ),
    ):
        try:
            console_service_logger.info("Attempting to delete permission")
            current_user: dict = request.state.user
            await auth_service.delete_permission(id, current_user)
            return SuccessResponse(AuthSuccessMsg.PERMISSION_DELETE)
        except AuthException as ex:
            console_service_logger.error(
                "Delete permission failed: permission not found: {id}, error: {ex}".format(
                    id=id, ex=repr(ex)
                )
            )
            return NotFoundResponse(str(ex))
        except Exception as ex:
            console_service_logger.error(
                "Unexpected error during delete permission: {}".format(repr(ex))
            )
            return InternalServerErrorResponse(ErrorMsg.INTERNAL_SERVER_ERROR)

    @auth_router.post("/reset_password")
    @permission_check("console:reset_password")
    @inject
    async def reset_password(
        request: Request,
        reset_password_request: ResetPasswordRequest,
        auth_service: AuthService = Depends(Provide[Container.auth_service]),
        console_service_logger: ConsoleServiceLogger = Depends(
            Provide[Container.console_service_logger]
        ),
    ) -> SuccessResponse:
        try:
            console_service_logger.info(
                "Attempting to reset password for user: {}".format(
                    reset_password_request.email
                )
            )
            current_user: dict = request.state.user
            result: str = await auth_service.reset_password(
                current_user, reset_password_request
            )
            return SuccessResponse(result)
        except AuthException as exc:
            console_service_logger.error(
                "Error during reset password: {}".format(str(exc))
            )
            return BadRequestResponse(str(exc))
        except Exception as exc:
            console_service_logger.error(
                "Unexpected error occurred while reset password: {}".format(str(exc))
            )
            return InternalServerErrorResponse(ErrorMsg.INTERNAL_SERVER_ERROR)

    @auth_router.get(
        "/get_parents/{role_id}/partner/{partner_id}",
        response_model=list[Contrasts.ParentUserResponse],
    )
    @permission_check("console:get_parent_users_by_role_id")
    @inject
    async def get_parent_users_by_role_id(
        request: Request,
        role_id: UUID,
        partner_id: UUID,
        auth_service: AuthService = Depends(Provide[Container.auth_service]),
        console_service_logger: ConsoleServiceLogger = Depends(
            Provide[Container.console_service_logger]
        ),
        user_service: UserService = Depends(Provide["console_service"]),
    ):
        try:
            console_service_logger.info(
                "Attempting to get parents for the role id: {}".format(role_id)
            )

            current_user: dict = request.state.user

            current_user_id: UUID = current_user.get(CurrentUserMap.USER_ID)

            user_details: User = await user_service.get_user_details(current_user_id)

            current_user_partner_id: UUID = current_user.get(CurrentUserMap.PARTNER_ID)

            current_user_hierarchy: int = user_details.get(
                CurrentUserMap.ROLE_HIERARCHY_LEVEL
            )

            if (
                current_user_hierarchy >= CurrentUserMap.ADMIN_ROLE_HIERARCHY_LEVEL
                and partner_id != current_user_partner_id
            ):
                console_service_logger.error(
                    "Can't get the users of different partner."
                )
                raise AuthException(AuthExceptionMsg.USERS_OF_DIFFERENT_PARTNER)

            parents: list[Contrasts.ParentUserResponse] = (
                await auth_service.get_parent_users_by_role_id(role_id, partner_id)
            )
            return SuccessResponse(parents)
        except RoleNotFoundError as exec:
            console_service_logger.error(
                "Unexpected error during getting parents: {}".format(repr(exec))
            )
            return NotFoundResponse(str(exec))
        except Exception as exec:
            console_service_logger.error("Can't get the users of different partner.")
            return BadRequestResponse(detail=str(exec))
        except Exception as exec:
            console_service_logger.error(
                "Unexpected error occured during getting parents: {}".format(repr(exec))
            )
            return InternalServerErrorResponse(ErrorMsg.INTERNAL_SERVER_ERROR)

    @auth_router.get("/get_permissions_for_all_roles", response_model=dict)
    @permission_check("console:get_default_role_permission_matrix")
    @inject
    async def get_default_role_permission_matrix(
        request: Request,
        is_internal_permission: Optional[bool] = False,
        auth_service: AuthService = Depends(Provide[Container.auth_service]),
        partner_config_service: PartnerConfigService = Depends(
            Provide[Container.partner_config_service]
        ),
        console_service_logger: ConsoleServiceLogger = Depends(
            Provide[Container.console_service_logger]
        ),
    ):
        try:
            console_service_logger.info("fetching permissions for all the roles.")
            current_user: dict = request.state.user
            user_id: UUID = current_user.get(CurrentUserMap.USER_ID)
            partner_id: UUID = current_user.get(CurrentUserMap.PARTNER_ID)

            filter_partner_id: Optional[UUID] = None
            if not is_internal_permission:
                config = await partner_config_service.get_partner_config_by_key(
                    partner_id, PartnerConfigEnum.IS_PARTNER_CUSTOM_ROLES_ENABLED.value
                )
                if config and config.value == True:
                    filter_partner_id = partner_id

            console_service_logger.info("Fetching default role permission matrix...")
            matrix: dict = await auth_service.get_role_permissions_matrix(
                user_id, is_internal_permission, filter_partner_id
            )
            console_service_logger.info(
                "permissions fetched successfully: {}".format(matrix)
            )
            return SuccessResponse(matrix)
        except AuthException as exec:
            console_service_logger.error("Auth exception occured: {}".format(exec))
            return BadRequestResponse(detail=str(exec))

        except Exception as ex:
            console_service_logger.error(
                "Unexpected error during fetching permission matrix: {}".format(
                    repr(ex)
                )
            )
            return InternalServerErrorResponse(ErrorMsg.INTERNAL_SERVER_ERROR)

    @auth_router.patch(
        "/permission/{permission_id}",
        response_model=UpdatePermissionResponse,
    )
    @permission_check("console:update_permission")
    @inject
    async def update_permission(
        request: Request,
        permission_id: UUID,
        permission_data: UpdatePermissionRquest,
        auth_service: AuthService = Depends(Provide[Container.auth_service]),
        console_service_logger: ConsoleServiceLogger = Depends(
            Provide[Container.console_service_logger]
        ),
    ):
        try:
            console_service_logger.info(
                "Attempting to update permission with id: {}".format(permission_id)
            )

            updated_permission: UpdatePermissionResponse = (
                await auth_service.update_permission(permission_id, permission_data)
            )
            console_service_logger.info(
                "Permission with id: {} updated successfully".format(permission_id)
            )
            return SuccessResponse(data=updated_permission)
        except PermissionNotFoundError as exec:
            console_service_logger.error(
                "Permission not found during updating permission: {}".format(repr(exec))
            )
            return NotFoundResponse(str(exec))
        except AuthException as exec:
            console_service_logger.error(
                "Error during updating permission: {}".format(str(exec))
            )
            return ResourceConflictResponse(str(exec))
        except Exception as exec:
            console_service_logger.error(
                "Unexpected error during updating permission: {}".format(repr(exec))
            )
            return InternalServerErrorResponse(ErrorMsg.INTERNAL_SERVER_ERROR)

    @auth_router.post("/assume_user/{user_id}")
    @permission_check("console:assume_user")
    @inject
    async def assume_user(
        request: Request,
        svc_name: ServiceNames,
        user_id: UUID = Path(..., ge=1, le=2_147_483_647),
        auth_service: AuthService = Depends(Provide[Container.auth_service]),
        console_service_logger: ConsoleServiceLogger = Depends(
            Provide[Container.console_service_logger]
        ),
    ) -> SuccessResponse:
        try:
            console_service_logger.info(
                "Attempting to get token as assuming user: {}".format(user_id)
            )

            result: dict = await auth_service.assume_user(request, user_id, svc_name.value)
            return SuccessResponse(result)
        except UserNotFoundError as exc:
            console_service_logger.error(
               "Unexpected error occurred while assuming user: {}, error: {}".format(
                user_id, str(exc)
               )
            )
            return NotFoundResponse(str(exc))
        except AuthException as ex:
            console_service_logger.error(
                "Unexpected error during login: {}".format(repr(ex))
            )
            return BadRequestResponse(str(ex))
        except Exception as exc:
            console_service_logger.error(
                f"Unexpected error occurred while assuming user: {user_id}, error: {str(exc)}"
            )
            return InternalServerErrorResponse(ErrorMsg.INTERNAL_SERVER_ERROR)

    @auth_router.get("/categories")
    @permission_check("console:get_categories")
    @inject
    async def get_categories(
        request: Request,
        auth_service: AuthService = Depends(Provide[Container.auth_service]),
        console_service_logger: ConsoleServiceLogger = Depends(
            Provide[Container.console_service_logger]
        ),
    ) -> SuccessResponse:
        try:
            console_service_logger.info("getting all the categories")
            categories: dict[str, list[str]] = auth_service.get_categories()
            return SuccessResponse(categories)
        except Exception as exec:
            console_service_logger.error(
                "Got an unexpected error while getting the categories: {}".format(
                    str(exec)
                )
            )
            return InternalServerErrorResponse(detail=str(exec))

    @auth_router.get("/resources")
    @permission_check("console:get_permission_title_by_category_name")
    @inject
    async def get_permission_title_by_category_name(
        request: Request,
        category: str = Query(..., min_length=1, max_length=64),
        service: ServiceNames = Query(...),
        auth_service: AuthService = Depends(Provide[Container.auth_service]),
        console_service_logger: ConsoleServiceLogger = Depends(
            Provide[Container.console_service_logger]
        ),
    ) -> SuccessResponse:
        try:
            console_service_logger.info(
                "Getting permission title for: {}".format(category)
            )
            permission_title: list[str] = (
                auth_service.get_permission_title_by_category_name(category, service)
            )
            return SuccessResponse(permission_title)
        except Exception as exec:
            console_service_logger.error("Unexpected error: {}".format(repr(exec)))
            return InternalServerErrorResponse(ErrorMsg.INTERNAL_SERVER_ERROR)

    @auth_router.patch("/role/{role_id}")
    @permission_check("console:update_role")
    @inject
    async def update_role(
        request: Request,
        role_id: UUID,
        role_data: UpdateRoleRequest = Body(...),
        auth_service: AuthService = Depends(Provide[Container.auth_service]),
        console_service_logger: ConsoleServiceLogger = Depends(
            Provide[Container.console_service_logger]
        ),
    ) -> SuccessResponse:
        try:
            console_service_logger.info("Updating role: {}".format(role_id))
            result: dict = await auth_service.update_role(role_id, role_data)
            return SuccessResponse(result)
        except RoleNotFoundError as exc:
            console_service_logger.error(
                "Role not found error occurred while updating role: {}, error: {}".format(
                    role_id, exc
                )
            )
            return NotFoundResponse(str(exc))
        except AuthException as exc:
            console_service_logger.error(
                "Auth exception occurred while updating role: {}, error: {}".format(
                    role_id, str(exc)
                )
            )
            return BadRequestResponse(str(exc))
        except Exception as exc:
            console_service_logger.error(
                "Unexpected error occurred while updating role: {}, error: {}".format(
                    role_id, str(exc)
                )
            )
            return InternalServerErrorResponse(ErrorMsg.INTERNAL_SERVER_ERROR)

    @auth_router.post("/validate-otp", status_code=status.HTTP_201_CREATED)
    @inject
    async def validate_otp(
        request: Request,
        payload: OtpValidateRequest,
        auth_service: AuthService = Depends(Provide[Container.auth_service]),
        console_service_logger: ConsoleServiceLogger = Depends(
            Provide[Container.console_service_logger]
        ),
    ):
        """
        Endpoint to validate OTP.
        - Takes user email and OTP.
        - If valid, generates session and returns access token.
        """
        try:
            console_service_logger.info(
                "Validating OTP for user: {}".format(payload.email)
            )

            response_data = await auth_service.validate_otp(request, payload)

            log_message, data = (
                (
                    f"OTP verification successful for user: {payload.credential}",
                    response_data,
                )
                if payload.is_verify
                else (
                    f"OTP validated and token generated for user: {payload.credential}",
                    TokenResponse(**response_data),
                )
            )

            console_service_logger.info(log_message)
            return SuccessResponse(jsonable_encoder(data))

        except AuthException as ex:
            console_service_logger.error(
                "OTP validation failed for user {}: {}".format(payload.email, repr(ex))
            )
            return UnauthorizedResponse(str(ex))
        except Exception as ex:
            console_service_logger.error(
                "Unexpected error during OTP validation: {}".format(repr(ex))
            )
            return InternalServerErrorResponse(ErrorMsg.INTERNAL_SERVER_ERROR)