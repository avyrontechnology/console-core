"""OAuth server runtime configuration — env-driven values only.

Pure literal constants (error codes, byte lengths, PKCE limits, scope catalog,
rate-limit window) live in [constants.py](./constants.py). This module only
holds values that change between environments and are read from env vars
at import time.
"""

import os

# Re-export so callers can keep importing scopes from one place.
from src.components.oauth_server.constants import SCOPE_CATALOG, all_scope_names  # noqa: F401


def _bool(name: str, default: str = "false") -> bool:
    return str(os.getenv(name, default)).strip().lower() in ("1", "true", "yes", "on")


def _int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None or raw == "":
        return default
    try:
        return int(raw)
    except ValueError:
        return default


# ── Feature gate ──────────────────────────────────────────────────────────────
# When false, the OAuth router is NOT mounted at all. Used by ops to kill the
# whole subsystem from outside the code path.
OAUTH_ENABLED: bool = _bool("OAUTH_ENABLED", "false")

# When false, /oauth/register returns 503. Lets ops stop new client registrations
# without disabling existing token issuance / validation.
OAUTH_REGISTRATION_ENABLED: bool = _bool("OAUTH_REGISTRATION_ENABLED", "true")


# ── Identity ─────────────────────────────────────────────────────────────────
# The public origin under which this OAuth server lives. Used as the `iss`
# claim in every token we mint and as the base for every URL in our discovery
# documents. RFC 8414 is strict about exact-match — no trailing slash.
OAUTH_ISSUER_URL: str = os.getenv("OAUTH_ISSUER_URL", "").rstrip("/")

# The Resource URL that protected MCP requests will land on. Embedded in the
# `aud` claim of issued access tokens and surfaced via /.well-known/oauth-
# protected-resource. Defaults to maglo-service /mcp under the same host as
# the issuer when not overridden.
OAUTH_RESOURCE_URL: str = (
    os.getenv("OAUTH_RESOURCE_URL", "").rstrip("/")
    or (f"{OAUTH_ISSUER_URL}/maglo-service/v1/mcp" if OAUTH_ISSUER_URL else "")
)


# ── Signing keys ─────────────────────────────────────────────────────────────
# Directory containing one or more `*.pem` RSA private keys. Filename (sans
# extension) is used as the JWT `kid`. The lexicographically-newest file is
# used to sign new tokens; all keys in the directory are published in JWKS
# so previously-issued tokens stay verifiable during rotation.
OAUTH_SIGNING_KEY_PATH: str = os.getenv(
    "OAUTH_SIGNING_KEY_PATH", "/secrets/oauth-keys"
)


# ── Token TTLs ───────────────────────────────────────────────────────────────
# Access tokens are stateless RS256 JWTs; they cannot be revoked individually
# without a deny-list. Keep TTL short so revocation-via-refresh propagates fast.
OAUTH_ACCESS_TOKEN_TTL_SECONDS: int = _int("OAUTH_ACCESS_TOKEN_TTL_SECONDS", 3600)
OAUTH_REFRESH_TOKEN_TTL_SECONDS: int = _int(
    "OAUTH_REFRESH_TOKEN_TTL_SECONDS", 30 * 24 * 3600
)
OAUTH_AUTH_CODE_TTL_SECONDS: int = _int("OAUTH_AUTH_CODE_TTL_SECONDS", 600)
# Stash TTL for an in-progress /authorize that bounced through login/consent.
OAUTH_AUTHORIZE_REQUEST_TTL_SECONDS: int = _int(
    "OAUTH_AUTHORIZE_REQUEST_TTL_SECONDS", 600
)


# ── DCR abuse guards ─────────────────────────────────────────────────────────
OAUTH_REGISTRATION_RATE_PER_IP_PER_HOUR: int = _int(
    "OAUTH_REGISTRATION_RATE_PER_IP_PER_HOUR", 30
)
OAUTH_REGISTRATION_RATE_GLOBAL_PER_HOUR: int = _int(
    "OAUTH_REGISTRATION_RATE_GLOBAL_PER_HOUR", 1000
)


# ── Redirect URI policy ──────────────────────────────────────────────────────
# Localhost http://127.0.0.1:* is normally a security violation. Gate it
# behind an env so dev / int can flip it on without making prod permissive.
OAUTH_ALLOW_LOCAL_REDIRECT: bool = _bool("OAUTH_ALLOW_LOCAL_REDIRECT", "false")


# ── Scopes ────────────────────────────────────────────────────────────────────
# `SCOPE_CATALOG` and `all_scope_names` are re-exported from constants.py
# (see imports above) so callers keep importing from `oauth_server.config`.
