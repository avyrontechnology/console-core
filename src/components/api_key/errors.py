from src.components.common.errors import NotFoundError


class ApiKeyNotFoundError(NotFoundError):

    entity_name: str = "Api Key for partner"
