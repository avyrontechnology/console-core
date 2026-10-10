"""Custom plan-related exceptions."""

from src.components.common.errors import NotFoundError


class PlanNotFoundError(NotFoundError):
    """Raised when a Plan is not found in the database."""

    entity_name: str = "Plan"


class WalletPlanExistsError(Exception):
    """Raised when attempting to create a wallet plan when one already exists"""

    def __init__(self, message: str = "An active wallet plan already exists"):
        self.message = message
        super().__init__(self.message)


class PlanHierarchyExistsError(Exception):
    """Raised when a plan with the same hierarchy already exists."""

    def __init__(self, hierarchy: int):
        self.message = f"A plan with hierarchy {hierarchy} already exists. Hierarchy must be unique."
        super().__init__(self.message)
