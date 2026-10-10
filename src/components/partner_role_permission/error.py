from src.components.common.errors import NotFoundError


class PartnerRolePermissionNotFoundError(NotFoundError):

    entity_name: str = "Partner Role Permission"
