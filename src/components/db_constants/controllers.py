from typing import List, Optional

from dependency_injector.wiring import Provide, inject
from fastapi import APIRouter, Depends, File, Form, Query, Request, UploadFile

from src.components.common.constants import CurrentUserMap
from src.components.common.response import (
    BadRequestResponse,
    InternalServerErrorResponse,
    NotFoundResponse,
    SuccessNoContentResponse,
    SuccessResponse,
    ValidationErrorResponse,
)
from src.components.db_constants import messages
from src.components.db_constants.enums import ConstantsTypes
from src.components.db_constants.models import ConstantsBase
from src.components.db_constants.schema import ConstantResponseSchema
from src.components.db_constants.services import ConstantsService
from src.components.digital_assets.constants import DigitalAssetEnum
from src.components.rbac.permission_dependency import PermissionDependency
from src.components.rbac.permission_injector import permission_check
from src.core.container import Container
from src.exceptions import (
    ConstantNotFoundException,
    ConstantVersionException,
    ConstantVersionNotFoundException,
)
from src.loggers.console_service_logger import ConsoleServiceLogger


class ConstantsController:
    """
    Controller for handling operations on constants such as fetching, updating, and rolling back constants.
    """

    constants_router = APIRouter()

    @constants_router.get(
        "/get_constants",
        response_model=ConstantResponseSchema,
        description="Fetch constants data based on constant type",
    )
    @permission_check(PermissionDependency)
    @inject
    async def get_constants(
        request: Request,
        constant_type: ConstantsTypes = Query(
            ...,
            description=messages.CONSTANT_TYPE_DESCRIPTION,
        ),
        constants_service: ConstantsService = Depends(
            Provide[Container.constants_service]
        ),
        console_service_logger: ConsoleServiceLogger = Depends(
            Provide[Container.console_service_logger]
        ),
    ):
        """
        Get constants data for the selected constant type.
        """
        try:
            console_service_logger.info(
                "Fetching constants of type: {} ({})".format(
                    constant_type.name, constant_type.value
                )
            )

            constant_model: type[ConstantsBase] = ConstantsTypes.get_db_constant_model(
                constant_type.value
            )
            constant_data: List[ConstantResponseSchema] = (
                await constants_service.get_constants_details(constant_model)
            )

            if not constant_data:
                console_service_logger.warning(
                    "No constants found for type: {} ({})".format(
                        constant_type.name, constant_type.value
                    )
                )
                return SuccessNoContentResponse()

            console_service_logger.info(
                "Constants successfully fetched for type: {} ({})".format(
                    constant_type.name, constant_type.value
                )
            )
            return SuccessResponse(data=constant_data)

        except Exception as error:
            console_service_logger.error(
                "Unexpected error while fetching constants for type {}: {}".format(
                    constant_type.name, error
                )
            )
            return InternalServerErrorResponse(detail=messages.GET_CONSTANTS_EXCEPTION)

    @constants_router.put(
        "/update_constant/{id}",
        response_model=ConstantResponseSchema,
        description="Update constants data based on constant ID",
    )
    @permission_check(PermissionDependency)
    @inject
    async def update_constant(
        request: Request,
        id: int,
        constant_type: ConstantsTypes = Query(
            ...,
            description=messages.CONSTANT_TYPE_DESCRIPTION,
        ),
        value: Optional[str] = Form(None),
        media_file: Optional[UploadFile] = File(None),
        description: Optional[str] = Form(None),
        constants_service: ConstantsService = Depends(
            Provide[Container.constants_service]
        ),
        console_service_logger: ConsoleServiceLogger = Depends(
            Provide[Container.console_service_logger]
        ),
    ):
        """
        Update constants data for the selected constant ID.
        """
        try:
            console_service_logger.info(
                "Received request to update constant ID: {}, Type: {}".format(
                    id, constant_type.name
                )
            )
            current_user: dict = request.state.user
            user_id: int = current_user.get("user_id")
            constant_model: type[ConstantsBase] = ConstantsTypes.get_db_constant_model(
                constant_type.value
            )

            constant: List[ConstantResponseSchema] = (
                await constants_service.get_constant_by_id(id, constant_model)
            )
            if not constant:
                return NotFoundResponse(detail=messages.CONSTANT_NOT_FOUND.format(id))

            if constant_type in [
                ConstantsTypes.GLOBAL_MEDIA_CONSTANTS,
                ConstantsTypes.MEDIA_CONSTANTS,
            ]:
                if not media_file:
                    return ValidationErrorResponse(
                        detail=messages.FILE_REQUIRED_FOR_MEDIA
                    )
                updated_value: object = media_file
                is_media_type: bool = True
                asset_type: str = (
                    DigitalAssetEnum.GLOBAL_MEDIA_CONSTANT.name
                    if constant_type == ConstantsTypes.GLOBAL_MEDIA_CONSTANTS
                    else DigitalAssetEnum.CONSOLE_MEDIA_CONSTANT.name
                )
            else:
                if not value:
                    return ValidationErrorResponse(
                        detail=messages.VALUE_REQUIRED_FOR_NON_MEDIA
                    )
                updated_value: str = value
                is_media_type: bool = False
                asset_type: Optional[str] = None

            updated_constant: List[ConstantResponseSchema] = (
                await constants_service.update_constant(
                    id=id,
                    constant_model=constant_model,
                    value=updated_value,
                    is_media_type=is_media_type,
                    asset_type=asset_type,
                    user_id=user_id,
                    description=description,
                )
            )

            console_service_logger.info(
                "Successfully updated constant ID: {}, Type: {}".format(
                    id, constant_type.name
                )
            )
            return SuccessResponse(data=updated_constant)

        except Exception as e:
            console_service_logger.error(
                "An Error occured while updating constant ID {}:, Type: {}".format(
                    id, constant_type.name
                )
            )
            return InternalServerErrorResponse(
                detail=messages.UPDATE_CONSTANT_EXCEPTION.format(e)
            )

    @constants_router.put(
        "/rollback_constant/{id}",
        response_model=ConstantResponseSchema,
        description="Rollback a constant to a previous version",
    )
    @permission_check(PermissionDependency)
    @inject
    async def rollback_constant(
        request: Request,
        id: int,
        target_version: int,
        constant_type: ConstantsTypes = Query(
            ...,
            description=messages.CONSTANT_TYPE_DESCRIPTION,
        ),
        constants_service: ConstantsService = Depends(
            Provide[Container.constants_service]
        ),
        console_service_logger: ConsoleServiceLogger = Depends(
            Provide[Container.console_service_logger]
        ),
    ):
        """
        Rollback a constant to the specified version. The constant's version will be updated, and the value will be restored from additional_info.
        """
        try:
            console_service_logger.info(
                "Received request to rollback constant ID: {}, Target Version: {}".format(
                    id, target_version
                )
            )
            current_user: dict = request.state.user
            user_id: int = current_user.get(CurrentUserMap.USER_ID)

            updated_constant: List[ConstantResponseSchema] = (
                await constants_service.rollback_constant(
                    id=id,
                    target_version=target_version,
                    constant_type=constant_type,
                    user_id=user_id,
                )
            )

            console_service_logger.info(
                "Successfully rolled back constant ID: {} to version {}".format(
                    id, target_version
                )
            )
            return SuccessResponse(data=updated_constant)

        except ConstantNotFoundException as exec:
            console_service_logger.error(
                "Constant with ID {} not found: {}".format(id, str(exec))
            )
            return NotFoundResponse(detail=str(exec))

        except ConstantVersionNotFoundException as exec:
            console_service_logger.error(
                "Version not found for constant ID {}: {}".format(id, str(exec))
            )
            return NotFoundResponse(detail=str(exec))

        except ConstantVersionException as exec:
            console_service_logger.error(
                "Constant ID {} is already at the requested version: {}".format(
                    id, str(exec)
                )
            )
            return BadRequestResponse(detail=str(exec))

        except Exception as e:
            console_service_logger.error(
                "An Error occurred while rolling back constant ID {} to version {}: {}".format(
                    id, target_version, str(e)
                )
            )
            return InternalServerErrorResponse(
                detail=messages.ROLLBACK_CONSTANT_EXCEPTION.format(e)
            )
