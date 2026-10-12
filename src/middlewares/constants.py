from typing import Tuple

OPTIONAL_AUTH_PATHS: Tuple[str, ...] = (
    "get-plans",
    "billing-details",
    "get-modules",
)


class Product:
    TALKO = "talko"
    CONSOLE = "console"

    VALID_VALUES = frozenset({TALKO, CONSOLE})


class Platform:
    WEB = "web"
    APP = "app"

    VALID_VALUES = frozenset({WEB, APP})


class ClientType:
    UNKNOWN = "unknown"

    VALID_VALUES: frozenset[str] = frozenset(
        f"{p}-{pl}" for p in Product.VALID_VALUES for pl in Platform.VALID_VALUES
    )