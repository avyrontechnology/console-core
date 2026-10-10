from typing import List, Optional


class StandardStatuses:
    ACTIVE = "Active"
    AWAY = "Away"
    BUSY = "Busy"
    ON_BREAK = "On Break"

    @classmethod
    def all(cls) -> List[str]:
        return [cls.ACTIVE, cls.AWAY, cls.BUSY, cls.ON_BREAK]

    @classmethod
    def _default_icons(cls) -> dict:
        # System-wide default icon colors, shown until a partner sets its own
        # via the status-icon update flow. Partner-set values always take
        # priority.
        return {
            StandardStatuses.ACTIVE: "#22C55E",     # green
            StandardStatuses.AWAY: "#D1D5DB",       # light gray
            StandardStatuses.BUSY: "#B91C1C",       # red
            StandardStatuses.ON_BREAK: "#F97316",   # orange
        }

    @classmethod
    def default_icon(cls, name: str) -> Optional[str]:
        return cls._default_icons().get(name)


class UserTrackerPartnerConfigKey:
    USER_TRACKER_STATUSES = "user_tracker_statuses"


class UserTrackerResponseMsg:
    STATUS_UPDATED: str = "Status updated successfully."
    CUSTOM_STATUSES_UPDATED: str = "Custom statuses updated successfully."
    FORBIDDEN: str = "You are not authorized to perform this action."

    # Not found
    USER_NOT_FOUND: str = "User not found or inactive."
    STATUS_NOT_FOUND: str = "Provided status does not exist in fixed or custom statuses."

    # Validation
    EMPTY_STATUS_NOT_ALLOWED: str = "Status value cannot be empty."
    STATUS_TOO_SHORT: str = "Status must be at least 2 characters long."
    STATUS_TOO_LONG: str = "Status must be at most 50 characters long."
    FIXED_STATUS_CONFLICT: str = "Cannot use a fixed status name as a custom status."
    DUPLICATE_CUSTOM_STATUS: str = "Duplicate status in submitted list (case-insensitive)."


class UserTrackerValidation:
    STATUS_MIN_LENGTH = 2
    STATUS_MAX_LENGTH = 50
    ICON_MAX_LENGTH = 100