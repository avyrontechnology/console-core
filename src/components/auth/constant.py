from enum import Enum


class TokenKeys:
    USER_ID = "user_id"
    USER_SESSION_ID = "user_session_id"
    EXPIRED = "exp"
    NAME = "name"
    ACCESS_TOKEN = "access_token"
    PERMISSIONS = "user_permissions"
    TOKEN_TYPE = "bearer"
    ROLE = "user_role"
    PARTNER = "partner_id"
    IS_ACTIVE = "is_active"
    IS_MAGLO_ENABLED = "is_maglo_enabled"
    IS_BABBLER_ENABLED = "is_babbler_enabled"
    IS_TALKO_ENABLED = "is_talko_enabled"
    IS_INTERNAL: str = "is_internal"
    PARTNER_ID: str = "partner_id"
    IS_WALLET_ENABLED: str = "is_wallet_enabled"
    IS_MAGLO_APP_ENABLED: str = "is_maglo_app_enabled"
    SUBSCRIPTION_MODE: str = "subscription_mode"
    IS_OBOTAAI_ENABLED: str = "is_obotaai_enabled"


class AuthExceptionMsg:
    ROLE_EXISTS: str = (
        "Role with this Hierarchy or slug already exists or Role is deactivated"
    )
    PERMISSIONS_EXISTS: str = (
        "Permission with this slug already exists or Permission is deactivated"
    )
    USER_NOT_FOUND: str = "Email not found"
    INCORRECT_PWD: str = "Incorrect email or password"
    EMAIL_EXIST: str = "User with this email already exist"
    PHONE_NUMBER_EXIST: str = "User with this phone number already exist"
    PARENT_VALIDATION: str = (
        "The selected parent is not valid for this user's hierarchy. "
        "Please select a parent with a higher hierarchy level."
    )
    PARTNER_LIMIT: str = (
        "You have reached the maximum {} user creation limit for your plan. Please upgrade your plan to add more users."
    )
    UNSUCCESSFULL_LOGOUT: str = "Unsuccessfull attempt for logout"
    SESSION_NOT_FOUND: str = "Session not found"
    TOKEN_EXPIRED_OR_INVALID: str = "Token is expired or invalid"
    PASSWORD_NOT_STRONG: str = (
        "Password must include 8+ characters, an uppercase letter, a number, and a special character."
    )
    USER_EXIST: str = "User with given info already exist"
    PASSWORD_REQUIRED: str = "Current password not entered"
    EXISTING_PASSWORD_WARNING: str = (
        "New password cannot be the same as the existing password"
    )
    ADMIN_EXIST: str = "Admin already exists"
    INTERNAL_FLAG_UPDATION_NOT_ALLOWED: str = (
        "Can't update is internal flag as current user's partner is not internal"
    )
    INVALID_CATEGORY_NAME: str = "Invalid category is provided"
    SVC_NOT_ENABLED: str = "Service: {} is not enabled for user: {}"
    RESTRICT_LOGIN: str = "Partner is inactive, can't log in."
    USERS_OF_DIFFERENT_PARTNER: str = "Can't get the users of different partner."
    ACCOUNT_DELETED: str = "Account is deleted."
    MAGLO_APP_NOT_ENABLED: str = "Maglo app is not enabled."
    USER_MAGLO_APP_NOT_ENABLED: str = "User is not enabled for the Maglo app."
    PARTNER_SERVICE_NOT_ENABLED: str = "Service '{}' is not enabled for this partner."


class AuthSuccessMsg:
    SUCCESSFULL_LOGOUT: str = "User Successfully Logged out"
    ROLE_DELETE: str = "Role deleted successfully."
    PERMISSION_DELETE: str = "Permission deleted successfully."
    PASSWORD_RESET_SUCCESSFULLY: str = "Password reset successfully."


class UserNameLength:
    MAX_LENGTH: int = 25
    MIN_LENGTH: int = 5
    NAME_MIN_LENGTH: int = 2
    NAME_MAX_LENGTH: int = 40


class RPCExceptionMsg:
    ERROR_MSG: str = "Error fetching child users"
    USER_ID_NOT_FOUND: str = "User ID not provided"
    USERS_IDS_NOT_FOUND: str = "Users IDs not provided"
    ROLE_ID_NOT_FOUND: str = "Role ID not provided"


class UserKeys:
    USER_ID: str = "user_id"
    EMAIL: str = "email"
    IS_ACTIVE: str = "is_active"
    IS_SUSPENDED: str = "is_suspended"
    NAME: str = "name"
    PARTNER_ID: str = "partner_id"
    ROLE_HIERARCHY_LEVEL: str = "role_hierarchy_level"
    PARTNER_NAME: str = "partner_name"
    IS_MAGLO_PUBLISHER: str = "is_maglo_publisher"
    ROLE: str = "role"
    IS_BABBLER_ENABLED: str = "is_babbler_enabled"
    IS_MAGLO_ENABLED: str = "is_maglo_enabled"
    PHONE_NUMBER: str = "phone_number"
    IS_TALKO_ENABLED: str = "is_talko_enabled"
    IS_ACTIVE: str = "is_active"
    IS_EMAIL_VERIFIED: str = "is_email_verified"
    IS_PHONE_NUMBER_VERIFIED: str = "is_phone_number_verified"
    IS_WALKTHROUGH_COMPLETED: str = "is_walkthrough_completed"
    CLOUD_AGENT_NUMBER: str = "cloud_agent_number"
    IS_GSM_CALLING_ENABLED: str = "is_gsm_calling_enabled"
    IS_MEETING_LOG_ENABLED: str = "is_meeting_log_enabled"
    ENABLE_DIALER: str = "enable_dialer"
    CAN_CLONE_SERVICE_BOARD: str = "can_clone_service_board"


class RoleDictKeys:
    SLUG = "slug"
    HIERARCHY = "hierarchy"


class UserHierarchyLevel:
    ADMIN_LEVEL_HIERARCHY: int = 1
    SUPER_ADMIN_HIERARCHY: int = 0


class PermissionAttributes:
    CREATED_AT: str = "created_at"
    DISPLAY_TEXT: str = "display_text"
    DESCRIPTION: str = "description"
    IS_ACTIVE: str = "is_active"
    ID: str = "id"
    DEFAULT_ROLE_PERMISSION: str = "default_role_permission"
    PARTNER_ROLE_PERMISSION: str = "partner_role_permission"


class ServiceNames(str, Enum):
    MAGLO: str = "maglo"
    CONSOLE: str = "console"
    BABBLER: str = "babbler"
    TALKO: str = "talko"
    MAGLO_APP: str = "maglo_app"
    OBOTAAI: str  = "obotaai"
    BABBLER_APP: str = "babbler_app"


SvcFlagMap = {
    "maglo": "is_maglo_enabled",
    "babbler": "is_babbler_enabled",
    "talko": "is_talko_enabled",
    "maglo_app": "is_maglo_app_enabled",
    "obotaai": "is_obotaai_enabled",
    "babbler_app": "is_babbler_app_enabled",
}

config_keys: list[str] = [
    "is_maglo_enabled",
    "is_babbler_enabled",
    "is_talko_enabled",
    "is_wallet_enabled",
    "is_maglo_app_enabled",
    "is_gsm_calling_enabled",
    "is_meeting_log_enabled",
    "enable_dialer",
    "is_obotaai_enabled",
    "is_babbler_app_enabled",
    "can_view_products",
    "can_view_inventory",
    "can_view_payment_history",
    "can_view_report_management",
    "can_clone_service_board" , 
]


class OtpType(str, Enum):
    EMAIL = "email"
    LOGIN = "login"
    PHONE_NUMBER = "phone_number"


class OtpConstants:
    OTP_TIMEOUT: int = 2  # 2 Minutes


class SignupConfigKeys(str, Enum):
    MAGLO: str = "maglo"
    TALKO: str = "talko"
    BABBLER: str = "babbler"

    def to_config_key(self) -> str:
        return f"is_{self.value}_enabled"


class ServiceKeys:
    IS_MAGLO_ENABLED = "is_maglo_enabled"
    IS_TALKO_ENABLED = "is_talko_enabled"
    IS_BABBLER_ENABLED = "is_babbler_enabled"
    IS_OBOTAAI_ENABLED = "is_obotaai_enabled"