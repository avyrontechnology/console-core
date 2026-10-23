from typing import FrozenSet

# Public-catalog routes that work without a token (pricing pages etc.).
# Matched by ROUTE NAME (function name), never by substring — see middleware.
OPTIONAL_AUTH_ROUTES: FrozenSet[str] = frozenset(
    {
        "get_active_plans",  # GET /get-plans
        "get_billing_details",  # POST /billing-details
        "get_modules",  # GET /get-modules
    }
)

# Kept for backward-compat importers; prefer OPTIONAL_AUTH_ROUTES.
OPTIONAL_AUTH_PATHS: tuple = (
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