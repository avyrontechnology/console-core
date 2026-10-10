from contextlib import AbstractContextManager
from typing import Callable, List, Optional, Tuple 

from sqlalchemy import func, select 
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from src.components.location.models import Cities, Countries, States
from src.loggers.console_service_logger import ConsoleServiceLogger


class LocationRepository:
    def __init__(
        self,
        session_factory: Callable[..., AbstractContextManager[AsyncSession]],
        console_service_logger: ConsoleServiceLogger,
    ) -> None:
        self.__session_factory: Callable[..., AbstractContextManager[AsyncSession]] = (
            session_factory
        )
        self.__console_service_logger: ConsoleServiceLogger = console_service_logger

    async def get_all_countries(self, search_by: str) -> List[dict]:
        """
        Returns plain dicts instead of ORM objects — avoids model_validate overhead
        and detached-instance issues after session closes.
        Only selects the 3 columns actually used in CountryResponse.
        """
        try:
            async with self.__session_factory() as session:
                self.__console_service_logger.info(
                    "Attempting Fetching all countries from database"
                )
                query = (
                    select(Countries.id, Countries.name, Countries.slug)
                    .order_by(Countries.name)
                )
                if search_by:
                    query = query.where(Countries.name.ilike(f"%{search_by}%"))

                result = await session.execute(query)
                return [dict(row) for row in result.mappings().all()]
        except Exception as ex:
            self.__console_service_logger.error(
                "Error fetching countries: {}".format(str(ex))
            )
            raise ex

    async def get_states_by_country(
        self,
        country_id: Optional[int],
        search_by: str,
        limit: Optional[int] = None,
        offset: Optional[int] = None,
    ) -> Tuple[List[dict], int]:
        try:
            async with self.__session_factory() as session:
                self.__console_service_logger.info(
                    "Attempting fetching states for country_id: {}".format(country_id)
                )
                query = select(States.id, States.name, States.slug).order_by(
                    States.name
                )
                if country_id is not None:
                    query = query.where(States.country_id == country_id)
                if search_by:
                    query = query.where(States.name.ilike(f"%{search_by}%"))

                is_paginated: bool = limit is not None and offset is not None

                if is_paginated:
                    query_with_count = query.add_columns(
                        func.count().over().label("total_count")
                    )
                    row_offset = (offset - 1) * limit
                    query_with_count = query_with_count.offset(row_offset).limit(limit)

                    result = await session.execute(query_with_count)
                    rows = result.mappings().all()

                    if not rows:
                        return [], 0

                    total_count = rows[0]["total_count"]
                    states = [
                        {"id": r["id"], "name": r["name"], "slug": r["slug"]}
                        for r in rows
                    ]
                    return states, total_count
                else:
                    result = await session.execute(query)
                    states = [dict(row) for row in result.mappings().all()]
                    return states, len(states)

        except Exception as ex:
            self.__console_service_logger.error(f"Error fetching states: {str(ex)}")
            raise ex
   
    async def get_cities_by_state(
        self,
        state_id: Optional[int],
        search_by: str,
        limit: Optional[int] = None,
        offset: Optional[int] = None,
    ) -> Tuple[List[dict], int]:
        try:
            async with self.__session_factory() as session:
                self.__console_service_logger.info(
                    "Attempting fetching cities for state_id: {}".format(state_id)
                )
                query = select(Cities.id, Cities.name, Cities.slug).order_by(
                    Cities.name
                )
                if state_id is not None:
                    query = query.where(Cities.state_id == state_id)
                if search_by:
                    query = query.where(Cities.name.ilike(f"%{search_by}%"))

                is_paginated: bool = limit is not None and offset is not None

                if is_paginated:
                    query_with_count = query.add_columns(
                        func.count().over().label("total_count")
                    )
                    row_offset = (offset - 1) * limit
                    query_with_count = query_with_count.offset(row_offset).limit(limit)

                    result = await session.execute(query_with_count)
                    rows = result.mappings().all()

                    if not rows:
                        return [], 0

                    total_count = rows[0]["total_count"]
                    cities = [
                        {"id": r["id"], "name": r["name"], "slug": r["slug"]}
                        for r in rows
                    ]
                    return cities, total_count
                else:
                    result = await session.execute(query)
                    cities = [dict(row) for row in result.mappings().all()]
                    return cities, len(cities)

        except Exception as ex:
            self.__console_service_logger.error(
                "Unexpected error fetching cities: {}".format(str(ex))
            )
            raise ex

    async def is_country_exists(self, country_id: int) -> bool:
        try:
            async with self.__session_factory() as session:
                query = select(Countries.id).where(Countries.id == country_id)
                result = await session.execute(query)
                return result.scalar() is not None
        except Exception as ex:
            self.__console_service_logger.error(
                "Error checking country existence: {}".format(str(ex))
            )
            raise ex

    async def is_state_exists(self, state_id: int) -> bool:
        try:
            async with self.__session_factory() as session:
                query = select(States.id).where(States.id == state_id)
                result = await session.execute(query)
                return result.scalar() is not None
        except Exception as ex:
            self.__console_service_logger.error(
                "Error checking state existence: {}".format(str(ex))
            )
            raise ex

    async def get_state_by_id(self, state_id: int) -> States:
        try:
            async with self.__session_factory() as session:
                query = select(States).where(States.id == state_id)
                result = await session.execute(query)
                return result.scalar()
        except Exception as ex:
            self.__console_service_logger.error(
                "Error fetching state by ID: {}".format(str(ex))
            )
            raise ex

    async def get_city_by_id(self, city_id: int) -> Cities:
        try:
            async with self.__session_factory() as session:
                query = select(Cities).where(Cities.id == city_id)
                result = await session.execute(query)
                return result.scalar()
        except Exception as ex:
            self.__console_service_logger.error(
                "Error fetching city by ID: {}".format(str(ex))
            )
            raise ex
    
    async def get_all_states(self) -> List[States]:
        try:
            async with self.__session_factory() as session:
                self.__console_service_logger.info(
                    "Fetching all states from database"
                )
                result = await session.execute(select(States).order_by(States.name))
                return result.scalars().all()
        except Exception as ex:
            self.__console_service_logger.error(
                "Error fetching all states: {}".format(str(ex))
            )
            raise ex
 
    async def get_all_cities(self) -> List[Cities]:
        try:
            async with self.__session_factory() as session:
                self.__console_service_logger.info(
                    "Fetching all cities from database"
                )
                result = await session.execute(select(Cities).order_by(Cities.name))
                return result.scalars().all()
        except Exception as ex:
            self.__console_service_logger.error(
                "Unexpected error fetching all cities: {}".format(str(ex))
            )
            raise ex