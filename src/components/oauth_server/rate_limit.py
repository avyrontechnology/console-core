"""DCR rate-limiter.

RFC 7591 DCR is unauthenticated by spec, so the only thing standing between
us and a botnet that registers 50k clients is rate limiting + a kill switch.

This limiter uses the project's central :class:`CacheHelper` for atomic
INCR + EXPIRE on Redis — the same Redis pool every other component shares.
That gives us:

  * **Multi-instance correctness.** Console-service runs >1 replica; an
    in-process counter would let an attacker spread requests across pods
    and bypass the limit.
  * **One canonical primitive.** ``CacheHelper.incr_with_ttl`` is also what
    the future MCP rate-limiter (plan Phase 10), per-user quotas, and dedup
    windows will use — no per-component reimplementation.
  * **Observability.** Errors funnel through ``ConsoleServiceLogger`` and
    surface in the same log stream as the rest of the OAuth flow.

Fail-closed policy: if Redis is unreachable, every registration is denied
(returns ``False``). DCR is unauthenticated, so failing open during a Redis
outage would expose us to abuse precisely when we're least able to detect
it. Existing tokens / refreshes are unaffected — only NEW client
registration is gated by this limiter.
"""

import time
from typing import Optional

from src.components.cache.helper import CacheHelper
from src.components.oauth_server import config as oauth_cfg
from src.components.oauth_server.constants import OAuthRateLimit
from src.core.redis import RedisCache
from src.loggers.console_service_logger import ConsoleServiceLogger


class DCRRateLimiter:
    """Two-tier rate limiter: per-IP + global, both hourly.

    Both checks must pass for ``allow()`` to return True. Bucket boundaries
    are wall-clock aligned (``now // 3600``) so an attacker can't slide a
    request stream across a rolling window — a known limitation of the
    fixed-window scheme is the 2× burst at bucket boundaries, which we
    accept because DCR limits are coarse (tens per hour, not per second).
    """

    def __init__(
        self,
        cache_helper: CacheHelper,
        console_service_logger: Optional[ConsoleServiceLogger] = None,
    ):
        self._cache = cache_helper
        self._logger = console_service_logger

    async def allow(self, *, ip: str) -> bool:
        if not oauth_cfg.OAUTH_REGISTRATION_ENABLED:
            return False

        per_ip_limit = oauth_cfg.OAUTH_REGISTRATION_RATE_PER_IP_PER_HOUR
        global_limit = oauth_cfg.OAUTH_REGISTRATION_RATE_GLOBAL_PER_HOUR
        if per_ip_limit <= 0 and global_limit <= 0:
            # Both disabled — treat as "unlimited" (operator opt-out).
            return True

        bucket = int(time.time()) // OAuthRateLimit.WINDOW_SECONDS
        ip_key = f"{OAuthRateLimit.KEY_PREFIX}ip:{ip}:{bucket}"
        global_key = f"{OAuthRateLimit.KEY_PREFIX}global:{bucket}"
        ttl = OAuthRateLimit.WINDOW_SECONDS + OAuthRateLimit.TTL_PADDING_SECONDS

        # Per-IP check first — cheaper to reject early before the global
        # counter is touched (and avoids inflating it on a 429 path).
        if per_ip_limit > 0:
            ip_count = await self._cache.incr_with_ttl(
                key=ip_key,
                ttl_seconds=ttl,
                prefix=RedisCache.KeysPrefix.CONSOLE,
            )
            if ip_count is None:
                # Redis unreachable — fail closed.
                if self._logger is not None:
                    self._logger.error(
                        "[oauth.dcr.rl] redis unavailable; denying registration ip=%s",
                        ip,
                    )
                return False
            if ip_count > per_ip_limit:
                return False

        if global_limit > 0:
            global_count = await self._cache.incr_with_ttl(
                key=global_key,
                ttl_seconds=ttl,
                prefix=RedisCache.KeysPrefix.CONSOLE,
            )
            if global_count is None:
                if self._logger is not None:
                    self._logger.error(
                        "[oauth.dcr.rl] redis unavailable on global check; "
                        "denying registration ip=%s",
                        ip,
                    )
                return False
            if global_count > global_limit:
                return False

        return True
