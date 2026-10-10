"""OAuth-spec error responses.

OAuth 2.0/2.1 has very specific error shapes:
  - At the token/registration/revocation endpoints, errors are JSON 400/401
    bodies with `error` (and optional `error_description`, `error_uri`).
  - At the /authorize endpoint, errors are REDIRECTS back to redirect_uri
    with the same fields as query params — EXCEPT when the redirect_uri or
    client_id is itself bad, in which case we MUST NOT redirect (would leak
    the auth code to an attacker).

Keep these helpers tight — they're called from every error path.
"""

from typing import Optional
from urllib.parse import urlencode

from fastapi import HTTPException
from fastapi.responses import JSONResponse, RedirectResponse

from src.components.oauth_server.constants import OAuthErrorCode

# Module-level aliases so callers can keep writing
# ``from src.components.oauth_server.errors import INVALID_GRANT`` rather
# than reaching into the OAuthErrorCode class on every line. Single source
# of truth still lives on the class.
INVALID_REQUEST = OAuthErrorCode.INVALID_REQUEST
INVALID_CLIENT = OAuthErrorCode.INVALID_CLIENT
INVALID_GRANT = OAuthErrorCode.INVALID_GRANT
UNAUTHORIZED_CLIENT = OAuthErrorCode.UNAUTHORIZED_CLIENT
UNSUPPORTED_GRANT_TYPE = OAuthErrorCode.UNSUPPORTED_GRANT_TYPE
UNSUPPORTED_RESPONSE_TYPE = OAuthErrorCode.UNSUPPORTED_RESPONSE_TYPE
INVALID_SCOPE = OAuthErrorCode.INVALID_SCOPE
ACCESS_DENIED = OAuthErrorCode.ACCESS_DENIED
SERVER_ERROR = OAuthErrorCode.SERVER_ERROR
TEMPORARILY_UNAVAILABLE = OAuthErrorCode.TEMPORARILY_UNAVAILABLE


def oauth_error_response(
    error: str,
    description: Optional[str] = None,
    status_code: int = 400,
    headers: Optional[dict] = None,
) -> JSONResponse:
    body = {"error": error}
    if description:
        body["error_description"] = description
    return JSONResponse(status_code=status_code, content=body, headers=headers or {})


def oauth_authorize_error_redirect(
    redirect_uri: str,
    state: Optional[str],
    error: str,
    description: Optional[str] = None,
) -> RedirectResponse:
    """Build a 302 redirect to the client's redirect_uri carrying the error.

    ONLY call this once both `client_id` and `redirect_uri` have been
    validated against the registered client — otherwise you redirect to an
    attacker-controlled URL.
    """
    params = {"error": error}
    if description:
        params["error_description"] = description
    if state:
        params["state"] = state
    sep = "&" if "?" in redirect_uri else "?"
    return RedirectResponse(url=f"{redirect_uri}{sep}{urlencode(params)}", status_code=302)


class OAuthError(HTTPException):
    """Used inside service-layer code; converted to JSON by the controller."""

    def __init__(
        self,
        error: str,
        description: Optional[str] = None,
        status_code: int = 400,
    ):
        super().__init__(status_code=status_code, detail={"error": error, "description": description})
        self.error = error
        self.description = description
