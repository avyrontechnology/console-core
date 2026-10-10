from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.components.user_metadata.services import UserMetadataService

"""
conftest.py is a special configuration file that defines fixtures, 
hooks, and configurations to be shared across multiple test files within a 
directory. It provides a centralized place for setting up commonly used fixtures and behaviors, 
making it easier to manage dependencies and configurations in tests.
"""


@pytest.fixture(scope="session")
def mock_session_factory():
    """Fixture for creating a mock session factory."""
    session = AsyncMock(spec=AsyncSession)
    session_factory = MagicMock()
    session_factory.return_value.__aenter__.return_value = session
    session_factory.return_value.__aexit__.return_value = None
    return session_factory


@pytest.fixture(scope="session")
def mock_logger():
    """Fixture for creating a mock logger."""
    return MagicMock()


@pytest.fixture(scope="session")
def redis_mock():
    """Fixture for creating a mock Redis client."""
    return AsyncMock()


# New fixture to mock the user metadata repository
@pytest.fixture
def mock_user_metadata_repository():
    """Fixture for creating a mock user metadata repository."""
    return AsyncMock()  # Use AsyncMock if methods are asynchronous


# Fixture for the user metadata service
@pytest.fixture
def user_metadata_service(mock_user_metadata_repository, mock_logger):
    """Fixture for creating an instance of UserMetadataService."""
    # Passing mock_logger as console_service_logger
    return UserMetadataService(
        repository=mock_user_metadata_repository,
        logger=mock_logger,
        console_service_logger=mock_logger,  # Use a separate mock if needed
    )
