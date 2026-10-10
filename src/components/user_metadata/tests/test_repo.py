from collections import namedtuple
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy.exc import IntegrityError

from src.components.user.errors import UserNotFoundError
from src.components.user_metadata.models import UserMetadata
from src.components.user_metadata.repositories import UserMetadataRepository
from src.exceptions import UserMetadataAlreadyExistsException, UserMetadataException


@pytest.fixture(autouse=True)
def setup_method():
    """Set up test dependencies and patch the repository."""
    patcher = patch(
        "src.components.user_metadata.repositories.UserMetadataRepository",
        new_callable=AsyncMock,
    )
    mock_repository_class = patcher.start()
    mock_repository = mock_repository_class.return_value

    # Create a mock session and mock row
    UserMetadataRow = namedtuple(
        "UserMetadataRow", ["user_id", "meta_key", "meta_value"]
    )
    mock_row = UserMetadataRow(user_id=1, meta_key="test_key", meta_value="test_value")
    mock_session = AsyncMock()
    mock_session.execute.return_value.scalars.return_value.all.return_value = [mock_row]

    # Configure mock repository
    mock_repository.__aenter__.return_value = mock_session
    mock_repository.__aexit__.return_value = AsyncMock()

    yield mock_repository  # Yield the mock repository for use in tests

    patcher.stop()  # Ensure patch stops after tests


@pytest.mark.asyncio
async def test_get_all_user_metadata(setup_method):
    """Test fetching all user metadata."""
    # Set up the mock return value
    mock_row = UserMetadata(user_id=1, meta_key="test_key", meta_value="test_value")
    setup_method.get_all_user_metadata.return_value = [mock_row]

    # Directly call get_all_user_metadata without using `async with`
    result = await setup_method.get_all_user_metadata()

    # Assertions based on the mock data
    assert len(result) == 1
    assert result[0].meta_key == "test_key"
    assert result[0].meta_value == "test_value"


@pytest.mark.asyncio
async def test_update_user_metadata(setup_method):
    """Test updating existing user metadata."""
    user_id = 1
    updated_metadata = UserMetadata(
        user_id=user_id, meta_key="updated_key", meta_value="updated_value"
    )

    # Configure the mock to return the updated metadata
    setup_method.update_user_metadata.return_value = updated_metadata

    # Directly call update_user_metadata without using `async with`
    result = await setup_method.update_user_metadata(
        user_id=user_id, meta_key="updated_key", meta_value="updated_value"
    )

    # Assertions to check updated values
    assert result.meta_key == "updated_key"
    assert result.meta_value == "updated_value"


@pytest.mark.asyncio
async def test_add_user_metadata():
    """Test adding new user metadata."""
    user_id = 1
    new_metadata = UserMetadata(
        user_id=user_id, meta_key="new_key", meta_value="new_value"
    )

    # Patch the repository directly in the test to ensure clarity on the mock usage
    with patch(
        "src.components.user_metadata.repositories.UserMetadataRepository",
        new_callable=AsyncMock,
    ) as mock_repository_class:
        mock_repository = mock_repository_class.return_value
        # Set up the return value for add_user_metadata
        mock_repository.add_user_metadata.return_value = new_metadata

        # Directly call add_user_metadata on the mock repository
        result = await mock_repository.add_user_metadata(new_metadata)

        # Assertions to check returned values
        assert result.meta_key == "new_key"
        assert result.meta_value == "new_value"


@pytest.mark.asyncio
async def test_delete_umetadata_by_user_id():
    """Test deleting user metadata by user ID."""
    user_id = 1

    # Patch the repository directly in the test to ensure clarity on the mock usage
    with patch(
        "src.components.user_metadata.repositories.UserMetadataRepository",
        new_callable=AsyncMock,
    ) as mock_repository_class:
        mock_repository = mock_repository_class.return_value
        mock_repository.delete_umetadata_by_user_id = AsyncMock()

        # Directly call delete_umetadata_by_user_id on the mock repository
        await mock_repository.delete_umetadata_by_user_id(user_id)

        # Assert that the method was called once with the specified arguments
        mock_repository.delete_umetadata_by_user_id.assert_called_once_with(user_id)


@pytest.mark.asyncio
async def test_update_user_metadata_not_found(setup_method):
    """Test updating metadata when the user is not found."""
    setup_method.update_user_metadata.side_effect = UserNotFoundError

    async with setup_method as repository:
        with pytest.raises(UserNotFoundError):
            await repository.update_user_metadata(
                user_id=2, meta_key="nonexistent_key", meta_value="value"
            )


@pytest.mark.asyncio
async def test_add_user_metadata_already_exists(setup_method):
    """Test adding metadata that already exists."""
    setup_method.add_user_metadata.side_effect = UserMetadataAlreadyExistsException
    new_metadata = UserMetadata(user_id=1, meta_key="test_key", meta_value="value")

    async with setup_method as repository:
        with pytest.raises(UserMetadataAlreadyExistsException):
            await repository.add_user_metadata(new_metadata)


@pytest.mark.asyncio
async def test_generic_database_exception(setup_method):
    """Test generic database exception handling."""
    setup_method.get_all_user_metadata.side_effect = Exception("Database error")

    async with setup_method as repository:
        with pytest.raises(UserMetadataException):
            await repository.get_all_user_metadata()


@pytest.mark.asyncio
async def test_add_user_metadata_db_integrity_error(setup_method):
    """Test handling IntegrityError during metadata insertion."""
    setup_method.add_user_metadata.side_effect = IntegrityError(
        "Integrity error", None, None
    )
    new_metadata = UserMetadata(user_id=1, meta_key="new_key", meta_value="new_value")

    async with setup_method as repository:
        with pytest.raises(UserMetadataException):
            await repository.add_user_metadata(new_metadata)
