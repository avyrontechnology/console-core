from dependency_injector.wiring import Provide, inject
from fastapi import APIRouter, Depends

from src.components.common.response import (
    SuccessResponse,
    InternalServerErrorResponse,
)
from src.components.db_constants.schema import NavbarMarqueeResponseSchema
from src.components.db_constants.services import ConstantsService
from src.core.container import Container
from src.loggers.console_service_logger import ConsoleServiceLogger


class AppConfigController:

    app_config_router = APIRouter(prefix="/app-config", tags=["App Config"])

    @app_config_router.get(
        "/navbar-marquee", response_model=NavbarMarqueeResponseSchema
    )
    @inject
    async def get_navbar_marquee(
        constants_service: ConstantsService = Depends(
            Provide[Container.constants_service]
        ),
        console_service_logger: ConsoleServiceLogger = Depends(
            Provide[Container.console_service_logger]
        ),
    ):
        """
        Returns the current navbar marquee status and message.
        Readable by any authenticated user of any partner — no RBAC
        permission required, since it only drives what the navbar renders.
        `message` is null whenever the marquee is disabled or unconfigured.
        """
        try:
            console_service_logger.info("Fetching navbar marquee config")
            navbar_marquee: NavbarMarqueeResponseSchema = (
                await constants_service.get_navbar_marquee_config()
            )
            console_service_logger.info(
                "Navbar marquee config fetched successfully: {}".format(
                    navbar_marquee
                )
            )
            return SuccessResponse(
                data=navbar_marquee,
                message="Navbar marquee config fetched successfully",
            )
        except Exception as exec:
            console_service_logger.error(
                "Unexpected error occured while fetching navbar marquee config: {}".format(
                    exec
                )
            )
            return InternalServerErrorResponse()