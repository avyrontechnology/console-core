from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

"""
conftest.py is a special configuration file that defines fixtures,
hooks, and configurations to be shared across multiple test files within a
directory. It provides a centralized place for setting up commonly used fixtures and behaviors,
making it easier to manage dependencies and configurations in tests.
"""

# Several models (User chief among them) declare relationships as lazy,
# string-based references ("Partner", "UserMetadata", ...) to dodge circular
# imports. Those strings only resolve once every referenced class has been
# imported somewhere in the process. App startup does this transitively via
# the router wiring; a test file that imports just one or two models in
# isolation does not, and SQLAlchemy's mapper configuration then fails with
# "failed to locate a name (...)". Importing the full route registration
# here, once, up front for every test under this directory closes that gap
# without hand-listing every model the relationships happen to reference.
import src.routes.base  # noqa: F401


@pytest.fixture(scope="session")
def mock_session_factory():
    """Fixture for creating a mock session factory."""
    session = AsyncMock(spec=AsyncSession)
    session_factory = MagicMock()
    session_factory.return_value.__aenter__.return_value = session
    session_factory.return_value.__aexit__.return_value = None
    return session_factory

@pytest.fixture(scope="session")
def mock_mongo_db_session():
    """Fixture for creating a mock MongoDB session manager"""
    
    mongo_mock = MagicMock()
    mock_context = mongo_mock.return_value.__aenter__.return_value
    collection_context = MagicMock()
    collection_context.__aenter__.return_value = AsyncMock()  
    collection_context.__aexit__.return_value = None
    mock_context.collection.return_value = collection_context

    return mongo_mock


@pytest.fixture(scope="session")
def mock_logger():
    """Fixture for creating a mock logger."""
    return MagicMock()


@pytest.fixture(scope="session")
def redis_mock():
    """Fixture for creating a mock Redis client."""
    return AsyncMock()
