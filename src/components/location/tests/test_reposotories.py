from uuid import UUID
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.components.location.models import Cities, Countries, States
from src.components.location.repositories import LocationRepository


class MockRow:
    """Mock object that behaves like a SQLAlchemy Row for dict conversion."""
    def __init__(self, **kwargs):
        self._data = kwargs
    
    def keys(self):
        return self._data.keys()
    
    def __iter__(self):
        return iter(self._data.items())
    
    def __getitem__(self, key):
        return self._data[key]


@pytest.mark.asyncio
class TestLocationRepository:

    @pytest.fixture(autouse=True)
    def setup_class(self, mock_session_factory, mock_logger):
        """Set up the repository using fixtures for mock session and logger."""
        self.location_repository = LocationRepository(
            session_factory=mock_session_factory, console_service_logger=mock_logger
        )
        self.session = mock_session_factory.return_value.__aenter__.return_value
        self.mock_logger = mock_logger

    async def test_get_all_countries(self):
        """Test fetching all countries without a search filter."""
        # Mock the database response - needs to mimic result.mappings().all()
        mock_mappings = MagicMock()
        mock_mappings.all.return_value = [MockRow(id= UUID("11111111-1111-1111-1111-111111111111"), name="India", slug="india")]
        mock_execute = MagicMock()
        mock_execute.mappings.return_value = mock_mappings
        self.session.execute = AsyncMock(return_value=mock_execute)

        result = await self.location_repository.get_all_countries(search_by="")

        assert len(result) == 1
        assert result[0]["id"] == UUID("11111111-1111-1111-1111-111111111111")
        assert result[0]["name"] == "India"
        self.mock_logger.info.assert_called_with(
            "Attempting Fetching all countries from database"
        )

    async def test_get_all_countries_with_search(self):
        """Test fetching countries with a search filter."""
        # Mock the database response - needs to mimic result.mappings().all()
        mock_mappings = MagicMock()
        mock_mappings.all.return_value = [MockRow(id= UUID("11111111-1111-1111-1111-111111111111"), name="India", slug="india")]
        mock_execute = MagicMock()
        mock_execute.mappings.return_value = mock_mappings
        self.session.execute = AsyncMock(return_value=mock_execute)

        result = await self.location_repository.get_all_countries(search_by="Ind")

        assert len(result) == 1
        assert result[0]["id"] == UUID("11111111-1111-1111-1111-111111111111")
        assert result[0]["name"] == "India"
        self.mock_logger.info.assert_called_with(
            "Attempting Fetching all countries from database"
        )

    async def test_get_states_by_country(self):
        """Test fetching states for a given country."""
        # Mock the database response - needs to mimic result.mappings().all()
        mock_mappings = MagicMock()
        mock_mappings.all.return_value = [MockRow(id= UUID("11111111-1111-1111-1111-111111111111"), name="Maharashtra", slug="maharashtra")]
        mock_execute = MagicMock()
        mock_execute.mappings.return_value = mock_mappings
        self.session.execute = AsyncMock(return_value=mock_execute)

        result, total_count = await self.location_repository.get_states_by_country(
            country_id= UUID("11111111-1111-1111-1111-111111111111"), search_by=""
        )

        assert len(result) == 1
        assert result[0]["id"] == UUID("11111111-1111-1111-1111-111111111111")
        assert result[0]["name"] == "Maharashtra"
        assert total_count == 1

    async def test_get_states_by_country_with_search(self):
        """Test fetching states with a search filter."""
        # Mock the database response - needs to mimic result.mappings().all()
        mock_mappings = MagicMock()
        mock_mappings.all.return_value = [MockRow(id= UUID("11111111-1111-1111-1111-111111111111"), name="Maharashtra", slug="maharashtra")]
        mock_execute = MagicMock()
        mock_execute.mappings.return_value = mock_mappings
        self.session.execute = AsyncMock(return_value=mock_execute)

        result, total_count = await self.location_repository.get_states_by_country(
            country_id= UUID("11111111-1111-1111-1111-111111111111"), search_by="Maha"
        )

        assert len(result) == 1
        assert result[0]["id"] == UUID("11111111-1111-1111-1111-111111111111")
        assert result[0]["name"] == "Maharashtra"
        assert total_count == 1

    async def test_get_cities_by_state(self):
        """Test fetching cities for a given state."""
        # Mock the database response - needs to mimic result.mappings().all()
        mock_mappings = MagicMock()
        mock_mappings.all.return_value = [MockRow(id= UUID("11111111-1111-1111-1111-111111111111"), name="Mumbai", slug="mumbai")]
        mock_execute = MagicMock()
        mock_execute.mappings.return_value = mock_mappings
        self.session.execute = AsyncMock(return_value=mock_execute)

        result, total_count = await self.location_repository.get_cities_by_state(
            state_id= UUID("11111111-1111-1111-1111-111111111111"), search_by="Mum"
        )

        assert len(result) == 1
        assert result[0]["id"] == UUID("11111111-1111-1111-1111-111111111111")
        assert result[0]["name"] == "Mumbai"
        assert total_count == 1

    async def test_get_all_countries_exception(self):
        """Test handling exception in get_all_countries."""
        self.session.execute = AsyncMock(side_effect=Exception("Database error"))

        with pytest.raises(Exception, match="Database error"):
            await self.location_repository.get_all_countries(search_by="")

        self.mock_logger.error.assert_called_with(
            "Error fetching countries: Database error"
        )

    async def test_get_states_by_country_exception(self):
        """Test handling exception in get_states_by_country."""
        self.session.execute = AsyncMock(side_effect=Exception("Database error"))

        with pytest.raises(Exception, match="Database error"):
            await self.location_repository.get_states_by_country(
                country_id= UUID("11111111-1111-1111-1111-111111111111"), search_by=""
            )

        self.mock_logger.error.assert_called_with(
            "Error fetching states: Database error"
        )

    async def test_get_cities_by_state_exception(self):
        """Test handling exception in get_cities_by_state."""
        self.session.execute = AsyncMock(side_effect=Exception("Unexpected error"))

        with pytest.raises(Exception, match="Unexpected error"):
            await self.location_repository.get_cities_by_state(state_id= UUID("11111111-1111-1111-1111-111111111111"), search_by="")

        self.mock_logger.error.assert_called_with(
            "Unexpected error fetching cities: Unexpected error"
        )

    async def test_is_country_exists_found(self):
        """Test if a country exists (returns True)."""
        mock_result = MagicMock()
        mock_result.scalar.return_value = 1  # Simulate country ID found
        self.session.execute = AsyncMock(return_value=mock_result)

        result = await self.location_repository.is_country_exists(country_id= UUID("11111111-1111-1111-1111-111111111111"))

        assert result is True

    async def test_is_country_exists_not_found(self):
        """Test if a country does not exist (returns False)."""
        mock_result = MagicMock()
        mock_result.scalar.return_value = None
        self.session.execute = AsyncMock(return_value=mock_result)

        result = await self.location_repository.is_country_exists(country_id= UUID("99999999-9999-9999-9999-999999999999"))

        assert result is False

    async def test_is_country_exists_exception(self):
        """Test exception handling in is_country_exists."""
        self.session.execute = AsyncMock(side_effect=Exception("Database error"))

        with pytest.raises(Exception, match="Database error"):
            await self.location_repository.is_country_exists(country_id= UUID("11111111-1111-1111-1111-111111111111"))

    async def test_is_state_exists_found(self):
        """Test if a state exists (returns True)."""
        mock_result = MagicMock()
        mock_result.scalar.return_value = 1
        self.session.execute = AsyncMock(return_value=mock_result)

        result = await self.location_repository.is_state_exists(state_id= UUID("11111111-1111-1111-1111-111111111111"))

        assert result is True

    async def test_is_state_exists_not_found(self):
        """Test if a state does not exist (returns False)."""
        mock_result = MagicMock()
        mock_result.scalar.return_value = None
        self.session.execute = AsyncMock(return_value=mock_result)

        result = await self.location_repository.is_state_exists(state_id= UUID("99999999-9999-9999-9999-999999999999"))

        assert result is False

    async def test_is_state_exists_exception(self):
        """Test exception handling in is_state_exists."""
        self.session.execute = AsyncMock(side_effect=Exception("Database error"))

        with pytest.raises(Exception, match="Database error"):
            await self.location_repository.is_state_exists(state_id= UUID("11111111-1111-1111-1111-111111111111"))

    async def test_get_state_by_id(self):
        """Test fetching a state by ID."""
        # Arrange
        mock_state = MagicMock(id= UUID("11111111-1111-1111-1111-111111111111"), country_id= UUID("17417417-4174-1741-7417-417417417417"))
        mock_result = MagicMock()
        mock_result.scalar.return_value = mock_state
        self.session.execute = AsyncMock(return_value=mock_result)

        # Act
        result = await self.location_repository.get_state_by_id(1)

        # Assert
        assert result == mock_state
        self.mock_logger.info.assert_called_with(
            "Attempting fetching cities for state_id: 11111111-1111-1111-1111-111111111111"
        )

    async def test_get_city_by_id_success(self):
        """Test fetching a city by ID."""
        # Arrange
        mock_city = MagicMock(id= UUID("22222222-2222-2222-2222-222222222222"), state_id= UUID("11111111-1111-1111-1111-111111111111"))
        mock_result = MagicMock()
        mock_result.scalar.return_value = mock_city
        self.session.execute = AsyncMock(return_value=mock_result)

        # Act
        result = await self.location_repository.get_city_by_id(2)

        # Assert
        assert result == mock_city
        self.mock_logger.info.assert_called_with(
            "Attempting fetching cities for state_id: 11111111-1111-1111-1111-111111111111"
        )

    async def test_get_state_by_id_exception(self):
        """Test exception handling in get_state_by_id."""
        # Arrange
        self.session.execute = AsyncMock(side_effect=Exception("Database error"))

        # Act & Assert
        with pytest.raises(Exception, match="Database error"):
            await self.location_repository.get_state_by_id(1)

        self.mock_logger.error.assert_called_with(
            "Error fetching state by ID: Database error"
        )

    async def test_get_city_by_id_exception(self):
        """Test exception handling in get_city_by_id."""
        # Arrange
        self.session.execute = AsyncMock(side_effect=Exception("Database error"))

        # Act & Assert
        with pytest.raises(Exception, match="Database error"):
            await self.location_repository.get_city_by_id(2)

        self.mock_logger.error.assert_called_with(
            "Error fetching city by ID: Database error"
        )
