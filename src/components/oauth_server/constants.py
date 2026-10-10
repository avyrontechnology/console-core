"""Pure constants for the OAuth 2.1 authorization server.

Anything that is a literal, regex, byte-length, or spec-defined string lives
here. Anything that reads an env var (issuer URL, TTLs, feature flags) lives
in [config.py](./config.py). The split keeps the constants module fully
side-effect-free so it can be imported anywhere without dragging in
``os.getenv`` behaviour.

Convention: group related values under a class — keeps the namespace tidy
when imported and matches the existing project style (see
``src/components/plan/constants.py``).
"""

import re


# ── OAuth-spec error codes ───────────────────────────────────────────────────
# Names match RFC 6749 / OAuth 2.1 exactly. Used in JSON responses on the
# token / DCR endpoints, and in redirect-back errors on /authorize.
class OAuthErrorCode:
    INVALID_REQUEST = "invalid_request"
    INVALID_CLIENT = "invalid_client"
    INVALID_GRANT = "invalid_grant"
    UNAUTHORIZED_CLIENT = "unauthorized_client"
    UNSUPPORTED_GRANT_TYPE = "unsupported_grant_type"
    UNSUPPORTED_RESPONSE_TYPE = "unsupported_response_type"
    INVALID_SCOPE = "invalid_scope"
    ACCESS_DENIED = "access_denied"
    SERVER_ERROR = "server_error"
    TEMPORARILY_UNAVAILABLE = "temporarily_unavailable"


# ── Token + credential byte lengths ──────────────────────────────────────────
class OAuthSize:
    # All measured in bytes; ``secrets.token_urlsafe`` returns ~1.33× chars.
    ACCESS_TOKEN_BYTES = 32  # JTI claim entropy
    AUTH_CODE_BYTES = 32  # opaque code material before SHA-256 hash
    REFRESH_TOKEN_BYTES = 48  # higher entropy — long-lived secret
    REQUEST_ID_BYTES = 24  # authorize-request stash id
    CLIENT_ID_BYTES = 24  # opaque client_id
    CLIENT_SECRET_BYTES = 40  # entropy for the one-time-revealed secret


# ── PKCE (RFC 7636) ──────────────────────────────────────────────────────────
class OAuthPKCE:
    # Spec §4.1: 43 ≤ len(code_verifier) ≤ 128.
    MIN_VERIFIER_LEN = 43
    MAX_VERIFIER_LEN = 128
    # Spec §4.1: unreserved ALPHA / DIGIT / "-" / "." / "_" / "~".
    VERIFIER_REGEX = re.compile(r"^[A-Za-z0-9_\-.~]+$")
    SUPPORTED_METHOD = "S256"


# ── Redirect-URI policy ──────────────────────────────────────────────────────
# Loopback HTTP redirect URIs are normally a security violation; we accept
# them at registration ONLY when OAUTH_ALLOW_LOCAL_REDIRECT=true.
LOOPBACK_HOSTS = frozenset({"127.0.0.1", "::1", "localhost"})


# ── Rate limiter (DCR) ───────────────────────────────────────────────────────
class OAuthRateLimit:
    # Fixed-window bucket size in seconds. Buckets are wall-clock-aligned at
    # ``now // WINDOW_SECONDS`` so an attacker cannot slide requests across
    # an arbitrary window. Known fixed-window limitation: 2× burst at bucket
    # boundary — acceptable because DCR limits are coarse (tens per hour).
    WINDOW_SECONDS = 3600
    # Redis key namespace, distinct from any other limiter in the codebase.
    KEY_PREFIX = "oauth:dcr:rl:"
    # Padding (seconds) added to the EXPIRE so wall-clock skew across pods
    # doesn't briefly drop a bucket before the window ends.
    TTL_PADDING_SECONDS = 60


# ── JWKS endpoint cache hint ─────────────────────────────────────────────────
# Sent on /oauth/jwks.json. Two values so testing on local/dev/int doesn't
# get bitten by browsers (Swagger UI in particular) holding onto a stale
# response for an hour after a misconfigured first hit.
#
#   PROD  — keys rotate rarely (quarterly per the runbook); 1h client-side
#           cache cuts traffic to the endpoint by ~3600x without meaningful
#           rotation latency.
#   DEV   — keys are often regenerated or the dir is misconfigured during
#           initial setup; ``no-cache`` makes every browser refresh re-fetch.
JWKS_CACHE_CONTROL_HEADER_PROD = "public, max-age=3600"
JWKS_CACHE_CONTROL_HEADER_NON_PROD = "no-cache"


def jwks_cache_control_header() -> str:
    """Pick the right Cache-Control value based on the running environment.
    Matches ``AppEnvironment.AllowedEnvs`` values from ``core/app_env.py``.
    """
    import os

    env = (os.getenv("ENV") or "").strip().lower()
    if env in ("production", "staging"):
        return JWKS_CACHE_CONTROL_HEADER_PROD
    return JWKS_CACHE_CONTROL_HEADER_NON_PROD


# Legacy alias — keep the old name resolving so any external references
# (logs, tests, docs) don't break. New code should call
# ``jwks_cache_control_header()``.
JWKS_CACHE_CONTROL_HEADER = JWKS_CACHE_CONTROL_HEADER_PROD


# ── Token-endpoint client-auth methods ───────────────────────────────────────
class OAuthClientAuthMethod:
    BASIC = "client_secret_basic"
    POST = "client_secret_post"
    NONE = "none"

    @classmethod
    def all(cls) -> tuple[str, ...]:
        return (cls.BASIC, cls.POST, cls.NONE)


# ── OAuth 2.1 grant types ────────────────────────────────────────────────────
class OAuthGrantType:
    AUTHORIZATION_CODE = "authorization_code"
    REFRESH_TOKEN = "refresh_token"

    @classmethod
    def supported(cls) -> list[str]:
        return [cls.AUTHORIZATION_CODE, cls.REFRESH_TOKEN]


# ── /authorize response types ────────────────────────────────────────────────
class OAuthResponseType:
    CODE = "code"

    @classmethod
    def supported(cls) -> list[str]:
        return [cls.CODE]


# ── Token type returned in /oauth/token success body ─────────────────────────
class OAuthTokenType:
    BEARER = "Bearer"


# ── JWT signing (RFC 7515 / 7519) ────────────────────────────────────────────
class OAuthSigningAlgorithm:
    RS256 = "RS256"


class OAuthJwtHeader:
    """JOSE header values stamped on every issued JWT."""

    TYP = "JWT"


# ── HTTP header names + cache hints ──────────────────────────────────────────
class HttpHeader:
    AUTHORIZATION = "Authorization"
    XFF = "X-Forwarded-For"
    USER_AGENT = "User-Agent"
    CACHE_CONTROL = "Cache-Control"
    PRAGMA = "Pragma"
    WWW_AUTHENTICATE = "WWW-Authenticate"


# RFC 6749 §5.1 — token-endpoint responses MUST NOT be cached anywhere.
NO_STORE_RESPONSE_HEADERS: dict = {
    HttpHeader.CACHE_CONTROL: "no-store",
    HttpHeader.PRAGMA: "no-cache",
}

BASIC_AUTH_PREFIX = "Basic "


# ── Scopes ───────────────────────────────────────────────────────────────────
# Granular scope names a token can carry, and a human-readable description
# shown on the consent screen. New scopes added here must be paired with an
# entry in maglo-service's ``OPERATION_SCOPE`` map (see scopes.py there).
class OAuthScope:
    LEADS_READ = "maglo:leads:read"
    FOLLOWUPS_READ = "maglo:followups:read"
    SERVICE_BOARDS_READ = "maglo:service_boards:read"
    CUSTOM_FIELDS_READ = "maglo:custom_fields:read"
    SECTIONS_READ = "maglo:sections:read"


SCOPE_CATALOG: dict[str, str] = {
    OAuthScope.LEADS_READ: "Read leads, lead requests, history, and activity",
    OAuthScope.FOLLOWUPS_READ: "Read follow-ups and comments",
    OAuthScope.SERVICE_BOARDS_READ: "Read service boards and management overview",
    OAuthScope.CUSTOM_FIELDS_READ: "Read custom field definitions and values",
    OAuthScope.SECTIONS_READ: "Read section catalogue and board mappings",
}


def all_scope_names() -> str:
    """Return the space-separated string of every supported scope."""
    return " ".join(SCOPE_CATALOG.keys())
