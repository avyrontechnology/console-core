from src.components.common.errors import NotFoundError


class CountryNotFoundError(NotFoundError):

    entity_name: str = "Country"


class StateNotFoundError(NotFoundError):

    entity_name: str = "State"


class CityNotFoundError(NotFoundError):
    entity_name: str = "City"
