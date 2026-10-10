from src.components.common.errors import NotFoundError


class UserNotFoundError(NotFoundError):

    entity_name: str = "User"


class PublisherExistsError(Exception):
    """Raised when trying to add a user with is_maglo_publisher=True for a partner that already has a maglo publisher."""

    pass
