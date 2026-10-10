from enum import Enum


class RoleLevel(Enum):
    ONBOARDING_SUPER_ADMIN: int = 0
    ONBOARDING_ADMIN: int = -4
    ADMIN: int = 1
    MAINTAINER: int = 2


class RoleHierarchyLevel:
    ONBOARDING_SUPER_ADMIN_LEVEL: int = 0
    ONBOARDING_ADMIN_LEVEL: int = -4
    ADMIN_LEVEL: int = 1
    MANAGER_LEVEL: int = 4
    USER_LEVEL: int = 8
    SYSTEM_ADMIN: int = -1


class RoleActionFlagKeys:
    CAN_VIEW_DASHBOARD: str = "can_view_dashboard"
    CAN_VIEW_PARTNERS: str = "can_view_partners"
    CAN_VIEW_PERMISSIONS: str = "can_view_permissions"
    CAN_VIEW_USERS: str = "can_view_users"
    CAN_VIEW_CONFIGURATIONS: str = "can_view_configurations"
    CAN_VIEW_ADD_PERMISSIONS: str = "can_view_add_permissions"
    CAN_VIEW_PARTNER_INFO: str = "can_view_partner_info"
    CAN_VIEW_INTERNAL_ROLES: str = "can_view_internal_roles"
    CAN_EDIT_INTERNAL_ROLES: str = "can_edit_internal_roles"
    CAN_VIEW_PARTNER_CONFIG: str = "can_view_partner_config"
    CAN_ASSUME_USER: str = "can_assume_user"
    CAN_VIEW_PLANS: str = "can_view_plans"
    CAN_VIEW_ORDER_HISTORY: str = "can_view_order_history"
    CAN_EDIT_BABBLER_PRICING: str = "can_edit_babbler_pricing"
    CAN_VIEW_API_ADMIN: str = "can_view_api_admin"


class PartnerDashboardCardsAttributes:
    TOTAL_PARTNERS: str = "Total Partners"
    LAST_WEEK_PARTNERS: str = "Last 7 Days Partners"
    PARTNERS_MORE_THAN_FIFTY_LICENSES: str = "Partners > 50 Licenses"
    PARTNERS_USING_HOLLAR: str = "Partners Using Hollar"
    PARTNERS_USING_BABLAR: str = "Partners Using Babbler"
    PARTNERS_USING_MAGLO: str = "Partners Using Maglo"
    INCOMPLETE_REGISTRATIONS: str = "Incomplete Registrations"
