from enum import Enum


class UserAttributes:
    USER: str = "user"
    EMAIL: str = "email"
    PHONE_NUMBER: str = "phone_number"


class CurrentUserMap:
    USER_ID: str = "user_id"
    PARTNER_ID: str = "partner_id"
    EMAIL: str = "email"
    ROLE_HIERARCHY_LEVEL: str = "role_hierarchy_level"
    ADMIN_ROLE_HIERARCHY_LEVEL: int = 1
    MAINTAINER_ROLE_HIERARCHY_LEVEL: int = 3
    SUPER_ADMIN_ROLE_HIERARCHY_LEVEL: int = 0


# app config constants


class MagloAppConfig:
    ANDROID_LATEST_VERSION = "1.0.12"
    IOS_LATEST_VERSION = "1.0.11"


class BabblerAppConfig:

    ANDROID_LATEST_VERSION = "2.3.0"
    IOS_LATEST_VERSION = "2.2.0"


class FieldType(Enum):
    """Supported field types"""

    INTEGER = "integer"
    STRING = "string"
    FLOAT = "float"
    BOOLEAN = "boolean"
    DICT = "dict"


class Limits:
    EPOCH_MS_MIN: int = 1000000000000
    EPOCH_MS_MAX: int = 9999999999999
    MAX_INT: int = 2147483647
