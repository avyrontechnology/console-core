"""FastAPI routes for the OAuth 2.1 authorization server.

Mirrors the project's controller convention (see ``AuthController``,
``UserController``, ``OrderController``): a single class that owns the
APIRouter and exposes every route handler as a class method. Helpers
live in [helpers.py](./helpers.py); business logic lives in
[service.py](./service.py). This file does only HTTP plumbing — every
handler logs entry, traps unexpected failures, and returns either a
spec-correct OAuth error response or an ``InternalServerErrorResponse``.

Three routers — deliberately separate — so each can be mounted under the
right authentication policy in routes/base.py:

  * ``discovery_router`` — purely public; no auth, idempotent GETs.
  * ``oauth_public_router`` — public per OAuth spec (DCR + token endpoints).
  * ``oauth_authenticated_router`` — requires a console-service session
        (consent + authorize-continue endpoints, invoked by the SPA).
"""

import json
import time
from typing import Optional

from dependency_injector.wiring import Provide, inject
from fastapi import APIRouter, Depends, Form, Request, Response
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse

from src.components.common.response import InternalServerErrorResponse
from src.components.oauth_server import bridge as _oauth_bridge
from src.components.oauth_server import config as oauth_cfg
from src.components.oauth_server import helpers as _h
from src.components.oauth_server.constants import (
    NO_STORE_RESPONSE_HEADERS,
    HttpHeader,
    OAuthClientAuthMethod,
    OAuthGrantType,
    OAuthPKCE,
    OAuthResponseType,
    OAuthSigningAlgorithm,
    OAuthSize,
    jwks_cache_control_header,
)
from src.components.oauth_server.errors import (
    ACCESS_DENIED,
    INVALID_CLIENT,
    INVALID_GRANT,
    INVALID_REQUEST,
    INVALID_SCOPE,
    SERVER_ERROR,
    TEMPORARILY_UNAVAILABLE,
    UNSUPPORTED_GRANT_TYPE,
    UNSUPPORTED_RESPONSE_TYPE,
    OAuthError,
    oauth_authorize_error_redirect,
    oauth_error_response,
)
from src.components.oauth_server.keys import keyring
from src.components.oauth_server.rate_limit import DCRRateLimiter
from src.components.oauth_server.repositories import OAuthRepository
from src.components.oauth_server.schemas import (
    AuthorizeContinueRequest,
    ClientRegistrationRequest,
    ClientRegistrationResponse,
    ConsentDecisionRequest,
    ConsentDecisionResponse,
    ConsentDetailsResponse,
)
from src.components.oauth_server.service import OAuthService
from src.core.container import Container
from src.loggers.console_service_logger import ConsoleServiceLogger


class OAuthController:
    """Routes for the self-hosted OAuth 2.1 server.

    Every endpoint exists here. Three APIRouter instances live as class
    attributes so routes/base.py can mount them under their respective
    auth policies.
    """

    discovery_router = APIRouter()
    oauth_public_router = APIRouter(prefix="/oauth")
    oauth_authenticated_router = APIRouter(prefix="/oauth")

    # Mounted DIRECTLY on the FastAPI app (NOT under /console-service/v1).
    # RFC 8414 §3 + RFC 9728 §3 prescribe well-known URLs constructed by
    # inserting ``/.well-known/<name>`` BETWEEN the host and the
    # issuer/resource path:
    #
    #   issuer       : https://host/console-service/v1
    #   spec well-known: https://host/.well-known/oauth-authorization-server/console-service/v1
    #
    # Spec-strict clients (Claude.ai Custom Connectors observed in the
    # field) compute this exact URL from the issuer claim. Without these
    # routes the discovery chain 401/404s and the client gives up before
    # ever reaching /oauth/register. We ALSO keep the legacy "naive"
    # routes on ``discovery_router`` (under /console-service/v1) so any
    # client that follows the explicit URL from our WWW-Authenticate
    # header keeps working too.
    well_known_root_router = APIRouter()

    # ── Discovery + JWKS (no auth) ────────────────────────────────────────────

    @staticmethod
    def _build_authorization_server_metadata(console_service_logger):
        """Shared body of the OAuth authorization-server discovery doc.

        Lifted out of the route handler so both the path-prefixed
        endpoint (under /console-service/v1) and the RFC-8414 root-
        level endpoint can return the exact same JSON without
        duplicating the construction logic.
        """
        try:
            console_service_logger.info(
                "OAuth discovery: authorization-server metadata requested"
            )
            issuer = oauth_cfg.OAUTH_ISSUER_URL
            if not issuer:
                console_service_logger.error(
                    "OAUTH_ISSUER_URL not configured; discovery unavailable"
                )
                return oauth_error_response(
                    SERVER_ERROR,
                    "OAUTH_ISSUER_URL not configured",
                    status_code=503,
                )
            return {
                "issuer": issuer,
                "authorization_endpoint": f"{issuer}/oauth/authorize",
                "token_endpoint": f"{issuer}/oauth/token",
                "registration_endpoint": f"{issuer}/oauth/register",
                "revocation_endpoint": f"{issuer}/oauth/revoke",
                "introspection_endpoint": f"{issuer}/oauth/introspect",
                "jwks_uri": f"{issuer}/oauth/jwks.json",
                "response_types_supported": OAuthResponseType.supported(),
                "grant_types_supported": OAuthGrantType.supported(),
                "token_endpoint_auth_methods_supported": list(
                    OAuthClientAuthMethod.all()
                ),
                "code_challenge_methods_supported": [OAuthPKCE.SUPPORTED_METHOD],
                "scopes_supported": list(oauth_cfg.SCOPE_CATALOG.keys()),
            }
        except Exception as exc:
            console_service_logger.error(
                "Error building authorization-server metadata: {}".format(str(exc))
            )
            return InternalServerErrorResponse()

    @staticmethod
    def _build_protected_resource_metadata(console_service_logger):
        """Shared body of the OAuth protected-resource discovery doc."""
        try:
            console_service_logger.info(
                "OAuth discovery: protected-resource metadata requested"
            )
            issuer = oauth_cfg.OAUTH_ISSUER_URL
            if not issuer:
                console_service_logger.error(
                    "OAUTH_ISSUER_URL not configured; protected-resource unavailable"
                )
                return oauth_error_response(
                    SERVER_ERROR,
                    "OAUTH_ISSUER_URL not configured",
                    status_code=503,
                )
            return {
                "resource": oauth_cfg.OAUTH_RESOURCE_URL,
                "authorization_servers": [issuer],
                "bearer_methods_supported": ["header"],
                "scopes_supported": list(oauth_cfg.SCOPE_CATALOG.keys()),
            }
        except Exception as exc:
            console_service_logger.error(
                "Error building protected-resource metadata: {}".format(str(exc))
            )
            return InternalServerErrorResponse()

    # ── Discovery routes (naive path-append form, under /console-service/v1) ─

    @discovery_router.get("/.well-known/oauth-authorization-server")
    @inject
    async def well_known_authorization_server(
        console_service_logger: ConsoleServiceLogger = Depends(
            Provide[Container.console_service_logger]
        ),
    ):
        return OAuthController._build_authorization_server_metadata(
            console_service_logger
        )

    @discovery_router.get("/.well-known/oauth-protected-resource")
    @inject
    async def well_known_protected_resource(
        console_service_logger: ConsoleServiceLogger = Depends(
            Provide[Container.console_service_logger]
        ),
    ):
        return OAuthController._build_protected_resource_metadata(
            console_service_logger
        )

    @discovery_router.get("/oauth/jwks.json")
    @inject
    async def jwks_endpoint(
        console_service_logger: ConsoleServiceLogger = Depends(
            Provide[Container.console_service_logger]
        ),
    ):
        try:
            console_service_logger.info("OAuth JWKS requested")
            keyring.ensure_loaded()
            return JSONResponse(
                content=keyring.jwks(),
                headers={HttpHeader.CACHE_CONTROL: jwks_cache_control_header()},
            )
        except Exception as exc:
            console_service_logger.error(
                "Error serving JWKS: {}".format(str(exc))
            )
            return InternalServerErrorResponse()

    # ── RFC-8414 / RFC-9728 spec-correct discovery (root-mounted) ────────────
    #
    # The issuer URL for our deployment is
    # ``https://<host>/console-service/v1``. Per RFC 8414 §3 (well-known
    # URI for authorization-server metadata) and RFC 9728 §3 (same for
    # protected-resource metadata), spec-strict clients construct the
    # discovery URL by inserting ``/.well-known/<name>`` BETWEEN the host
    # and the issuer/resource path:
    #
    #   https://<host>/.well-known/oauth-authorization-server/console-service/v1
    #   https://<host>/.well-known/oauth-protected-resource/console-service/v1
    #
    # Claude.ai's Custom Connector does it this way. The "naive" path-
    # append form we serve via ``discovery_router`` (under the prefix)
    # also works for clients that follow our explicit WWW-Authenticate
    # ``resource_metadata`` URL — we serve both so neither flavour fails.
    #
    # Routes mirror the JSON-building logic of the prefixed handlers
    # above; we delegate to the same helpers via direct call so a future
    # change to the discovery payload only needs to land in one place.

    @well_known_root_router.get(
        "/.well-known/oauth-authorization-server/console-service/v1"
    )
    @inject
    async def well_known_authorization_server_rfc8414(
        console_service_logger: ConsoleServiceLogger = Depends(
            Provide[Container.console_service_logger]
        ),
    ):
        return OAuthController._build_authorization_server_metadata(
            console_service_logger
        )

    @well_known_root_router.get(
        "/.well-known/oauth-protected-resource/console-service/v1"
    )
    @inject
    async def well_known_protected_resource_rfc9728(
        console_service_logger: ConsoleServiceLogger = Depends(
            Provide[Container.console_service_logger]
        ),
    ):
        return OAuthController._build_protected_resource_metadata(
            console_service_logger
        )

    # ── Bridge HTML (Phase-8 stop-gap; see oauth_server/bridge.py) ────────────
    #
    # Renders a single self-contained login + consent screen so a real MCP
    # client (Claude.ai Custom Connectors, ChatGPT) can complete the
    # auth-code flow end-to-end before the SPA team builds the proper UI.
    #
    # Public — no auth required to load the page (it logs the user in via
    # the existing ``/do_login/console`` API from inside the page itself).
    # The page never has access to any user data on its own; everything it
    # does is gated by the JWT it receives from the login API.

    @discovery_router.get("/oauth/bridge", response_class=HTMLResponse)
    @inject
    async def oauth_bridge_page(
        request: Request,
        console_service_logger: ConsoleServiceLogger = Depends(
            Provide[Container.console_service_logger]
        ),
    ):
        try:
            console_service_logger.info(
                "OAuth bridge page requested (oauth_request_id=%s)",
                request.query_params.get("oauth_request_id"),
            )
            # Resolve the API base the page should fetch against. Prefer
            # the configured issuer URL (works in deployed envs); fall
            # back to the request's own host+root_path (works in local /
            # docker where ISSUER_URL may be missing or mismatched).
            api_base = (oauth_cfg.OAUTH_ISSUER_URL or "").rstrip("/")
            if not api_base:
                root_path = request.scope.get("root_path", "") or ""
                api_base = "{}://{}{}".format(
                    request.url.scheme,
                    request.url.netloc,
                    root_path,
                )
            return HTMLResponse(content=_oauth_bridge.render(api_base))
        except Exception as exc:
            console_service_logger.error(
                "Error rendering OAuth bridge page: {}".format(str(exc))
            )
            return InternalServerErrorResponse()

    # ── Dynamic Client Registration ───────────────────────────────────────────

    @oauth_public_router.post("/register")
    @inject
    async def register_client(
        body: ClientRegistrationRequest,
        request: Request,
        repository: OAuthRepository = Depends(Provide[Container.oauth_repository]),
        rate_limiter: DCRRateLimiter = Depends(Provide[Container.oauth_rate_limiter]),
        console_service_logger: ConsoleServiceLogger = Depends(
            Provide[Container.console_service_logger]
        ),
    ):
        try:
            console_service_logger.info(
                "OAuth DCR requested: name={!r}".format(body.client_name)
            )
            if not oauth_cfg.OAUTH_REGISTRATION_ENABLED:
                console_service_logger.warning(
                    "DCR call while registration disabled"
                )
                return oauth_error_response(
                    TEMPORARILY_UNAVAILABLE,
                    "registration disabled",
                    status_code=503,
                )

            ip = _h.client_ip(request)
            if not await rate_limiter.allow(ip=ip):
                console_service_logger.warning(
                    "[oauth.dcr] rate-limited registration ip={}".format(ip)
                )
                return oauth_error_response(
                    TEMPORARILY_UNAVAILABLE,
                    "too many registrations; try later",
                    status_code=429,
                )

            for uri in body.redirect_uris:
                err = OAuthService.validate_registered_redirect_uri(uri)
                if err:
                    console_service_logger.error(
                        "DCR rejected: invalid redirect_uri={} reason={}".format(
                            uri, err
                        )
                    )
                    return oauth_error_response(
                        INVALID_REQUEST, err, status_code=400
                    )

            auth_method = (
                body.token_endpoint_auth_method or OAuthClientAuthMethod.BASIC
            )
            if auth_method not in OAuthClientAuthMethod.all():
                console_service_logger.error(
                    "DCR rejected: unsupported token_endpoint_auth_method={}".format(
                        auth_method
                    )
                )
                return oauth_error_response(
                    INVALID_REQUEST,
                    "unsupported token_endpoint_auth_method",
                    status_code=400,
                )

            requested_scope = body.scope or oauth_cfg.all_scope_names()
            allowed_scopes = OAuthService.parse_and_filter_scopes(
                requested_scope, oauth_cfg.all_scope_names()
            )
            if not allowed_scopes:
                console_service_logger.error(
                    "DCR rejected: no requested scope is in the supported set"
                )
                return oauth_error_response(
                    INVALID_SCOPE,
                    "no requested scope is in the supported set",
                    status_code=400,
                )

            client_id = OAuthService.generate_opaque(OAuthSize.CLIENT_ID_BYTES)
            client_secret = (
                None
                if auth_method == OAuthClientAuthMethod.NONE
                else OAuthService.generate_opaque(OAuthSize.CLIENT_SECRET_BYTES)
            )
            client_secret_hash = (
                None
                if client_secret is None
                else OAuthService.hash_secret(client_secret)
            )

            async with repository.session_factory() as session:
                await repository.insert_client(
                    session,
                    client_id=client_id,
                    client_secret_hash=client_secret_hash,
                    client_name=body.client_name[:255],
                    redirect_uris=list(body.redirect_uris),
                    grant_types=OAuthGrantType.supported(),
                    scope=" ".join(allowed_scopes),
                    token_endpoint_auth_method=auth_method,
                    registered_by_ip=ip,
                    registered_user_agent=_h.user_agent(request),
                )
                await session.commit()

            console_service_logger.info(
                "[oauth.dcr] registered client_id={} name={!r} method={} ip={}".format(
                    client_id, body.client_name, auth_method, ip
                )
            )

            resp = ClientRegistrationResponse(
                client_id=client_id,
                client_secret=client_secret,
                client_id_issued_at=int(time.time()),
                client_secret_expires_at=0,
                client_name=body.client_name,
                redirect_uris=list(body.redirect_uris),
                grant_types=OAuthGrantType.supported(),
                token_endpoint_auth_method=auth_method,
                scope=" ".join(allowed_scopes),
            )
            return JSONResponse(
                status_code=201,
                content=resp.model_dump(exclude_none=True),
                headers=dict(NO_STORE_RESPONSE_HEADERS),
            )
        except Exception as exc:
            console_service_logger.error(
                "Unhandled error in DCR: {}".format(str(exc))
            )
            return InternalServerErrorResponse()

    # ── /oauth/authorize ──────────────────────────────────────────────────────

    @oauth_public_router.get("/authorize")
    @inject
    async def authorize_endpoint(
        request: Request,
        client_id: str,
        redirect_uri: str,
        response_type: str = "code",
        scope: Optional[str] = None,
        state: Optional[str] = None,
        code_challenge: Optional[str] = None,
        code_challenge_method: str = OAuthPKCE.SUPPORTED_METHOD,
        repository: OAuthRepository = Depends(Provide[Container.oauth_repository]),
        console_service_logger: ConsoleServiceLogger = Depends(
            Provide[Container.console_service_logger]
        ),
    ):
        try:
            console_service_logger.info(
                "OAuth /authorize requested client_id={} redirect_uri={}".format(
                    client_id, redirect_uri
                )
            )
            # Validate client + redirect_uri BEFORE anything that could leak
            # via redirect (auth code → attacker if redirect_uri unverified).
            async with repository.session_factory() as session:
                client = await repository.get_active_client(session, client_id)
            if not client:
                console_service_logger.error(
                    "/authorize rejected: unknown client_id={}".format(client_id)
                )
                return oauth_error_response(
                    INVALID_CLIENT, "unknown client_id", status_code=400
                )
            if not OAuthService.is_registered_redirect_uri(client, redirect_uri):
                console_service_logger.error(
                    "/authorize rejected: redirect_uri not registered "
                    "client_id={} redirect_uri={}".format(client_id, redirect_uri)
                )
                return oauth_error_response(
                    INVALID_REQUEST,
                    "redirect_uri not registered",
                    status_code=400,
                )

            # Below this line we can safely redirect errors back to redirect_uri.
            if response_type != OAuthResponseType.CODE:
                return oauth_authorize_error_redirect(
                    redirect_uri,
                    state,
                    UNSUPPORTED_RESPONSE_TYPE,
                    "only 'code' is supported",
                )
            if not code_challenge or code_challenge_method != OAuthPKCE.SUPPORTED_METHOD:
                return oauth_authorize_error_redirect(
                    redirect_uri,
                    state,
                    INVALID_REQUEST,
                    "PKCE S256 challenge is required",
                )

            requested_scopes = OAuthService.parse_and_filter_scopes(
                scope, client.scope
            )
            if not requested_scopes:
                return oauth_authorize_error_redirect(
                    redirect_uri,
                    state,
                    INVALID_SCOPE,
                    "no allowed scope requested",
                )

            request_id = OAuthService.new_request_id()
            payload = {
                "client_id": client.client_id,
                "redirect_uri": redirect_uri,
                "scopes": requested_scopes,
                "state": state,
                "code_challenge": code_challenge,
                "code_challenge_method": code_challenge_method,
            }
            expires_at = (
                OAuthService.now_ms()
                + oauth_cfg.OAUTH_AUTHORIZE_REQUEST_TTL_SECONDS * 1000
            )

            user_id = _h.current_user_id(request)
            async with repository.session_factory() as session:
                await repository.insert_authorize_request(
                    session,
                    request_id=request_id,
                    payload=payload,
                    user_id=user_id,
                    expires_at=expires_at,
                )
                await session.commit()

            if not user_id:
                console_service_logger.info(
                    "/authorize bouncing to login: request_id={}".format(request_id)
                )
                return RedirectResponse(
                    url=_h.login_redirect_for(request_id), status_code=302
                )

            async with repository.session_factory() as session:
                consent = await repository.get_consent(
                    session, user_id, client.client_id
                )
            if consent and set(requested_scopes).issubset(
                set(consent.scopes or [])
            ):
                return await OAuthController._emit_code_and_redirect(
                    repository=repository,
                    user_id=user_id,
                    client_id=client.client_id,
                    redirect_uri=redirect_uri,
                    scopes=requested_scopes,
                    code_challenge=code_challenge,
                    code_challenge_method=code_challenge_method,
                    state=state,
                    request_id_to_clear=request_id,
                    console_service_logger=console_service_logger,
                )

            console_service_logger.info(
                "/authorize bouncing to consent: request_id={} user_id={}".format(
                    request_id, user_id
                )
            )
            return RedirectResponse(
                url=_h.consent_redirect_for(request_id), status_code=302
            )
        except Exception as exc:
            console_service_logger.error(
                "Unhandled error in /authorize: {}".format(str(exc))
            )
            return InternalServerErrorResponse()

    # ── /oauth/authorize/continue (SPA, after login) ──────────────────────────

    @oauth_authenticated_router.post("/authorize/continue")
    @inject
    async def authorize_continue(
        body: AuthorizeContinueRequest,
        request: Request,
        repository: OAuthRepository = Depends(Provide[Container.oauth_repository]),
        console_service_logger: ConsoleServiceLogger = Depends(
            Provide[Container.console_service_logger]
        ),
    ):
        try:
            user_id = _h.current_user_id(request)
            console_service_logger.info(
                "/authorize/continue: request_id={} user_id={}".format(
                    body.oauth_request_id, user_id
                )
            )
            if not user_id:
                return oauth_error_response(
                    ACCESS_DENIED, "login required", status_code=401
                )

            async with repository.session_factory() as session:
                req_row = await repository.get_authorize_request(
                    session, body.oauth_request_id
                )
            if not req_row or req_row.expires_at <= OAuthService.now_ms():
                console_service_logger.error(
                    "/authorize/continue: request expired or missing "
                    "request_id={}".format(body.oauth_request_id)
                )
                return oauth_error_response(
                    INVALID_REQUEST,
                    "authorize request expired",
                    status_code=400,
                )
            if req_row.user_id is None:
                async with repository.session_factory() as session:
                    await repository.update_authorize_request_user(
                        session, body.oauth_request_id, user_id
                    )
                    await session.commit()
            elif req_row.user_id != user_id:
                console_service_logger.error(
                    "/authorize/continue: user mismatch request_id={} "
                    "stash_user={} session_user={}".format(
                        body.oauth_request_id, req_row.user_id, user_id
                    )
                )
                return oauth_error_response(
                    ACCESS_DENIED,
                    "request belongs to a different user",
                    status_code=403,
                )

            payload = req_row.payload or {}
            client_id = payload.get("client_id")
            redirect_uri = payload.get("redirect_uri")
            requested_scopes = payload.get("scopes") or []

            async with repository.session_factory() as session:
                client = await repository.get_active_client(session, client_id)
            if not client or not OAuthService.is_registered_redirect_uri(
                client, redirect_uri or ""
            ):
                console_service_logger.error(
                    "/authorize/continue: stale client/redirect "
                    "client_id={}".format(client_id)
                )
                return oauth_error_response(
                    INVALID_CLIENT,
                    "client/redirect_uri no longer valid",
                    status_code=400,
                )

            async with repository.session_factory() as session:
                consent = await repository.get_consent(
                    session, user_id, client_id
                )
            if not (
                consent and set(requested_scopes).issubset(set(consent.scopes or []))
            ):
                return JSONResponse(
                    status_code=200,
                    content={
                        "next": "consent",
                        "consent_url": _h.consent_redirect_for(
                            body.oauth_request_id
                        ),
                    },
                )

            code = OAuthService.mint_auth_code()
            code_hash = OAuthService.sha256_hex(code)
            expires_at = (
                OAuthService.now_ms()
                + oauth_cfg.OAUTH_AUTH_CODE_TTL_SECONDS * 1000
            )
            async with repository.session_factory() as session:
                await repository.insert_auth_code(
                    session,
                    code_hash=code_hash,
                    client_id=client_id,
                    user_id=user_id,
                    redirect_uri=redirect_uri,
                    scopes=list(requested_scopes),
                    code_challenge=payload["code_challenge"],
                    code_challenge_method=payload["code_challenge_method"],
                    expires_at=expires_at,
                )
                await repository.delete_authorize_request(
                    session, body.oauth_request_id
                )
                await session.commit()

            params = {"code": code}
            if payload.get("state"):
                params["state"] = payload["state"]
            return JSONResponse(
                status_code=200,
                content={
                    "next": "redirect",
                    "redirect": _h.append_query(redirect_uri, params),
                },
            )
        except Exception as exc:
            console_service_logger.error(
                "Unhandled error in /authorize/continue: {}".format(str(exc))
            )
            return InternalServerErrorResponse()

    # ── /oauth/consent/details + /decision ────────────────────────────────────

    @oauth_authenticated_router.get(
        "/consent/details", response_model=ConsentDetailsResponse
    )
    @inject
    async def consent_details(
        oauth_request_id: str,
        request: Request,
        repository: OAuthRepository = Depends(Provide[Container.oauth_repository]),
        console_service_logger: ConsoleServiceLogger = Depends(
            Provide[Container.console_service_logger]
        ),
    ):
        try:
            user_id = _h.current_user_id(request)
            console_service_logger.info(
                "/consent/details: request_id={} user_id={}".format(
                    oauth_request_id, user_id
                )
            )
            if not user_id:
                return oauth_error_response(
                    ACCESS_DENIED, "login required", status_code=401
                )

            async with repository.session_factory() as session:
                req_row = await repository.get_authorize_request(
                    session, oauth_request_id
                )
                if not req_row or req_row.expires_at <= OAuthService.now_ms():
                    return oauth_error_response(
                        INVALID_REQUEST,
                        "consent request expired",
                        status_code=400,
                    )
                if req_row.user_id and req_row.user_id != user_id:
                    return oauth_error_response(
                        ACCESS_DENIED,
                        "request belongs to a different user",
                        status_code=403,
                    )
                client = await repository.get_active_client(
                    session, req_row.payload["client_id"]
                )
            if not client:
                return oauth_error_response(
                    INVALID_CLIENT,
                    "client no longer valid",
                    status_code=400,
                )

            scopes = list(req_row.payload.get("scopes") or [])
            descriptions = [oauth_cfg.SCOPE_CATALOG.get(s, s) for s in scopes]
            return ConsentDetailsResponse(
                client_name=client.client_name,
                client_id=client.client_id,
                scopes=scopes,
                scope_descriptions=descriptions,
            )
        except Exception as exc:
            console_service_logger.error(
                "Unhandled error in /consent/details: {}".format(str(exc))
            )
            return InternalServerErrorResponse()

    @oauth_authenticated_router.post(
        "/consent/decision", response_model=ConsentDecisionResponse
    )
    @inject
    async def consent_decision(
        body: ConsentDecisionRequest,
        request: Request,
        repository: OAuthRepository = Depends(Provide[Container.oauth_repository]),
        console_service_logger: ConsoleServiceLogger = Depends(
            Provide[Container.console_service_logger]
        ),
    ):
        try:
            user_id = _h.current_user_id(request)
            console_service_logger.info(
                "/consent/decision: request_id={} user_id={} allow={}".format(
                    body.oauth_request_id, user_id, body.allow
                )
            )
            if not user_id:
                return oauth_error_response(
                    ACCESS_DENIED, "login required", status_code=401
                )

            async with repository.session_factory() as session:
                req_row = await repository.get_authorize_request(
                    session, body.oauth_request_id
                )
            if not req_row or req_row.expires_at <= OAuthService.now_ms():
                return oauth_error_response(
                    INVALID_REQUEST,
                    "consent request expired",
                    status_code=400,
                )
            if req_row.user_id and req_row.user_id != user_id:
                return oauth_error_response(
                    ACCESS_DENIED,
                    "request belongs to a different user",
                    status_code=403,
                )

            payload = req_row.payload or {}
            redirect_uri = payload.get("redirect_uri") or ""
            state = payload.get("state")

            if not body.allow:
                async with repository.session_factory() as session:
                    await repository.delete_authorize_request(
                        session, body.oauth_request_id
                    )
                    await session.commit()
                console_service_logger.info(
                    "/consent/decision: user denied request_id={}".format(
                        body.oauth_request_id
                    )
                )
                params = {"error": ACCESS_DENIED}
                if state:
                    params["state"] = state
                return ConsentDecisionResponse(
                    redirect=_h.append_query(redirect_uri, params)
                )

            client_id = payload["client_id"]
            requested_scopes = payload.get("scopes") or []
            code = OAuthService.mint_auth_code()
            code_hash = OAuthService.sha256_hex(code)
            expires_at = (
                OAuthService.now_ms()
                + oauth_cfg.OAUTH_AUTH_CODE_TTL_SECONDS * 1000
            )
            async with repository.session_factory() as session:
                await repository.upsert_consent(
                    session, user_id, client_id, list(requested_scopes)
                )
                await repository.mark_authorize_request_consented(
                    session, body.oauth_request_id
                )
                await repository.insert_auth_code(
                    session,
                    code_hash=code_hash,
                    client_id=client_id,
                    user_id=user_id,
                    redirect_uri=redirect_uri,
                    scopes=list(requested_scopes),
                    code_challenge=payload["code_challenge"],
                    code_challenge_method=payload["code_challenge_method"],
                    expires_at=expires_at,
                )
                await repository.delete_authorize_request(
                    session, body.oauth_request_id
                )
                await session.commit()

            params = {"code": code}
            if state:
                params["state"] = state
            return ConsentDecisionResponse(
                redirect=_h.append_query(redirect_uri, params)
            )
        except Exception as exc:
            console_service_logger.error(
                "Unhandled error in /consent/decision: {}".format(str(exc))
            )
            return InternalServerErrorResponse()

    # ── /oauth/token ──────────────────────────────────────────────────────────

    @oauth_public_router.post("/token")
    @inject
    async def token_endpoint(
        request: Request,
        grant_type: str = Form(...),
        code: Optional[str] = Form(None),
        redirect_uri: Optional[str] = Form(None),
        code_verifier: Optional[str] = Form(None),
        refresh_token: Optional[str] = Form(None),
        client_id: Optional[str] = Form(None),
        client_secret: Optional[str] = Form(None),
        scope: Optional[str] = Form(None),
        repository: OAuthRepository = Depends(Provide[Container.oauth_repository]),
        oauth_service: OAuthService = Depends(Provide[Container.oauth_service]),
        console_service_logger: ConsoleServiceLogger = Depends(
            Provide[Container.console_service_logger]
        ),
    ):
        try:
            console_service_logger.info(
                "/oauth/token: grant_type={}".format(grant_type)
            )
            resolved_id, resolved_secret = _h.resolve_client_credentials(
                request, client_id, client_secret
            )
            if not resolved_id:
                return oauth_error_response(
                    INVALID_CLIENT, "client_id required", status_code=401
                )

            async with repository.session_factory() as session:
                try:
                    client = await oauth_service.authenticate_client(
                        session,
                        client_id=resolved_id,
                        client_secret=resolved_secret,
                        require_secret=True,
                    )
                except OAuthError as e:
                    return oauth_error_response(
                        e.error, e.description, status_code=e.status_code
                    )

            if grant_type == OAuthGrantType.AUTHORIZATION_CODE:
                if not code or not redirect_uri:
                    return oauth_error_response(
                        INVALID_REQUEST,
                        "code and redirect_uri required",
                        status_code=400,
                    )

                # NOTE: SQLAlchemy 2.x uses ``expire_on_commit=True`` by
                # default. Once we commit, every ORM attribute on ``row``
                # is expired and re-reading it triggers a refresh — which
                # fails the moment the ``async with`` block exits and the
                # session closes ("Instance ... is not bound to a Session;
                # attribute refresh operation cannot proceed"). The
                # consume_* path goes through ``UPDATE ... RETURNING``,
                # so this is the dangerous shape. SELECT-only rows
                # already have their column attrs eagerly loaded and
                # don't hit this.
                #
                # Fix: snapshot every attribute we still need into plain
                # locals INSIDE the session block, before commit closes
                # us out.
                async with repository.session_factory() as session:
                    row = await repository.consume_auth_code(
                        session, OAuthService.sha256_hex(code)
                    )
                    if row is None:
                        await session.commit()
                        row_client_id = None
                        row_redirect_uri = None
                        row_code_challenge = None
                        row_user_id = None
                        row_scopes: list = []
                    else:
                        row_client_id = row.client_id
                        row_redirect_uri = row.redirect_uri
                        row_code_challenge = row.code_challenge
                        row_user_id = row.user_id
                        row_scopes = list(row.scopes or [])
                        await session.commit()

                if row is None:
                    return oauth_error_response(
                        INVALID_GRANT,
                        "code is invalid, expired, or already used",
                        status_code=400,
                    )
                if row_client_id != client.client_id:
                    console_service_logger.error(
                        "/oauth/token: code/client mismatch client_id={} "
                        "stash_client={}".format(client.client_id, row_client_id)
                    )
                    return oauth_error_response(
                        INVALID_GRANT,
                        "code/client mismatch",
                        status_code=400,
                    )
                if row_redirect_uri != redirect_uri:
                    return oauth_error_response(
                        INVALID_GRANT,
                        "redirect_uri mismatch",
                        status_code=400,
                    )
                if not OAuthService.verify_pkce_s256(
                    code_verifier or "", row_code_challenge
                ):
                    console_service_logger.error(
                        "/oauth/token: PKCE verification failed client_id={}".format(
                            client.client_id
                        )
                    )
                    return oauth_error_response(
                        INVALID_GRANT,
                        "PKCE verification failed",
                        status_code=400,
                    )

                return await OAuthController._issue_tokens(
                    repository=repository,
                    oauth_service=oauth_service,
                    console_service_logger=console_service_logger,
                    client_id=client.client_id,
                    user_id=row_user_id,
                    scopes=row_scopes,
                    parent_refresh_hash=None,
                )

            if grant_type == OAuthGrantType.REFRESH_TOKEN:
                if not refresh_token:
                    return oauth_error_response(
                        INVALID_REQUEST,
                        "refresh_token required",
                        status_code=400,
                    )
                token_hash = OAuthService.sha256_hex(refresh_token)
                async with repository.session_factory() as session:
                    replay = await oauth_service.detect_and_handle_replay(
                        session, token_hash=token_hash
                    )
                    if replay:
                        await session.commit()
                        return oauth_error_response(
                            INVALID_GRANT,
                            "refresh_token replayed; chain revoked",
                            status_code=400,
                        )

                # Same detached-instance hazard as the auth-code path —
                # snapshot row attributes inside the session block.
                async with repository.session_factory() as session:
                    row = await repository.consume_refresh_token(
                        session, token_hash
                    )
                    if row is None:
                        await session.commit()
                        row_client_id = None
                        row_user_id = None
                        row_scopes = []
                        row_token_hash = None
                    else:
                        row_client_id = row.client_id
                        row_user_id = row.user_id
                        row_scopes = list(row.scopes or [])
                        row_token_hash = row.token_hash
                        await session.commit()

                if row is None or row_client_id != client.client_id:
                    return oauth_error_response(
                        INVALID_GRANT,
                        "refresh_token invalid",
                        status_code=400,
                    )

                scopes = row_scopes
                if scope:
                    requested = OAuthService.parse_and_filter_scopes(
                        scope, client.scope
                    )
                    if not set(requested).issubset(set(scopes)):
                        return oauth_error_response(
                            INVALID_SCOPE,
                            "requested scope exceeds granted scope",
                            status_code=400,
                        )
                    scopes = requested

                return await OAuthController._issue_tokens(
                    repository=repository,
                    oauth_service=oauth_service,
                    console_service_logger=console_service_logger,
                    client_id=client.client_id,
                    user_id=row_user_id,
                    scopes=scopes,
                    parent_refresh_hash=row_token_hash,
                )

            return oauth_error_response(
                UNSUPPORTED_GRANT_TYPE,
                "unsupported grant_type: {}".format(grant_type),
                status_code=400,
            )
        except Exception as exc:
            console_service_logger.error(
                "Unhandled error in /oauth/token: {}".format(str(exc))
            )
            return InternalServerErrorResponse()

    # ── /oauth/revoke ─────────────────────────────────────────────────────────

    @oauth_public_router.post("/revoke")
    @inject
    async def revoke_endpoint(
        request: Request,
        token: str = Form(...),
        token_type_hint: Optional[str] = Form(None),
        client_id: Optional[str] = Form(None),
        client_secret: Optional[str] = Form(None),
        repository: OAuthRepository = Depends(Provide[Container.oauth_repository]),
        oauth_service: OAuthService = Depends(Provide[Container.oauth_service]),
        console_service_logger: ConsoleServiceLogger = Depends(
            Provide[Container.console_service_logger]
        ),
    ):
        try:
            console_service_logger.info(
                "/oauth/revoke: token_type_hint={}".format(token_type_hint)
            )
            resolved_id, resolved_secret = _h.resolve_client_credentials(
                request, client_id, client_secret
            )
            if not resolved_id:
                return oauth_error_response(
                    INVALID_CLIENT, "client_id required", status_code=401
                )

            async with repository.session_factory() as session:
                try:
                    client = await oauth_service.authenticate_client(
                        session,
                        client_id=resolved_id,
                        client_secret=resolved_secret,
                        require_secret=True,
                    )
                except OAuthError as e:
                    return oauth_error_response(
                        e.error, e.description, status_code=e.status_code
                    )

                # RFC 7009 §2.2 — unknown tokens still return 200. Access
                # tokens are stateless JWTs, so we only act on refresh
                # tokens here. ``token_type_hint`` is accepted for spec
                # compatibility but not used to branch.
                token_hash = OAuthService.sha256_hex(token)
                await repository.revoke_refresh_token(
                    session, token_hash, client.client_id
                )
                await session.commit()

            return Response(status_code=200)
        except Exception as exc:
            console_service_logger.error(
                "Unhandled error in /oauth/revoke: {}".format(str(exc))
            )
            return InternalServerErrorResponse()

    # ── /oauth/introspect ─────────────────────────────────────────────────────

    @oauth_public_router.post("/introspect")
    @inject
    async def introspect_endpoint(
        request: Request,
        token: str = Form(...),
        client_id: Optional[str] = Form(None),
        client_secret: Optional[str] = Form(None),
        repository: OAuthRepository = Depends(Provide[Container.oauth_repository]),
        oauth_service: OAuthService = Depends(Provide[Container.oauth_service]),
        console_service_logger: ConsoleServiceLogger = Depends(
            Provide[Container.console_service_logger]
        ),
    ):
        import jwt as pyjwt

        try:
            console_service_logger.info("/oauth/introspect requested")
            resolved_id, resolved_secret = _h.resolve_client_credentials(
                request, client_id, client_secret
            )
            if not resolved_id:
                return oauth_error_response(
                    INVALID_CLIENT, "client_id required", status_code=401
                )

            async with repository.session_factory() as session:
                try:
                    await oauth_service.authenticate_client(
                        session,
                        client_id=resolved_id,
                        client_secret=resolved_secret,
                        require_secret=True,
                    )
                except OAuthError as e:
                    return oauth_error_response(
                        e.error, e.description, status_code=e.status_code
                    )

            keyring.ensure_loaded()
            try:
                header = pyjwt.get_unverified_header(token)
                kid = header.get("kid")
                jwk = keyring.get_public_jwk(kid) if kid else None
                if not jwk:
                    return JSONResponse(content={"active": False})
                public_key = pyjwt.algorithms.RSAAlgorithm.from_jwk(
                    json.dumps(jwk)
                )
                claims = pyjwt.decode(
                    token,
                    key=public_key,
                    algorithms=[OAuthSigningAlgorithm.RS256],
                    audience=oauth_cfg.OAUTH_RESOURCE_URL or None,
                    issuer=oauth_cfg.OAUTH_ISSUER_URL or None,
                    options={"require": ["exp", "iat", "iss", "aud"]},
                )
            except Exception:
                # Verification failure is the *normal* "active=false" path
                # per RFC 7662 §2.2; don't log as an error.
                return JSONResponse(content={"active": False})

            return JSONResponse(content={"active": True, **claims})
        except Exception as exc:
            console_service_logger.error(
                "Unhandled error in /oauth/introspect: {}".format(str(exc))
            )
            return InternalServerErrorResponse()

    # ── Private orchestration helpers ─────────────────────────────────────────

    @staticmethod
    async def _emit_code_and_redirect(
        *,
        repository: OAuthRepository,
        console_service_logger: ConsoleServiceLogger,
        user_id: int,
        client_id: str,
        redirect_uri: str,
        scopes,
        code_challenge: str,
        code_challenge_method: str,
        state: Optional[str],
        request_id_to_clear: Optional[str],
    ) -> RedirectResponse:
        """Mint a one-shot auth code, persist, drop the pending stash, and
        302 back to the client's registered redirect_uri.
        """
        try:
            code = OAuthService.mint_auth_code()
            code_hash = OAuthService.sha256_hex(code)
            expires_at = (
                OAuthService.now_ms()
                + oauth_cfg.OAUTH_AUTH_CODE_TTL_SECONDS * 1000
            )
            async with repository.session_factory() as session:
                await repository.insert_auth_code(
                    session,
                    code_hash=code_hash,
                    client_id=client_id,
                    user_id=user_id,
                    redirect_uri=redirect_uri,
                    scopes=list(scopes),
                    code_challenge=code_challenge,
                    code_challenge_method=code_challenge_method,
                    expires_at=expires_at,
                )
                if request_id_to_clear:
                    await repository.delete_authorize_request(
                        session, request_id_to_clear
                    )
                await session.commit()

            params = {"code": code}
            if state:
                params["state"] = state
            return RedirectResponse(
                url=_h.append_query(redirect_uri, params), status_code=302
            )
        except Exception as exc:
            console_service_logger.error(
                "Error emitting auth code client_id={} user_id={}: {}".format(
                    client_id, user_id, str(exc)
                )
            )
            return InternalServerErrorResponse()

    @staticmethod
    async def _issue_tokens(
        *,
        repository: OAuthRepository,
        oauth_service: OAuthService,
        console_service_logger: ConsoleServiceLogger,
        client_id: str,
        user_id: int,
        scopes,
        parent_refresh_hash: Optional[str],
    ):
        """Mint an access-token + refresh-token pair and persist the refresh
        side. Returns the spec-shaped /oauth/token JSON response.
        """
        try:
            user_details = await oauth_service.get_user_details(user_id)
            if not user_details:
                console_service_logger.error(
                    "/oauth/token: user no longer exists user_id={}".format(user_id)
                )
                return oauth_error_response(
                    INVALID_GRANT, "user no longer exists", status_code=400
                )

            try:
                access_token, ttl = OAuthService.mint_access_token(
                    user_id=user_id,
                    client_id=client_id,
                    scopes=list(scopes),
                    partner_id=user_details.get("partner_id"),
                    role=None,
                    role_hierarchy_level=user_details.get("role_hierarchy_level"),
                )
            except OAuthError as e:
                return oauth_error_response(
                    e.error, e.description, status_code=e.status_code
                )

            refresh = OAuthService.mint_refresh_token()
            refresh_hash = OAuthService.sha256_hex(refresh)
            refresh_expires = (
                OAuthService.now_ms()
                + oauth_cfg.OAUTH_REFRESH_TOKEN_TTL_SECONDS * 1000
            )
            async with repository.session_factory() as session:
                await repository.insert_refresh_token(
                    session,
                    token_hash=refresh_hash,
                    client_id=client_id,
                    user_id=user_id,
                    scopes=list(scopes),
                    expires_at=refresh_expires,
                    parent_token_hash=parent_refresh_hash,
                )
                await session.commit()

            console_service_logger.info(
                "/oauth/token: tokens issued client_id={} user_id={}".format(
                    client_id, user_id
                )
            )
            return _h.ok_token_json(
                access_token=access_token,
                ttl=ttl,
                refresh_token=refresh,
                scope=" ".join(scopes),
            )
        except Exception as exc:
            console_service_logger.error(
                "Error issuing tokens client_id={} user_id={}: {}".format(
                    client_id, user_id, str(exc)
                )
            )
            return InternalServerErrorResponse()
