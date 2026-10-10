from unittest.mock import MagicMock, patch

import pytest

from src.components.payment.client_factory import get_payment_client
from src.components.payment.enum import PaymentClientEnum
from src.components.payment.vendors.razorpay_client import RazorpayClient


class TestPaymentClientFactory:

    def teardown_method(self):
        from src.components.payment import client_factory
        client_factory._client_instance = None  # reset singleton

    @patch("src.components.payment.client_factory.ENV")
    @patch("src.components.payment.client_factory.RazorpayClient")
    def test_get_razorpay_client(self, mock_razorpay_client, mock_env):
        mock_env.PAYMENT_CLIENT = PaymentClientEnum.RAZORPAY

        instance_mock = MagicMock(spec=RazorpayClient)
        mock_razorpay_client.return_value = instance_mock

        client = get_payment_client()
        assert client == instance_mock
        mock_razorpay_client.assert_called_once()

    @patch("src.components.payment.client_factory.ENV")
    def test_unsupported_payment_client(self, mock_env):
        mock_env.PAYMENT_CLIENT = "UNKNOWN_CLIENT"  # string, not MagicMock
        from src.components.payment.client_factory import get_payment_client

        # Reset singleton to force creation
        global _client_instance
        _client_instance = None

        with pytest.raises(ValueError, match="Unsupported payment client"):
            get_payment_client()

    @patch("src.components.payment.client_factory.ENV")
    @patch("src.components.payment.client_factory.RazorpayClient")
    def test_singleton_behavior(self, mock_razorpay_client, mock_env):
        mock_env.PAYMENT_CLIENT = PaymentClientEnum.RAZORPAY

        instance_mock = MagicMock(spec=RazorpayClient)
        mock_razorpay_client.return_value = instance_mock

        # Reset singleton to force creation
        from src.components.payment import client_factory
        client_factory._client_instance = None

        client1 = get_payment_client()
        client2 = get_payment_client()

        assert client1 is client2
        mock_razorpay_client.assert_called_once()
