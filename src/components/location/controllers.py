from uuid import UUID
from typing import List, Optional

from dependency_injector.wiring import Provide, inject
from fastapi import APIRouter, Depends, Query, Request, status

from src.components.common.errors import ErrorMsg
from src.components.common.response import (
    BadRequestResponse, 
    InternalServerErrorResponse,
    NotFoundResponse,
    SuccessResponse,
)
from src.components.location.errors import CountryNotFoundError, StateNotFoundError
from src.components.location.schemas import (
    CityPaginatedResponse,
    CityResponse,
    CountryResponse,
    StatePaginatedResponse,
    StateResponse,
)
from src.components.location.services import LocationService
from src.components.rbac.permission_dependency import PermissionDependency
from src.components.rbac.permission_injector import permission_check
from src.core.container import Container
from src.loggers.console_service_logger import ConsoleServiceLogger


class LocationController:

    location_router = APIRouter()

    @location_router.get("/countries", response_model=List[CountryResponse])
    @inject
    async def get_all_countries(
        request: Request,
        search_by: Optional[str] = Query(
            None, description="filter countries by country name"
        ),
        location_service: LocationService = Depends(
            Provide[Container.location_service]
        ),
        console_service_logger: ConsoleServiceLogger = Depends(
            Provide[Container.console_service_logger]
        ),
    ):
        try:
            console_service_logger.info("Fetching all countries from database")
            countries: List[CountryResponse] = await location_service.get_countries(
                search_by
            )
            return SuccessResponse(countries)
        except Exception as exc:
            console_service_logger.error(
                "Unexpected error while fetching countries: {}".format(str(exc))
            )
            return InternalServerErrorResponse(ErrorMsg.INTERNAL_SERVER_ERROR)

    @location_router.get("/states", response_model=StatePaginatedResponse) 
    @inject
    async def get_states_by_country(
        request: Request,
        country_id: Optional[UUID] = Query(
            None, description="filter states by country id"
        ),
        search_by: Optional[str] = Query(None, description="filter state by name"),
        limit: Optional[int] = Query(
            None, description="number of records per page", ge=1
        ),
        offset: Optional[int] = Query(
            None, description="page number, 1-based", ge=1
        ),
        location_service: LocationService = Depends(
            Provide[Container.location_service]
        ),
        console_service_logger: ConsoleServiceLogger = Depends(
            Provide[Container.console_service_logger]
        ),
    ):
        if (limit is None) != (offset is None):
            return BadRequestResponse(
                detail="Both 'limit' and 'offset' must be provided together for pagination."
            )

        try:
            console_service_logger.info("Attempting to fetching states")
            result: StatePaginatedResponse = await location_service.get_states_by_country(
                country_id, search_by, limit, offset
            )
            return SuccessResponse(
                data=result.data,                
                pagination={
                    "total_count": result.total_count,
                    "limit": result.limit,
                    "offset": result.offset,
                } 
            )
        except CountryNotFoundError as exc:
            console_service_logger.error("Country not found: {}".format(str(exc)))
            return NotFoundResponse(str(exc))
        except Exception as exc:
            console_service_logger.error(
                "Unexpected error while fetching states: {}".format(str(exc))
            )
            return InternalServerErrorResponse(ErrorMsg.INTERNAL_SERVER_ERROR)

    @location_router.get("/cities", response_model=List[CityResponse])
    @inject
    async def get_cities_by_state(
        request: Request,
        state_id: Optional[UUID] = Query(None, description="filter cities by state id"),
        search_by: Optional[str] = Query(None, description="filter city by name"),
        limit: Optional[int] = Query(
            None, description="number of records per page", ge=1
        ),
        offset: Optional[int] = Query(
            None, description="page number, 1-based", ge=1
        ),
        location_service: LocationService = Depends(
            Provide[Container.location_service]
        ),
        console_service_logger: ConsoleServiceLogger = Depends(
            Provide[Container.console_service_logger]
        ),
    ):
        if (limit is None) != (offset is None):
            return BadRequestResponse(
                detail="Both 'limit' and 'offset' must be provided together for pagination."
            )

        try:
            console_service_logger.info("Attempting fetching cities")
            result: CityPaginatedResponse = await location_service.get_cities_by_state(
                state_id, search_by, limit, offset
            )
            return SuccessResponse(
                data = result.data,
                pagination={
                    "total_count": result.total_count,
                    "limit": result.limit,
                    "offset": result.offset,
                }
            )
        except StateNotFoundError as exc:
            console_service_logger.error("State not found: {}".format(str(exc)))
            return NotFoundResponse(str(exc))
        except Exception as exc:
            console_service_logger.error(
                "Unexpected error fetching cities: {}".format(str(exc))
            )
            return InternalServerErrorResponse(ErrorMsg.INTERNAL_SERVER_ERROR)
