from dependency_injector.wiring import Provide, inject
from fastapi import Depends, Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.routing import Match
from starlette_context import context
from uuid import UUID
import time

from src.components.api_key.services import ApiKeyService
from src.components.auth.constant import AuthExceptionMsg, TokenKeys
from src.components.auth.util import AuthUtility
from src.components.cache import Keys as CacheKeys
from src.components.cache.helper import CacheHelper
from src.components.common.response import (
    InternalServerErrorResponse,
    UnauthorizedResponse,
)
from src.components.session_mangement.services import UserSessionService
from src.components.user.models import User
from src.components.user.repositories import UserRepository
from src.core.container import Container
from src.loggers.console_service_logger import ConsoleServiceLogger
from src.middlewares.constants import OPTIONAL_AUTH_ROUTES


def _resolve_route(app, scope: dict):
    """Find the route matching this scope before the router has run.

    Uses Starlette's own matcher so the name we trust is the resolved route,
    never a substring of the URL.
    """
    try:
        for route in app.routes:
            match, _child_scope = route.matches(scope)
            if match == Match.FULL:
                return route
    except Exception:
        return None
    return None


def _normalize_id_claims(payload: dict) -> dict:
    """Parse JWT string ID claims to UUID (tolerate-both)."""
    for _claim in ("user_id", "partner_id"):
        _val = payload.get(_claim)
        if isinstance(_val, str):
            try:
                payload[_claim] = UUID(_val)
            except ValueError:
                pass
    return payload


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
        cache_helper: CacheHelper = Depends(Provide[Container.cache_helper]),
    ):

        # Public routes, matched by ROUTE NAME (function name) — never by
        # substring, so /x/webhook or /evil-get-plans can't slip through.
        # Static-asset paths are matched exactly below.
        public_route_names = {
            "do_login",
            "validate_otp",
            "do_signup",
            "get_all_countries",
            "get_states_by_country",
            "get_cities_by_state",
            "add_partner",  # POST /create_partner (onboarding)
            "onboard_partner",
            "payment_webhook",
            "get_user_details_by_ivr",
            "calculate_amount",
            "upsert_partner_db_config",
            "get_partner_db_config",
            "delete_partner_db_config",
        }
        public_exact_paths = {
            "/docs",
            "/openapi.json",
            "/robots.txt",
        }

        route = None
        try:
            scope = request.scope
        except AttributeError:
            scope = None
        if isinstance(scope, dict):
            route = scope.get("route")
        if route is None and isinstance(scope, dict):
            # BaseHTTPMiddleware runs BEFORE the router, so scope["route"] is
            # still unset. Resolve it by matching the app's routes ourselves;
            # without this every public route (login, signup, webhooks) was
            # treated as private and answered 401.
            route = _resolve_route(request.app, scope)
        route_name = getattr(route, "name", None) or getattr(route, "path", None)
        request_path: str = request.url.path

        # Skip excluded endpoints
        if route_name in public_route_names or request_path in public_exact_paths:
            console_service_logger.info(
                f"Skipping auth middleware for excluded path: {request.url.path}"
            )
            return await call_next(request)

        is_optional_auth = route_name in OPTIONAL_AUTH_ROUTES

        # -----------------------------------------
        # 1) CHECK API KEY FIRST
        # -----------------------------------------
        api_key = request.headers.get("API-KEY")
        authorization: str = request.headers.get("Authorization")

        if api_key and authorization:
            # Ambiguous credentials: fail closed instead of silently
            # preferring one (previously the key silently won).
            console_service_logger.error(
                "Conflicting credentials: both API-KEY and Authorization present"
            )
            return UnauthorizedResponse(
                detail="Ambiguous credentials: send either API-KEY or Authorization, not both"
            )

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
        # (authorization already read above for the precedence check)

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
            payload = _normalize_id_claims(payload)

            # Fast path: login wrote this payload to cache (TTL = token
            # expiry); logout/bust deletes it. A hit skips the DB session
            # lookup below. Expiry is re-checked from the payload itself.
            cache_hit = False
            try:
                cached = await cache_helper.get_cache(
                    key=CacheKeys.TOKEN.format(payload.get("partner_id"), token)
                )
                if isinstance(cached, dict) and cached.get("user_id"):
                    exp = cached.get(TokenKeys.EXPIRED)
                    if exp is None or float(exp) > time.time():
                        payload = _normalize_id_claims(dict(cached))
                        cache_hit = True
                        console_service_logger.debug(
                            "Token payload served from cache."
                        )
            except Exception as cache_exc:
                console_service_logger.debug(
                    f"Token cache lookup failed, falling back to DB: {cache_exc}"
                )

            if not cache_hit:
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

        if api_key_details.expires_at is not None:
            from src.components.common.datetime import DateTimeUtil

            if float(api_key_details.expires_at) <= float(
                DateTimeUtil.get_current_time()
            ):
                console_service_logger.error(
                    f"API Key expired. Partner ID: {api_key_details.partner_id}"
                )
                return UnauthorizedResponse(detail="Expired API Key")

        partner_id = api_key_details.partner_id

        console_service_logger.info(
            f"API Key validated successfully. Associated partner_id: {partner_id}"
        )

        # Least privilege: act as the key's user_context user, NOT the
        # system admin. Falls back to system admin only when the key
        # carries no user_context (legacy keys) — still partner-scoped.
        key_user_id = None
        if isinstance(api_key_details.user_context, dict):
            key_user_id = api_key_details.user_context.get("user_id")
        if key_user_id is not None:
            try:
                key_user_id = (
                    key_user_id if isinstance(key_user_id, UUID) else UUID(str(key_user_id))
                )
            except (ValueError, AttributeError, TypeError):
                console_service_logger.error("API Key has malformed user_context.")
                return UnauthorizedResponse(detail="Invalid API Key")

        acting_user_id = key_user_id
        acting_role_id = None
        if acting_user_id is None:
            console_service_logger.info(
                "API key has no user_context; resolving system admin user..."
            )
            system_admin: User = await user_repository.get_system_admin_user()
            if not system_admin:
                console_service_logger.error(
                    "System admin user not found. Cannot authenticate using API Key."
                )
                return UnauthorizedResponse(detail="System admin not found")
            acting_user_id = system_admin.id
            acting_role_id = system_admin.role_id
            console_service_logger.info(
                f"System admin resolved successfully. user_id={system_admin.id}, role_id={system_admin.role_id}"
            )

        # Construct request.state.user + an explicit API-key marker so
        # downstream (PermissionDependency) can enforce key scopes.
        # Scopes are NOT in state.user: empty/missing = deny-all there.
        request.state.user = {
            "user_id": acting_user_id,
            "partner_id": partner_id,
            "role_id": acting_role_id,
        }
        request.state.api_key = {
            "scopes": list(api_key_details.scopes or []),
            "key_id": str(api_key_details.id),
        }

        context.update({"user": request.state.user})
        console_service_logger.info(
            f"API Key authentication completed. user_id={acting_user_id}, partner_id={partner_id}. "
            f"Skipping JWT authentication."
        )

        return await call_next(request)
