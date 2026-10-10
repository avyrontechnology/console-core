# src/components/payment/client_factory.py
from src.components.payment.enum import PaymentClientEnum
from src.components.payment.vendors.base_client import BasePaymentClient
from src.components.payment.vendors.razorpay_client import RazorpayClient
from src.core.environment import ENV

_client_instance: BasePaymentClient = None


def get_payment_client() -> BasePaymentClient:
    """
    Singleton factory for payment client.
    Dynamically selects vendor from ENV.
    """
    global _client_instance
    if _client_instance is None:
        client_name = ENV.PAYMENT_CLIENT.upper()
        if client_name == PaymentClientEnum.RAZORPAY:
            _client_instance = RazorpayClient()
        else:
            raise ValueError("Unsupported payment client: {}".format(client_name))
    return _client_instance
