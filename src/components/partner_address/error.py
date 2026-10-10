from src.components.common.errors import NotFoundError


class AddressNotFoundError(NotFoundError):

    entity_name: str = "Partner address"
