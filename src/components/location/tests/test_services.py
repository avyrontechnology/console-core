from uuid import UUID
from unittest.mock import AsyncMock

import pytest

from src.components.cache import TTL
from src.components.cache import Keys as CacheKeys
from src.components.cache.helper import CacheHelper
from src.components.location.errors import (
    CityNotFoundError,
    CountryNotFoundError,
    StateNotFoundError,
)
from src.components.location.schemas import CityResponse, CountryResponse, StateResponse
from src.components.location.services import LocationService
from src.loggers.console_service_logger import ConsoleServiceLogger


@pytest.mark.asyncio
class TestLocationService:

    @pytest.fixture(autouse=True)
    def setup_class(self):
        self.logger_mock = AsyncMock(spec=ConsoleServiceLogger)
        self.location_repository_mock = AsyncMock()
        self.console_service_cache = AsyncMock(spec=CacheHelper)
        self.location_service = LocationService(
            location_repository=self.location_repository_mock,
            console_service_logger=self.logger_mock,
            console_service_cache=self.console_service_cache,
        )

        self.country_id= UUID("11111111-1111-1111-1111-111111111111")
        self.state_id= UUID("11111111-1111-1111-1111-111111111111")
        self.city_id= UUID("11111111-1111-1111-1111-111111111111")
        self.country_response = CountryResponse(
            id=self.country_id, name="India", slug="india"
        )
        self.state_response = StateResponse(
            id=self.state_id, name="Maharashtra", slug="maharashtra"
        )
        self.city_response = CityResponse(id= UUID("11111111-1111-1111-1111-111111111111"), name="Mumbai", slug="mumbai")

    async def test_get_countries_success(self):
        self.location_repository_mock.get_all_countries.return_value = [
            self.country_response
        ]
        countries = await self.location_service.get_countries(search_by="India")

        assert len(countries) > 0
        assert countries[0].name == "India"
        self.logger_mock.info.assert_called_with("Attempting fetching all countries.")

    async def test_get_states_by_country_success(self):
        self.location_repository_mock.get_states_by_country.return_value = (
        [self.state_response], 1  # Return tuple (states, total_count)
        )
        self.location_repository_mock.is_country_exists.return_value = True

        response = await self.location_service.get_states_by_country(
            self.country_id, search_by="Maharashtra"
        )

        assert response.total_count == 1
        assert len(response.data) > 0
        assert response.data[0].name == "Maharashtra"
        self.logger_mock.info.assert_called_with(
            f"Attempting fetching states for country_id: {self.country_id}"
        )

    async def test_get_cities_by_state_success(self):
        self.location_repository_mock.get_cities_by_state.return_value = (
        [self.city_response], 1  # Return tuple (cities, total_count)
        )
        self.location_repository_mock.is_state_exists.return_value = True

        response = await self.location_service.get_cities_by_state(
            self.state_id, search_by="Mumbai"
        )

        assert response.total_count == 1
        assert len(response.data) > 0
        assert response.data[0].name == "Mumbai"
        self.logger_mock.info.assert_called_with(
            f"Attempting fetching cities for state_id: {self.state_id}"
        )


    async def test_get_states_by_country_not_found(self):
        self.location_repository_mock.is_country_exists.return_value = False

        with pytest.raises(CountryNotFoundError):
            await self.location_service.get_states_by_country(
                self.country_id, search_by="Maharashtra"
            )

    async def test_get_cities_by_state_not_found(self):
        self.location_repository_mock.is_state_exists.return_value = False

        with pytest.raises(StateNotFoundError):
            await self.location_service.get_cities_by_state(
                self.state_id, search_by="Mumbai"
            )

    async def test_get_countries_exception(self):
        self.location_repository_mock.get_all_countries.side_effect = Exception(
            "Database error"
        )

        with pytest.raises(Exception, match=r".*Database error.*"):
            await self.location_service.get_countries(search_by="India")

        self.logger_mock.error.assert_called_with(
            "Unexpected error fetching countries: Database error"
        )

    async def test_get_states_by_country_exception(self):
        self.location_repository_mock.get_states_by_country.side_effect = Exception(
            "Database error"
        )

        with pytest.raises(Exception, match=r".*Database error.*"):
            await self.location_service.get_states_by_country(
                self.country_id, search_by="Maharashtra"
            )

        self.logger_mock.error.assert_called_with(
            "Unexpected error fetching states: Database error"
        )

    async def test_get_cities_by_state_exception(self):
        self.location_repository_mock.get_cities_by_state.side_effect = Exception(
            "Database error"
        )

        with pytest.raises(Exception, match=r".*Database error.*"):
            await self.location_service.get_cities_by_state(
                self.state_id, search_by="Mumbai"
            )

        self.logger_mock.error.assert_called_with(
            "Unexpected error fetching cities: Database error"
        )

    async def test_is_country_exists_success(self):
        self.location_repository_mock.is_country_exists.return_value = True
        exists = await self.location_service.is_country_exists(self.country_id)
        assert exists is True

    async def test_is_country_exists_failure(self):
        self.location_repository_mock.is_country_exists.return_value = False
        exists = await self.location_service.is_country_exists(self.country_id)
        assert exists is False

    async def test_is_country_exists_exception(self):
        self.location_repository_mock.is_country_exists.side_effect = Exception(
            "Database error"
        )

        with pytest.raises(Exception, match=r".*Database error.*"):
            await self.location_service.is_country_exists(self.country_id)

        self.logger_mock.error.assert_called_with(
            "Error checking country availability: Database error"
        )

    async def test_is_state_exists_success(self):
        self.location_repository_mock.is_state_exists.return_value = True
        exists = await self.location_service.is_state_exists(self.state_id)
        assert exists is True

    async def test_is_state_exists_failure(self):
        self.location_repository_mock.is_state_exists.return_value = False
        exists = await self.location_service.is_state_exists(self.state_id)
        assert exists is False

    async def test_is_state_exists_exception(self):
        self.location_repository_mock.is_state_exists.side_effect = Exception(
            "Database error"
        )

        with pytest.raises(Exception, match=r".*Database error.*"):
            await self.location_service.is_state_exists(self.state_id)

        self.logger_mock.error.assert_called_with(
            "Error checking state availability: Database error"
        )

    async def test_validate_location_hierarchy_success(self):
        """Test successful validation when hierarchy is correct."""
        self.location_repository_mock.get_state_by_id.return_value = AsyncMock(
            country_id=self.country_id
        )
        self.location_repository_mock.get_city_by_id.return_value = AsyncMock(
            state_id=self.state_id
        )
        self.location_service.is_country_exists = AsyncMock(return_value=True)

        await self.location_service.validate_location_hierarchy(
            self.country_id, self.state_id, self.city_id
        )

        self.logger_mock.info.assert_called_with(
            f"Validating location hierarchy for country_id: {self.country_id}, state_id: {self.state_id}, city_id: {self.city_id}"
        )

    async def test_validate_location_hierarchy_country_not_found(self):
        """Test validation failure when country is not found."""
        self.location_service.is_country_exists = AsyncMock(return_value=False)

        with pytest.raises(CountryNotFoundError):
            await self.location_service.validate_location_hierarchy(
                self.country_id, self.state_id, self.city_id
            )

        self.logger_mock.error.assert_called_with(
            "Country not found: Country not found, id: 11111111-1111-1111-1111-111111111111"
        )

    async def test_validate_location_hierarchy_state_not_found(self):
        """Test validation failure when state is not found or belongs to a different country."""
        self.location_service.is_country_exists = AsyncMock(return_value=True)
        self.location_repository_mock.get_state_by_id.return_value = (
            None  # State does not exist
        )

        with pytest.raises(StateNotFoundError):
            await self.location_service.validate_location_hierarchy(
                self.country_id, self.state_id, self.city_id
            )

        self.logger_mock.error.assert_called_with(
            "State not found: State not found, id: 11111111-1111-1111-1111-111111111111"
        )

    async def test_validate_location_hierarchy_city_not_found(self):
        """Test validation failure when city is not found or belongs to a different state."""
        self.location_service.is_country_exists = AsyncMock(return_value=True)
        self.location_repository_mock.get_state_by_id.return_value = AsyncMock(
            country_id=self.country_id
        )
        self.location_repository_mock.get_city_by_id.return_value = (
            None  # City does not exist
        )

        with pytest.raises(CityNotFoundError):
            await self.location_service.validate_location_hierarchy(
                self.country_id, self.state_id, self.city_id
            )

        self.logger_mock.error.assert_called_with(
            "City not found: City not found, id: 11111111-1111-1111-1111-111111111111"
        )

    @pytest.mark.asyncio
    async def test_get_countries_from_cache(self, setup_class):
        """Test retrieving countries from cache when no search term is provided."""
        self.console_service_cache.get_cache.return_value = [self.country_response]
        countries = await self.location_service.get_countries(search_by="")

        assert len(countries) > 0
        assert countries[0].name == "India"
        self.logger_mock.info.assert_called_with("Found cached data of all countries.")
        self.location_repository_mock.get_all_countries.assert_not_called()
        self.console_service_cache.get_cache.assert_called_with(key=CacheKeys.COUNTRIES)

    @pytest.mark.asyncio
    async def test_get_countries_cache_miss(self, setup_class):
        """Test fetching countries from repository and caching when cache is empty."""
        self.console_service_cache.get_cache.return_value = None
        self.location_repository_mock.get_all_countries.return_value = [
            self.country_response
        ]

        countries = await self.location_service.get_countries(search_by="")

        assert len(countries) > 0
        assert countries[0].name == "India"
        self.console_service_cache.set_cache.assert_called_with(
            key=CacheKeys.COUNTRIES,
            value=[self.country_response],
            ttl=TTL.ONE_WEEK,
        )
        self.location_repository_mock.get_all_countries.assert_called_with("")

    @pytest.mark.asyncio
    async def test_get_countries_no_cache_with_search(self, setup_class):
        """Test bypassing cache when search term is provided."""
        self.location_repository_mock.get_all_countries.return_value = [
            self.country_response
        ]

        countries = await self.location_service.get_countries(search_by="India")

        assert len(countries) > 0
        assert countries[0].name == "India"
        self.console_service_cache.get_cache.assert_not_called()
        self.console_service_cache.set_cache.assert_not_called()
        self.location_repository_mock.get_all_countries.assert_called_with("India")

    @pytest.mark.asyncio
    async def test_get_states_by_country_from_cache(self, setup_class):
        """Test retrieving states from cache when no search term is provided."""
        cache_key = CacheKeys.STATES.format(self.country_id)
        self.location_repository_mock.is_country_exists.return_value = True
        self.console_service_cache.get_cache.return_value = [self.state_response]

        response = await self.location_service.get_states_by_country(
            self.country_id, search_by=""
        )

        # Fix: Check response.data instead of using len() directly
        assert len(response.data) > 0
        assert response.data[0].name == "Maharashtra"
        self.logger_mock.info.assert_called_with(
            f"Found cached data of states for country_id: {self.country_id}"
        )
        self.location_repository_mock.get_states_by_country.assert_not_called()
        self.console_service_cache.get_cache.assert_called_with(key=cache_key)

    @pytest.mark.asyncio
    async def test_get_states_by_country_cache_miss(self, setup_class):
        """Test fetching states from repository and caching when cache is empty."""
        cache_key = CacheKeys.STATES.format(self.country_id)
        self.location_repository_mock.is_country_exists.return_value = True
        self.console_service_cache.get_cache.return_value = None
        # Fix: Return a tuple instead of just a list
        self.location_repository_mock.get_states_by_country.return_value = (
            [self.state_response], 1
        )

        response = await self.location_service.get_states_by_country(
            self.country_id, search_by=""
        )

        # Fix: Check response.data instead of using len() directly
        assert len(response.data) > 0
        assert response.data[0].name == "Maharashtra"
        self.console_service_cache.set_cache.assert_called_with(
            key=cache_key,
            value=[self.state_response],
            ttl=TTL.ONE_WEEK,
        )
        self.location_repository_mock.get_states_by_country.assert_called_with(
            self.country_id, "", None, None
        )

    @pytest.mark.asyncio
    async def test_get_states_by_country_no_cache_with_search(self, setup_class):
        """Test bypassing cache for states when search term is provided."""
        self.location_repository_mock.is_country_exists.return_value = True
        self.location_repository_mock.get_states_by_country.return_value = (
            [self.state_response], 1
        )

        response = await self.location_service.get_states_by_country(
            self.country_id, search_by="Maharashtra"
        )

        assert response.total_count == 1
        assert len(response.data) > 0
        assert response.data[0].name == "Maharashtra"
        self.console_service_cache.get_cache.assert_not_called()
        self.console_service_cache.set_cache.assert_not_called()
        self.location_repository_mock.get_states_by_country.assert_called_with(
            self.country_id, "Maharashtra", None, None
        )

    @pytest.mark.asyncio
    async def test_get_cities_by_state_from_cache(self, setup_class):
        """Test retrieving cities from cache when no search term is provided."""
        cache_key = CacheKeys.CITIES.format(self.state_id)
        self.location_repository_mock.is_state_exists.return_value = True
        self.console_service_cache.get_cache.return_value = [self.city_response]

        response = await self.location_service.get_cities_by_state(
            self.state_id, search_by=""
        )

        assert response.total_count > 0
        assert len(response.data) > 0
        assert response.data[0].name == "Mumbai"
        self.logger_mock.info.assert_called_with(
            f"Found cached data of states for country_id: {self.state_id}"
        )
        self.location_repository_mock.get_cities_by_state.assert_not_called()
        self.console_service_cache.get_cache.assert_called_with(key=cache_key)

    @pytest.mark.asyncio
    async def test_get_cities_by_state_no_cache_with_search(self, setup_class):
        """Test bypassing cache for cities when search term is provided."""
        self.location_repository_mock.is_state_exists.return_value = True
        self.location_repository_mock.get_cities_by_state.return_value = (
            [self.city_response], 1
        )

        response = await self.location_service.get_cities_by_state(
            self.state_id, search_by="Mumbai"
        )

        assert response.total_count == 1
        assert len(response.data) > 0
        assert response.data[0].name == "Mumbai"
        self.console_service_cache.get_cache.assert_not_called()
        self.console_service_cache.set_cache.assert_not_called()
        self.location_repository_mock.get_cities_by_state.assert_called_with(
            self.state_id, "Mumbai", None, None
        )

    @pytest.mark.asyncio
    async def test_get_cities_by_state_cache_miss(self, setup_class):
        """Test fetching cities from repository and caching when cache is empty."""
        cache_key = CacheKeys.CITIES.format(self.state_id)
        self.location_repository_mock.is_state_exists.return_value = True
        self.console_service_cache.get_cache.return_value = None
        self.location_repository_mock.get_cities_by_state.return_value = (
            [self.city_response], 1
        )

        response = await self.location_service.get_cities_by_state(
            self.state_id, search_by=""
        )

        assert response.total_count == 1
        assert len(response.data) > 0
        assert response.data[0].name == "Mumbai"
        self.console_service_cache.set_cache.assert_called_with(
            key=cache_key,
            value=[self.city_response],
            ttl=TTL.ONE_WEEK,
        )
        self.location_repository_mock.get_cities_by_state.assert_called_with(
            self.state_id, "", None, None
        )
