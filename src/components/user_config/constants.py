from enum import Enum


class UserConfigAttributes:
    KEY_CONFLICT: str = "user config with key: {} already exists."
    USER_CONFIG_NOT_FOUND: str = "user config not found for user id: {}"
    KEY_DESCRIPTION: str = "Config Key must be a string."
    USER_ID_DESCRIPTION: str = "User ID must be a positive integer."
    NEW_VALUE: str = "new_value"
    INVALID_USER: str = "One or more user ids are invalid or do not belong to the partner id"

class UserConfig:
    is_super_admin: bool = False


class UserConfigEnum(str, Enum):
    """Enum class for User Config."""

    IS_SUPER_ADMIN = "is_super_admin"
    IS_MAGLO_ENABLED = "is_maglo_enabled"
    IS_BABBLER_ENABLED = "is_babbler_enabled"
    IS_TALKO_ENABLED = "is_talko_enabled"
    IS_MAGLO_APP_ENABLED = "is_maglo_app_enabled"
    IS_GSM_CALLING_ENABLED = "is_gsm_calling_enabled"
    IS_MEETING_LOG_ENABLED = "is_meeting_log_enabled"
    CAN_VIEW_CONTACT = "can_view_contact"
    CAN_VIEW_ORGANIZATION = "can_view_organization"
    IS_OBOTAAI_ENABLED = "is_obotaai_enabled"
    ENABLE_DIALER = "enable_dialer"
    IS_BABBLER_APP_ENABLED = "is_babbler_app_enabled"
    CAN_VIEW_PRODUCTS = "can_view_products"
    CAN_VIEW_INVENTORY = "can_view_inventory"

    NOTIFICATION_MAGLO = "notification.maglo"
    NOTIFICATION_MAGLO_LEAD_ASSIGNED = "notification.maglo.lead_assigned"
    NOTIFICATION_MAGLO_BULK_LEAD_ASSIGNED = "notification.maglo.bulk_lead_assigned"
    NOTIFICATION_MAGLO_FOLLOWUP = "notification.maglo.followup"
    NOTIFICATION_MAGLO_APP = "notification.maglo_app"   
    NOTIFICATION_BABBLER = "notification.babbler"
    NOTIFICATION_BABBLER_APP = "notification.babbler_app"
    NOTIFICATION_TALKO = "notification.talko"
    NOTIFICATION_WHATSAPP = "notification.whatsapp"
    NOTIFICATION_OBOTAAI = "notification.obotaai"
    CAN_VIEW_PAYMENT_HISTORY = "can_view_payment_history"
    CAN_VIEW_REPORT_MANAGEMENT = "can_view_report_management"
