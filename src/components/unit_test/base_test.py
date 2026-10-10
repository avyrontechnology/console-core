import os
import unittest
from unittest.mock import AsyncMock, patch

from fastapi import Depends

from src.core.app_env import AppEnvironment
from src.core.db import Base
from src.exceptions import EnvironmentNotFoundException


class BaseTestSetup(unittest.IsolatedAsyncioTestCase):
    async def mock_session_context(self):
        self.mock_session = AsyncMock()

    @patch("src.core.db.DatabaseSessionManager.session", new_callable=AsyncMock)
    async def asyncSetUp(self, mock_db_session) -> None:
        """
        Set up mock DB session for the tests, ensuring the testing environment is used.
        """
        self.mock_db_session = mock_db_session

        if (
            os.getenv("Env", AppEnvironment.AllowedEnvs.Testing.value)
            == AppEnvironment.AllowedEnvs.Testing.value
        ):
            async with self.mock_db_session as session:
                session.run_sync = AsyncMock()
                session.execute = AsyncMock()

                await self.setup_tables(session)

                await self.initialize_dependency()

        else:
            raise EnvironmentNotFoundException("Testing environment not set")

    async def setup_tables(self, session):
        """
        Override this method in child classes to define table setup logic.
        """
        pass

    async def initialize_dependency(self):
        """for child classes to initialize services or dependencies."""
        pass

    @patch("src.core.db.DatabaseSessionManager.session", new_callable=AsyncMock)
    async def asyncTearDown(self, mock_db_session) -> None:
        """
        Tear down after each test.
        """
        if (
            os.getenv("Env", AppEnvironment.AllowedEnvs.Testing.value)
            == AppEnvironment.AllowedEnvs.Testing.value
        ):
            async with mock_db_session as session:
                session.run_sync = AsyncMock()

                await self.teardown_tables(session)

    async def teardown_tables(self, session):
        """
        Override this method in child classes to define table teardown logic.
        """
        pass
