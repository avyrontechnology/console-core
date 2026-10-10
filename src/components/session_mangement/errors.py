from src.components.common.errors import NotFoundError


class UserSessionNotFoundError(NotFoundError):
    entity_name: str = "user_session"
