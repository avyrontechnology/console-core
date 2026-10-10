"""
Helper utilities for the user_tracker component.
"""

from src.components.common.constants import CurrentUserMap


def can_manage_custom_statuses(current_user: dict) -> bool:
    """Return whether the user has the Admin role (Super Admin excluded)."""
    return (
        current_user.get(CurrentUserMap.ROLE_HIERARCHY_LEVEL)
        == CurrentUserMap.ADMIN_ROLE_HIERARCHY_LEVEL
    )
