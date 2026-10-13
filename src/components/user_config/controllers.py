from uuid import UUID
from typing import List, Optional

from dependency_injector.wiring import Provide, inject
from fastapi import APIRouter, Body, Depends, Query, Request
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
from src.components.rbac.permission_injector import permission_check
from src.components.user.errors import UserNotFoundError
from src.components.user.services import UserService
from src.components.user_config.constants import UserConfigAttributes, UserConfigEnum
from src.components.user_config.errors import UserConfigKeyError
from src.components.user_config.schemas import (
    UpdateUserConfigResponse,
    UserConfigData,
    UserConfigRequest,
    UserConfigResponse,
    UserConfigUpdateRequest,
)
from src.components.user_config.services import UserConfigService
from src.core.container import Container
from src.exceptions import (
    PartnerConfigException,
    UnauthorisedException,
    UserConfigException,
)
from src.loggers.console_service_logger import ConsoleServiceLogger


class UserConfigController:

    user_config_router = APIRouter()

    @user_config_router.post("/user-config", response_model=UserConfigResponse)
    @permission_check("console:create_user_config")
    @inject
    async def create_user_config(
        request: Request,
        user_config_data: UserConfigRequest = Body(
            ..., description="User Config data."
        ),
        console_service_logger: ConsoleServiceLogger = Depends(
            Provide[Container.console_service_logger]
        ),
        user_config_service: UserConfigService = Depends(
            Provide[Container.user_config_service]
        ),
    ):
        try:
            key: str = user_config_data.key
            if UserConfigEnum(key) not in UserConfigEnum.__members__.values():
                return BadRequestResponse(detail=f"Invalid Config Key: {key}")
            current_user: dict = request.state.user
            console_service_logger.info(
                "Attempting to create user config for user id: {}".format(
                    user_config_data.user_id
                )
            )
            user_config: UserConfigResponse = (
                await user_config_service.create_user_config(
                    user_config_data, current_user
                )
            )
            console_service_logger.info(
                "user config created successfully for user id: {} : {}".format(
                    user_config_data.user_id, user_config
                )
            )
            return ResourceCreatedResponse(data=user_config)
        except UserNotFoundError as exec:
            console_service_logger.error(
                "Not found error occured while creating user config: {}".format(exec)
            )
            return NotFoundResponse(detail=str(exec))
        except UserConfigException as exec:
            console_service_logger.error(
                "User config exception occured: {}".format(exec)
            )
            return BadRequestResponse(detail=str(exec))
        except ValueError:
            console_service_logger.error(
                f"Invalid Key while creating User Config with key: {key}"
            )
            return BadRequestResponse(
                detail=f"Invalid Key while creating User Config with key: {key}"
            )
        except UnauthorisedException as exc:
            console_service_logger.error(
                "An Unauthorised error occured: {}".format(exc)
            )
            return UnauthorizedResponse(detail=str(exc))
        except IntegrityError as exc:
            console_service_logger.error("Integrity error occured: {}".format(exc))
            return ResourceConflictResponse(
                detail=UserConfigAttributes.KEY_CONFLICT.format(user_config_data.key)
            )
        except Exception as exc:
            console_service_logger.error("An Unexpected error occured: {}".format(exc))
            return InternalServerErrorResponse()

    @user_config_router.get("/user-config", response_model=UserConfigResponse)
    @permission_check("console:get_user_config_by_key")
    @inject
    async def get_user_config_by_key(
        request: Request,
        key: str = Query(...),
        console_service_logger: ConsoleServiceLogger = Depends(
            Provide[Container.console_service_logger]
        ),
        user_config_service: UserConfigService = Depends(
            Provide[Container.user_config_service]
        ),
    ):
        try:
            current_user: dict = request.state.user
            user_id: UUID = current_user.get(CurrentUserMap.USER_ID)
            console_service_logger.info(
                "Attempting to fetch user config for user id: {}".format(user_id)
            )
            user_config: UserConfigResponse = (
                await user_config_service.get_user_config_by_key(user_id, key)
            )
            console_service_logger.info(
                "user config fetched successfully for user id: {} : {}".format(
                    user_id, user_config
                )
            )
            return SuccessResponse(data=user_config)
        except ValueError as value_error:
            console_service_logger.error(
                f"Value Error while getting UserConfig: {value_error}"
            )
            return BadRequestResponse(detail=str(value_error))
        except PartnerConfigException:
            console_service_logger.error(
                "User config not found for user id: {}".format(user_id)
            )
            return NotFoundResponse(
                detail=UserConfigAttributes.USER_CONFIG_NOT_FOUND.format(user_id)
            )
        except Exception as exc:
            console_service_logger.error("An Unexpected error occured: {}".format(exc))
            return InternalServerErrorResponse()

    @user_config_router.patch(
        "/user-configs/{partner_id}", response_model=List[UpdateUserConfigResponse]
    )
    @permission_check("console:upsert_user_config")
    @inject
    async def upsert_user_config(
        request: Request,
        partner_id: UUID,
        user_ids: List[int] = Query(
            ..., description="List of user IDs whose configurations need to be updated."
        ),
        update_user_config_data: UserConfigData = Body(
            ..., description="New values for the user configuration."
        ),
        console_service_logger: ConsoleServiceLogger = Depends(
            Provide[Container.console_service_logger]
        ),
        user_config_service: UserConfigService = Depends(
            Provide[Container.user_config_service]
        ),
    ):
        try:
            current_user: dict = request.state.user
            console_service_logger.info(
                "Attempting to update user config for user ids: {}".format(user_ids)
            )

            user_configs = await user_config_service.update_user_config(
                partner_id, user_ids, update_user_config_data, current_user
            )
            console_service_logger.info(
                "user config updated successfully for user ids: {} : {}".format(
                    user_ids, user_configs
                )
            )
            return SuccessResponse(data=user_configs)
        except UserConfigKeyError as exc:
            console_service_logger.error(f"User config key not found: {exc}")
            return BadRequestResponse(exc)
        except UserConfigException as exc:
            console_service_logger.error(
                "User config not found for user ids: {}".format(user_ids)
            )
            return BadRequestResponse(detail=str(exc))
        except Exception as exc:
            console_service_logger.error("Unexpected error occured: {}".format(exc))
            return InternalServerErrorResponse()

    @user_config_router.get("/user-configs", response_model=List[UserConfigResponse])
    @permission_check("console:get_user_configs_by_user_id")
    @inject
    async def get_user_configs_by_user_id(
        request: Request,
        user_id: Optional[UUID] = None,
        console_service_logger: ConsoleServiceLogger = Depends(
            Provide[Container.console_service_logger]
        ),
        user_config_service: UserConfigService = Depends(
            Provide[Container.user_config_service]
        ),
        user_svc: UserService = Depends(Provide[Container.console_service]),
    ):
        try:
            current_user: dict = request.state.user
            if user_id and await user_svc.is_user_internal(
                current_user.get(CurrentUserMap.USER_ID)
            ):
                pass
            else:
                user_id = current_user.get(CurrentUserMap.USER_ID)

            console_service_logger.info(
                "Attempting to fetch user configs for user id: {}".format(user_id)
            )
            user_configs = await user_config_service.get_user_configs_by_user_id(
                user_id
            )
            console_service_logger.info(
                "user configs fetched successfully for user id: {} : {}".format(
                    user_id, user_configs
                )
            )
            return SuccessResponse(data=user_configs)

        except PartnerConfigException as exc:
            console_service_logger.error(
                "No user config is available for user id: {}: {}".format(user_id, exc)
            )
            return NotFoundResponse(detail=str(exc))
        except UnauthorisedException as exc:
            console_service_logger.error("Unauthorised error occured: {}".format(exc))
            return UnauthorizedResponse(detail=str(exc))
        except Exception as exc:
            console_service_logger.error("Unexpected error occured: {}".format(exc))
            return InternalServerErrorResponse()
