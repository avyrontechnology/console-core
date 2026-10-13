from uuid import UUID
from dependency_injector.wiring import Provide, inject
from fastapi import APIRouter, Body, Depends, Request
from fastapi.encoders import jsonable_encoder

from src.components.common.errors import ErrorMsg
from src.components.common.response import (
    BadRequestResponse,
    InternalServerErrorResponse,
    NotFoundResponse,
    ResourceConflictResponse,
    ResourceCreatedResponse,
    SuccessResponse,
)
from src.components.partner.error import PartnerNotFoundError
from src.components.partner_meta_data.constant import PartnerMetaDataExceptionMsg
from src.components.partner_meta_data.models import PartnerMetaData
from src.components.partner_meta_data.schema import (
    PartnerMetadata,
    PartnerMetaDataResponse,
    UpdatePartnerMetaData,
)
from src.components.partner_meta_data.services import PartnerMetaDataServices
from src.components.rbac.permission_injector import permission_check
from src.core.container import Container
from src.exceptions import PartnerMetaDataException, PartnerNotFoundException
from src.loggers.console_service_logger import ConsoleServiceLogger


class PartnerMetaDataController:
    """
    This api has one-to-one relationship with partner whenever new partner will create
    after that PartnerMetaData will also created
    """

    partner_meta_data_router = APIRouter()

    @partner_meta_data_router.post(
        "/partner_meta_data/{partner_id}", response_model=PartnerMetaDataResponse
    )
    @permission_check("console:create_partner_metadata")
    @inject
    async def create_partner_metadata(
        request: Request,
        partner_id: UUID,
        partner_meta_data: PartnerMetadata = Body(...),
        partner_meta_data_service: PartnerMetaDataServices = Depends(
            Provide[Container.partner_meta_data_service]
        ),
        console_service_logger: ConsoleServiceLogger = Depends(
            Provide[Container.console_service_logger]
        ),
    ):
        try:
            console_service_logger.info(
                "Attempting to create partner metadata Partner ID: {}".format(
                    partner_id
                )
            )

            created_partner_metadata: PartnerMetaData = (
                await partner_meta_data_service.create_partner_metadata(
                    partner_id=partner_id, partner_meta_data=partner_meta_data
                )
            )
            console_service_logger.info(
                "Partner metadata created successfully, Partner ID: {}".format(
                    partner_id
                )
            )
            return ResourceCreatedResponse(jsonable_encoder(created_partner_metadata))
        except PartnerNotFoundError as exc:
            console_service_logger.error(
                "Partner not found while creating meta data: {}".format(str(exc))
            )
            return NotFoundResponse(str(exc))
        except PartnerMetaDataException as e:
            console_service_logger.error(
                "Unexpected error during partner meta data creation: {}".format(str(e))
            )
            return ResourceConflictResponse(str(e))
        except Exception as ex:
            console_service_logger.error(
                "Unexpected error during partner meta data creation: {}".format(str(ex))
            )
            return InternalServerErrorResponse(ErrorMsg.INTERNAL_SERVER_ERROR)

    @partner_meta_data_router.patch(
        "/partner_meta_data/{partner_id}", response_model=PartnerMetaDataResponse
    )
    @permission_check("console:update_partner_meta_data")
    @inject
    async def update_partner_meta_data(
        request: Request,
        partner_id: UUID,
        update_data: UpdatePartnerMetaData = Body(...),
        partner_meta_data_service: PartnerMetaDataServices = Depends(
            Provide[Container.partner_meta_data_service]
        ),
        console_service_logger: ConsoleServiceLogger = Depends(
            Provide[Container.console_service_logger]
        ),
    ):
        try:
            console_service_logger.info(
                "Attempting to update partner metadata Partner ID: {}".format(
                    partner_id
                )
            )
            updated_partner_meta_data: PartnerMetaDataResponse = (
                await partner_meta_data_service.update_partner_meta_data(
                    partner_id, update_data
                )
            )
            console_service_logger.info(
                "Partner metadata updated successfully, data:{}".format(
                    updated_partner_meta_data
                )
            )
            return SuccessResponse(
                jsonable_encoder(
                    PartnerMetaDataResponse.from_orm(updated_partner_meta_data)
                )
            )

        except PartnerMetaDataException as ex:
            console_service_logger.error(
                "Error occurred while update partner metadata by partner_id '{}' error: {}".format(
                    partner_id, ex
                )
            )
            return NotFoundResponse(str(ex))
        except PartnerNotFoundException as exc:
            console_service_logger.error(
                "Partner not found for given partner id: {} giving error: {}".format(
                    partner_id, exc
                )
            )
            return NotFoundResponse(
                detail="Parnter  not found for partner id : {}".format(partner_id)
            )

        except Exception as ex:
            console_service_logger.error(
                "Error occurred while update partner metadata by partner_id '{} error: {}'".format(
                    partner_id, ex
                )
            )
            return InternalServerErrorResponse(ErrorMsg.INTERNAL_SERVER_ERROR)

    @partner_meta_data_router.get(
        "/partner_meta_data/partner/{partner_id}",
        response_model=PartnerMetaDataResponse,
    )
    @permission_check("console:get_partner_meta_data")
    @inject
    async def get_partner_meta_data(
        request: Request,
        partner_id: UUID,
        partner_meta_data_service: PartnerMetaDataServices = Depends(
            Provide[Container.partner_meta_data_service]
        ),
        console_service_logger: ConsoleServiceLogger = Depends(
            Provide[Container.console_service_logger]
        ),
    ):
        try:
            console_service_logger.info(
                "Attempting to partner metadata by partner id: {}".format(partner_id)
            )
            partner_meta_data: PartnerMetaData | None = (
                await partner_meta_data_service.get_partner_meta_data_by_partner_id(
                    partner_id
                )
            )

            console_service_logger.debug(
                "Got the ParnterMetaData : {}, with partner_id: {} ".format(
                    partner_meta_data, partner_id
                )
            )
            if not partner_meta_data:
                return SuccessResponse(
                    message="Partner Meta Data not found for partner id : {}".format(
                        partner_id
                    ),
                    data=PartnerMetaData(
                        type_of_business="  ",
                        years_in_business=0,
                        annual_revenue=0,
                        is_talko_enabled=False,
                    ),
                )

            console_service_logger.info(
                "Successfully fetched partner metadata by partner_id {} {}".format(
                    partner_id, partner_meta_data
                )
            )
            return SuccessResponse(
                jsonable_encoder(PartnerMetaDataResponse.from_orm(partner_meta_data))
            )
        except Exception as ex:
            console_service_logger.error(
                "Error occurred while get partner metadata by partner_id {}".format(ex)
            )
            return InternalServerErrorResponse(ErrorMsg.INTERNAL_SERVER_ERROR)
