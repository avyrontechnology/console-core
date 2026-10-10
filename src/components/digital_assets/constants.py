from enum import Enum


class DigitalAssetEnum(Enum):
    CONSOLE_PARTNER_GST = 1
    CONSOLE_PARTNER_LOGO = 2
    GLOBAL_MEDIA_CONSTANT = 3
    CONSOLE_MEDIA_CONSTANT = 4
    MAGLO_MEDIA_CONSTANT = 5
    OTHER = 100  # For uncategorized assets; allows adding new categories above without renumbering.


class StorageProvidersEnum(Enum):
    AWS = 1
    AZURE = 2
    DIGITAL_OCEAN = 3


URL_EXPIRATION_TIME = 24 * 60 * 60  # Expiration time in seconds
