from src.components.common.errors import NotFoundError


class PartnerMetaDataNotFoundError(NotFoundError):

    entity_name: str = "Partner Meta Data"
