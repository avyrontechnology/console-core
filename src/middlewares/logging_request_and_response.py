import json
import time

from dependency_injector.wiring import Provide, inject
from fastapi import Depends, Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import StreamingResponse
from starlette_context import context
from starlette_context.plugins.request_id import RequestIdPlugin

from src.components.api_logs.services import APILogService
from src.components.common.errors import ErrorMsg
from src.components.common.response import (
    BadRequestResponse,
    InternalServerErrorResponse,
)
from src.middlewares.constants import ClientType
from src.core.container import Container
from src.loggers.console_service_logger import ConsoleServiceLogger
from src.components.auth.masker import mask_for_logs


class RequestResponseLoggingMiddleware(BaseHTTPMiddleware):
    EXCLUDED_PATHS = (
        "/docs",
        "/openapi.json",
        "/robots.txt",
        "/create_partner",
        "/partner",
        "/update_constant",
        "/get_user_details_by_ivr",
    )

    @staticmethod
    def _parse_request_body(body: bytes):
        """Parse request body safely."""
        if not body:
            return None
        try:
            return json.loads(body.decode("utf-8"))
        except Exception:
            return body.decode("utf-8", errors="ignore")

    @staticmethod
    def _get_client_ip(request: Request) -> str:
        """Extract client IP from request."""
        return (
            request.headers.get("x-forwarded-for")
            or request.headers.get("x-real-ip")
            or getattr(request.client, "host", "UNKNOWN_IP")
        )

    @staticmethod
    def _parse_response_body(response: Response, raw_body: bytes):
        """Parse response body based on status code and content type."""
        if response.status_code == 204:
            return {"message": "No Content"}

        if response.media_type and (
            "pdf" in response.media_type or "octet-stream" in response.media_type
        ):
            return {"message": "<binary content>"}

        decoded = None
        try:
            decoded = raw_body.decode("utf-8")
            return json.loads(decoded) if decoded else {"message": "No body"}
        except Exception:
            return decoded if raw_body else None

    def _log_request(
        self,
        request: Request,
        request_body,
        client_type: str,
        console_service_logger: ConsoleServiceLogger,
    ):
        """Log request details. Password is masked"""
        console_service_logger.info(
            json.dumps(
                {
                    "request_method": request.method,
                    "request_url": str(request.url),
                    "request_headers": dict(request.headers),
                    "request_body": request_body,
                    "client_type": client_type,
                }
            )
        )

    def _log_response(
        self,
        response: Response,
        response_data,
        response_time: float,
        console_service_logger: ConsoleServiceLogger,
    ):
        """Log response details."""
        console_service_logger.info(
            json.dumps(
                {
                    "response_status_code": response.status_code,
                    "response_body": response_data,
                    "response_time": f"{response_time:.4f} seconds",
                }
            )
        )

    async def _persist_api_log(
        self,
        log_doc_dict: dict,
        api_log_service: APILogService,
        console_service_logger: ConsoleServiceLogger,
    ):
        """Persist API log to database. Password is already masked in the dict."""
        try:
            await api_log_service.log_api(log_doc_dict)
        except Exception as log_error:
            console_service_logger.error(f"API log persistence failed: {log_error}")

    @inject
    async def dispatch(
        self,
        request: Request,
        call_next,
        console_service_logger: ConsoleServiceLogger = Depends(
            Provide[Container.console_service_logger]
        ),
        api_log_service: APILogService = Depends(Provide[Container.api_log_service]),
    ):
        if any(request.url.path.endswith(p) for p in self.EXCLUDED_PATHS):
            return await call_next(request)

        log_id = context.get(RequestIdPlugin.key, "FALLBACK-ID")
        client_ip = self._get_client_ip(request)

        raw_client_type = request.headers.get("X-Client-Type", "").lower().strip()
        if raw_client_type and raw_client_type not in ClientType.VALID_VALUES:
            return BadRequestResponse(
                detail=f"Invalid X-Client-Type '{raw_client_type}'. Must be one of: {', '.join(sorted(ClientType.VALID_VALUES))}"
            )
        client_type = raw_client_type or ClientType.UNKNOWN
        context.update({"client_type": client_type})
        
        start_time = time.time()
        body = await request.body()
        request.state.body = body

        request_body = self._parse_request_body(body)
        safe_request_body = (
            mask_for_logs(request_body)
            if isinstance(request_body, (dict, list))
            else request_body
        )
        self._log_request(request, safe_request_body, client_type, console_service_logger)

        try:
            response: Response = await call_next(request)

            response_body_bytes = [section async for section in response.body_iterator]
            raw_body = b"".join(response_body_bytes)

            response_data = self._parse_response_body(response, raw_body)
            response_time = time.time() - start_time

            self._log_response(
                response, response_data, response_time, console_service_logger
            )

            log_doc_dict = {
                "log_id": log_id,
                "ip_address": client_ip,
                "request": {
                    "request_method": request.method,
                    "request_url": str(request.url),
                    "request_headers": dict(request.headers),
                    "request_body": safe_request_body,
                    "client_type": client_type,
                },
                "response": {
                    "response_status_code": response.status_code,
                    "response_body": response_data,
                    "response_time": response_time,
                },
                "timestamp": time.time(),
            }

            await self._persist_api_log(
                log_doc_dict, api_log_service, console_service_logger
            )

            async def response_stream():
                yield raw_body

            return StreamingResponse(
                response_stream(),
                status_code=response.status_code,
                headers=dict(response.headers),
                media_type=response.media_type,
            )

        except Exception as e:
            console_service_logger.error(f"Middleware failure: {e}")
            return InternalServerErrorResponse(detail=ErrorMsg.INTERNAL_SERVER_ERROR)
