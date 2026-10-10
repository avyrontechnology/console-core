from enum import Enum


class TeamStrictHierarchyMode(str, Enum):
    """
    Controls how the strict-hierarchy policy is applied *inside teams*.

    - OFF     : strict hierarchy is not applied within teams.
    - FULL    : strict hierarchy is applied to every member subject to it.
    - PARTIAL : strict hierarchy applies starting from a tagged role downward —
                members whose effective role hierarchy is >= the tagged role's
                hierarchy (that role and more-junior roles) follow strict; more
                senior roles are exempt. Requires ``start_role_id``.
    """

    OFF = "off"
    FULL = "full"
    PARTIAL = "partial"


class TeamExceptionMsg:
    TEAM_NOT_FOUND: str = "Team does not exist or is inactive."
    PARTNER_NOT_FOUND: str = "Partner does not exist or is inactive."
    TEAMS_NOT_ENABLED: str = "Teams feature is not enabled for this partner."
    PARENT_DIFFERENT_PARTNER: str = "Parent team belongs to a different partner."
    PARENT_CYCLE: str = "Parent assignment would create a cycle in the team tree."
    PARENT_NOT_FOUND: str = "Parent team does not exist."
    INTERNAL_MISMATCH: str = (
        "Team internal flag must match the partner's internal flag."
    )
    MEMBER_DIFFERENT_PARTNER: str = (
        "Cannot add a user from a different partner to this team."
    )
    MEMBER_USER_NOT_FOUND: str = "User does not exist or is inactive."
    DUPLICATE_MEMBER: str = "User is already a member of this team."
    MEMBER_NOT_FOUND: str = "User is not a member of this team."
    ROLE_NOT_IN_CATALOG: str = (
        "Override role is not part of this partner's effective role catalog."
    )
    START_ROLE_REQUIRED: str = (
        "A start role must be tagged for PARTIAL strict-hierarchy mode."
    )
    INVALID_START_ROLE: str = (
        "The tagged start role is not part of this partner's effective role catalog."
    )


class TeamSuccessMsg:
    TEAM_DELETED: str = "Team deleted successfully."
    MEMBER_REMOVED: str = "Team member removed successfully."
    STRICT_POLICY_UPDATED: str = "Team strict-hierarchy policy updated successfully."
