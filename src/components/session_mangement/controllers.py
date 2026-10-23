from dependency_injector.wiring import Provide, inject
from fastapi import APIRouter, Depends, Request

from src.loggers.console_service_logger import ConsoleServiceLogger
from src.core.container import Container
from typing import List
from src.components.session_mangement.services import UserSessionService
from src.components.auth.constant import ServiceNames
from src.components.common.response import SuccessResponse, InternalServerErrorResponse
from src.components.rbac.permission_injector import permission_check

class UserSessionController:

    user_session_router = APIRouter()

    @user_session_router.post("/deactive-user-session")
    @permission_check("console:deactivate_sessions_by_service_name")
    @inject
    async def deactivate_sessions_by_service_name(
        request: Request,
        service_name: ServiceNames,
        user_session_service: UserSessionService = Depends(Provide[Container.user_session_service]),
        console_logger: ConsoleServiceLogger = Depends(
            Provide[Container.console_service_logger]
        ),
    ):
        try:

            console_logger.info("Attempting to deactivated session by service name={}".format(service_name))

            response: str = (
                await user_session_service.deactivate_all_sessions_by_service_name(service_name)
            )

            return SuccessResponse(
                data=response
            )

        except Exception as ex:
            console_logger.error("Unexpected error occrred while deactivating session by service name {}, error: {}".format(service_name,str(ex)))
            return InternalServerErrorResponse(str(ex))
