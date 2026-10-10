import json
from typing import Any, Dict, List, Optional, Union

from redis import asyncio as aioredis

from src.components.cache import Keys as CacheKeys
from src.core.redis import RedisCache
from src.loggers.console_service_logger import ConsoleServiceLogger


class CacheHelper:
    def __init__(
        self,
        redis_pool: aioredis.Redis,
        console_service_logger: ConsoleServiceLogger,
    ):
        self.__redis = redis_pool
        self.__logger = console_service_logger

    async def set_cache(
        self,
        key: str,
        value: Any,
        prefix: RedisCache.KeysPrefix = RedisCache.KeysPrefix.CONSOLE,
        ttl: Optional[int] = None,
    ) -> bool:
        """Set a single cache entry with optional ttl (Time To Live in seconds)."""
        try:
            serialized_value = json.dumps(
                value,
                default=lambda o: o.__dict__ if hasattr(o, "__dict__") else str(o),
            )
            full_key = f"{prefix.value}{key}"
            await self.__redis.set(full_key, serialized_value, ex=ttl)
            self.__logger.info("Successfully set cache for key: {}".format(full_key))
            return True
        except Exception as e:
            self.__logger.error(
                "Error setting cache for key: {}, error: {}".format(full_key, str(e))
            )
            return False

    async def get_cache(
        self,
        key: str,
        prefix: RedisCache.KeysPrefix = RedisCache.KeysPrefix.CONSOLE,
    ) -> Optional[Any]:
        """Retrieve a single cache entry."""
        try:
            full_key = f"{prefix.value}{key}"
            value = await self.__redis.get(full_key)
            if value is None:
                self.__logger.info("Cache miss for key: {}".format(full_key))
                return None
            self.__logger.info("Cache hit for key: {}".format(full_key))
            return json.loads(value.decode("utf-8"))
        except Exception as e:
            self.__logger.error(
                "Error getting cache for key: {}, error: {}".format(full_key, str(e))
            )
            return None

    async def delete_cache(
        self,
        key: str,
        prefix: RedisCache.KeysPrefix = RedisCache.KeysPrefix.CONSOLE,
    ) -> bool:
        """Delete a single cache entry."""
        try:
            full_key = f"{prefix.value}{key}"
            result = bool(await self.__redis.delete(full_key))
            self.__logger.info(
                "Successfully deleted cache for key: {}".format(full_key)
            )
            return result
        except Exception as e:
            self.__logger.error(
                "Error deleting cache for key: {}, error: {}".format(full_key, str(e))
            )
            return False

    async def bulk_set_cache(
        self,
        data: Dict[str, Any],
        prefix: RedisCache.KeysPrefix = RedisCache.KeysPrefix.CONSOLE,
        ttl: Optional[int] = None,
    ) -> bool:
        """Set multiple cache entries in a single operation."""
        try:
            pipeline = self.__redis.pipeline()
            full_keys = []
            for key, value in data.items():
                serialized_value = json.dumps(
                    value,
                    default=lambda o: o.__dict__ if hasattr(o, "__dict__") else str(o),
                )
                full_key = f"{prefix.value}{key}"
                full_keys.append(full_key)
                pipeline.set(full_key, serialized_value, ex=ttl)
            await pipeline.execute()
            self.__logger.info(
                "Successfully bulk set cache for keys: {}".format(", ".join(full_keys))
            )
            return True
        except Exception as e:
            self.__logger.error(
                "Error bulk setting cache for keys: {}, error: {}".format(
                    ", ".join(full_keys), str(e)
                )
            )
            return False

    async def bulk_get_cache(
        self,
        keys: List[str],
        prefix: RedisCache.KeysPrefix = RedisCache.KeysPrefix.CONSOLE,
    ) -> Dict[str, Any]:
        """Retrieve multiple cache entries in a single operation."""
        try:
            full_keys = [f"{prefix.value}{key}" for key in keys]
            values = await self.__redis.mget(full_keys)
            result = {}
            for key, value in zip(keys, values):
                if value is not None:
                    result[key] = json.loads(value.decode("utf-8"))
                    self.__logger.info(
                        "Cache hit for key: {}".format(f"{prefix.value}{key}")
                    )
                else:
                    self.__logger.info(
                        "Cache miss for key: {}".format(f"{prefix.value}{key}")
                    )
            return result
        except Exception as e:
            self.__logger.error(
                "Error bulk getting cache for keys: {}, error: {}".format(
                    ", ".join(full_keys), str(e)
                )
            )
            return {}

    async def bulk_delete_cache(
        self,
        keys: List[str],
        prefix: RedisCache.KeysPrefix = RedisCache.KeysPrefix.CONSOLE,
    ) -> int:
        """Delete multiple cache entries in a single operation."""
        try:
            full_keys = [f"{prefix.value}{key}" for key in keys]
            await self.__redis.delete(*full_keys)
            self.__logger.info(
                "Successfully bulk deleted cache for keys: {}".format(
                    ", ".join(full_keys)
                )
            )
            return True
        except Exception as e:
            self.__logger.error(
                "Error bulk deleting cache for keys: {}, error: {}".format(
                    ", ".join(full_keys), str(e)
                )
            )
            return False

    async def clear_pattern(
        self,
        prefix: RedisCache.KeysPrefix,
        pattern: Optional[Union[str, List[str]]] = None,
    ) -> bool:
        """Clear all cache entries with a specific prefix and optional pattern or list of patterns."""
        try:
            patterns = [pattern] if isinstance(pattern, str) else (pattern or [""])
            all_keys = []
            for p in patterns:
                match_pattern = f"{prefix.value}{p}*"
                keys = await self.__redis.keys(match_pattern)
                all_keys.extend(keys)
                self.__logger.info(
                    "Found keys for pattern: {}, keys: {}".format(
                        match_pattern, ", ".join(key.decode("utf-8") for key in keys)
                    )
                )

            if all_keys:
                await self.__redis.delete(*all_keys)
                self.__logger.info(
                    "Successfully cleared cache for {} keys across patterns".format(
                        len(all_keys)
                    )
                )
            else:
                self.__logger.info(
                    "No keys found for any patterns with prefix: {}".format(
                        prefix.value
                    )
                )
            return True
        except Exception as e:
            self.__logger.error(
                "Error clearing cache for prefix: {}, error: {}".format(
                    prefix.value, str(e)
                )
            )
            return False

    # ---------------- maglo cross-service invalidation ------------------- #
    # maglo-service caches console/auth identity data under the MAGLO prefix
    # with long TTLs and treats console as the source of truth. Console owns
    # invalidation on mutation. The three helpers below name the intent so the
    # (many) mutation sites don't each hand-roll the key patterns and drift.

    async def invalidate_role_derived_user_caches(self) -> None:
        """Bust the per-user role/data-scope caches maglo derives from a Role
        (``GRPC_GET_USER_DETAILS`` carries ``role_data_scope`` +
        ``role_hierarchy_level``; ``GRPC_GET_USER_ROLE`` carries roles +
        hierarchy). Call after any change to a Role's ``data_scope`` /
        ``hierarchy`` or to which Role a user points at.

        Broad by necessity: ``GRPC_GET_USER_DETAILS`` bakes the partner segment
        as a literal ``*`` (``.format("*", user_id)``), so it can't be scoped
        per partner — this clears every user's entry across all partners.
        """
        await self.clear_pattern(
            prefix=RedisCache.KeysPrefix.MAGLO,
            pattern=[
                CacheKeys.GRPC_GET_USER_DETAILS.format("*", ""),
                CacheKeys.GRPC_GET_USER_ROLE.format(""),
                # Team-scoped role cache carries the effective role's
                # hierarchy/data_scope, which shift with the same edits.
                CacheKeys.GRPC_GET_USER_TEAM_ROLE.split("{}")[0],
            ],
        )

    async def invalidate_user_permissions_cache(self) -> None:
        """Bust maglo's ``GRPC_GET_USER_PERMISSIONS`` (RBAC permission set,
        cached ONE_WEEK). Call after any grant/revoke of a permission on a role.
        The key is ``:{user_id}`` only (no partner segment), so this clears all
        users' permission sets."""
        await self.clear_pattern(
            prefix=RedisCache.KeysPrefix.MAGLO,
            pattern=[
                CacheKeys.GRPC_GET_USER_PERMISSIONS.format(""),
                # The team-scoped role cache embeds that role's permission set,
                # so a grant/revoke on any role must bust it too. Broad by
                # necessity (the key can't be reverse-mapped to affected users).
                CacheKeys.GRPC_GET_USER_TEAM_ROLE.split("{}")[0],
                # Same for the per-role configured-permissions cache.
                CacheKeys.GRPC_GET_ROLE_PERMISSIONS.split("{}")[0],
            ],
        )

    async def invalidate_user_team_role_cache(
        self, user_id: Optional[int] = None, team_id: Optional[int] = None
    ) -> None:
        """Bust maglo's ``GRPC_GET_USER_TEAM_ROLE`` (team-scoped effective role +
        permissions).

        - both ids: clear just that ``(user, team)`` entry;
        - ``user_id`` only: clear all of that user's team entries (a membership
          add/update/remove can change their effective role in that team);
        - neither: clear every entry (a role's identity/permissions changed).
        """
        if user_id is not None and team_id is not None:
            await self.delete_cache(
                key=CacheKeys.GRPC_GET_USER_TEAM_ROLE.format(user_id, team_id),
                prefix=RedisCache.KeysPrefix.MAGLO,
            )
        elif user_id is not None:
            await self.clear_pattern(
                prefix=RedisCache.KeysPrefix.MAGLO,
                pattern=CacheKeys.GRPC_GET_USER_TEAM_ROLE.format(user_id, ""),
            )
        else:
            await self.clear_pattern(
                prefix=RedisCache.KeysPrefix.MAGLO,
                pattern=CacheKeys.GRPC_GET_USER_TEAM_ROLE.split("{}")[0],
            )

    async def invalidate_partner_teams_cache(self, partner_id: int) -> None:
        """Bust the partner's team caches maglo reads
        (``GRPC_GET_PARTNER_TEAMS`` for the partner, and every
        ``GRPC_GET_USER_TEAMS`` under it). These keys carry ``partner_id`` so
        the clear stays partner-scoped."""
        await self.clear_pattern(
            prefix=RedisCache.KeysPrefix.MAGLO,
            pattern=CacheKeys.GRPC_GET_USER_TEAMS.format(partner_id, ""),
        )
        await self.delete_cache(
            key=CacheKeys.GRPC_GET_PARTNER_TEAMS.format(partner_id),
            prefix=RedisCache.KeysPrefix.MAGLO,
        )

    async def incr_with_ttl(
        self,
        key: str,
        ttl_seconds: int,
        prefix: RedisCache.KeysPrefix = RedisCache.KeysPrefix.CONSOLE,
    ) -> Optional[int]:
        """Atomically increment ``key`` and set ``ttl_seconds`` on first write.

        The canonical counter primitive for rate-limiters / quotas / dedup
        windows. Pipelined so INCR and EXPIRE travel as a single round-trip
        and never race. Returns the post-increment count, or ``None`` if
        Redis is unreachable so callers can choose their own
        fail-open / fail-closed policy.

        Why a primitive on the helper instead of ad-hoc ``redis.incr`` calls
        scattered in components: every counter in the codebase ends up
        needing the same TTL-on-first-write semantics; centralising it
        keeps key namespacing (``prefix.value`` join) and observability
        consistent.
        """
        full_key = f"{prefix.value}{key}"
        try:
            pipe = self.__redis.pipeline()
            pipe.incr(full_key)
            pipe.expire(full_key, ttl_seconds)
            results = await pipe.execute()
            # results = [count_after_incr, expire_ok_bool]
            count = int(results[0])
            return count
        except Exception as e:
            self.__logger.error(
                "incr_with_ttl failed for key={}, err={}".format(full_key, str(e))
            )
            return None
