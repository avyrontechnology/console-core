from typing import Any, List, Optional, Tuple  

from src.components.cache import TTL
from src.components.cache import Keys as CacheKeys
from src.components.cache.helper import CacheHelper
from src.components.location.errors import (
    CityNotFoundError,
    CountryNotFoundError,
    StateNotFoundError,
)
from src.components.location.models import Cities, Countries, States
from src.components.location.repositories import LocationRepository
from src.components.location.schemas import (
    CityPaginatedResponse,
    CityResponse,
    CountryResponse,
    StatePaginatedResponse,
    StateResponse,
)
from src.loggers.console_service_logger import ConsoleServiceLogger


class LocationService:
    def __init__(
        self,
        location_repository: LocationRepository,
        console_service_logger: ConsoleServiceLogger,
        console_service_cache: CacheHelper,
    ) -> None:
        self.__repository: LocationRepository = location_repository
        self.__console_service_logger: ConsoleServiceLogger = console_service_logger
        self.__console_service_cache: CacheHelper = console_service_cache

    async def get_countries(self, search_by: str) -> List[CountryResponse]:
        try:
            self.__console_service_logger.info("Attempting fetching all countries.")

            if not search_by:
                cached_data: Any = await self.__console_service_cache.get_cache(
                    key=CacheKeys.COUNTRIES
                )
                if cached_data:
                    self.__console_service_logger.info("Found cached data of all countries.")
                    return [
                        CountryResponse.model_validate(country)  # ← restored
                        for country in cached_data
                    ]

            countries: List[dict] = await self.__repository.get_all_countries(search_by)

            if not search_by:
                await self.__console_service_cache.set_cache(
                    key=CacheKeys.COUNTRIES,
                    value=countries,
                    ttl=TTL.ONE_WEEK,
                )

            return [CountryResponse.model_validate(c) for c in countries]  # ← restored
        except Exception as ex:
            self.__console_service_logger.error(
                "Unexpected error fetching countries: {}".format(str(ex))
            )
            raise ex

    async def get_states_by_country(
        self,
        country_id: Optional[int],
        search_by: str,
        limit: Optional[int] = None,   
        offset: Optional[int] = None,  
    ) -> StatePaginatedResponse:      
        try:
            self.__console_service_logger.info(
                "Attempting fetching states for country_id: {}".format(
                    country_id or "all"
                )
            )

            if country_id and not await self.is_country_exists(country_id):
                raise CountryNotFoundError(country_id)

            is_paginated: bool = limit is not None and offset is not None
            cache_key: str = CacheKeys.STATES.format(country_id or "")

            if not search_by and not is_paginated:  
                cached_data = await self.__console_service_cache.get_cache(
                    key=cache_key
                )
                if cached_data:
                    self.__console_service_logger.info(
                        "Found cached data of states for country_id: {}".format(
                            country_id or "all"
                        )
                    )
                    state_list: List[dict] = [
                        StateResponse.model_validate(state) for state in cached_data
                    ]
                    return StatePaginatedResponse(
                        total_count=len(state_list),
                        limit=None,
                        offset=None,
                        data=state_list,
                    )

            states, total_count = await self.__repository.get_states_by_country(
                country_id, search_by, limit, offset
            )

            if not search_by and not is_paginated:  
                await self.__console_service_cache.set_cache(
                    key=cache_key,
                    value=states,
                    ttl=TTL.ONE_WEEK,
                )

            return StatePaginatedResponse(
                total_count=total_count,
                limit=limit,
                offset=offset,
                data=[StateResponse.model_validate(state) for state in states],
            )
        except Exception as ex:
            self.__console_service_logger.error(
                "Unexpected error fetching states: {}".format(str(ex))
            )
            raise ex
 

    async def get_cities_by_state(
        self,
        state_id: int,
        search_by: str,
        limit: Optional[int] = None,  
        offset: Optional[int] = None, 
    ) -> CityPaginatedResponse:
        try:
            self.__console_service_logger.info(
                "Attempting fetching cities for state_id: {}".format(state_id)
            )

            if state_id and not await self.is_state_exists(state_id):
                raise StateNotFoundError(state_id)

            is_paginated: bool = limit is not None and offset is not None
            cache_key: str = CacheKeys.CITIES.format(state_id or "")

            if not search_by and not is_paginated:  
                cached_data = await self.__console_service_cache.get_cache(
                    key=cache_key
                )
                if cached_data:
                    self.__console_service_logger.info(
                        "Found cached data of states for country_id: {}".format(
                            state_id or "all"
                        )
                    )

                    city_list: List[dict] = [CityResponse.model_validate(city) for city in cached_data]
                    return CityPaginatedResponse(
                        total_count=len(city_list),
                        limit=None,
                        offset=None,
                        data=city_list,
                    )

            cities, total_count = await self.__repository.get_cities_by_state(
                state_id, search_by, limit, offset
            )

            if not search_by and not is_paginated:  
                await self.__console_service_cache.set_cache(
                    key=cache_key,
                    value=cities,
                    ttl=TTL.ONE_WEEK,
                )

            return CityPaginatedResponse(
                total_count=total_count,
                limit=limit,
                offset=offset,
                data=[CityResponse.model_validate(city) for city in cities],
            )
        except Exception as ex:
            self.__console_service_logger.error(
                "Unexpected error fetching cities: {}".format(str(ex))
            )
            raise ex

    async def is_country_exists(self, country_id: int) -> bool:
        try:
            exists: bool = await self.__repository.is_country_exists(country_id)
            return exists
        except Exception as ex:
            self.__console_service_logger.error(
                "Error checking country availability: {}".format(str(ex))
            )
            raise ex

    async def is_state_exists(self, state_id: int) -> bool:
        try:
            exists: bool = await self.__repository.is_state_exists(state_id)
            return exists
        except Exception as ex:
            self.__console_service_logger.error(
                "Error checking state availability: {}".format(str(ex))
            )
            raise ex

    async def validate_location_hierarchy(
        self, country_id: int, state_id: int, city_id: int
    ) -> None:
        """
        Validation method to ensure the hierarchy of country, state, and city is correct.
        """
        try:
            self.__console_service_logger.info(
                "Validating location hierarchy for country_id: {}, state_id: {}, city_id: {}".format(
                    country_id, state_id, city_id
                )
            )
            if not await self.is_country_exists(country_id):
                raise CountryNotFoundError(country_id)

            state: States = await self.__repository.get_state_by_id(state_id)
            if not state or state.country_id != country_id:
                raise StateNotFoundError(state_id)

            city: Cities = await self.__repository.get_city_by_id(city_id)
            if not city or city.state_id != state_id:
                raise CityNotFoundError(city_id)
        except CountryNotFoundError as exec:
            self.__console_service_logger.error(
                "Country not found: {}".format(str(exec))
            )
            raise exec
        except StateNotFoundError as exec:
            self.__console_service_logger.error("State not found: {}".format(str(exec)))
            raise exec
        except CityNotFoundError as exec:
            self.__console_service_logger.error("City not found: {}".format(str(exec)))
            raise exec
        except Exception as ex:
            self.__console_service_logger.error(
                "Error validating location hierarchy: {}".format(str(ex))
            )
            raise ex
