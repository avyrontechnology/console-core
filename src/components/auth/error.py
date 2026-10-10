from src.components.common.errors import NotFoundError
from src.exceptions import AuthException


class RoleNotFoundError(NotFoundError):

    entity_name: str = "Role"


class PermissionNotFoundError(NotFoundError):

    entity_name: str = "Permission"


class OtpMediumMissing(Exception):
    def __init__(self, message: str = "OTP Medium is missing"):
        super().__init__(message)


class OtpTemplateNotFound(Exception):
    def __init__(self, message: str = "OTP template not found"):
        super().__init__(message)
        
class UserCreatedButEmailFailedError(AuthException):  
    pass
