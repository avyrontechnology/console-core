import contextlib
from typing import Any, AsyncIterator

from sqlalchemy.ext.asyncio import (
    AsyncConnection,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import declarative_base
from sqlalchemy.pool import NullPool

Base = declarative_base()

# Flipped to True by the Celery worker bootstrap (see console_celery.async_utils)
# BEFORE the engine is built. Celery prefork workers must NOT reuse pooled
# asyncpg connections: a connection left in a bad/busy state (interrupted query,
# task_time_limit kill, undrained await) otherwise lingers in the pool and every
# later task that checks it out fails with "another operation is in progress".
# NullPool opens a fresh connection per session and discards it on close.
USE_NULL_POOL = False

# Heavily inspired by https://praciano.com.br/fastapi-and-async-sqlalchemy-20-with-pytest-done-right.html


class DatabaseSessionManager:
    def __init__(self, host: str, engine_kwargs: dict[str, Any] = {}):
        if USE_NULL_POOL:
            # No pooling: every session gets a brand-new connection (workers).
            self._engine = create_async_engine(
                host,
                poolclass=NullPool,
                **engine_kwargs
            )
        else:
            self._engine = create_async_engine(
                host,
                pool_size=10,  # number of persistent connections
                max_overflow=20,  # extra temporary connections
                pool_timeout=30,  # timeout for waiting on a connection
                pool_recycle=1800,  # recycle connections after 30 mins (optional)
                **engine_kwargs
            )
        self._sessionmaker = async_sessionmaker(autocommit=False, bind=self._engine)

    async def close(self):
        if self._engine is None:
            raise Exception("DatabaseSessionManager is not initialized")
        await self._engine.dispose()

        self._engine = None
        self._sessionmaker = None

    @contextlib.asynccontextmanager
    async def connect(self) -> AsyncIterator[AsyncConnection]:
        if self._engine is None:
            raise Exception("DatabaseSessionManager is not initialized")

        async with self._engine.begin() as connection:
            try:
                yield connection
            except Exception:
                await connection.rollback()
                raise

    @contextlib.asynccontextmanager
    async def session(self) -> AsyncIterator[AsyncSession]:
        if self._sessionmaker is None:
            raise Exception("DatabaseSessionManager is not initialized")

        session = self._sessionmaker()
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()
