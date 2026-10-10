# src/components/payment/vendors/base_client.py
from abc import ABC, abstractmethod
from typing import Any, Dict, Optional


class BasePaymentClient(ABC):
    """
    Abstract base class for any payment gateway client.
    """

    @abstractmethod
    def initiate_order(
        self,
        amount: float,
        currency: str = "INR",
        notes: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Initiates an order in the payment gateway and returns gateway order details.
        """

    @abstractmethod
    def validate_signature(self, payload: Dict[str, Any]) -> bool:
        """
        Validate the signature/callback payload from gateway.
        """

    @abstractmethod
    def handle_callback(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """
        Handle asynchronous callback from gateway.
        """

    @abstractmethod
    def verify_webhook_signature(
        self,
        raw_body: bytes,
        signature: str,
    ) -> None:
        """
        Verify the webhook signature from the payment gateway.
        """

    @abstractmethod
    def fetch_order(self, order_id: str) -> Dict[str, Any]:
        """
        Fetch order details from the gateway.
        """

    @abstractmethod
    def fetch_order_payments(self, order_id: str) -> Dict[str, Any]:
        """
        Fetch payments for an order from the gateway.
        """
