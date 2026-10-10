"""OAuth service layer — pure business logic, no FastAPI/HTTP concerns.

Encapsulated as a class ``OAuthService`` so it matches the project's existing
service distribution (see ``AuthService``, ``OrderService``, ``UserService``).
Dependencies (repository, user repository, logger) are injected at
construction via the DI container; pure helpers (PKCE math, hashing,
redirect-URI policy, scope filtering) are kept as ``@staticmethod`` on the
class so they're co-located with the rest of the OAuth logic instead of
floating at module level.

Responsibilities split:
  * Controllers (``controllers.py``) translate HTTP → service calls and
    service results → HTTP responses. They do no business logic.
  * Service (this module) owns the *what*: token issuance, replay detection,
    consent bookkeeping, redirect-URI validation, JWT signing.
  * Repository (``repositories.py``) owns the *where*: every DB read/write.
"""

import base64
import hashlib
import secrets
from typing import List, Optional, Tuple
from urllib.parse import urlparse

import jwt as pyjwt
from passlib.context import CryptContext

from src.components.common.datetime import DateTimeUtil
from src.components.oauth_server import config as oauth_cfg
from src.components.oauth_server.constants import (
    LOOPBACK_HOSTS,
    OAuthClientAuthMethod,
    OAuthJwtHeader,
    OAuthPKCE,
    OAuthSigningAlgorithm,
    OAuthSize,
)
from src.components.oauth_server.errors import (
    INVALID_CLIENT,
    OAuthError,
)
from src.components.oauth_server.keys import keyring
from src.components.oauth_server.models import OAuthClient, OAuthRefreshToken
from src.components.oauth_server.repositories import OAuthRepository
from src.loggers.console_service_logger import ConsoleServiceLogger


# passlib backend cache — module-level so it's initialised exactly once.
# Mirrors ``src/components/auth/util.py``'s pattern. Same algorithm and cost
# as the existing user-password hashing path.
_pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


class OAuthService:
    """Business logic for the OAuth 2.1 server.

    Stateful pieces (repositories, logger) are injected. Pure helpers live
    as ``@staticmethod`` so the class doubles as a namespace and there's no
    "module function vs class method" ambiguity for readers.
    """

    def __init__(
        self,
        oauth_repository: OAuthRepository,
        user_repository,
        console_service_logger: ConsoleServiceLogger,
    ):
        self.__repository = oauth_repository
        self.__user_repository = user_repository
        self.__oauth_service_logger = console_service_logger

    # ── Pure primitives (staticmethods, no DI needed) ────────────────────

    @staticmethod
    def now_ms() -> int:
        """Current Unix time in milliseconds — matches the project-wide
        timestamp convention (see ``DateTimeUtil.get_current_time``). Every
        ``*_at`` column on the OAuth tables stores this same integer.
        """
        return int(DateTimeUtil.get_current_time())

    @staticmethod
    def sha256_hex(value: str) -> str:
        return hashlib.sha256(value.encode("utf-8")).hexdigest()

    @staticmethod
    def generate_opaque(num_bytes: int = OAuthSize.ACCESS_TOKEN_BYTES) -> str:
        return secrets.token_urlsafe(num_bytes)

    @staticmethod
    def hash_secret(secret: str) -> str:
        return _pwd_context.hash(secret)

    @staticmethod
    def verify_secret(secret: str, stored_hash: str) -> bool:
        try:
            return _pwd_context.verify(secret, stored_hash)
        except (ValueError, TypeError):
            return False

    @staticmethod
    def mint_refresh_token() -> str:
        """Opaque refresh token — high-entropy random string."""
        return OAuthService.generate_opaque(OAuthSize.REFRESH_TOKEN_BYTES)

    @staticmethod
    def mint_auth_code() -> str:
        return OAuthService.generate_opaque(OAuthSize.AUTH_CODE_BYTES)

    @staticmethod
    def new_request_id() -> str:
        return OAuthService.generate_opaque(OAuthSize.REQUEST_ID_BYTES)

    # ── PKCE (RFC 7636) ──────────────────────────────────────────────────

    @staticmethod
    def verify_pkce_s256(verifier: str, challenge: str) -> bool:
        """RFC 7636 §4.6 — challenge = BASE64URL(SHA256(verifier))."""
        if not verifier or not challenge:
            return False
        if not (OAuthPKCE.MIN_VERIFIER_LEN <= len(verifier) <= OAuthPKCE.MAX_VERIFIER_LEN):
            return False
        if not OAuthPKCE.VERIFIER_REGEX.fullmatch(verifier):
            return False
        digest = hashlib.sha256(verifier.encode("ascii")).digest()
        computed = base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")
        return secrets.compare_digest(computed, challenge)

    # ── Redirect-URI policy ──────────────────────────────────────────────

    @staticmethod
    def validate_registered_redirect_uri(uri: str) -> Optional[str]:
        """Return None if the URI is acceptable for registration, else an
        error string. Run at DCR time — we then store and exact-match at
        /authorize.
        """
        try:
            parsed = urlparse(uri)
        except ValueError:
            return "redirect_uri is not a valid URL"
        if not parsed.scheme or not parsed.netloc:
            return "redirect_uri must be absolute"
        if parsed.fragment:
            return "redirect_uri must not contain a fragment"
        if parsed.scheme == "https":
            return None
        if parsed.scheme == "http":
            host = (parsed.hostname or "").lower()
            if host in LOOPBACK_HOSTS and oauth_cfg.OAUTH_ALLOW_LOCAL_REDIRECT:
                return None
            return "http redirect_uri is only allowed for loopback in dev"
        return "redirect_uri must use https (or loopback http in dev)"

    @staticmethod
    def is_registered_redirect_uri(client: OAuthClient, uri: str) -> bool:
        """Exact-match policy — the single biggest source of OAuth CVEs is
        loose redirect_uri matching. Do not relax without security review.
        """
        return uri in (client.redirect_uris or [])

    # ── Scope handling ───────────────────────────────────────────────────

    @staticmethod
    def parse_and_filter_scopes(
        requested: Optional[str],
        client_allowed: str,
    ) -> List[str]:
        """Return the intersection of (requested ∩ client.scope ∩ catalog).

        If ``requested`` is None or empty, default to every scope the client
        is registered for (filtered against the catalog).
        """
        catalog = set(oauth_cfg.SCOPE_CATALOG.keys())
        client_set = {s for s in (client_allowed or "").split() if s}
        if requested:
            req_set = {s for s in requested.split() if s}
        else:
            req_set = client_set
        return sorted(req_set & client_set & catalog)

    # ── JWT minting ──────────────────────────────────────────────────────

    @staticmethod
    def mint_access_token(
        *,
        user_id: int,
        client_id: str,
        scopes: List[str],
        partner_id: Optional[int],
        role: Optional[str],
        role_hierarchy_level: Optional[int],
        extra_claims: Optional[dict] = None,
    ) -> Tuple[str, int]:
        """Issue an RS256 JWT. Returns (token, ttl_seconds).

        Raises ``OAuthError(server_error)`` if the issuer URL isn't
        configured (deployment misconfiguration) or if the key-ring has
        no private key to sign with (provisioning gap).
        """
        if not oauth_cfg.OAUTH_ISSUER_URL:
            raise OAuthError(
                error="server_error",
                description="OAUTH_ISSUER_URL not configured",
                status_code=500,
            )
        # JWT `iat` / `exp` are Unix SECONDS (RFC 7519 §4.1.4-§4.1.6); our
        # DB columns store milliseconds — keep the two units separated.
        now_s = OAuthService.now_ms() // 1000
        ttl = oauth_cfg.OAUTH_ACCESS_TOKEN_TTL_SECONDS
        claims = {
            "iss": oauth_cfg.OAUTH_ISSUER_URL,
            "sub": f"maglo:{user_id}",
            "aud": oauth_cfg.OAUTH_RESOURCE_URL,
            "iat": now_s,
            "exp": now_s + ttl,
            "jti": OAuthService.generate_opaque(OAuthSize.ACCESS_TOKEN_BYTES // 2),
            "scope": " ".join(scopes),
            "client_id": client_id,
            "maglo_user_id": user_id,
        }
        if partner_id is not None:
            claims["partner_id"] = partner_id
        if role is not None:
            claims["role"] = role
        if role_hierarchy_level is not None:
            claims["role_hierarchy_level"] = role_hierarchy_level
        if extra_claims:
            claims.update(extra_claims)

        try:
            token = pyjwt.encode(
                claims,
                keyring.primary_private_pem(),
                algorithm=OAuthSigningAlgorithm.RS256,
                headers={
                    "kid": keyring.primary_kid,
                    "typ": OAuthJwtHeader.TYP,
                },
            )
        except RuntimeError as ex:
            # Raised by KeyRing.primary_kid when no signing key is loaded.
            raise OAuthError(
                error="server_error",
                description="OAuth signing key not provisioned",
                status_code=500,
            ) from ex
        return token, ttl

    # ── Client authentication ────────────────────────────────────────────

    async def authenticate_client(
        self,
        session,
        *,
        client_id: str,
        client_secret: Optional[str],
        require_secret: bool = True,
    ) -> OAuthClient:
        """Look up the client and verify the secret (if applicable).

        For public clients (``token_endpoint_auth_method == "none"``) the
        ``client_secret`` is ignored — PKCE on the auth path is what binds
        the request, so this is safe.

        Raises ``OAuthError(invalid_client)`` on unknown / disabled client
        or secret mismatch; any other failure (e.g. DB) propagates as the
        original exception for the controller to translate to 500.
        """
        try:
            client = await self.__repository.get_active_client(session, client_id)
            if not client:
                self.__oauth_service_logger.error(
                    "Unknown OAuth client_id={}".format(client_id)
                )
                raise OAuthError(
                    INVALID_CLIENT, "unknown client_id", status_code=401
                )

            if client.token_endpoint_auth_method == OAuthClientAuthMethod.NONE:
                return client

            if not require_secret:
                return client

            if not client_secret:
                self.__oauth_service_logger.error(
                    "client_secret missing for client_id={}".format(client_id)
                )
                raise OAuthError(
                    INVALID_CLIENT, "client_secret required", status_code=401
                )
            if not client.client_secret_hash or not OAuthService.verify_secret(
                client_secret, client.client_secret_hash
            ):
                self.__oauth_service_logger.error(
                    "client_secret mismatch for client_id={}".format(client_id)
                )
                raise OAuthError(
                    INVALID_CLIENT, "client_secret mismatch", status_code=401
                )

            return client
        except OAuthError:
            raise
        except Exception as ex:
            self.__oauth_service_logger.error(
                "Error authenticating client client_id={}: {}".format(
                    client_id, str(ex)
                )
            )
            raise ex

    # ── Refresh-token-theft chain revocation ─────────────────────────────

    async def detect_and_handle_replay(
        self,
        session,
        *,
        token_hash: str,
    ) -> Optional[dict]:
        """If the presented refresh token has ALREADY been consumed, revoke
        the entire chain it came from and return a diagnostic dict the
        caller can hand to the application logger. Returns ``None`` when
        there is no replay (proceed with normal refresh).

        Any unexpected DB error propagates so the controller can return
        500 — better to fail closed than silently grant a refresh during
        an outage.
        """
        try:
            row: Optional[OAuthRefreshToken] = (
                await self.__repository.peek_refresh_token(session, token_hash)
            )
            if not row or row.consumed_at is None:
                return None

            root = row
            seen = set()
            while root.parent_token_hash and root.parent_token_hash not in seen:
                seen.add(root.parent_token_hash)
                parent = await self.__repository.peek_refresh_token(
                    session, root.parent_token_hash
                )
                if not parent:
                    break
                root = parent
            revoked = await self.__repository.revoke_chain(
                session, root.token_hash
            )
            diagnostic = {
                "token_hash_prefix": token_hash[:12],
                "root_hash_prefix": root.token_hash[:12],
                "client_id": row.client_id,
                "user_id": row.user_id,
                "revoked": revoked,
            }
            self.__oauth_service_logger.error(
                "[oauth.theft] refresh-token replay token={} root={} "
                "client_id={} user_id={} revoked={}".format(
                    diagnostic["token_hash_prefix"],
                    diagnostic["root_hash_prefix"],
                    diagnostic["client_id"],
                    diagnostic["user_id"],
                    diagnostic["revoked"],
                )
            )
            return diagnostic
        except Exception as ex:
            self.__oauth_service_logger.error(
                "Error during refresh-token replay detection: {}".format(str(ex))
            )
            raise ex

    # ── User lookup pass-through (used by controllers during token issue)

    async def get_user_details(self, user_id: int):
        """Thin wrapper around UserRepository so controllers don't reach
        into a second repository directly — keeps the service the single
        point of contact for any auth-flow user attribute lookup.
        """
        try:
            return await self.__user_repository.get_user_details(user_id)
        except Exception as ex:
            self.__oauth_service_logger.error(
                "Error fetching user details user_id={}: {}".format(
                    user_id, str(ex)
                )
            )
            raise ex
