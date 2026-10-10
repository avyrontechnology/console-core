"""SQLAlchemy models for the OAuth 2.1 server.

Naming convention: every table is prefixed ``oauth_`` so they're trivially
listable / droppable without touching unrelated console tables.

We do NOT inherit from ``MetaData`` (the common base in this repo) because the
plan's schema deliberately uses opaque-string primary keys (``client_id``,
``code_hash``, ``token_hash``) rather than autoincrement ints, and a different
audit shape. Inheriting Base directly keeps the schema spec-pure.

Timestamp convention: every ``*_at`` column is ``BigInteger`` storing
milliseconds since the Unix epoch, matching the project-wide convention
(see ``components/database/base_model.py``'s ``MetaData`` base + the helper
``components/common/datetime.py``). Service-layer helpers cast to/from
``int`` only; we deliberately don't store native ``DateTime`` so the OAuth
tables read consistently with everything else in the console DB.
"""

from sqlalchemy import (
    BigInteger,
    Boolean,
    Column,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB

from src.core.db import Base


class OAuthClient(Base):
    """A client registered via RFC 7591 Dynamic Client Registration.

    One row per (Claude.ai, ChatGPT, any partner connector). ``client_secret``
    is only ever returned once at /oauth/register; we store only a bcrypt hash.
    """

    __tablename__ = "oauth_clients"

    client_id = Column(String(64), primary_key=True)
    client_secret_hash = Column(String(128), nullable=True)
    client_name = Column(String(255), nullable=False)
    redirect_uris = Column(JSONB, nullable=False)  # list[str], exact-match
    grant_types = Column(JSONB, nullable=False)  # ["authorization_code","refresh_token"]
    scope = Column(String(2048), nullable=False)  # space-separated allowed scopes
    token_endpoint_auth_method = Column(String(64), nullable=False)
    registered_at = Column(BigInteger, nullable=False)
    registered_by_ip = Column(String(64), nullable=True)
    registered_user_agent = Column(String(512), nullable=True)
    disabled_at = Column(BigInteger, nullable=True)  # admin kill switch


class OAuthAuthorizationCode(Base):
    """Short-lived (~10 min) single-use auth code issued at /oauth/authorize.

    Storage strategy: we store the SHA-256 hash of the code, not the code
    itself, so a leaked DB snapshot doesn't grant token-exchange power.
    Single-use enforced via atomic UPDATE on ``consumed_at``.
    """

    __tablename__ = "oauth_authorization_codes"

    code_hash = Column(String(128), primary_key=True)
    client_id = Column(String(64), nullable=False, index=True)
    user_id = Column(Integer, nullable=False, index=True)
    redirect_uri = Column(String(1024), nullable=False)
    scopes = Column(JSONB, nullable=False)  # list[str]
    code_challenge = Column(String(128), nullable=False)
    code_challenge_method = Column(String(16), nullable=False)
    expires_at = Column(BigInteger, nullable=False, index=True)
    consumed_at = Column(BigInteger, nullable=True)


class OAuthRefreshToken(Base):
    """Long-lived (~30 d) single-use refresh token (rotation-on-use).

    ``parent_token_hash`` links the rotation chain so we can revoke every
    descendant on suspected reuse (token-theft detection).
    """

    __tablename__ = "oauth_refresh_tokens"

    token_hash = Column(String(128), primary_key=True)
    client_id = Column(String(64), nullable=False, index=True)
    user_id = Column(Integer, nullable=False, index=True)
    scopes = Column(JSONB, nullable=False)
    issued_at = Column(BigInteger, nullable=False)
    expires_at = Column(BigInteger, nullable=False, index=True)
    revoked_at = Column(BigInteger, nullable=True)
    consumed_at = Column(BigInteger, nullable=True)
    parent_token_hash = Column(String(128), nullable=True, index=True)


class OAuthConsent(Base):
    """Per (user × client) consent grant.

    Storing scopes here means re-asking only when the client requests scopes
    NOT yet covered by the existing consent. Hard-deleting a row revokes;
    soft-revocation via ``revoked_at`` for audit.
    """

    __tablename__ = "oauth_consents"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    user_id = Column(Integer, nullable=False, index=True)
    client_id = Column(String(64), nullable=False, index=True)
    scopes = Column(JSONB, nullable=False)
    granted_at = Column(BigInteger, nullable=False)
    revoked_at = Column(BigInteger, nullable=True)

    __table_args__ = (
        UniqueConstraint("user_id", "client_id", name="uq_oauth_consent_user_client"),
    )


class OAuthAuthorizeRequest(Base):
    """Short-lived stash for an in-progress /authorize that bounced through
    login or consent. Holds the full original request so we can resume after
    login without re-validating client_id / redirect_uri / PKCE.
    """

    __tablename__ = "oauth_authorize_requests"

    request_id = Column(String(64), primary_key=True)
    payload = Column(JSONB, nullable=False)  # full original request params
    user_id = Column(Integer, nullable=True, index=True)  # set after login
    consent_recorded = Column(Boolean, nullable=False, default=False)
    expires_at = Column(BigInteger, nullable=False, index=True)
