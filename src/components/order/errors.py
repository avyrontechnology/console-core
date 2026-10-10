from src.components.common.errors import NotFoundError


class OrderNotFoundError(NotFoundError):
    entity_name: str = "Order"


class DurationValidationError(Exception):
    """
    Raised when duration is validated.
    """


class OrderAlreadyProcessedError(Exception):
    """
    Raised when an attempt is made to process an already processed order.
    """


class PlanInactiveError(Exception):
    """Raised when plan is not active or not found."""

    pass


class NoActiveEntitlementError(Exception):
    """Raised when user doesn't have required active entitlements."""

    pass


class NoBillingForWalletError(Exception):
    """Raised when billing is calculated for plan type wallet."""

    pass


class InvalidUpgradeError(Exception):
    """Raised when upgrade validation fails."""

    pass


class MissingPlanIdError(Exception):
    """Raised when plan_id is required but not provided."""

    pass


class AuthenticationRequiredError(Exception):
    """Raised when authentication is required for the operation."""

    pass


class SelfServeManualOrderError(Exception):
    """Raised when trying to create a manual order for a self-served subscription."""

    pass
