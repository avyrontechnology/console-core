import hashlib
import hmac
from unittest.mock import MagicMock, patch

import pytest
import razorpay.errors

from src.components.payment.enum import PaymentStatusEnum
from src.components.payment.errors import WebhookSignatureError
from src.components.payment.vendors.razorpay_client import RazorpayClient


@pytest.fixture
def razorpay_client():
    with patch(
        "src.components.payment.vendors.razorpay_client.razorpay.Client"
    ) as mock_client:
        yield RazorpayClient()


def test_initiate_order_success(razorpay_client):
    # Arrange
    razorpay_client.client.order.create = MagicMock(return_value={"id": "order_123"})
    amount = 500
    currency = "INR"
    notes = {"key": "value"}

    # Act
    result = razorpay_client.initiate_order(amount, currency, notes)

    # Assert
    assert result["id"] == "order_123"
    razorpay_client.client.order.create.assert_called_once_with(
        {"amount": amount, "currency": currency, "notes": notes}
    )


def test_validate_signature_success(razorpay_client):
    order_id = "order_1"
    payment_id = "pay_1"
    msg = f"{order_id}|{payment_id}"
    signature = hmac.new(
        bytes(razorpay_client._key_secret, "utf-8"),
        bytes(msg, "utf-8"),
        hashlib.sha256,
    ).hexdigest()

    payload = {"order_id": order_id, "payment_id": payment_id, "signature": signature}

    assert razorpay_client.validate_signature(payload) is True


def test_validate_signature_failure(razorpay_client):
    payload = {"order_id": "x", "payment_id": "y", "signature": "invalid"}
    assert razorpay_client.validate_signature(payload) is False


def test_handle_callback_payment_success(razorpay_client):
    payload = {
        "event": "payment.captured",
        "payload": {
            "payment": {
                "entity": {
                    "id": "pay_1",
                    "order_id": "order_1",
                    "method": "card",
                    "status": "captured",
                }
            }
        },
    }

    result = razorpay_client.handle_callback(payload)
    assert result["order_id"] == "order_1"
    assert result["payment_id"] == "pay_1"
    assert result["payment_method"] == "card"
    assert result["status"] == PaymentStatusEnum.SUCCESS


def test_handle_callback_payment_pending(razorpay_client):
    payload = {
        "event": "payment.authorized",
        "payload": {
            "payment": {
                "entity": {
                    "id": "pay_1",
                    "order_id": "order_1",
                    "method": "card",
                    "status": "authorized",
                }
            }
        },
    }

    result = razorpay_client.handle_callback(payload)
    assert result["status"] == PaymentStatusEnum.PENDING


def test_handle_callback_payment_failed(razorpay_client):
    payload = {
        "event": "payment.failed",
        "payload": {
            "payment": {
                "entity": {
                    "id": "pay_1",
                    "order_id": "order_1",
                    "method": "card",
                    "status": "failed",
                }
            }
        },
    }

    result = razorpay_client.handle_callback(payload)
    assert result["status"] == PaymentStatusEnum.FAILED


def test_handle_callback_order_success(razorpay_client):
    payload = {
        "event": "order.paid",
        "payload": {"order": {"entity": {"id": "order_1", "status": "paid"}}},
    }

    result = razorpay_client.handle_callback(payload)
    assert result["order_id"] == "order_1"
    assert result["payment_id"] is None
    assert result["payment_method"] is None
    assert result["status"] == PaymentStatusEnum.SUCCESS


def test_handle_callback_order_failed(razorpay_client):
    payload = {
        "event": "order.failed",
        "payload": {"order": {"entity": {"id": "order_1", "status": "created"}}},
    }

    result = razorpay_client.handle_callback(payload)
    assert result["status"] == PaymentStatusEnum.FAILED


def test_handle_callback_invalid_payload(razorpay_client):
    payload = {"event": "unknown", "payload": {}}
    result = razorpay_client.handle_callback(payload)
    assert result["status"] == PaymentStatusEnum.FAILED
    assert result["order_id"] is None
    assert result["payment_id"] is None
    assert result["payment_method"] is None


# -------------------------------------------------------------------------
# Test: Successful signature verification
# -------------------------------------------------------------------------
def test_verify_webhook_signature_success(razorpay_client):
    """Test successful webhook signature verification"""
    # Arrange
    raw_payload = (
        '{"event":"payment.captured","payload":{"payment":{"entity":{"id":"pay_123"}}}}'
    )
    received_signature = "valid_signature_hash"

    # Mock the utility.verify_webhook_signature to not raise any exception
    razorpay_client.client.utility.verify_webhook_signature = MagicMock()

    # Act
    result = razorpay_client.verify_webhook_signature(raw_payload, received_signature)

    # Assert
    assert result is True
    razorpay_client.client.utility.verify_webhook_signature.assert_called_once_with(
        body=raw_payload,
        signature=received_signature,
        secret=razorpay_client._webhook_secret,
    )


# -------------------------------------------------------------------------
# Test: Signature verification fails (SignatureVerificationError)
# -------------------------------------------------------------------------
def test_verify_webhook_signature_invalid_signature(razorpay_client):
    """Test when signature verification fails with SignatureVerificationError"""
    # Arrange
    raw_payload = '{"event":"payment.captured"}'
    received_signature = "invalid_signature"

    # Mock the utility method to raise SignatureVerificationError
    razorpay_client.client.utility.verify_webhook_signature = MagicMock(
        side_effect=razorpay.errors.SignatureVerificationError("Invalid signature")
    )

    # Act & Assert
    with pytest.raises(WebhookSignatureError):
        razorpay_client.verify_webhook_signature(raw_payload, received_signature)

    razorpay_client.client.utility.verify_webhook_signature.assert_called_once_with(
        body=raw_payload,
        signature=received_signature,
        secret=razorpay_client._webhook_secret,
    )


# -------------------------------------------------------------------------
# Test: Webhook secret not configured
# -------------------------------------------------------------------------
def test_verify_webhook_signature_no_secret(razorpay_client):
    """Test when webhook secret is not configured"""
    # Arrange
    raw_payload = '{"event":"payment.captured"}'
    received_signature = "some_signature"

    # Set webhook secret to empty/None
    razorpay_client._webhook_secret = ""

    # Act
    # The WebhookSignatureError is raised but caught by the generic Exception handler
    # which returns False
    result = razorpay_client.verify_webhook_signature(raw_payload, received_signature)

    # Assert
    assert result is False


# -------------------------------------------------------------------------
# Test: Webhook secret is None
# -------------------------------------------------------------------------
def test_verify_webhook_signature_secret_none(razorpay_client):
    """Test when webhook secret is None"""
    # Arrange
    raw_payload = '{"event":"payment.captured"}'
    received_signature = "some_signature"

    # Set webhook secret to None
    razorpay_client._webhook_secret = None

    # Act
    # The WebhookSignatureError is raised but caught by the generic Exception handler
    # which returns False
    result = razorpay_client.verify_webhook_signature(raw_payload, received_signature)

    # Assert
    assert result is False


# -------------------------------------------------------------------------
# Test: Generic exception during verification
# -------------------------------------------------------------------------
def test_verify_webhook_signature_generic_exception(razorpay_client):
    """Test when unexpected exception occurs during verification"""
    # Arrange
    raw_payload = '{"event":"payment.captured"}'
    received_signature = "some_signature"

    # Mock the utility method to raise a generic exception
    razorpay_client.client.utility.verify_webhook_signature = MagicMock(
        side_effect=Exception("Unexpected error occurred")
    )

    # Act
    result = razorpay_client.verify_webhook_signature(raw_payload, received_signature)

    # Assert
    assert result is False
    razorpay_client.client.utility.verify_webhook_signature.assert_called_once_with(
        body=raw_payload,
        signature=received_signature,
        secret=razorpay_client._webhook_secret,
    )


# -------------------------------------------------------------------------
# Test: Different payload formats
# -------------------------------------------------------------------------
def test_verify_webhook_signature_with_different_payloads(razorpay_client):
    """Test signature verification with various payload formats"""
    # Arrange
    test_payloads = [
        "{}",  # Empty JSON
        '{"event":"order.paid","payload":{"order":{"entity":{"id":"order_123"}}}}',  # Order event
        '{"event":"payment.failed","payload":{"payment":{"entity":{"id":"pay_456","status":"failed"}}}}',  # Failed payment
    ]

    received_signature = "valid_sig"
    razorpay_client.client.utility.verify_webhook_signature = MagicMock()

    # Act & Assert
    for payload in test_payloads:
        result = razorpay_client.verify_webhook_signature(payload, received_signature)
        assert result is True

    # Verify it was called for each payload
    assert razorpay_client.client.utility.verify_webhook_signature.call_count == len(
        test_payloads
    )


# -------------------------------------------------------------------------
# Test: Empty signature
# -------------------------------------------------------------------------
def test_verify_webhook_signature_empty_signature(razorpay_client):
    """Test with empty signature string"""
    # Arrange
    raw_payload = '{"event":"payment.captured"}'
    received_signature = ""

    # Mock to raise SignatureVerificationError for empty signature
    razorpay_client.client.utility.verify_webhook_signature = MagicMock(
        side_effect=razorpay.errors.SignatureVerificationError("Empty signature")
    )

    # Act & Assert
    with pytest.raises(WebhookSignatureError):
        razorpay_client.verify_webhook_signature(raw_payload, received_signature)


# -------------------------------------------------------------------------
# Test: Empty payload
# -------------------------------------------------------------------------
def test_verify_webhook_signature_empty_payload(razorpay_client):
    """Test with empty payload string"""
    # Arrange
    raw_payload = ""
    received_signature = "some_signature"

    razorpay_client.client.utility.verify_webhook_signature = MagicMock()

    # Act
    result = razorpay_client.verify_webhook_signature(raw_payload, received_signature)

    # Assert
    assert result is True
    razorpay_client.client.utility.verify_webhook_signature.assert_called_once_with(
        body=raw_payload,
        signature=received_signature,
        secret=razorpay_client._webhook_secret,
    )


# -------------------------------------------------------------------------
# Test: Network/timeout exception
# -------------------------------------------------------------------------
def test_verify_webhook_signature_network_error(razorpay_client):
    """Test when network or timeout error occurs"""
    # Arrange
    raw_payload = '{"event":"payment.captured"}'
    received_signature = "valid_signature"

    # Mock to raise a network-related exception
    razorpay_client.client.utility.verify_webhook_signature = MagicMock(
        side_effect=ConnectionError("Network timeout")
    )

    # Act
    result = razorpay_client.verify_webhook_signature(raw_payload, received_signature)

    # Assert
    assert result is False


# -------------------------------------------------------------------------
# Test: fetch_order
# -------------------------------------------------------------------------
def test_fetch_order_success(razorpay_client):
    """Test fetching an order from Razorpay"""
    razorpay_client.client.order = MagicMock()
    razorpay_client.client.order.fetch.return_value = {
        "id": "order_abc",
        "status": "paid",
    }

    result = razorpay_client.fetch_order("order_abc")

    assert result == {"id": "order_abc", "status": "paid"}
    razorpay_client.client.order.fetch.assert_called_once_with("order_abc")


def test_fetch_order_propagates_exception(razorpay_client):
    """Test that fetch_order raises on gateway error rather than swallowing it"""
    razorpay_client.client.order = MagicMock()
    razorpay_client.client.order.fetch.side_effect = Exception("Network error")

    with pytest.raises(Exception):
        razorpay_client.fetch_order("order_abc")


# -------------------------------------------------------------------------
# Test: fetch_order_payments
# -------------------------------------------------------------------------
def test_fetch_order_payments_success(razorpay_client):
    """Test fetching payments for an order from Razorpay"""
    razorpay_client.client.order = MagicMock()
    razorpay_client.client.order.payments.return_value = {
        "items": [{"id": "pay_abc", "status": "captured", "method": "upi"}]
    }

    result = razorpay_client.fetch_order_payments("order_abc")

    assert result["items"][0]["id"] == "pay_abc"
    razorpay_client.client.order.payments.assert_called_once_with("order_abc")


def test_fetch_order_payments_propagates_exception(razorpay_client):
    """Test that fetch_order_payments raises on gateway error rather than swallowing it"""
    razorpay_client.client.order = MagicMock()
    razorpay_client.client.order.payments.side_effect = Exception("Network error")

    with pytest.raises(Exception):
        razorpay_client.fetch_order_payments("order_abc")
