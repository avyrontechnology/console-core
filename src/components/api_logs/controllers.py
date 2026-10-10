from dependency_injector.wiring import Provide, inject
from fastapi import APIRouter, Body, Depends, Query, Request, UploadFile, status

from src.components.api_logs.schemas import ApiLogResponse
from src.components.api_logs.services import APILogService
from src.components.common.response import InternalServerErrorResponse, SuccessResponse
from src.components.rbac.permission_dependency import PermissionDependency
from src.components.rbac.permission_injector import permission_check
from src.core.container import Container
from src.loggers.console_service_logger import ConsoleServiceLogger


class ApiLogsController:

    api_log_router = APIRouter()

    @api_log_router.get("/api_logs/{log_id}", response_model=list[ApiLogResponse])
    @permission_check(PermissionDependency)
    @inject
    async def get_api_logs_by_log_id(
        request: Request,
        log_id: str,
        api_log_service: APILogService = Depends(Provide[Container.api_log_service]),
        console_service_logger: ConsoleServiceLogger = Depends(
            Provide[Container.console_service_logger]
        ),
    ):
        try:
            console_service_logger.info(
                "Trying to get api logs by log id: {}".format(log_id)
            )
            api_logs: list[ApiLogResponse] = (
                await api_log_service.get_api_log_by_log_id(log_id)
            )
            return SuccessResponse(data=api_logs)
        except Exception as exec:
            console_service_logger.error(
                "An unexpected error occured while getting api logs: {}".format(exec)
            )
            return InternalServerErrorResponse(detail=str(exec))
