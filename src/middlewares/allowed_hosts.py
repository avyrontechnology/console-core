import json

from dependency_injector.wiring import Provide, inject
from fastapi import Depends, Request
from starlette.middleware.base import BaseHTTPMiddleware

from src.components.common.response import (
    BadRequestResponse,
    ForbiddenResponse,
    InternalServerErrorResponse,
)
from src.core.container import Container
from src.loggers.console_service_logger import ConsoleServiceLogger


class AllowedHostsMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, allowed_hosts: list[str]):
        super().__init__(app)
        self.allowed_hosts = allowed_hosts

    @inject
    async def dispatch(
        self,
        request,
        call_next,
        console_service_logger: ConsoleServiceLogger = Depends(
            Provide[Container.console_service_logger]
        ),
    ):

        try:
            console_service_logger.debug("Verfying Allowed Hosts at Middleware...")
            if request.headers.get("content-type") == "application/json":
                await request.json()  # Attempt to parse JSON
            host = request.headers.get("host")
            if host not in self.allowed_hosts:
                console_service_logger.error(f"Host not Allowed Host: {host}")
                return ForbiddenResponse(detail="Host Not Allowed")
            return await call_next(request)
        except json.JSONDecodeError as exc:
            return BadRequestResponse("Invalid JSON format")
        except Exception as exc:
            console_service_logger.error(f"Got an unexpected Error: {exc}")
            return InternalServerErrorResponse()
