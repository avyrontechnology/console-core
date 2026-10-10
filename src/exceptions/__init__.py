from typing import Optional


class LoggerException(Exception):
    def __init__(self, *args: object) -> None:
        super().__init__(*args)


class AuthException(Exception):
    def __init__(self, *args: object) -> None:
        super().__init__(*args)


class PartnerRolePermissionException(Exception):
    def __init__(self, *args: object) -> None:
        super().__init__(*args)


class PartnerMetaDataException(Exception):
    def __init__(self, *args: object) -> None:
        super().__init__(*args)


class EnvironmentNotFoundException(Exception):
    def __init__(self, *args: object) -> None:
        super().__init__(*args)


class PartnerException(Exception):
    def __init__(self, message: str, id: Optional[int] = None):
        self.message = message
        self.id = id
        super().__init__(message)


class UserMetadataException(Exception):
    def __init__(self, message: str, error_code: str = None):
        super().__init__(message)
        self.message = message
        self.error_code = error_code


class UserMetadataAlreadyExistsException(Exception):
    def __init__(self, *args: object) -> None:
        super().__init__(*args)


class UserException(Exception):
    def __init__(self, *args: object) -> None:
        super().__init__(*args)


class UnauthorizedUserException(Exception):
    def __init__(
        self, message: str = "Unauthorized: You do not have access to this resource"
    ):
        self.message = message
        super().__init__(self.message)


class AddressExistsException(Exception):
    def __init__(self, *args: object) -> None:
        super().__init__(*args)


class ConstantNotFoundException(Exception):
    """
    Raised when a constant is not found in the database.
    """

    def __init__(self, message: str):
        super().__init__(message)


class ConstantVersionException(Exception):
    """
    Raised when there is an issue with the version of the constant.
    """

    def __init__(self, message: str):
        super().__init__(message)


class ConstantVersionNotFoundException(Exception):
    """
    Raised when the version of constant is not found.
    """

    def __init__(self, message: str):
        super().__init__(message)


class PartnerStatusUnchangedException(Exception):
    def __init__(self, *args: object) -> None:
        super().__init__(*args)


class PartnerConfigException(Exception):
    def __init__(self, *args: object) -> None:
        super().__init__(*args)


class PartnerActiveSubscriptionException(Exception):
    def __init__(self, *args: object) -> None:
        super().__init__(*args)


class UnauthorisedException(Exception):
    def __init__(self, *args: object) -> None:
        super().__init__(*args)


class PartnerNotFoundException(Exception):
    def __init__(self, *args: object) -> None:
        super().__init__(*args)


class DefaultRolePermissionException(Exception):
    def __init__(self, *args: object) -> None:
        super().__init__(*args)


class UserConfigException(Exception):
    def __init__(self, *args) -> None:
        super().__init__(*args)


class ApiKeyException(Exception):
    def __init__(self, *args) -> None:
        super().__init__(*args)

class TeamException(Exception):
    def __init__(self, *args) -> None:
        super().__init__(*args)
