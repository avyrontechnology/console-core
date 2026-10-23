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


# app config constants (retired product apps removed; navbar marquee lives on)


class FieldType(Enum):
    """Supported field types"""

    INTEGER = "integer"
    STRING = "string"
    FLOAT = "float"
    BOOLEAN = "boolean"
    DICT = "dict"
    UUID = "uuid"


class Limits:
    EPOCH_MS_MIN: int = 1000000000000
    EPOCH_MS_MAX: int = 9999999999999
    MAX_INT: int = 2147483647
