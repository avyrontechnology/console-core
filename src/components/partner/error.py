from src.components.common.errors import NotFoundError


class PartnerNotFoundError(NotFoundError):

    entity_name: str = "Partner"


class InvalidPartnerIdsError(Exception):
    def __init__(self, invalid_partner_ids: list[int]):
        self.invalid_partner_ids = invalid_partner_ids
        super().__init__(
            f"Invalid partner IDs: {', '.join(map(str, invalid_partner_ids))}"
        )
