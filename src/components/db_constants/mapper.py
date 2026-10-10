from typing import List

from src.components.db_constants.models import (
    Constants,
    DynamicVariables,
    GlobalConstants,
    GlobalDynamicVariables,
    GlobalMediaConstants,
    MediaConstants,
)

constants: List[str] = [
    "VERSION_CAP",
    "IS_GST_ENABLED",
    "GST_PERCENTAGE",
    "BABBLER_PLATFORM_FEE",
    "SERVICE_BOARD_ADD_ON_PRICE",
    "ENTITLEMENT_START_DATE_UPDATE_WINDOW_HOURS",
    "ENT_START_DATE_UPDATE_MAX_COUNT",
    "MAX_GRACE_DAYS_PER_ATTEMPT",
    "MAX_GRACE_ATTEMPTS",
    "SUBSCRIPTION_POPUP_FREQUENCY_MINUTES",
    "SUBSCRIPTION_POPUP_DAYS_BEFORE_EXPIRY",
    "IS_WALLET_GST_ENABLED",
    "IS_WALLET_CONVENIENCE_FEE_ENABLED",
    "WALLET_GST_PERCENTAGE",
    "WALLET_CONVENIENCE_FEE_PERCENTAGE",
]

dynamic_variables = []

media_constants = []

global_constants = []

global_dynamic_variables = [
    "NAVBAR_MARQUEE_ENABLED",
    "NAVBAR_MARQUEE_MESSAGE",
]

global_media_constants = []

# mapping of constants to their corresponding database models
CONSTANT_KEY_TO_MODEL_MAPPER = [
    (constants, Constants),
    (dynamic_variables, DynamicVariables),
    (media_constants, MediaConstants),
    (global_constants, GlobalConstants),
    (global_dynamic_variables, GlobalDynamicVariables),
    (global_media_constants, GlobalMediaConstants),
]
