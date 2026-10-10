"""Request / response helpers shared by the OAuth controller.

Lives separately from controllers.py so the controller file stays
focused on route definitions (matches the project pattern — most
components keep a thin controller and push helpers to a service /
utility module). Pure functions only; no DB / network I/O.

Anything that touches Redis, the DB, or the JWKS goes through the
service layer (``service.py``) or repositories (``repositories.py``)
— not here.
"""

import base64
import os
from typing import Optional, Tuple
from urllib.parse import urlencode

from fastapi import Request
from fastapi.responses import JSONResponse

from src.components.oauth_server.constants import (
    BASIC_AUTH_PREFIX,
    NO_STORE_RESPONSE_HEADERS,
    HttpHeader,
    OAuthTokenType,
)


# ── Request shaping ──────────────────────────────────────────────────────────
def client_ip(request: Request) -> str:
    """Best-effort client IP. Honours the first hop in ``X-Forwarded-For``
    when behind a trusted proxy. Falls back to the socket peer; rate-limiter
    callers tolerate spoofed XFF because the global cap is the backstop.
    """
    xff = request.headers.get(HttpHeader.XFF)
    if xff:
        return xff.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def user_agent(request: Request) -> Optional[str]:
    ua = request.headers.get(HttpHeader.USER_AGENT)
    return ua[:512] if ua else None


def current_user_id(request: Request) -> Optional[int]:
    """Return the logged-in console user id from request.state.user, or None.

    The console-service AuthMiddleware places either the decoded JWT payload
    (dict) or, for unauthenticated optional-auth requests, None on
    request.state.user. We handle both.
    """
    user = getattr(request.state, "user", None)
    if not user:
        return None
    if isinstance(user, dict):
        return user.get("user_id") or user.get("id")
    return getattr(user, "user_id", None) or getattr(user, "id", None)


def resolve_client_credentials(
    request: Request,
    form_client_id: Optional[str],
    form_client_secret: Optional[str],
) -> Tuple[Optional[str], Optional[str]]:
    """Per RFC 6749 §2.3.1 — Basic auth wins over body params if both set."""
    auth = request.headers.get(HttpHeader.AUTHORIZATION, "")
    if auth.startswith(BASIC_AUTH_PREFIX):
        try:
            raw = base64.b64decode(auth[len(BASIC_AUTH_PREFIX):]).decode("utf-8")
            if ":" in raw:
                cid, sec = raw.split(":", 1)
                return cid, sec
        except Exception:
            return None, None
    return form_client_id, form_client_secret


# ── SPA redirect URL builders ────────────────────────────────────────────────
def login_redirect_for(request_id: str) -> str:
    """SPA login URL — frontend reads ?oauth_request_id and POSTs to
    /oauth/authorize/continue after login.
    """
    base = os.getenv("OAUTH_LOGIN_REDIRECT_URL", "/login")
    sep = "&" if "?" in base else "?"
    return f"{base}{sep}{urlencode({'oauth_request_id': request_id})}"


def consent_redirect_for(request_id: str) -> str:
    base = os.getenv("OAUTH_CONSENT_REDIRECT_URL", "/oauth/consent")
    sep = "&" if "?" in base else "?"
    return f"{base}{sep}{urlencode({'oauth_request_id': request_id})}"


def append_query(url: str, params: dict) -> str:
    """Append ``params`` to a URL that may or may not already carry a query
    string. Used to attach ``?code=...&state=...`` to a registered
    redirect_uri at the end of the auth flow.
    """
    sep = "&" if "?" in url else "?"
    return f"{url}{sep}{urlencode(params)}"


# ── Response builders ────────────────────────────────────────────────────────
def ok_token_json(
    access_token: str,
    ttl: int,
    refresh_token: Optional[str],
    scope: str,
) -> JSONResponse:
    """Spec-shaped /oauth/token success response (RFC 6749 §5.1)."""
    body = {
        "access_token": access_token,
        "token_type": OAuthTokenType.BEARER,
        "expires_in": ttl,
        "scope": scope,
    }
    if refresh_token:
        body["refresh_token"] = refresh_token
    return JSONResponse(
        content=body,
        status_code=200,
        headers=dict(NO_STORE_RESPONSE_HEADERS),
    )
