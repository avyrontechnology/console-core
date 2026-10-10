from src.components.common.errors import NotFoundError


class TeamNotFoundError(NotFoundError):
    entity_name: str = "Team"


class TeamException(Exception):
    """Raised for team validation / business-rule violations."""
