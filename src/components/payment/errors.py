class PaymentError(Exception):
    """Generic payment exception."""

    pass


class PaymentNotFoundError(PaymentError):
    """Raised when payment/order is not found."""

    def __init__(self, order_id: str):
        super().__init__("Payment not found for order_id: {}".format(order_id))
        self.order_id = order_id


class PaymentValidationError(PaymentError):
    """Raised when payment signature validation fails."""

    def __init__(self, message: str = "Invalid payment signature"):
        super().__init__(message)


class WebhookSignatureError(PaymentError):
    """Raised when webhook signature verification fails"""

    def __init__(self, message: str = "Webhook signature verification failed"):
        super().__init__(message)
