import pytest
from unittest.mock import AsyncMock, MagicMock
from src.components.api_key.repositories import ApiKeyRepository
from src.components.api_key.models import ApiKey


@pytest.mark.asyncio
class TestApiKeyRepository:

    @pytest.fixture(autouse=True)
    def setup_class(self, mock_session_factory, mock_logger):
        """Set up repository with mock session and logger."""
        self.api_key_repository = ApiKeyRepository(
            session_factory=mock_session_factory,
            console_service_logger=mock_logger
        )
        self.session = mock_session_factory.return_value.__aenter__.return_value
        self.mock_logger = mock_logger

    # ------------------------------------------------------------------------
    # generate_api_key
    # ------------------------------------------------------------------------
    async def test_generate_api_key_success(self):
        """Test successful API key generation."""
        mock_api_key = ApiKey(id=1, partner_id=10, is_active=True)

        self.session.commit = AsyncMock()
        self.session.refresh = AsyncMock()
        self.session.add = MagicMock()

        result = await self.api_key_repository.generate_api_key(10, 5)

        self.session.add.assert_called_once()
        self.session.commit.assert_awaited()
        self.session.refresh.assert_awaited()
        self.mock_logger.info.assert_any_call(
            "API key generated successfully for partner_id: 10"
        )
        assert isinstance(result, ApiKey)

    async def test_generate_api_key_exception(self):
        """Test exception handling in generate_api_key."""
        self.session.commit = MagicMock(side_effect=Exception("Unexpected Error"))

        with pytest.raises(Exception, match="Unexpected Error"):
            await self.api_key_repository.generate_api_key(10, 5)

        self.mock_logger.error.assert_called_with(
            "Error generating API key for partner_id=10: Unexpected Error"
        )

    # ------------------------------------------------------------------------
    # validate_api_key
    # ------------------------------------------------------------------------
    async def test_validate_api_key_success(self):
        """Test successful API key validation."""
        mock_api_key = ApiKey(id=1, key="test123", is_active=True)

        mock_scalars = MagicMock()
        mock_scalars.first.return_value = mock_api_key
        mock_execute = MagicMock()
        mock_execute.scalars.return_value = mock_scalars

        self.session.execute = AsyncMock(return_value=mock_execute)

        result = await self.api_key_repository.validate_api_key("test123")

        assert result == mock_api_key
        self.mock_logger.info.assert_called_with("Validating API key: test123...")

    async def test_validate_api_key_not_found(self):
        """Test validate_api_key returns None if not found."""
        mock_scalars = MagicMock()
        mock_scalars.first.return_value = None
        mock_execute = MagicMock()
        mock_execute.scalars.return_value = mock_scalars

        self.session.execute = AsyncMock(return_value=mock_execute)

        result = await self.api_key_repository.validate_api_key("invalidkey")

        assert result is None
        self.mock_logger.info.assert_called_with("Validating API key: invalidkey...")

    async def test_validate_api_key_exception(self):
        """Test exception handling in validate_api_key."""
        self.session.execute = AsyncMock(side_effect=Exception("Query failed"))

        with pytest.raises(Exception, match="Query failed"):
            await self.api_key_repository.validate_api_key("key123")

        self.mock_logger.error.assert_called_with(
            "Unexpected error while validating API key=key123...: Query failed"
        )

    # ------------------------------------------------------------------------
    # get_active_api_key
    # ------------------------------------------------------------------------
    async def test_get_active_api_key_success(self):
        """Test successful retrieval of active API key."""
        mock_api_key = ApiKey(id=2, partner_id=10, is_active=True)

        mock_scalars = MagicMock()
        mock_scalars.first.return_value = mock_api_key
        mock_execute = MagicMock()
        mock_execute.scalars.return_value = mock_scalars
        self.session.execute = AsyncMock(return_value=mock_execute)

        result = await self.api_key_repository.get_active_api_key(10)

        assert result == mock_api_key
        self.mock_logger.info.assert_any_call(
            "Successfully fetched active API key for partner_id: 10"
        )

    async def test_get_active_api_key_not_found(self):
        """Test get_active_api_key returns None if no key is found."""
        mock_scalars = MagicMock()
        mock_scalars.first.return_value = None
        mock_execute = MagicMock()
        mock_execute.scalars.return_value = mock_scalars
        self.session.execute = AsyncMock(return_value=mock_execute)

        result = await self.api_key_repository.get_active_api_key(999)
        assert result is None
        self.mock_logger.info.assert_any_call(
            "Attempting to fetch active API key for partner_id: 999"
        )

    async def test_get_active_api_key_exception(self):
        """Test exception handling in get_active_api_key."""
        self.session.execute = AsyncMock(side_effect=Exception("DB error"))

        with pytest.raises(Exception, match="DB error"):
            await self.api_key_repository.get_active_api_key(10)

        self.mock_logger.error.assert_called_with(
            "Error fetching API key for partner_id=10: DB error"
        )

    # ------------------------------------------------------------------------
    # inactivate_api_key
    # ------------------------------------------------------------------------
    async def test_inactivate_api_key_success(self):
        """Test successful inactivation of API key."""
        mock_api_key = ApiKey(id=3, partner_id=20, is_active=False)

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_api_key
        self.session.execute = AsyncMock(return_value=mock_result)
        self.session.commit = AsyncMock()

        result = await self.api_key_repository.inactivate_api_key(20, 5)

        assert result is True
        self.session.commit.assert_awaited()
        self.mock_logger.info.assert_any_call(
            "API key for partner_id=20 successfully inactivated by user_id=5"
        )

    async def test_inactivate_api_key_not_found(self):
        """Test inactivate_api_key returns None when no active key found."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        self.session.execute = AsyncMock(return_value=mock_result)

        result = await self.api_key_repository.inactivate_api_key(30, 7)

        assert result is False
        self.mock_logger.warning.assert_called_with(
            "No active API key found for partner_id=30"
        )

    async def test_inactivate_api_key_exception(self):
        """Test exception handling in inactivate_api_key."""
        self.session.execute = AsyncMock(side_effect=Exception("Update failed"))

        with pytest.raises(Exception, match="Update failed"):
            await self.api_key_repository.inactivate_api_key(10, 1)

        self.mock_logger.error.assert_called_with(
            "Unexpected error while inactivating API key for partner_id=10: Update failed"
        )
