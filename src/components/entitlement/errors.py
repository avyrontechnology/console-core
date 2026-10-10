from src.components.common.errors import NotFoundError


class EntitlementNotFoundError(NotFoundError):
    entity_name: str = "Entitlement"


class OrderNotFoundForEntitlementError(Exception):
    def __init__(self, order_id: int):
        super().__init__(f"entitlement not found for order_id={order_id}")


class EntitlementStartDateUpdateLimitExceededError(Exception):
    def __init__(self, current_count: int, max_allowed: int):
        super().__init__(
            f"Start date update limit exceeded. Current count: {current_count}, Maximum allowed: {max_allowed}"
        )


class EntitlementStartDateUpdateWindowExpiredError(Exception):
    def __init__(self, hours_window: int):
        super().__init__(
            f"Start date can only be updated within {hours_window} hours of entitlement creation"
        )


class EntitlementNotEligibleForStartDateUpdateError(Exception):
    pass


class NoPermissionToUpdateEntitlementError(Exception):
    pass
