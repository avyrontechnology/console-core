from typing import List, Optional

from dependency_injector.wiring import Provide, inject
from fastapi import APIRouter, Depends, Query, Request

from src.components.audit_log.schema import AuditLogResponse
from src.components.audit_log.services import AuditService
from src.components.common.response import InternalServerErrorResponse, SuccessResponse
from src.components.rbac.permission_injector import permission_check
from src.core.container import Container
from src.loggers.console_service_logger import ConsoleServiceLogger


class AuditLogController:

    audit_log_router = APIRouter()

    @audit_log_router.get("/audit-logs", response_model=List[AuditLogResponse])
    @permission_check("console:get_audit_logs")
    @inject
    async def get_audit_logs(
        request: Request,
        resource: Optional[str] = Query(default=None),
        action: Optional[str] = Query(default=None),
        limit: int = Query(default=50, ge=1, le=500),
        offset: int = Query(default=0, ge=0),
        audit_service: AuditService = Depends(Provide[Container.audit_service]),
        console_service_logger: ConsoleServiceLogger = Depends(
            Provide[Container.console_service_logger]
        ),
    ):
        try:
            console_service_logger.info(
                "Fetching audit logs resource={} action={}".format(resource, action)
            )
            logs: list[AuditLogResponse] = await audit_service.get_audit_logs(
                resource=resource, action=action, limit=limit, offset=offset
            )
            return SuccessResponse(data=logs)
        except Exception as exec:
            console_service_logger.error(
                "An unexpected error occured while fetching audit logs: {}".format(exec)
            )
            return InternalServerErrorResponse(detail=str(exec))
