import enum

from redis import asyncio

from src.core.environment import ENV


class RedisCache:

    class KeysPrefix(enum.Enum):
        CONSOLE = "console:"
        MAGLO = "maglo:"
        TALKO = "talko:"
        BABBLER = "babbler:"

    @staticmethod
    async def init_redis_pool():
        url = "{protocol}://{username}:{password}@{host}:{port}/{db}".format(
            protocol=ENV.CACHE_PROTOCOL,
            username=ENV.CACHE_USERNAME,
            password=ENV.CACHE_PASSWORD,
            host=ENV.CACHE_HOST,
            port=ENV.CACHE_PORT,
            db=ENV.CACHE_DB,
        )
        print("#--------------- Redis URL: ", url, " ---------------#")
        pool = asyncio.from_url(url)
        yield pool
        pool.close()
        await pool.wait_closed()
