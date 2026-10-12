import json
import unittest
from unittest.mock import AsyncMock, MagicMock, call

from src.components.cache.helper import CacheHelper
from src.core.redis import RedisCache


class TestCacheHelper(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.redis_pool = AsyncMock()
        self.logger = MagicMock()
        self.cache_helper = CacheHelper(self.redis_pool, self.logger)
        self.prefix = RedisCache.KeysPrefix.CONSOLE

    async def test_set_cache_success(self):
        # Arrange
        key = "test_key"
        value = {"data": "test"}
        full_key = f"{self.prefix.value}{key}"
        self.redis_pool.set = AsyncMock(return_value=True)

        # Act
        result = await self.cache_helper.set_cache(key, value, self.prefix)

        # Assert
        self.redis_pool.set.assert_called_once_with(
            full_key, json.dumps(value), ex=None
        )
        self.logger.info.assert_called_once_with(
            f"Successfully set cache for key: {full_key}"
        )
        self.assertTrue(result)

    async def test_set_cache_error(self):
        # Arrange
        key = "test_key"
        value = {"data": "test"}
        full_key = f"{self.prefix.value}{key}"
        self.redis_pool.set = AsyncMock(side_effect=Exception("Redis error"))

        # Act
        result = await self.cache_helper.set_cache(key, value, self.prefix)

        # Assert
        self.redis_pool.set.assert_called_once_with(
            full_key, json.dumps(value), ex=None
        )
        self.logger.error.assert_called_once_with(
            f"Error setting cache for key: {full_key}, error: Redis error"
        )
        self.assertFalse(result)

    async def test_get_cache_hit(self):
        # Arrange
        key = "test_key"
        full_key = f"{self.prefix.value}{key}"
        value = {"data": "test"}
        serialized_value = json.dumps(value).encode("utf-8")
        self.redis_pool.get = AsyncMock(return_value=serialized_value)

        # Act
        result = await self.cache_helper.get_cache(key, self.prefix)

        # Assert
        self.redis_pool.get.assert_called_once_with(full_key)
        self.logger.info.assert_called_once_with(f"Cache hit for key: {full_key}")
        self.assertEqual(result, value)

    async def test_get_cache_miss(self):
        # Arrange
        key = "test_key"
        full_key = f"{self.prefix.value}{key}"
        self.redis_pool.get = AsyncMock(return_value=None)

        # Act
        result = await self.cache_helper.get_cache(key, self.prefix)

        # Assert
        self.redis_pool.get.assert_called_once_with(full_key)
        self.logger.info.assert_called_once_with(f"Cache miss for key: {full_key}")
        self.assertIsNone(result)

    async def test_get_cache_error(self):
        # Arrange
        key = "test_key"
        full_key = f"{self.prefix.value}{key}"
        self.redis_pool.get = AsyncMock(side_effect=Exception("Redis error"))

        # Act
        result = await self.cache_helper.get_cache(key, self.prefix)

        # Assert
        self.redis_pool.get.assert_called_once_with(full_key)
        self.logger.error.assert_called_once_with(
            f"Error getting cache for key: {full_key}, error: Redis error"
        )
        self.assertIsNone(result)

    async def test_delete_cache_success(self):
        # Arrange
        key = "test_key"
        full_key = f"{self.prefix.value}{key}"
        self.redis_pool.delete = AsyncMock(return_value=1)

        # Act
        result = await self.cache_helper.delete_cache(key, self.prefix)

        # Assert
        self.redis_pool.delete.assert_called_once_with(full_key)
        self.logger.info.assert_called_once_with(
            f"Successfully deleted cache for key: {full_key}"
        )
        self.assertTrue(result)

    async def test_delete_cache_error(self):
        # Arrange
        key = "test_key"
        full_key = f"{self.prefix.value}{key}"
        self.redis_pool.delete = AsyncMock(side_effect=Exception("Redis error"))

        # Act
        result = await self.cache_helper.delete_cache(key, self.prefix)

        # Assert
        self.redis_pool.delete.assert_called_once_with(full_key)
        self.logger.error.assert_called_once_with(
            f"Error deleting cache for key: {full_key}, error: Redis error"
        )
        self.assertFalse(result)

    async def test_bulk_set_cache_success(self):
        # Arrange
        data = {"key1": {"data": "test1"}, "key2": {"data": "test2"}}
        full_keys = [f"{self.prefix.value}{key}" for key in data.keys()]
        pipeline = AsyncMock()
        pipeline.set = MagicMock()
        pipeline.execute = AsyncMock(return_value=[True, True])
        self.redis_pool.pipeline = MagicMock(return_value=pipeline)

        # Act
        result = await self.cache_helper.bulk_set_cache(data, self.prefix)

        # Assert
        self.redis_pool.pipeline.assert_called_once()
        pipeline.execute.assert_called_once()
        for key, value in data.items():
            pipeline.set.assert_any_call(
                f"{self.prefix.value}{key}", json.dumps(value), ex=None
            )
        self.logger.info.assert_called_once_with(
            f"Successfully bulk set cache for keys: {', '.join(full_keys)}"
        )
        self.assertTrue(result)

    async def test_bulk_set_cache_error(self):
        # Arrange
        data = {"key1": {"data": "test1"}, "key2": {"data": "test2"}}
        full_keys = [f"{self.prefix.value}{key}" for key in data.keys()]
        pipeline = AsyncMock()
        pipeline.set = MagicMock()
        pipeline.execute = AsyncMock(side_effect=Exception("Redis error"))
        self.redis_pool.pipeline = MagicMock(return_value=pipeline)

        # Act
        result = await self.cache_helper.bulk_set_cache(data, self.prefix)

        # Assert
        self.redis_pool.pipeline.assert_called_once()
        pipeline.execute.assert_called_once()
        self.logger.error.assert_called_once_with(
            f"Error bulk setting cache for keys: {', '.join(full_keys)}, error: Redis error"
        )
        self.assertFalse(result)

    async def test_bulk_get_cache_success(self):
        # Arrange
        keys = ["key1", "key2"]
        full_keys = [f"{self.prefix.value}{key}" for key in keys]
        values = [json.dumps({"data": "test1"}).encode("utf-8"), None]
        self.redis_pool.mget = AsyncMock(return_value=values)

        # Act
        result = await self.cache_helper.bulk_get_cache(keys, self.prefix)

        # Assert
        self.redis_pool.mget.assert_called_once_with(full_keys)
        self.logger.info.assert_any_call(f"Cache hit for key: {full_keys[0]}")
        self.logger.info.assert_any_call(f"Cache miss for key: {full_keys[1]}")
        self.assertEqual(result, {"key1": {"data": "test1"}})

    async def test_bulk_get_cache_error(self):
        # Arrange
        keys = ["key1", "key2"]
        full_keys = [f"{self.prefix.value}{key}" for key in keys]
        self.redis_pool.mget = AsyncMock(side_effect=Exception("Redis error"))

        # Act
        result = await self.cache_helper.bulk_get_cache(keys, self.prefix)

        # Assert
        self.redis_pool.mget.assert_called_once_with(full_keys)
        self.logger.error.assert_called_once_with(
            f"Error bulk getting cache for keys: {', '.join(full_keys)}, error: Redis error"
        )
        self.assertEqual(result, {})

    async def test_bulk_delete_cache_success(self):
        # Arrange
        keys = ["key1", "key2"]
        full_keys = [f"{self.prefix.value}{key}" for key in keys]
        self.redis_pool.delete = AsyncMock(return_value=2)

        # Act
        result = await self.cache_helper.bulk_delete_cache(keys, self.prefix)

        # Assert
        self.redis_pool.delete.assert_called_once_with(*full_keys)
        self.logger.info.assert_called_once_with(
            f"Successfully bulk deleted cache for keys: {', '.join(full_keys)}"
        )
        self.assertTrue(result)

    async def test_bulk_delete_cache_error(self):
        # Arrange
        keys = ["key1", "key2"]
        full_keys = [f"{self.prefix.value}{key}" for key in keys]
        self.redis_pool.delete = AsyncMock(side_effect=Exception("Redis error"))

        # Act
        result = await self.cache_helper.bulk_delete_cache(keys, self.prefix)

        # Assert
        self.redis_pool.delete.assert_called_once_with(*full_keys)
        self.logger.error.assert_called_once_with(
            f"Error bulk deleting cache for keys: {', '.join(full_keys)}, error: Redis error"
        )
        self.assertFalse(result)

    async def test_clear_pattern_error(self):
        # Arrange
        pattern = "ENLIST_AGENTS_PARTNER:12"
        match_pattern = f"{self.prefix.value}{pattern}*"
        self.redis_pool.keys = AsyncMock(side_effect=Exception("Redis error"))

        # Act
        result = await self.cache_helper.clear_pattern(self.prefix, pattern)

        # Assert
        self.redis_pool.keys.assert_called_once_with(match_pattern)
        self.redis_pool.delete.assert_not_called()
        self.assertFalse(result)
        # Check logger.error call
        expected_error_message = (
            f"Error clearing cache for prefix: {self.prefix.value}, error: Redis error"
        )
        self.logger.error.assert_called_once_with(expected_error_message)

    async def test_clear_pattern_success_with_keys(self):
        # Arrange
        pattern = "ENLIST_AGENTS_PARTNER:12"
        match_pattern = f"{self.prefix.value}{pattern}*"
        keys = [
            b"console:ENLIST_AGENTS_PARTNER:12_USER:33",
            b"console:ENLIST_AGENTS_PARTNER:12_OTHER",
        ]
        self.redis_pool.keys = AsyncMock(return_value=keys)
        self.redis_pool.delete = AsyncMock(return_value=len(keys))

        # Act
        result = await self.cache_helper.clear_pattern(self.prefix, pattern)

        # Assert
        self.redis_pool.keys.assert_called_once_with(match_pattern)
        self.redis_pool.delete.assert_called_once_with(*keys)
        self.assertTrue(result)
        # Check logger.info calls
        expected_log_message = (
            f"Found keys for pattern: {match_pattern}, "
            f"keys: {', '.join(key.decode('utf-8') for key in keys)}"
        )
        self.assertIn(
            call(expected_log_message),
            self.logger.info.call_args_list,
            "Expected log message not found in logger.info calls",
        )

    async def test_clear_pattern_no_keys_found(self):
        # Arrange
        pattern = "ENLIST_AGENTS_PARTNER:12"
        match_pattern = f"{self.prefix.value}{pattern}*"
        self.redis_pool.keys = AsyncMock(return_value=[])

        # Act
        result = await self.cache_helper.clear_pattern(self.prefix, pattern)

        # Assert
        self.redis_pool.keys.assert_called_once_with(match_pattern)
        self.redis_pool.delete.assert_not_called()
        self.assertTrue(result)
        # Check logger.info calls
        expected_log_message = (
            f"No keys found for any patterns with prefix: {self.prefix.value}"
        )
        self.assertIn(
            call(expected_log_message),
            self.logger.info.call_args_list,
            "Expected log message not found in logger.info calls",
        )

    async def test_clear_pattern_no_pattern(self):
        # Arrange
        match_pattern = f"{self.prefix.value}*"
        keys = [b"console:KEY1", b"console:KEY2"]
        self.redis_pool.keys = AsyncMock(return_value=keys)
        self.redis_pool.delete = AsyncMock(return_value=len(keys))

        # Act
        result = await self.cache_helper.clear_pattern(self.prefix)

        # Assert
        self.redis_pool.keys.assert_called_once_with(match_pattern)
        self.redis_pool.delete.assert_called_once_with(*keys)
        self.assertTrue(result)
        # Check logger.info calls
        expected_log_message = (
            f"Found keys for pattern: {match_pattern}, "
            f"keys: {', '.join(key.decode('utf-8') for key in keys)}"
        )
        self.assertIn(
            call(expected_log_message),
            self.logger.info.call_args_list,
            "Expected log message not found in logger.info calls",
        )

    # ---------- cross-service invalidation helpers ------------------ #
    # These lock in the exact prefixed Redis match patterns; a drift here
    # silently stops the corresponding keys from being cleared.



