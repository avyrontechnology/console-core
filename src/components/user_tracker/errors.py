from src.components.common.errors import (
    NotFoundError,
    ResourceConflictError,
    ValidationError,
)


class UserTrackerNotFoundError(NotFoundError):
    """Raised when the target user does not exist or is inactive in console_users."""
    entity_name: str = "User"


class InvalidStatusError(NotFoundError):
    """
    Raised when the requested status is neither a fixed system status
    nor present in the partner's custom statuses list.
    """
    entity_name: str = "Status"


class CustomStatusAlreadyExistsError(ResourceConflictError):
    """
    Raised when admin tries to add a custom status that already exists
    """
    def __init__(self, status: str):
        super().__init__(f"Custom status already exists: '{status}'")
        self.status = status


class CustomStatusValidationError(ValidationError):
    """
    Raised during admin custom-status update when validation fails:

    """
    def __init__(self, message: str):
        super().__init__(message)


class UnauthorizedCustomStatusAccessError(Exception):
    """
    Raised when a user other than Admin tries to manage custom statuses.
    """
    def __init__(self, message: str = "Only Admin can manage custom statuses."):
        super().__init__(message)
