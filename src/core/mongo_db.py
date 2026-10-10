import contextlib
from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase
from pymongo.client_session import ClientSession
from typing import Any, AsyncIterator
from src.loggers.console_service_logger import ConsoleServiceLogger
from src.core.environment import ENV
from src.core.app_env import AppEnvironment

class MongoDatabaseSessionManager:
    def __init__(self, logger: ConsoleServiceLogger, engine_kwargs: dict[str, Any] = None):
        if engine_kwargs is None:
            engine_kwargs = {}

        self._logger = logger
        self._engine_kwargs = engine_kwargs
        self._client: AsyncIOMotorClient | None = None
        self._db: AsyncIOMotorDatabase | None = None

        # Database name directly from env
        self._db_name = getattr(ENV, "MONGO_DB", "console_mongo_db")

    def _get_connection_string(self):
        """
        Build MongoDB connection string dynamically.
        Works for both local Docker and integration envs.
        """
        if ENV.ENVIRONMENT != AppEnvironment.AllowedEnvs.Local.value:
            # Integration / Production (Atlas or DO-managed Mongo)
            self._host = (
                f"mongodb+srv://{ENV.MONGO_USER}:{ENV.MONGO_PASSWORD}@"
                f"{ENV.MONGO_HOST}/{ENV.MONGO_DB}?tls=true&authSource=admin"
            )    
        else:
            # Local (non-root user, no admin auth)
            self._host = (
                f"mongodb://{ENV.MONGO_USER}:{ENV.MONGO_PASSWORD}@"
                f"{ENV.MONGO_HOST}:{ENV.MONGO_PORT}/{ENV.MONGO_DB}?authSource=admin"
            )
            

    def _initialize_client(self):
        """
        Initialize MongoDB client and database handle.
        """
        if self._client is None:
            self._get_connection_string()
            self._logger.info(f"Connecting to MongoDB database: {self._db_name}")
            self._logger.info(f"MongoDB URI: {self._host}")
            self._client = AsyncIOMotorClient(self._host, **self._engine_kwargs)
            self._db = self._client[self._db_name]

    async def close(self):
        """
        Cleanly close MongoDB connection.
        """
        if self._client:
            self._client.close()
            self._client = None
            self._db = None

    @contextlib.asynccontextmanager
    async def connect(self) -> AsyncIterator[AsyncIOMotorDatabase]:
        """
        Yield a MongoDB database session with a transaction context.
        """
        self._initialize_client()
        session: ClientSession = await self._client.start_session()
        try:
            async with session.start_transaction():
                yield self._db
        finally:
            await session.end_session()

    @contextlib.asynccontextmanager
    async def collection(self, collection_name: str) -> AsyncIterator:
        """
        Yield a specific MongoDB collection handle.
        """
        async with self.connect() as db:
            collection = db[collection_name]
            try:
                yield collection
            except Exception as e:
                self._logger.error(f"Error during collection operation: {e}")
                raise
