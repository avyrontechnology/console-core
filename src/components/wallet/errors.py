"""Custom exception definitions for Wallet operations."""

from uuid import UUID
from src.components.common.errors import NotFoundError


class WalletNotFoundError(NotFoundError):
    """Raised when a wallet is not found for a given partner."""

    entity_name: str = "wallet"

    def __init__(self, partner_id: UUID) -> None:
        super().__init__(partner_id)


class WalletAlreadyExistsError(Exception):
    """Raised when a wallet already exists for a given partner."""

    entity_name: str = "wallet"

    def __init__(self, partner_id: UUID) -> None:
        super().__init__(
            f"{self.entity_name} already exists for partner id: {partner_id}"
        )


class InsufficientBalanceError(Exception):
    """Raised when a wallet does not have enough balance or frozen balance."""

    entity_name: str = "wallet"

    def __init__(self, message: str = "Insufficient balance.") -> None:
        super().__init__(message)


class WalletBalanceOverflowError(Exception):
    """Raised when a wallet balance or frozen balance exceeds the allowed limits."""

    entity_name: str = "wallet"

    def __init__(
        self, message: str = "Wallet balance exceeds maximum allowed limit."
    ) -> None:
        super().__init__(message)
