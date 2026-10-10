"""Repository layer — every OAuth DB read/write lives here.

Mirrors the project's repository convention (see ``AuthRepository``,
``OrderRepository``): the session factory + a ``ConsoleServiceLogger``
are injected at construction; every method wraps its work in try/except,
logs an info line on the happy path and an error line before re-raising.

The OAuth flow needs multi-statement atomicity in several places
(``consent_decision`` upserts consent + inserts an auth code + deletes
the pending stash in one transaction). So unlike most repos in this
codebase which open a fresh session per method, callers here pass in an
externally-owned ``AsyncSession`` and commit at the boundary they care
about. The try/except + logging shape is identical either way; only
the session ownership differs.
"""

from typing import List, Optional

from sqlalchemy import and_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.components.common.datetime import DateTimeUtil
from src.components.oauth_server.models import (
    OAuthAuthorizationCode,
    OAuthAuthorizeRequest,
    OAuthClient,
    OAuthConsent,
    OAuthRefreshToken,
)
from src.loggers.console_service_logger import ConsoleServiceLogger


class OAuthRepository:
    """SQL access for the OAuth 2.1 server's five tables."""

    def __init__(
        self,
        session_factory,
        oauth_service_logger: ConsoleServiceLogger = ConsoleServiceLogger(),
    ) -> None:
        # session_factory is typically ``DatabaseSessionManager.session`` —
        # an async context manager that yields an ``AsyncSession``.
        self.session_factory = session_factory
        self.__oauth_service_logger: ConsoleServiceLogger = oauth_service_logger

    @staticmethod
    def _now_ms() -> int:
        """Unix time in milliseconds — matches every other ``*_at`` column
        in this database (see ``DateTimeUtil.get_current_time``).
        """
        return int(DateTimeUtil.get_current_time())

    # ── Clients ──────────────────────────────────────────────────────────────

    async def insert_client(
        self,
        session: AsyncSession,
        *,
        client_id: str,
        client_secret_hash: Optional[str],
        client_name: str,
        redirect_uris: List[str],
        grant_types: List[str],
        scope: str,
        token_endpoint_auth_method: str,
        registered_by_ip: Optional[str],
        registered_user_agent: Optional[str],
    ) -> OAuthClient:
        try:
            row = OAuthClient(
                client_id=client_id,
                client_secret_hash=client_secret_hash,
                client_name=client_name,
                redirect_uris=redirect_uris,
                grant_types=grant_types,
                scope=scope,
                token_endpoint_auth_method=token_endpoint_auth_method,
                registered_by_ip=registered_by_ip,
                registered_user_agent=registered_user_agent,
                registered_at=self._now_ms(),
            )
            session.add(row)
            await session.flush()
            self.__oauth_service_logger.info(
                "OAuth client inserted: client_id={} name={!r}".format(
                    client_id, client_name
                )
            )
            return row
        except Exception as ex:
            self.__oauth_service_logger.error(
                "Error inserting OAuth client client_id={}: {}".format(
                    client_id, str(ex)
                )
            )
            raise ex

    async def get_active_client(
        self, session: AsyncSession, client_id: str
    ) -> Optional[OAuthClient]:
        try:
            result = await session.execute(
                select(OAuthClient).where(
                    and_(
                        OAuthClient.client_id == client_id,
                        OAuthClient.disabled_at.is_(None),
                    )
                )
            )
            return result.scalar_one_or_none()
        except Exception as ex:
            self.__oauth_service_logger.error(
                "Error fetching active OAuth client client_id={}: {}".format(
                    client_id, str(ex)
                )
            )
            raise ex

    async def disable_client(
        self, session: AsyncSession, client_id: str
    ) -> None:
        try:
            await session.execute(
                update(OAuthClient)
                .where(OAuthClient.client_id == client_id)
                .values(disabled_at=self._now_ms())
            )
            self.__oauth_service_logger.info(
                "OAuth client disabled: client_id={}".format(client_id)
            )
        except Exception as ex:
            self.__oauth_service_logger.error(
                "Error disabling OAuth client client_id={}: {}".format(
                    client_id, str(ex)
                )
            )
            raise ex

    # ── Authorization codes ──────────────────────────────────────────────────

    async def insert_auth_code(
        self,
        session: AsyncSession,
        *,
        code_hash: str,
        client_id: str,
        user_id: int,
        redirect_uri: str,
        scopes: List[str],
        code_challenge: str,
        code_challenge_method: str,
        expires_at: int,
    ) -> None:
        try:
            session.add(
                OAuthAuthorizationCode(
                    code_hash=code_hash,
                    client_id=client_id,
                    user_id=user_id,
                    redirect_uri=redirect_uri,
                    scopes=scopes,
                    code_challenge=code_challenge,
                    code_challenge_method=code_challenge_method,
                    expires_at=expires_at,
                )
            )
            await session.flush()
            self.__oauth_service_logger.info(
                "OAuth auth code stored for client_id={} user_id={}".format(
                    client_id, user_id
                )
            )
        except Exception as ex:
            self.__oauth_service_logger.error(
                "Error inserting auth code client_id={} user_id={}: {}".format(
                    client_id, user_id, str(ex)
                )
            )
            raise ex

    async def consume_auth_code(
        self, session: AsyncSession, code_hash: str
    ) -> Optional[OAuthAuthorizationCode]:
        """Atomically mark the auth code as consumed; return its row if and
        only if this call was the first to claim it (i.e. not previously
        consumed and not expired). Returns None on miss — auth-code reuse
        and expiry are normal flow control, not errors.
        """
        try:
            now = self._now_ms()
            result = await session.execute(
                update(OAuthAuthorizationCode)
                .where(
                    and_(
                        OAuthAuthorizationCode.code_hash == code_hash,
                        OAuthAuthorizationCode.consumed_at.is_(None),
                        OAuthAuthorizationCode.expires_at > now,
                    )
                )
                .values(consumed_at=now)
                .returning(OAuthAuthorizationCode)
            )
            row = result.scalar_one_or_none()
            if row is None:
                self.__oauth_service_logger.info(
                    "Auth-code consume miss (expired / already used)"
                )
            return row
        except Exception as ex:
            self.__oauth_service_logger.error(
                "Error consuming auth code: {}".format(str(ex))
            )
            raise ex

    async def peek_auth_code(
        self, session: AsyncSession, code_hash: str
    ) -> Optional[OAuthAuthorizationCode]:
        try:
            result = await session.execute(
                select(OAuthAuthorizationCode).where(
                    OAuthAuthorizationCode.code_hash == code_hash
                )
            )
            return result.scalar_one_or_none()
        except Exception as ex:
            self.__oauth_service_logger.error(
                "Error peeking auth code: {}".format(str(ex))
            )
            raise ex

    # ── Refresh tokens ───────────────────────────────────────────────────────

    async def insert_refresh_token(
        self,
        session: AsyncSession,
        *,
        token_hash: str,
        client_id: str,
        user_id: int,
        scopes: List[str],
        expires_at: int,
        parent_token_hash: Optional[str],
    ) -> None:
        try:
            session.add(
                OAuthRefreshToken(
                    token_hash=token_hash,
                    client_id=client_id,
                    user_id=user_id,
                    scopes=scopes,
                    issued_at=self._now_ms(),
                    expires_at=expires_at,
                    parent_token_hash=parent_token_hash,
                )
            )
            await session.flush()
            self.__oauth_service_logger.info(
                "Refresh token issued for client_id={} user_id={}{}".format(
                    client_id,
                    user_id,
                    " (rotation)" if parent_token_hash else "",
                )
            )
        except Exception as ex:
            self.__oauth_service_logger.error(
                "Error inserting refresh token client_id={} user_id={}: {}".format(
                    client_id, user_id, str(ex)
                )
            )
            raise ex

    async def consume_refresh_token(
        self, session: AsyncSession, token_hash: str
    ) -> Optional[OAuthRefreshToken]:
        """Atomically claim a refresh token. Returns the row if the token is
        valid (not previously consumed, not revoked, not expired). None on
        miss — refresh-token reuse / revocation / expiry are normal flow
        control, the theft detector in the service layer escalates them.
        """
        try:
            now = self._now_ms()
            result = await session.execute(
                update(OAuthRefreshToken)
                .where(
                    and_(
                        OAuthRefreshToken.token_hash == token_hash,
                        OAuthRefreshToken.consumed_at.is_(None),
                        OAuthRefreshToken.revoked_at.is_(None),
                        OAuthRefreshToken.expires_at > now,
                    )
                )
                .values(consumed_at=now)
                .returning(OAuthRefreshToken)
            )
            return result.scalar_one_or_none()
        except Exception as ex:
            self.__oauth_service_logger.error(
                "Error consuming refresh token: {}".format(str(ex))
            )
            raise ex

    async def peek_refresh_token(
        self, session: AsyncSession, token_hash: str
    ) -> Optional[OAuthRefreshToken]:
        try:
            result = await session.execute(
                select(OAuthRefreshToken).where(
                    OAuthRefreshToken.token_hash == token_hash
                )
            )
            return result.scalar_one_or_none()
        except Exception as ex:
            self.__oauth_service_logger.error(
                "Error peeking refresh token: {}".format(str(ex))
            )
            raise ex

    async def revoke_refresh_token(
        self,
        session: AsyncSession,
        token_hash: str,
        client_id: Optional[str] = None,
    ) -> None:
        try:
            clauses = [OAuthRefreshToken.token_hash == token_hash]
            if client_id is not None:
                clauses.append(OAuthRefreshToken.client_id == client_id)
            await session.execute(
                update(OAuthRefreshToken)
                .where(and_(*clauses))
                .values(revoked_at=self._now_ms())
            )
            self.__oauth_service_logger.info(
                "Refresh token revoked{}".format(
                    " for client_id={}".format(client_id) if client_id else ""
                )
            )
        except Exception as ex:
            self.__oauth_service_logger.error(
                "Error revoking refresh token: {}".format(str(ex))
            )
            raise ex

    async def revoke_chain(
        self, session: AsyncSession, root_token_hash: str
    ) -> int:
        """Revoke a refresh token and every descendant in its rotation chain.

        Walks ``parent_token_hash`` links iteratively to avoid runaway
        recursion on a malformed chain. Returns the number of rows revoked.
        """
        try:
            to_revoke = [root_token_hash]
            seen: set = set()
            revoked = 0
            while to_revoke:
                current = to_revoke.pop()
                if current in seen:
                    continue
                seen.add(current)
                await self.revoke_refresh_token(session, current)
                revoked += 1
                children = await session.execute(
                    select(OAuthRefreshToken.token_hash).where(
                        OAuthRefreshToken.parent_token_hash == current
                    )
                )
                to_revoke.extend(c for (c,) in children.all())
            self.__oauth_service_logger.info(
                "Refresh-token chain revoked: root={} count={}".format(
                    root_token_hash[:12], revoked
                )
            )
            return revoked
        except Exception as ex:
            self.__oauth_service_logger.error(
                "Error revoking refresh-token chain root={}: {}".format(
                    root_token_hash[:12], str(ex)
                )
            )
            raise ex

    async def revoke_all_user_tokens(
        self,
        session: AsyncSession,
        user_id: int,
        client_id: Optional[str] = None,
    ) -> None:
        try:
            clauses = [
                OAuthRefreshToken.user_id == user_id,
                OAuthRefreshToken.revoked_at.is_(None),
            ]
            if client_id is not None:
                clauses.append(OAuthRefreshToken.client_id == client_id)
            await session.execute(
                update(OAuthRefreshToken)
                .where(and_(*clauses))
                .values(revoked_at=self._now_ms())
            )
            self.__oauth_service_logger.info(
                "All refresh tokens revoked for user_id={}{}".format(
                    user_id,
                    " client_id={}".format(client_id) if client_id else "",
                )
            )
        except Exception as ex:
            self.__oauth_service_logger.error(
                "Error revoking all refresh tokens user_id={}: {}".format(
                    user_id, str(ex)
                )
            )
            raise ex

    # ── Consents ─────────────────────────────────────────────────────────────

    async def get_consent(
        self, session: AsyncSession, user_id: int, client_id: str
    ) -> Optional[OAuthConsent]:
        try:
            result = await session.execute(
                select(OAuthConsent).where(
                    and_(
                        OAuthConsent.user_id == user_id,
                        OAuthConsent.client_id == client_id,
                        OAuthConsent.revoked_at.is_(None),
                    )
                )
            )
            return result.scalar_one_or_none()
        except Exception as ex:
            self.__oauth_service_logger.error(
                "Error fetching consent user_id={} client_id={}: {}".format(
                    user_id, client_id, str(ex)
                )
            )
            raise ex

    async def upsert_consent(
        self,
        session: AsyncSession,
        user_id: int,
        client_id: str,
        scopes: List[str],
    ) -> None:
        try:
            existing = await self.get_consent(session, user_id, client_id)
            if existing:
                merged = sorted(set(list(existing.scopes or []) + list(scopes)))
                await session.execute(
                    update(OAuthConsent)
                    .where(OAuthConsent.id == existing.id)
                    .values(
                        scopes=merged,
                        granted_at=self._now_ms(),
                        revoked_at=None,
                    )
                )
                self.__oauth_service_logger.info(
                    "Consent updated user_id={} client_id={} scopes={}".format(
                        user_id, client_id, merged
                    )
                )
                return
            session.add(
                OAuthConsent(
                    user_id=user_id,
                    client_id=client_id,
                    scopes=list(scopes),
                    granted_at=self._now_ms(),
                )
            )
            await session.flush()
            self.__oauth_service_logger.info(
                "Consent granted user_id={} client_id={} scopes={}".format(
                    user_id, client_id, scopes
                )
            )
        except Exception as ex:
            self.__oauth_service_logger.error(
                "Error upserting consent user_id={} client_id={}: {}".format(
                    user_id, client_id, str(ex)
                )
            )
            raise ex

    async def revoke_consent(
        self, session: AsyncSession, user_id: int, client_id: str
    ) -> None:
        try:
            await session.execute(
                update(OAuthConsent)
                .where(
                    and_(
                        OAuthConsent.user_id == user_id,
                        OAuthConsent.client_id == client_id,
                    )
                )
                .values(revoked_at=self._now_ms())
            )
            self.__oauth_service_logger.info(
                "Consent revoked user_id={} client_id={}".format(
                    user_id, client_id
                )
            )
        except Exception as ex:
            self.__oauth_service_logger.error(
                "Error revoking consent user_id={} client_id={}: {}".format(
                    user_id, client_id, str(ex)
                )
            )
            raise ex

    # ── Authorize-request stash ──────────────────────────────────────────────

    async def insert_authorize_request(
        self,
        session: AsyncSession,
        *,
        request_id: str,
        payload: dict,
        user_id: Optional[int],
        expires_at: int,
    ) -> None:
        try:
            session.add(
                OAuthAuthorizeRequest(
                    request_id=request_id,
                    payload=payload,
                    user_id=user_id,
                    expires_at=expires_at,
                )
            )
            await session.flush()
            self.__oauth_service_logger.info(
                "Authorize request stashed: request_id={} user_id={}".format(
                    request_id, user_id
                )
            )
        except Exception as ex:
            self.__oauth_service_logger.error(
                "Error stashing authorize request request_id={}: {}".format(
                    request_id, str(ex)
                )
            )
            raise ex

    async def get_authorize_request(
        self, session: AsyncSession, request_id: str
    ) -> Optional[OAuthAuthorizeRequest]:
        try:
            result = await session.execute(
                select(OAuthAuthorizeRequest).where(
                    OAuthAuthorizeRequest.request_id == request_id
                )
            )
            return result.scalar_one_or_none()
        except Exception as ex:
            self.__oauth_service_logger.error(
                "Error fetching authorize request request_id={}: {}".format(
                    request_id, str(ex)
                )
            )
            raise ex

    async def update_authorize_request_user(
        self, session: AsyncSession, request_id: str, user_id: int
    ) -> None:
        try:
            await session.execute(
                update(OAuthAuthorizeRequest)
                .where(OAuthAuthorizeRequest.request_id == request_id)
                .values(user_id=user_id)
            )
            self.__oauth_service_logger.info(
                "Authorize request bound to user: request_id={} user_id={}".format(
                    request_id, user_id
                )
            )
        except Exception as ex:
            self.__oauth_service_logger.error(
                "Error binding authorize request to user request_id={}: {}".format(
                    request_id, str(ex)
                )
            )
            raise ex

    async def mark_authorize_request_consented(
        self, session: AsyncSession, request_id: str
    ) -> None:
        try:
            await session.execute(
                update(OAuthAuthorizeRequest)
                .where(OAuthAuthorizeRequest.request_id == request_id)
                .values(consent_recorded=True)
            )
        except Exception as ex:
            self.__oauth_service_logger.error(
                "Error marking authorize request consented request_id={}: {}".format(
                    request_id, str(ex)
                )
            )
            raise ex

    async def delete_authorize_request(
        self, session: AsyncSession, request_id: str
    ) -> None:
        try:
            row = await self.get_authorize_request(session, request_id)
            if row:
                await session.delete(row)
        except Exception as ex:
            self.__oauth_service_logger.error(
                "Error deleting authorize request request_id={}: {}".format(
                    request_id, str(ex)
                )
            )
            raise ex
