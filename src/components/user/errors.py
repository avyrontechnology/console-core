from src.components.common.errors import NotFoundError


class UserNotFoundError(NotFoundError):

    entity_name: str = "User"

