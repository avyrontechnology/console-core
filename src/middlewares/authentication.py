from dependency_injector.wiring import Provide, inject
from fastapi import Depends, Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette_context import context
from uuid import UUID

from src.components.api_key.services import ApiKeyService
from src.components.auth.constant import AuthExceptionMsg
from src.components.auth.util import AuthUtility
from src.components.common.response import (
    InternalServerErrorResponse,
    UnauthorizedResponse,
)
from src.components.session_mangement.services import UserSessionService
from src.components.user.models import User
from src.components.user.repositories import UserRepository
from src.core.container import Container
from src.loggers.console_service_logger import ConsoleServiceLogger
from src.middlewares.constants import OPTIONAL_AUTH_PATHS


class AuthMiddleware(BaseHTTPMiddleware):

    @inject
    async def dispatch(
        self,
        request: Request,
        call_next,
        auth_utility: AuthUtility = Depends(Provide[Container.auth_service_utility]),
        console_service_logger: ConsoleServiceLogger = Depends(
            Provide[Container.console_service_logger]
        ),
        user_session_service: UserSessionService = Depends(
            Provide[Container.user_session_service]
        ),
    ):

        excluded_paths = (
            "do_login",
            "validate-otp",
            "do_signup",
            "countries",
            "states",
            "cities",
            "create_partner",
            "create_partner_address",
            "onboard_partner",
            "docs",
            "openapi.json",
            "robots.txt",
            "webhook",
            "get_user_details_by_ivr",
            "/users/bulk_create",
            "/calculate-amount",
        )

        # Skip excluded endpoints
        if any(request.url.path.endswith(path) for path in excluded_paths) or \
            "/internal/partner-db-config" in request.url.path:
            console_service_logger.info(
                f"Skipping auth middleware for excluded path: {request.url.path}"
            )
            return await call_next(request)

        is_optional_auth = any(
            request.url.path.endswith(path) for path in OPTIONAL_AUTH_PATHS
        )

        # -----------------------------------------
        # 1) CHECK API KEY FIRST
        # -----------------------------------------
        api_key = request.headers.get("API-KEY")

        if api_key:
            console_service_logger.info(
                "API Key detected in request headers. Starting API Key validation."
            )
            return await self._handle_api_key(
                request=request, api_key=api_key, call_next=call_next
            )

        # -----------------------------------------
        # 2) FALLBACK TO JWT AUTH
        # -----------------------------------------
        authorization: str = request.headers.get("Authorization")

        # If optional auth endpoint and no Authorization header, skip auth
        if is_optional_auth and not authorization:
            console_service_logger.info(
                f"Optional auth endpoint without token: {request.url.path}"
            )
            request.state.user = None
            return await call_next(request)

        console_service_logger.info("Extracting Authorization Header...")

        if not authorization or not authorization.startswith("Bearer "):
            console_service_logger.error("Missing or invalid Authorization header")
            return UnauthorizedResponse(detail="Unauthorized User")

        console_service_logger.info("Getting token from header at Middleware...")
        token_parts = authorization.split(" ")
        if len(token_parts) != 2:
            console_service_logger.error("Invalid Authorization header format")
            return UnauthorizedResponse(detail="Invalid Authorization Header Format")
        token: str = token_parts[1]

        if "logout" in request.url.path:
            console_service_logger.info("Logging out request...")
            request.state.token = token
            response = await call_next(request)
            return response

        try:
            payload = auth_utility.decode_access_token(token)
            if not payload:
                console_service_logger.error("Invalid or expired token")
                return UnauthorizedResponse(
                    detail=AuthExceptionMsg.TOKEN_EXPIRED_OR_INVALID
                )
            # UUID boundary: JWT carries IDs as strings; downstream code
            # compares them against UUID columns. Parse once here
            # (tolerate-both: leave value untouched if not a valid UUID).
            for _claim in ("user_id", "partner_id"):
                _val = payload.get(_claim)
                if isinstance(_val, str):
                    try:
                        payload[_claim] = UUID(_val)
                    except ValueError:
                        pass

            console_service_logger.info(
                "Retrieving session id from token payload at Middleware..."
            )
            user_session_id = payload.get("user_session_id")
            if not user_session_id:
                console_service_logger.error(
                    f"User Session not found in token payload: {user_session_id}"
                )
                return UnauthorizedResponse(
                    detail=AuthExceptionMsg.TOKEN_EXPIRED_OR_INVALID
                )

            console_service_logger.info(
                f"Verifying active session for user with session_id: {user_session_id}"
            )
            user_session = await user_session_service.get_user_session(user_session_id)
            if not (user_session and user_session.is_active):
                console_service_logger.info(
                    f"Active session not found for user with session_id: {user_session_id}"
                )
                return UnauthorizedResponse(
                    detail=AuthExceptionMsg.TOKEN_EXPIRED_OR_INVALID
                )

        except Exception as exc:
            console_service_logger.error(f"Internal Server Error: {exc}")
            return InternalServerErrorResponse(detail="Internal Server Error")

        # Add decoded user payload to request state
        request.state.user = payload
        context.update({"user": payload})

        console_service_logger.debug(f"Added state to request for user {payload}")

        return await call_next(request)

    async def _handle_api_key(
        self,
        request: Request,
        api_key: str,
        call_next,
        api_key_service: ApiKeyService = Depends(Provide[Container.api_key_service]),
        user_repository: UserRepository = Depends(Provide[Container.user_repository]),
        console_service_logger: ConsoleServiceLogger = Depends(
            Provide[Container.console_service_logger]
        ),
    ):
        api_key_details = await api_key_service.validate_api_key(api_key)

        if not api_key_details:
            console_service_logger.error(
                f"API Key validation failed. Invalid API Key: {api_key}"
            )
            return UnauthorizedResponse(detail="Invalid API Key")

        if not api_key_details.is_active:
            console_service_logger.error(
                f"API Key is inactive. Partner ID: {api_key_details.partner_id}"
            )
            return UnauthorizedResponse(detail="Inactive API Key")

        partner_id = api_key_details.partner_id

        console_service_logger.info(
            f"API Key validated successfully. Associated partner_id: {partner_id}"
        )

        # Get a system admin user
        console_service_logger.info(
            "Fetching system admin user for API Key authentication..."
        )
        system_admin: User = await user_repository.get_system_admin_user()
        if not system_admin:
            console_service_logger.error(
                "System admin user not found. Cannot authenticate using API Key."
            )
            return UnauthorizedResponse(detail="System admin not found")

        console_service_logger.info(
            f"System admin resolved successfully. user_id={system_admin.id}, role_id={system_admin.role_id}"
        )

        # Construct request.state.user
        request.state.user = {
            "user_id": system_admin.id,
            "partner_id": partner_id,
            "role_id": system_admin.role_id,
        }

        context.update({"user": request.state.user})
        console_service_logger.info(
            f"API Key authentication completed. user_id={system_admin.id}, partner_id={partner_id}. "
            f"Skipping JWT authentication."
        )

        return await call_next(request)
