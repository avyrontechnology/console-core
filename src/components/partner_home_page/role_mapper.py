from typing import Dict

from src.components.partner_home_page.constants import (
    RoleActionFlagKeys,
    RoleHierarchyLevel,
    RoleLevel,
)


class RoleFlagMapper:

    ROLE_FLAGS: Dict[RoleLevel, Dict[str, bool]] = {
        RoleLevel.ONBOARDING_SUPER_ADMIN: {
            RoleActionFlagKeys.CAN_VIEW_DASHBOARD: True,
            RoleActionFlagKeys.CAN_VIEW_PARTNERS: True,
            RoleActionFlagKeys.CAN_VIEW_PERMISSIONS: True,
            RoleActionFlagKeys.CAN_VIEW_USERS: True,
            RoleActionFlagKeys.CAN_VIEW_CONFIGURATIONS: True,
            RoleActionFlagKeys.CAN_VIEW_ADD_PERMISSIONS: True,
            RoleActionFlagKeys.CAN_VIEW_PARTNER_INFO: False,
            RoleActionFlagKeys.CAN_VIEW_INTERNAL_ROLES: True,
            RoleActionFlagKeys.CAN_EDIT_INTERNAL_ROLES: True,
            RoleActionFlagKeys.CAN_VIEW_PARTNER_CONFIG: True,
            RoleActionFlagKeys.CAN_ASSUME_USER: True,
            RoleActionFlagKeys.CAN_VIEW_PLANS: True,
            RoleActionFlagKeys.CAN_VIEW_ORDER_HISTORY: True,
            RoleActionFlagKeys.CAN_VIEW_API_ADMIN: False,
        },
        RoleLevel.ONBOARDING_ADMIN: {
            RoleActionFlagKeys.CAN_VIEW_DASHBOARD: True,
            RoleActionFlagKeys.CAN_VIEW_PARTNERS: False,
            RoleActionFlagKeys.CAN_VIEW_PERMISSIONS: True,
            RoleActionFlagKeys.CAN_VIEW_USERS: True,
            RoleActionFlagKeys.CAN_VIEW_CONFIGURATIONS: False,
            RoleActionFlagKeys.CAN_VIEW_ADD_PERMISSIONS: True,
            RoleActionFlagKeys.CAN_VIEW_PARTNER_INFO: True,
            RoleActionFlagKeys.CAN_VIEW_INTERNAL_ROLES: False,
            RoleActionFlagKeys.CAN_EDIT_INTERNAL_ROLES: False,
            RoleActionFlagKeys.CAN_VIEW_PARTNER_CONFIG: True,
            RoleActionFlagKeys.CAN_ASSUME_USER: False,
            RoleActionFlagKeys.CAN_VIEW_PLANS: False,
            RoleActionFlagKeys.CAN_VIEW_ORDER_HISTORY: False,
            RoleActionFlagKeys.CAN_VIEW_API_ADMIN: False,
        },
        RoleLevel.ADMIN: {
            RoleActionFlagKeys.CAN_VIEW_DASHBOARD: True,
            RoleActionFlagKeys.CAN_VIEW_PARTNERS: False,
            RoleActionFlagKeys.CAN_VIEW_PERMISSIONS: False,
            RoleActionFlagKeys.CAN_VIEW_USERS: True,
            RoleActionFlagKeys.CAN_VIEW_CONFIGURATIONS: False,
            RoleActionFlagKeys.CAN_VIEW_ADD_PERMISSIONS: False,
            RoleActionFlagKeys.CAN_VIEW_PARTNER_INFO: True,
            RoleActionFlagKeys.CAN_VIEW_INTERNAL_ROLES: False,
            RoleActionFlagKeys.CAN_EDIT_INTERNAL_ROLES: False,
            RoleActionFlagKeys.CAN_VIEW_PARTNER_CONFIG: False,
            RoleActionFlagKeys.CAN_VIEW_PLANS: False,
            RoleActionFlagKeys.CAN_VIEW_ORDER_HISTORY: False,
            RoleActionFlagKeys.CAN_VIEW_API_ADMIN: True,
        },
        RoleLevel.MAINTAINER: {
            RoleActionFlagKeys.CAN_VIEW_DASHBOARD: True,
            RoleActionFlagKeys.CAN_VIEW_PARTNERS: False,
            RoleActionFlagKeys.CAN_VIEW_PERMISSIONS: False,
            RoleActionFlagKeys.CAN_VIEW_USERS: True,
            RoleActionFlagKeys.CAN_VIEW_CONFIGURATIONS: False,
            RoleActionFlagKeys.CAN_VIEW_ADD_PERMISSIONS: False,
            RoleActionFlagKeys.CAN_VIEW_PARTNER_INFO: True,
            RoleActionFlagKeys.CAN_VIEW_INTERNAL_ROLES: False,
            RoleActionFlagKeys.CAN_EDIT_INTERNAL_ROLES: False,
            RoleActionFlagKeys.CAN_VIEW_PARTNER_CONFIG: True,
            RoleActionFlagKeys.CAN_VIEW_PLANS: False,
            RoleActionFlagKeys.CAN_VIEW_ORDER_HISTORY: False,
            RoleActionFlagKeys.CAN_VIEW_API_ADMIN: False,
        },
    }

    @staticmethod
    def get_flags(
        role_hierarchy_level: int, is_partner_internal: bool
    ) -> Dict[str, bool]:
        if (
            role_hierarchy_level == RoleHierarchyLevel.ONBOARDING_SUPER_ADMIN_LEVEL
            and is_partner_internal
        ):
            role_level: int = RoleLevel.ONBOARDING_SUPER_ADMIN

        elif (
            role_hierarchy_level == RoleHierarchyLevel.ONBOARDING_ADMIN_LEVEL
            and is_partner_internal
        ):
            role_level: int = RoleLevel.ONBOARDING_ADMIN

        elif role_hierarchy_level == RoleHierarchyLevel.ADMIN_LEVEL:
            role_level: int = RoleLevel.ADMIN

        elif (
            RoleHierarchyLevel.ADMIN_LEVEL
            < role_hierarchy_level
            < RoleHierarchyLevel.MANAGER_LEVEL
        ):
            role_level: int = RoleLevel.MAINTAINER

        else:
            return {}

        flags: Dict = RoleFlagMapper.ROLE_FLAGS.get(role_level, {})
        return flags
