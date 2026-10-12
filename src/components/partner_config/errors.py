from src.components.common.errors import NotFoundError, ValidationError


class PartnerConfigKeyError(NotFoundError):

    entity_name: str = "partner_config_key"

class PartnerNotFoundError(NotFoundError):
    entity_name = "Partner"

class PartnerConfigKeyError(NotFoundError):
    entity_name = "Partner Config Key"

class PartnerConfigValidationError(ValidationError):
    """Raised when payload validation fails for create/update email config."""
    pass