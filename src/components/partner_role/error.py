from src.components.common.errors import NotFoundError


class PartnerRoleNotFoundError(NotFoundError):
    entity_name: str = "Partner Role"


class PartnerRoleException(Exception):
    """Raised for partner-role validation / business-rule violations."""
