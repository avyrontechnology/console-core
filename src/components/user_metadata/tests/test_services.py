from unittest.mock import AsyncMock

import pytest

from src.components.user.errors import UserNotFoundError
from src.components.user_metadata.errors import UserMatadataNotFoundError
from src.components.user_metadata.repositories import UserMetadataRepository
from src.components.user_metadata.schema import UserMetadataSchema
from src.components.user_metadata.services import UserMetadataService
from src.exceptions import UserMetadataAlreadyExistsException


@pytest.mark.asyncio
class TestUserMetadataService:

    @pytest.fixture(scope="function", autouse=True)
    def user_metadata_service_setup(
        self, mock_session_factory, mock_logger, redis_mock
    ):
        """Fixture to initialize mocks before each test method."""
        # Setup for service layer dependencies
        self.mock_session = mock_session_factory.return_value.__aenter__.return_value
        self.mock_logger = mock_logger
        self.redis_mock = redis_mock

        # Mocked UserMetadataRepository with async methods to simulate database operations
        self.mock_user_metadata_repository = AsyncMock(spec=UserMetadataRepository)
        self.mock_user_metadata_repository.get_all_user_metadata = AsyncMock()
        self.mock_user_metadata_repository.get_all_user_metadata.return_value = []

        # Mock other repository methods
        self.mock_user_metadata_repository.add_user_metadata = AsyncMock()
        self.mock_user_metadata_repository.update_user_metadata = AsyncMock()
        self.mock_user_metadata_repository.delete_user_metadata_by_id = AsyncMock()

        # Mock the return value for adding user metadata
        self.mock_user_metadata_repository.add_user_metadata.return_value = (
            UserMetadataSchema(id=1, meta_key="new_key", meta_value="new_value")
        )

        # Create an instance of UserMetadataService with the mock repository and other dependencies
        self.user_metadata_service = UserMetadataService(
            audit_service=self.redis_mock,
            user_metadata_repository=self.mock_user_metadata_repository,
            console_service_logger=self.mock_logger,
        )

        # Return mock objects for use in the test
        return (
            self.mock_user_metadata_repository,
            self.user_metadata_service,
            self.mock_logger,
            self.redis_mock,
        )

    @pytest.mark.asyncio
    async def test_get_user_metadata(self):
        """Test for getting all user metadata successfully."""
        mock_metadata_list = [
            UserMetadataSchema(id=1, meta_key="key1", meta_value="value1"),
            UserMetadataSchema(id=2, meta_key="key2", meta_value="value2"),
        ]

        # Mock the repository method to return mock data
        self.mock_user_metadata_repository.get_all_user_metadata.return_value = (
            mock_metadata_list
        )

        # Run the service method
        result = await self.user_metadata_service.get_user_metadata()

        # Assertions
        self.mock_user_metadata_repository.get_all_user_metadata.assert_awaited_once()
        assert len(result) == 2
        assert result[0].id == 1
        assert result[1].meta_key == "key2"

    @pytest.mark.asyncio
    async def test_get_user_metadata_empty(self):
        """Test when no user metadata is found."""
        self.mock_user_metadata_repository.get_all_user_metadata.return_value = []

        # Execute the service method, expecting the custom exception
        with pytest.raises(UserMatadataNotFoundError) as exc_info:
            await self.user_metadata_service.get_user_metadata()

        assert "No user metadata found" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_add_user_metadata_success(self):
        """Test adding user metadata successfully."""
        mock_metadata = UserMetadataSchema(
            id=1, meta_key="new_key", meta_value="new_value"
        )
        current_user = {"user_id": 1}

        # Simulate a successful add operation
        self.mock_user_metadata_repository.add_user_metadata.return_value = (
            mock_metadata
        )

        # Run the service method
        await self.user_metadata_service.add_user_metadata(
            user_id=1, user_metadata=mock_metadata, current_user=current_user
        )

        # Check that both log messages were called
        self.mock_logger.info.assert_any_call(
            "Attempting to add metadata for user_id: 1"
        )
        self.mock_logger.info.assert_any_call(
            "Successfully added metadata for user_id: 1"
        )

        # Ensure that both log calls were made exactly once
        assert self.mock_logger.info.call_count == 2

    @pytest.mark.asyncio
    async def test_add_user_metadata_failure(self):
        """Test failure scenario when adding user metadata (e.g., metadata already exists)."""
        mock_metadata = UserMetadataSchema(
            id=1, meta_key="existing_key", meta_value="existing_value"
        )
        current_user = {"user_id": 1}

        # Simulate failure (e.g., metadata already exists)
        self.mock_user_metadata_repository.add_user_metadata.side_effect = (
            UserMetadataAlreadyExistsException(
                f"Metadata with key {mock_metadata.meta_key} already exists"
            )
        )

        # Run the service method and expect it to raise the expected exception
        with pytest.raises(UserMetadataAlreadyExistsException):
            await self.user_metadata_service.add_user_metadata(
                user_id=1, user_metadata=mock_metadata, current_user=current_user
            )

        # Ensure the error log was called
        self.mock_logger.error.assert_called_once_with(
            "Metadata already exists for user_id=1: Metadata with key existing_key already exists"
        )

    @pytest.mark.asyncio
    async def test_update_user_metadata_user_not_found(self):
        """Test updating user metadata when the user is not found."""
        mock_metadata = UserMetadataSchema(
            id=1, meta_key="new_key", meta_value="new_value"
        )
        current_user = {"user_id": 1}

        # Simulate user metadata not found
        self.mock_user_metadata_repository.get_user_metadata_by_user_id.return_value = (
            None
        )

        # Run the service method and assert exception is raised
        with pytest.raises(UserNotFoundError):
            await self.user_metadata_service.update_user_metadata(
                current_user, user_id=1, user_metadata=mock_metadata
            )

    @pytest.mark.asyncio
    async def test_update_user_metadata_success(self, user_metadata_service_setup):
        # Unpack the fixture
        (
            mock_user_metadata_repository,
            user_metadata_service,
            mock_logger,
            redis_mock,
        ) = user_metadata_service_setup

        current_user = {"user_id": 1}

        # Create the mock data to return
        mock_metadata = UserMetadataSchema(
            id=1, meta_key="existing_key", meta_value="existing_value"
        )
        mock_user_metadata_repository.update_user_metadata.return_value = mock_metadata

        # Call the service method
        await user_metadata_service.update_user_metadata(
            current_user, "new_key", "new_value"
        )

    @pytest.mark.asyncio
    async def test_delete_user_metadata_by_id_success(
        self, user_metadata_service_setup
    ):
        """Test successfully deleting user metadata."""
        # Unpack the returned mock objects
        (
            mock_user_metadata_repository,
            user_metadata_service,
            mock_logger,
            redis_mock,
        ) = user_metadata_service_setup

        id = 1
        current_user = {"user_id": 1}

        # Mock the repository's delete method to simulate success
        mock_user_metadata_repository.delete_user_metadata_by_id.return_value = None

        # Call the service method
        await user_metadata_service.delete_user_metadata_by_id(id, current_user)
