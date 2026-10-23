from enum import Enum

# Wide spacing used when (re)numbering a partner's role hierarchy so that new
# roles can almost always be inserted by bisection without a rebalance.
HIERARCHY_SPACING: int = 100

# Standard hierarchy value of Manager role in the global catalog.
# Used when deriving data_scope for materialized copies of global roles.
MANAGER_ROLE_HIERARCHY: int = 4

# Floor for a partner-owned role hierarchy.
# check (src/components/home/services.py) treats hierarchy < ADMIN_ROLE_HIERARCHY_LEVEL(1)
# as internal/system-only. A partner-created role must never be assigned a
# hierarchy below this floor, or it would be silently treated as an internal
# actor by that check (and by several `hierarchy <= MANAGER_ROLE_HIERARCHY_LEVEL`
# data-scope checks elsewhere).
MIN_PARTNER_HIERARCHY: int = 1

# Symmetric defensive ceiling. Not currently reachable in practice (would need
# ~100,000 chained BELOW-placements to approach _REBALANCE_TEMP_OFFSET in
# repositories.py), kept for consistency and cheap to enforce.
MAX_PARTNER_HIERARCHY: int = 999_999


class DataScope(str, Enum):
    """Semantic visibility tier carried by a role (drives data scoping)."""

    ALL = "ALL"
    SUBTREE = "SUBTREE"
    OWN = "OWN"


class RolePlacement(str, Enum):
    """Where a new role sits relative to a reference role in the hierarchy."""

    ABOVE = "above"  # more senior (lower hierarchy number)
    BELOW = "below"  # more junior (higher hierarchy number)


class PartnerRoleExceptionMsg:
    UNAUTHORIZED_PARTNER_ACCESS: str = (
        "Only internal users or the partner's own users can materialize this partner's role catalog."
    )
    CUSTOM_ROLES_NOT_ENABLED: str = (
        "Per-partner custom roles are not enabled for this partner."
    )
    INTERNAL_NOT_SUPPORTED: str = (
        "Custom roles are not supported for internal partners in this version."
    )
    PARTNER_NOT_FOUND: str = "Partner does not exist or is inactive."
    REFERENCE_ROLE_NOT_FOUND: str = (
        "Reference role is not part of this partner's role catalog."
    )
    BASE_ROLE_NOT_FOUND: str = (
        "Base role is not part of this partner's role catalog."
    )
    ROLE_NOT_FOUND: str = "Role does not exist for this partner."
    ROLE_IN_USE: str = "Cannot delete a role that is still assigned to users."
    INVALID_DATA_SCOPE: str = "data_scope must be one of ALL, SUBTREE, OWN."
    NO_ROOM_ABOVE: str = (
        "Cannot place a role above '{}' — it is already the partner's most senior role."
    )
    NO_ROOM_BELOW: str = (
        "Cannot place a role below '{}' — no hierarchy room remains in that direction."
    )


class PartnerRoleSuccessMsg:
    ROLE_DELETED: str = "Role deleted successfully."
