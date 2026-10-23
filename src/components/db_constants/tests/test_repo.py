from uuid import UUID
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy.exc import SQLAlchemyError

from src.components.db_constants.models import Constants, MediaConstants
from src.components.db_constants.repositories import ConstantsRepository


@pytest.mark.asyncio
class TestConstantsRepository:

    @pytest.fixture(autouse=True)
    def setup_class(self, mock_session_factory, mock_logger):
        """Set up the constants repository using fixtures for mock session and logger."""
        self.constants_repository = ConstantsRepository(
            session_factory=mock_session_factory, console_service_logger=mock_logger
        )
        self.session = mock_session_factory.return_value.__aenter__.return_value
        self.mock_logger = mock_logger

        # Mock constant objects (these can be reused in multiple tests)
        self.mock_constant = MagicMock(spec=MediaConstants)
        self.mock_constant.id = UUID("11111111-1111-1111-1111-111111111111")
        self.mock_constant.name = "Test Constant"
        self.mock_constant.value = "Test Value"
        self.mock_constant.description = "Test Description"
        self.mock_constant.version = 1
        self.mock_constant.updated_by= UUID("11111111-1111-1111-1111-111111111111")
        self.mock_constant.updated_at = "2025-01-01"
        self.mock_constant.additional_info = {}
        self.mock_constant.media = None

        # Mock constant objects (these can be reused in multiple tests)
        self.mock_constant_1 = MagicMock(spec=Constants)
        self.mock_constant_1.id = UUID("11111111-1111-1111-1111-111111111111")
        self.mock_constant_1.name = "Test Constant1"
        self.mock_constant_1.value = "Test Value"
        self.mock_constant_1.description = "Test Description"
        self.mock_constant_1.version = 1
        self.mock_constant_1.updated_by= UUID("11111111-1111-1111-1111-111111111111")
        self.mock_constant_1.updated_at = "2025-01-01"
        self.mock_constant_1.additional_info = {}
        self.mock_constant_1.media = None
        self.mock_constant_1.created_at = None

    async def test_get_constant_by_id_exception_handling(self):
        """Test exception handling when an error occurs during fetching by ID."""
        # Mock the session to raise an error when executing the query
        self.session.execute = AsyncMock(side_effect=SQLAlchemyError("Database error"))

        # Call the method and verify that an exception is raised
        with pytest.raises(SQLAlchemyError) as exc_info:
            await self.constants_repository.get_constant_by_id(MediaConstants, UUID("11111111-1111-1111-1111-111111111111"))

        # Assert that the exception message is correct
        assert str(exc_info.value) == "Database error"

        # Verify that the error was logged
        self.mock_logger.error.assert_any_call(
            "Error fetching constant with ID 11111111-1111-1111-1111-111111111111 for type <class 'src.components.db_constants.models.MediaConstants'>: Database error"
        )

    async def test_fetch_constant_by_type_success(self):
        """Test fetching constants by type."""
        # Mock session execute to return mock constants

        mock_scalars = MagicMock()
        mock_scalars.all.return_value = [self.mock_constant_1]

        mock_execute = MagicMock()
        mock_execute.scalars.return_value = mock_scalars

        self.session.execute = AsyncMock(return_value=mock_execute)

        constants = await self.constants_repository.fetch_constant_by_type(Constants)

        # Assert that constants were fetched and the response matches the mock data
        assert len(constants) == 1
        assert constants[0].id == UUID("11111111-1111-1111-1111-111111111111")
        assert constants[0].name == "Test Constant1"
        self.mock_logger.info.assert_called_with(
            "Fetching constants for model type: <class 'src.components.db_constants.models.Constants'>"
        )

    async def test_fetch_constant_by_type_media_model(self):
        """Test fetching constants with media model."""

        mock_scalars = MagicMock()
        mock_scalars.all.return_value = [self.mock_constant]

        mock_execute = MagicMock()
        mock_execute.scalars.return_value = mock_scalars

        self.session.execute = AsyncMock(return_value=mock_execute)

        constants = await self.constants_repository.fetch_constant_by_type(
            MediaConstants
        )

        assert len(constants) == 1
        self.mock_logger.info.assert_called_with(
            "Fetching constants for model type: <class 'src.components.db_constants.models.MediaConstants'>"
        )

    async def test_fetch_constant_by_type_error(self):
        """Test error handling in fetch_constant_by_type."""
        self.session.execute = AsyncMock(side_effect=SQLAlchemyError("Mock Error"))

        with pytest.raises(SQLAlchemyError):
            await self.constants_repository.fetch_constant_by_type(MediaConstants)

        self.mock_logger.error.assert_called_with(
            "Error fetching constants for type <class 'src.components.db_constants.models.MediaConstants'>: Mock Error"
        )

    async def test_get_constant_by_id_success(self):
        """Test retrieving a constant by ID successfully."""
        mock_scalars = MagicMock()
        mock_scalars.first.return_value = self.mock_constant

        mock_execute = MagicMock()
        mock_execute.scalars.return_value = mock_scalars

        self.session.execute = AsyncMock(return_value=mock_execute)

        await self.constants_repository.get_constant_by_id(MediaConstants, 1)

    async def test_update_constant_success(self):
        """Test updating a constant successfully."""
        mock_constant = MagicMock()
        mock_constant.value = "Updated Value"

        mock_scalars = MagicMock()
        mock_scalars.first.return_value = mock_constant

        mock_execute = AsyncMock()
        mock_execute.scalars.return_value = mock_scalars

        self.session.execute = AsyncMock(return_value=mock_execute)
        self.session.commit = AsyncMock()

        await self.constants_repository.update_constant(
            id= UUID("11111111-1111-1111-1111-111111111111"),
            constant_model=MediaConstants,
            value="Updated Value",
            version=2,
            additional_info={"key": "value"},
            user_id= UUID("11111111-1111-1111-1111-111111111111"),
        )
        # Ensure logging is called
        self.mock_logger.info.assert_called_with(
            "Successfully updated constant with ID: 11111111-1111-1111-1111-111111111111 for type <class 'src.components.db_constants.models.MediaConstants'>"
        )

    async def test_update_constant_error(self):
        """Test error handling in update_constant."""
        self.session.execute = AsyncMock(side_effect=SQLAlchemyError("Mock Error"))

        with pytest.raises(SQLAlchemyError):
            await self.constants_repository.update_constant(
                id= UUID("11111111-1111-1111-1111-111111111111"),
                constant_model=MediaConstants,
                value="Updated Value",
                version=2,
                additional_info={"key": "value"},
                user_id= UUID("11111111-1111-1111-1111-111111111111"),
            )
        self.mock_logger.error.assert_called_with(
            "Error updating constant with ID 11111111-1111-1111-1111-111111111111 for type <class 'src.components.db_constants.models.MediaConstants'>: Mock Error"
        )

    async def test_rollback_version_success(self):
        """Test rolling back a constant to a previous version."""
        mock_scalars = MagicMock()
        mock_scalars.first.return_value = self.mock_constant

        mock_execute = MagicMock()
        mock_execute.scalars.return_value = mock_scalars

        self.session.execute = AsyncMock(return_value=mock_execute)
        self.session.commit = AsyncMock()

        await self.constants_repository.rollback_version(
            id= UUID("11111111-1111-1111-1111-111111111111"),
            constant_model=MediaConstants,
            value="Rolled Back Value",
            version=1,
            user_id= UUID("11111111-1111-1111-1111-111111111111"),
            additional_info="sample text",
        )

        self.mock_logger.info.assert_called_with(
            "Successfully rolled back constant with ID: 11111111-1111-1111-1111-111111111111 to version: 1"
        )

    async def test_rollback_version_error(self):
        """Test error handling in rollback_version."""
        self.session.execute = AsyncMock(side_effect=SQLAlchemyError("Mock Error"))

        with pytest.raises(SQLAlchemyError):
            await self.constants_repository.rollback_version(
                id= UUID("11111111-1111-1111-1111-111111111111"),
                constant_model=MediaConstants,
                value="Rolled Back Value",
                version=1,
                user_id= UUID("11111111-1111-1111-1111-111111111111"),
                additional_info="sample text",
            )
        self.mock_logger.error.assert_called_with(
            "An error occured while rolling back constant with ID 11111111-1111-1111-1111-111111111111 to version 1 for type <class 'src.components.db_constants.models.MediaConstants'>: Mock Error"
        )



