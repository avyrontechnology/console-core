from uuid import UUID
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
        mock_api_key = ApiKey(id= UUID("11111111-1111-1111-1111-111111111111"), partner_id= UUID("10101010-1010-1010-1010-101010101010"), is_active=True)

        self.session.commit = AsyncMock()
        self.session.refresh = AsyncMock()
        self.session.add = MagicMock()

        result = await self.api_key_repository.generate_api_key(UUID("10101010-1010-1010-1010-101010101010"), UUID("55555555-5555-5555-5555-555555555555"))

        self.session.add.assert_called_once()
        self.session.commit.assert_awaited()
        self.session.refresh.assert_awaited()
        self.mock_logger.info.assert_any_call(
            "API key generated successfully for partner_id: 10101010-1010-1010-1010-101010101010"
        )
        assert isinstance(result, ApiKey)

    async def test_generate_api_key_exception(self):
        """Test exception handling in generate_api_key."""
        self.session.commit = MagicMock(side_effect=Exception("Unexpected Error"))

        with pytest.raises(Exception, match="Unexpected Error"):
            await self.api_key_repository.generate_api_key(UUID("10101010-1010-1010-1010-101010101010"), UUID("55555555-5555-5555-5555-555555555555"))

        self.mock_logger.error.assert_called_with(
            "Error generating API key for partner_id=10101010-1010-1010-1010-101010101010: Unexpected Error"
        )

    # ------------------------------------------------------------------------
    # validate_api_key
    # ------------------------------------------------------------------------
    async def test_validate_api_key_success(self):
        """Test successful API key validation."""
        mock_api_key = ApiKey(id= UUID("11111111-1111-1111-1111-111111111111"), key="test123", is_active=True)

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
        mock_api_key = ApiKey(id= UUID("22222222-2222-2222-2222-222222222222"), partner_id= UUID("10101010-1010-1010-1010-101010101010"), is_active=True)

        mock_scalars = MagicMock()
        mock_scalars.first.return_value = mock_api_key
        mock_execute = MagicMock()
        mock_execute.scalars.return_value = mock_scalars
        self.session.execute = AsyncMock(return_value=mock_execute)

        result = await self.api_key_repository.get_active_api_key(UUID("10101010-1010-1010-1010-101010101010"))

        assert result == mock_api_key
        self.mock_logger.info.assert_any_call(
            "Successfully fetched active API key for partner_id: 10101010-1010-1010-1010-101010101010"
        )

    async def test_get_active_api_key_not_found(self):
        """Test get_active_api_key returns None if no key is found."""
        mock_scalars = MagicMock()
        mock_scalars.first.return_value = None
        mock_execute = MagicMock()
        mock_execute.scalars.return_value = mock_scalars
        self.session.execute = AsyncMock(return_value=mock_execute)

        result = await self.api_key_repository.get_active_api_key(UUID("99999999-9999-9999-9999-999999999999"))
        assert result is None
        self.mock_logger.info.assert_any_call(
            "Attempting to fetch active API key for partner_id: 99999999-9999-9999-9999-999999999999"
        )

    async def test_get_active_api_key_exception(self):
        """Test exception handling in get_active_api_key."""
        self.session.execute = AsyncMock(side_effect=Exception("DB error"))

        with pytest.raises(Exception, match="DB error"):
            await self.api_key_repository.get_active_api_key(UUID("10101010-1010-1010-1010-101010101010"))

        self.mock_logger.error.assert_called_with(
            "Error fetching API key for partner_id=10101010-1010-1010-1010-101010101010: DB error"
        )

    # ------------------------------------------------------------------------
    # inactivate_api_key
    # ------------------------------------------------------------------------
    async def test_inactivate_api_key_success(self):
        """Test successful inactivation of API key."""
        mock_api_key = ApiKey(id= UUID("33333333-3333-3333-3333-333333333333"), partner_id= UUID("20202020-2020-2020-2020-202020202020"), is_active=False)

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_api_key
        self.session.execute = AsyncMock(return_value=mock_result)
        self.session.commit = AsyncMock()

        result = await self.api_key_repository.inactivate_api_key(UUID("20202020-2020-2020-2020-202020202020"), UUID("55555555-5555-5555-5555-555555555555"))

        assert result is True
        self.session.commit.assert_awaited()
        self.mock_logger.info.assert_any_call(
            "API key for partner_id=20202020-2020-2020-2020-202020202020 successfully inactivated by user_id=55555555-5555-5555-5555-555555555555"
        )

    async def test_inactivate_api_key_not_found(self):
        """Test inactivate_api_key returns None when no active key found."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        self.session.execute = AsyncMock(return_value=mock_result)

        result = await self.api_key_repository.inactivate_api_key(UUID("30303030-3030-3030-3030-303030303030"), UUID("77777777-7777-7777-7777-777777777777"))

        assert result is False
        self.mock_logger.warning.assert_called_with(
            "No active API key found for partner_id=30303030-3030-3030-3030-303030303030"
        )

    async def test_inactivate_api_key_exception(self):
        """Test exception handling in inactivate_api_key."""
        self.session.execute = AsyncMock(side_effect=Exception("Update failed"))

        with pytest.raises(Exception, match="Update failed"):
            await self.api_key_repository.inactivate_api_key(UUID("10101010-1010-1010-1010-101010101010"), UUID("11111111-1111-1111-1111-111111111111"))

        self.mock_logger.error.assert_called_with(
            "Unexpected error while inactivating API key for partner_id=10101010-1010-1010-1010-101010101010: Update failed"
        )
