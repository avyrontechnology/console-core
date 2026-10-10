from enum import Enum


class PartnerConfigAttributes:
    KEY_CONFLICT: str = "partner config with key: {} already exists."
    PARTNER_CONFIG_NOT_FOUND: str = "partner config not found for partner id: {}"
    KEY_DESCRIPTION: str = "Config Key must be a string."
    PARTNER_ID_DESCRIPTION: str = "Partner ID must be a positive integer."
    PARTNER_LEAD_SOURCE_ID_DESCRIPTION: str = (
        "Partner lead source must be positive integer"
    )
    NEW_VALUE: str = "new_value"


class PartnerConfigEnum(str, Enum):
    """Enum class for Partner Config."""

    IS_CUSTOM_ROLE_PERMISSION_ENABLED = "is_custom_role_permission_enabled"
    IS_OTP_ENABLED = "is_otp_enabled"
    IS_MAGLO_ENABLED = "is_maglo_enabled"
    IS_TALKO_ENABLED = "is_talko_enabled"
    IS_BABBLER_ENABLED = "is_babbler_enabled"
    SEND_USER_CREDENTIALS = "send_user_credentials"
    IS_EMAIL_VERIFICATION_ENABLED = "is_email_verification_enabled"
    IS_PHONE_NUMBER_VERIFICATION_ENABLED = "is_phone_number_verification_enabled"
    CAN_CREATE_DEALS = "can_create_deals"
    CAN_ADD_WORKFLOW = "can_add_workflow"
    CAN_VIEW_WORKFLOW = "can_view_workflow"
    IS_WALLET_ENABLED = "is_wallet_enabled"
    EMAIL_CONFIG_KEY = "email_config_key"
    SMTP_USERNAME = "smtp_username"
    SMTP_PASSWORD = "smtp_password"
    FROM_EMAIL = "from_email"
    IS_MAGLO_APP_ENABLED = "is_maglo_app_enabled"
    IS_BABBLER_APP_ENABLED = "is_babbler_app_enabled"
    IS_MAILER_ENABLED = "is_mailer_enabled"
    IS_GSM_CALLING_ENABLED = "is_gsm_calling_enabled"
    CAN_VIEW_TASK_MANAGEMENT = "can_view_task_management"
    IS_MEETING_LOG_ENABLED = "is_meeting_log_enabled"
    SUBSCRIPTION_MODE = "subscription_mode"
    IS_RULE_BASED_ASSIGNMENT_ENABLED = "is_rule_based_assignment_enabled"
    USER_TRACKER_STATUSES = "user_tracker_statuses"
    CAN_VIEW_PIPELINE_MANAGEMENT = "can_view_pipeline_management"
    IS_COMPLEMENTARY_BABBLER_ENABLED = "is_complementary_babbler_enabled"    
    CAN_VIEW_CONTACT = "can_view_contact"
    CAN_VIEW_ORGANIZATION = "can_view_organization"    
    ENABLE_DIALER = "enable_dialer"
    IS_BULK_WORKFLOW_ENABLED="is_bulk_workflow_enabled"
    CAN_VIEW_MVIEW_MANAGEMENT: str = 'can_view_mview_management'
    IS_ADVANCE_FILTER_ENABLED: str= 'is_advance_filter_enabled'
    CAN_VIEW_TEMPLATE_MANAGEMENT: str = "can_view_template_management"
    CAN_VIEW_PRODUCT_MANAGEMENT: str = "can_view_product_management"
    CAN_VIEW_FINANCE_MANAGEMENT: str = "can_view_finance_management"
    CAN_VIEW_CSF_LEAD_LISTING: str = "can_view_csf_lead_listing"  # ← ADD THIS
    IS_ADD_NUMBER_ENABLED = "is_add_number_enabled"
    CAN_VIEW_PRODUCTS: str = "can_view_products"
    CAN_VIEW_INVENTORY: str = "can_view_inventory"
    CAN_VIEW_ORDER_MANAGEMENT: str = "can_view_order_management"

    # Teams feature flags
    IS_TEAMS_ENABLED: str = "is_teams_enabled"
    IS_PARTNER_CUSTOM_ROLES_ENABLED: str = "is_partner_custom_roles_enabled"
    IS_TEAM_DATA_PARTITION_ENABLED: str = "is_team_data_partition_enabled"
    # Strict-hierarchy-in-teams policy (off | full | partial)
    TEAM_STRICT_HIERARCHY_MODE: str = "team_strict_hierarchy_mode"
    TEAM_STRICT_HIERARCHY_START_ROLE_ID: str = "team_strict_hierarchy_start_role_id"


    IS_OBOTAAI_ENABLED = "is_obotaai_enabled"
    PARTNER_DB_CONFIG = "partner_db_config"
    IS_USER_TRACKER_ENABLED = "is_user_tracker_enabled"
    CAN_VIEW_PAYMENT_HISTORY: str = "can_view_payment_history"
    IS_REENQUIRY_CHAIN_ENABLED: str = "is_reenquiry_chain_enabled"
    CAN_VIEW_REPORT_MANAGEMENT: str = "can_view_report_management"
    CAN_VIEW_HELPDESK_MANAGEMENT: str = "can_view_helpdesk_management"
    CAN_DOWNLOAD_CALL_LOGS: str = "can_download_call_logs"
    IS_INBOX_ENABLED: str = "is_inbox_enabled"
    IS_FIELD_TRACKING_ENABLED: str = "is_field_tracking_enabled"
    CAN_VIEW_INACTIVE_AGENTS: str = "can_view_inactive_agents"
    IS_AGENT_AVAILABILITY_BASED_ASSIGNMENT_ENABLED: str = "is_agent_availability_based_assignment_enabled"
    IS_STICKY_DIDS_ENABLED: str = "is_sticky_dids_enabled"
    CAN_ADD_ADDRESS_WITH_GOOGLE_PLACES: str = "can_add_address_with_google_places"
    IS_ASSIGNEE_SYNC_ENABLED: str = "is_assignee_sync_enabled"

MAILMG_BASE_URL = "https://maglo-mailer.makunaiglobal.ai/mailmg-service/v1"


class SubscriptionModeEnum(str, Enum):
    SELF_SERVED = "self_served"
    SALES_MANAGED = "sales_managed"
