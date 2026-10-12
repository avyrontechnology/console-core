from uuid import UUID
from typing import List

from dependency_injector.wiring import Provide, inject
from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.encoders import jsonable_encoder
from pydantic import ValidationError
from sqlalchemy.exc import IntegrityError

from src.components.auth.util import AuthUtility
from src.components.common.errors import ErrorMsg
from src.components.common.response import (
    BadRequestResponse,
    InternalServerErrorResponse,
    NotFoundResponse,
    ResourceCreatedResponse,
    SuccessNoContentResponse,
    SuccessResponse,
)
from src.components.rbac.permission_dependency import PermissionDependency
from src.components.rbac.permission_injector import permission_check
from src.components.user.errors import UserNotFoundError
from src.components.user_metadata.errors import (
    UnauthorizedUserException,
    UserMatadataNotFoundError,
)
from src.components.user_metadata.schema import (
    CreateUserMetaDataSchema,
    UpdateUserMetadataSchema,
    UserMetadataResponse,
)
from src.components.user_metadata.services import UserMetadataService
from src.core.container import Container
from src.exceptions import UserMetadataAlreadyExistsException, UserMetadataException
from src.loggers.console_service_logger import ConsoleServiceLogger


class UserMetadataController:

    user_metadata_router = APIRouter()

    @user_metadata_router.get(
        "/user_metadata", response_model=List[UserMetadataResponse]
    )
    @permission_check(PermissionDependency)
    @inject
    async def get_users_metadata(
        request: Request,
        user_metadata_service: UserMetadataService = Depends(
            Provide[Container.user_metadata_service]
        ),
        logger: ConsoleServiceLogger = Depends(
            Provide[Container.console_service_logger]
        ),
    ):

        try:
            logger.info("Attempting to fetch all user metadata.")
            metadata_list = await user_metadata_service.get_user_metadata()
            logger.info(
                "Successfully retrieved {} user metadata entries.".format(
                    len(metadata_list)
                )
            )
            users_metadata = [
                UserMetadataResponse.model_validate(metadata)
                for metadata in metadata_list
            ]
            return SuccessResponse(jsonable_encoder(users_metadata))

        except UserMatadataNotFoundError as ex:
            logger.error(
                "Error occurred while fetching all user metadata: {}".format(str(ex))
            )
            return NotFoundResponse(str(ex))
        except UserMetadataException as ex:
            logger.error(
                "Error occurred while fetching all user metadata: {}".format(str(ex))
            )
            return NotFoundResponse(str(ex))
        except Exception as ex:
            logger.error(
                "Internal server error while fetching all user metadata: {}".format(
                    str(ex)
                )
            )
            return InternalServerErrorResponse(ErrorMsg.INTERNAL_SERVER_ERROR)

    @user_metadata_router.get(
        "/user_metadata/{user_id}", response_model=UserMetadataResponse
    )
    @permission_check(PermissionDependency)
    @inject
    async def get_user_metadata_by_user_id(
        request: Request,
        user_id: UUID,
        user_metadata_service: UserMetadataService = Depends(
            Provide[Container.user_metadata_service]
        ),
        logger: ConsoleServiceLogger = Depends(
            Provide[Container.console_service_logger]
        ),
    ):
        """get user metadata by user id."""
        logger.info("Attempting to fetch metadata for user_id: {}.".format(user_id))
        try:
            metadata = await user_metadata_service.get_user_metadata_by_user_id(user_id)
            logger.info(
                "Successfully retrieved metadata for user_id: {}.".format(user_id)
            )
            return SuccessResponse(jsonable_encoder(metadata))
        except UserMatadataNotFoundError as ex:
            logger.error(
                "User meta data not found for user_id {}: {}".format(user_id, str(ex))
            )
            return NotFoundResponse(str(ex))
        except UserMetadataException as ex:
            logger.error(
                "User metadata error for user_id {}: {}".format(user_id, str(ex))
            )
            return NotFoundResponse(str(ex))
        except Exception as ex:
            logger.error(
                "Internal server error while fetching metadata for user_id {}: {}".format(
                    user_id, str(ex)
                )
            )
            return InternalServerErrorResponse(ErrorMsg.INTERNAL_SERVER_ERROR)

    @user_metadata_router.post(
        "/user_metadata/{user_id}", response_model=UserMetadataResponse
    )
    @permission_check(PermissionDependency)
    @inject
    async def add_user_metadata(
        request: Request,
        user_id: UUID,
        user_metadata: CreateUserMetaDataSchema,
        user_metadata_service: UserMetadataService = Depends(
            Provide[Container.user_metadata_service]
        ),
        logger: ConsoleServiceLogger = Depends(
            Provide[Container.console_service_logger]
        ),
    ):
        try:
            current_user: dict = request.state.user
            logger.info(
                "trying to add user meta data for user id : {}".format(user_metadata)
            )
            user_metadata = await user_metadata_service.add_user_metadata(
                user_id, user_metadata, current_user
            )
            logger.info(
                "user metadata added successfully for user id : {}".format(user_id)
            )
            return ResourceCreatedResponse(jsonable_encoder(user_metadata))
        except UserMetadataAlreadyExistsException as ex:
            logger.error(
                "User metadata already exists for user_id {}: {}".format(
                    user_id, str(ex)
                )
            )
            return BadRequestResponse(str(ex))
        except UserNotFoundError as exec:
            logger.error("User not found for user_id {}: {}".format(user_id, str(exec)))
            return NotFoundResponse(str(exec))
        except Exception as ex:
            logger.error(
                "Internal server error while updating metadata for user_id {}: {}".format(
                    user_id, str(ex)
                )
            )
            return InternalServerErrorResponse()

    @user_metadata_router.patch(
        "/user_metadata/{user_id}", response_model=UserMetadataResponse
    )
    @permission_check(PermissionDependency)
    @inject
    async def update_user_metadata(
        request: Request,
        user_id: UUID,
        user_metadata: UpdateUserMetadataSchema,
        user_metadata_service: UserMetadataService = Depends(
            Provide[Container.user_metadata_service]
        ),
        logger: ConsoleServiceLogger = Depends(
            Provide[Container.console_service_logger]
        ),
    ):
        try:
            logger.info(
                "Attempting to update metadata for user_id: {}.".format(user_id)
            )
            current_user: dict = request.state.user
            updated_metadata = await user_metadata_service.update_user_metadata(
                current_user, user_id, user_metadata
            )
            logger.info(
                "Successfully updated metadata for user_id: {}.".format(user_id)
            )
            return SuccessResponse(jsonable_encoder(updated_metadata))

        except HTTPException as ex:
            logger.error("Unauthorized access: {}".format(str(ex)))
            return BadRequestResponse("Unauthorized access: {}".format(str(ex)))
        except UserMatadataNotFoundError as ex:
            logger.error(
                "Error occurred while updating metadata for user_id {}: {}".format(
                    user_id, str(ex)
                )
            )
            return NotFoundResponse(str(ex))
        except UserNotFoundError as ex:
            logger.error("User not found for user_id {}: {}".format(user_id, str(ex)))
            return NotFoundResponse(str(ex))
        except Exception as ex:
            logger.error(
                "Internal server error while updating metadata for user_id {}: {}".format(
                    user_id, str(ex)
                )
            )
            return InternalServerErrorResponse()

    @user_metadata_router.delete("/user_metadata/{user_id}")
    @permission_check(PermissionDependency)
    @inject
    async def delete_user_metadata(
        request: Request,
        user_id: UUID,
        user_metadata_service: UserMetadataService = Depends(
            Provide[Container.user_metadata_service]
        ),
        logger: ConsoleServiceLogger = Depends(
            Provide[Container.console_service_logger]
        ),
    ):
        # TODO: Siddharth: Only agent or his superviser or account owner can delete their metadata not another agent can delete it
        """
        Endpoint to delete metadata for a given user_id.
        """
        logger.info(
            "Received request to delete metadata for user_id={}".format(user_id)
        )

        try:
            current_user: dict = request.state.user
            await user_metadata_service.delete_user_metadata_by_id(
                user_id, current_user
            )
            return SuccessNoContentResponse()
        except UserMatadataNotFoundError as ex:
            logger.error(
                " user meta data for User ID: {} not found: {}".format(user_id, str(ex))
            )
            return NotFoundResponse(str(ex))
        except UnauthorizedUserException as ex:
            logger.error("Unauthorized user: {}".format(str(ex)))
            return BadRequestResponse(str(ex))
        except Exception as ex:
            logger.error("Internal Server Error: {}".format(str(ex)))
            return InternalServerErrorResponse()
