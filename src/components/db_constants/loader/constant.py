# After adding constant here make sure to add the same in src.components.db_constants.mapper in their respective model

from src.components.db_constants.constants import DefaultConstants
from src.components.db_constants.initializer import LazyConstantLoader, constant_dict


class _DbConstantsMeta(type):
    """
    Metaclass to enable dynamic class-level constant resolution.
    """

    _DEFAULTS = {
        "VERSION_CAP": DefaultConstants.DEFAULT_VERSION_CAP,
        "GST_PERCENTAGE": DefaultConstants.DEFAULT_GST_PERCENTAGE,
        "IS_GST_ENABLED": DefaultConstants.DEFAULT_IS_GST_ENABLED,
        "ENTITLEMENT_START_DATE_UPDATE_WINDOW_HOURS": DefaultConstants.DEFAULT_ENTITLEMENT_START_DATE_UPDATE_WINDOW_HOURS,
        "ENT_START_DATE_UPDATE_MAX_COUNT": DefaultConstants.DEFAULT_ENT_START_DATE_UPDATE_MAX_COUNT,
        "MAX_GRACE_DAYS_PER_ATTEMPT": DefaultConstants.DEFAULT_MAX_GRACE_DAYS_PER_ATTEMPT,
        "MAX_GRACE_ATTEMPTS": DefaultConstants.DEFAULT_MAX_GRACE_ATTEMPTS,
        "SUBSCRIPTION_POPUP_FREQUENCY_MINUTES": DefaultConstants.DEFAULT_SUBSCRIPTION_POPUP_FREQUENCY_MINUTES,
        "SUBSCRIPTION_POPUP_DAYS_BEFORE_EXPIRY": DefaultConstants.DEFAULT_SUBSCRIPTION_POPUP_DAYS_BEFORE_EXPIRY,
        "IS_WALLET_GST_ENABLED": DefaultConstants.DEFAULT_IS_WALLET_GST_ENABLED,
        "IS_WALLET_CONVENIENCE_FEE_ENABLED": DefaultConstants.DEFAULT_IS_WALLET_CONVENIENCE_FEE_ENABLED,
        "WALLET_GST_PERCENTAGE": DefaultConstants.DEFAULT_WALLET_GST_PERCENTAGE,
        "WALLET_CONVENIENCE_FEE_PERCENTAGE": DefaultConstants.DEFAULT_WALLET_CONVENIENCE_FEE_PERCENTAGE,
    }

    def __getattr__(cls, key: str):
        default = cls._DEFAULTS.get(key)

        value = str(
            LazyConstantLoader(
                key,
                dict=constant_dict,
                default=default,
            )
        )

        if value in (None, "", "None"):
            return default

        if isinstance(default, bool):
            return value.lower() == "true"

        if isinstance(default, int):
            return int(value)

        if isinstance(default, float):
            return float(value)

        return value


class DbConstants(metaclass=_DbConstantsMeta):
    """
    Central DB-backed constants access layer.

    Usage:
        DbConstants.GST_PERCENTAGE
        DbConstants.IS_GST_ENABLED
    """

    pass
