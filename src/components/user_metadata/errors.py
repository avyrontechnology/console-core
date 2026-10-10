from src.components.common.errors import NotFoundError


class UserMatadataNotFoundError(NotFoundError):

    entity_name: str = "User meta data"


class UnauthorizedUserException(Exception):
    """Raised when a user tries to access unauthorized resources."""

    def __init__(
        self, message: str = "Unauthorized: You do not have access to this resource"
    ):
        self.message = message
        super().__init__(self.message)
