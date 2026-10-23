from uuid import UUID
from unittest.mock import AsyncMock, Mock, patch

import pytest

from src.components.payment.enum import PaymentStatusEnum
from src.components.payment.errors import (
    PaymentError,
    PaymentValidationError,
    WebhookSignatureError,
)
from src.components.payment.schema import InitiateOrderRequest, ValidateOrderRequest
from src.components.payment.services import PaymentService
from src.loggers.console_service_logger import ConsoleServiceLogger


@pytest.fixture
def mock_get_payment_client():
    with patch("src.components.payment.services.get_payment_client") as m:
        yield m


@pytest.mark.asyncio
class TestPaymentService:

    @pytest.fixture(autouse=True)
    def setup(self, mock_get_payment_client):
        # Mocks
        self.repo = AsyncMock()
        self.logger = AsyncMock(spec=ConsoleServiceLogger)

        # Client mock
        self.client = Mock()
        self.client.initiate_order.return_value = {"id": "order_test123"}
        self.client.verify_webhook_signature.return_value = True
        self.client.validate_signature.return_value = True
        self.client.handle_callback.return_value = {
            "order_id": "order_test123",
            "status": PaymentStatusEnum.SUCCESS,
            "payment_id": "pay_123",
            "payment_method": "card",
        }

        mock_get_payment_client.return_value = self.client

        # Service instance
        self.service = PaymentService(repository=self.repo, logger=self.logger)

        # Payloads
        self.initiate_payload = InitiateOrderRequest(
            partner_id= UUID("11111111-1111-1111-1111-111111111111"),
            amount=100.0,
            entity_name="PLAN",
        )

        self.validate_payload = ValidateOrderRequest(
            order_id="order_test123", payment_id="pay_123", signature="validsig"
        )

        self.webhook_payload = {
            "event": "payment.captured",
            "payload": {
                "payment": {
                    "entity": {
                        "id": "pay_123",
                        "order_id": "order_test123",
                        "status": "captured",
                        "method": "card",
                    }
                }
            },
        }

        self.raw_body = b'{"event":"payment.captured"}'
        self.signature = "valid_signature_hash"

    # -------------------- create_order --------------------

    async def test_create_order_success(self):
        self.repo.create_payment.return_value = None

        user_context = {"user_id": 42, "partner_id": "1"}

        result = await self.service.create_order(self.initiate_payload, user_context)

        assert result == {"id": "order_test123"}
        self.repo.create_payment.assert_called_once()
        self.logger.info.assert_called()

    async def test_create_order_fail_after_retries(self):
        self.client.initiate_order.side_effect = Exception("Fail")
        user_context = {"user_id": 42, "partner_id": "1"}

        with pytest.raises(PaymentError):
            await self.service.create_order(self.initiate_payload, user_context)

        assert self.client.initiate_order.call_count == 3

    async def test_create_order_exception(self):
        self.repo.create_payment.side_effect = Exception("DB error")
        user_context = {"user_id": 42, "partner_id": "1"}

        with pytest.raises(PaymentError):
            await self.service.create_order(self.initiate_payload, user_context)

        self.logger.error.assert_called()

    # -------------------- validate_order --------------------

    async def test_validate_order_success(self):
        payment = Mock()
        payment.id = UUID("10101010-1010-1010-1010-101010101010")
        self.repo.get_payment_by_order_id.return_value = payment

        current_user = {"user_id": UUID("42424242-4242-4242-4242-424242424242"), "partner_id": "1"}
        result = await self.service.validate_order(self.validate_payload, current_user)

        assert result["status"] == "success"
        assert result["order_id"] == "order_test123"

        self.repo.update_payment.assert_called_once_with(
            payment_id= UUID("10101010-1010-1010-1010-101010101010"),
            data={"payment_status": PaymentStatusEnum.SUCCESS, "updated_by": UUID("42424242-4242-4242-4242-424242424242")},
        )

    async def test_validate_order_invalid_signature(self):
        payment = Mock()
        payment.id = UUID("10101010-1010-1010-1010-101010101010")
        self.repo.get_payment_by_order_id.return_value = payment

        self.client.validate_signature.return_value = False
        current_user = {"user_id": UUID("42424242-4242-4242-4242-424242424242"), "partner_id": "1"}

        result = await self.service.validate_order(self.validate_payload, current_user)

        assert result["status"] == "failed"

        self.repo.update_payment.assert_called_once_with(
            payment_id= UUID("10101010-1010-1010-1010-101010101010"),
            data={"payment_status": PaymentStatusEnum.FAILED, "updated_by": UUID("42424242-4242-4242-4242-424242424242")},
        )

    async def test_validate_order_not_found(self):
        self.repo.get_payment_by_order_id.return_value = None
        current_user = {"user_id": 42, "partner_id": "1"}

        with pytest.raises(PaymentValidationError):
            await self.service.validate_order(self.validate_payload, current_user)

    async def test_validate_order_exception(self):
        self.repo.get_payment_by_order_id.side_effect = Exception("DB error")
        current_user = {"user_id": 42, "partner_id": "1"}

        with pytest.raises(PaymentValidationError):
            await self.service.validate_order(self.validate_payload, current_user)

        self.logger.error.assert_called()

    # -------------------- payment history --------------------

    async def test_get_payment_history_success(self):
        payments = [Mock(), Mock()]
        self.repo.get_payments_by_partner.return_value = payments

        result = await self.service.get_payment_history_by_partner(1)

        assert result == payments
        self.logger.info.assert_called_once()

    async def test_get_payment_history_exception(self):
        self.repo.get_payments_by_partner.side_effect = Exception("DB error")

        with pytest.raises(Exception):
            await self.service.get_payment_history_by_partner(1)

        self.logger.error.assert_called()

    # -------------------- handle_webhook --------------------

    async def test_handle_webhook_success_with_payment_found(self):
        """Test successful webhook processing when payment record exists"""
        payment = Mock()
        payment.id = 10
        self.repo.get_payment_by_order_id.return_value = payment

        result = await self.service.handle_webhook(
            self.webhook_payload, self.raw_body, self.signature
        )

        # Verify signature was checked
        self.client.verify_webhook_signature.assert_called_once_with(
            self.raw_body.decode("utf-8"), self.signature
        )

        # Verify callback was processed
        self.client.handle_callback.assert_called_once_with(self.webhook_payload)

        # Verify payment was fetched
        self.repo.get_payment_by_order_id.assert_called_once_with("order_test123")

        # Verify payment was updated
        self.repo.update_payment.assert_called_once_with(
            10,
            {
                "payment_status": PaymentStatusEnum.SUCCESS,
                "payment_method": "card",
                "payment_id": "pay_123",
                "additional_info": self.webhook_payload,
            },
        )

        # Verify result
        assert result["order_id"] == "order_test123"
        assert result["status"] == PaymentStatusEnum.SUCCESS
        assert result["payment_id"] == "pay_123"
        assert result["payment_method"] == "card"

        # Verify logging
        self.logger.info.assert_any_call("Webhook signature verified successfully")
        self.logger.info.assert_any_call("Processing payment webhook payload")
        self.logger.info.assert_any_call(
            "Webhook updated payment_id=pay_123 order_id=order_test123 status={}".format(
                PaymentStatusEnum.SUCCESS
            )
        )

    async def test_handle_webhook_success_with_payment_not_found(self):
        """Test successful webhook processing when payment record doesn't exist"""
        self.repo.get_payment_by_order_id.return_value = None

        result = await self.service.handle_webhook(
            self.webhook_payload, self.raw_body, self.signature
        )

        # Verify signature was checked
        self.client.verify_webhook_signature.assert_called_once()

        # Verify callback was processed
        self.client.handle_callback.assert_called_once_with(self.webhook_payload)

        # Verify payment lookup was attempted
        self.repo.get_payment_by_order_id.assert_called_once_with("order_test123")

        # Verify payment was NOT updated (since not found)
        self.repo.update_payment.assert_not_called()

        # Verify result
        assert result["order_id"] == "order_test123"
        assert result["status"] == PaymentStatusEnum.SUCCESS

        # Verify logging (but not the update log)
        self.logger.info.assert_any_call("Webhook signature verified successfully")
        self.logger.info.assert_any_call("Processing payment webhook payload")

    async def test_handle_webhook_success_without_order_id(self):
        """Test webhook processing when processed callback has no order_id"""
        self.client.handle_callback.return_value = {
            "status": PaymentStatusEnum.FAILED,
            "payment_id": "pay_456",
            "payment_method": "upi",
        }

        result = await self.service.handle_webhook(
            self.webhook_payload, self.raw_body, self.signature
        )

        # Verify signature was checked
        self.client.verify_webhook_signature.assert_called_once()

        # Verify callback was processed
        self.client.handle_callback.assert_called_once()

        # Verify payment lookup was NOT attempted (no order_id)
        self.repo.get_payment_by_order_id.assert_not_called()

        # Verify payment was NOT updated
        self.repo.update_payment.assert_not_called()

        # Verify result
        assert result.get("order_id") is None
        assert result["status"] == PaymentStatusEnum.FAILED
        assert result["payment_id"] == "pay_456"

    async def test_handle_webhook_missing_signature_none(self):
        """Test webhook fails when signature is None"""
        with pytest.raises(WebhookSignatureError) as exc_info:
            await self.service.handle_webhook(self.webhook_payload, self.raw_body, None)

        assert "Missing webhook signature" in str(exc_info.value)

        # Only ONE error log should be emitted
        assert self.logger.error.call_count == 1
        self.logger.error.assert_called_with("Webhook signature header missing")

    async def test_handle_webhook_missing_signature(self):
        """Test webhook fails when signature is missing"""
        with pytest.raises(WebhookSignatureError) as exc_info:
            await self.service.handle_webhook(self.webhook_payload, self.raw_body, "")

        assert "Missing webhook signature" in str(exc_info.value)

        # Verify signature verification was not called
        self.client.verify_webhook_signature.assert_not_called()

        # Only ONE error log should be emitted
        assert self.logger.error.call_count == 1
        self.logger.error.assert_called_with("Webhook signature header missing")

    async def test_handle_webhook_invalid_signature(self):
        """Test webhook fails when signature verification fails"""
        self.client.verify_webhook_signature.side_effect = Exception(
            "Invalid signature"
        )

        with pytest.raises(PaymentError) as exc_info:
            await self.service.handle_webhook(
                self.webhook_payload, self.raw_body, self.signature
            )

        assert "Invalid signature" in str(exc_info.value)

        # Verify signature verification was attempted
        self.client.verify_webhook_signature.assert_called_once_with(
            self.raw_body.decode("utf-8"), self.signature
        )

        # Verify callback was not processed
        self.client.handle_callback.assert_not_called()

        # Verify error was logged
        self.logger.error.assert_called()

    async def test_handle_webhook_callback_processing_error(self):
        """Test webhook fails when callback processing raises exception"""
        self.client.handle_callback.side_effect = Exception("Callback processing error")

        with pytest.raises(PaymentError) as exc_info:
            await self.service.handle_webhook(
                self.webhook_payload, self.raw_body, self.signature
            )

        assert "Callback processing error" in str(exc_info.value)

        # Verify signature was verified
        self.client.verify_webhook_signature.assert_called_once()

        # Verify callback was attempted
        self.client.handle_callback.assert_called_once()

        # Verify error was logged
        self.logger.error.assert_called_with(
            "Error processing webhook: Callback processing error"
        )

    async def test_handle_webhook_payment_lookup_error(self):
        """Test webhook fails when payment lookup raises exception"""
        self.repo.get_payment_by_order_id.side_effect = Exception("Database error")

        with pytest.raises(PaymentError) as exc_info:
            await self.service.handle_webhook(
                self.webhook_payload, self.raw_body, self.signature
            )

        assert "Database error" in str(exc_info.value)

        # Verify all steps up to payment lookup
        self.client.verify_webhook_signature.assert_called_once()
        self.client.handle_callback.assert_called_once()
        self.repo.get_payment_by_order_id.assert_called_once()

        # Verify update was not attempted
        self.repo.update_payment.assert_not_called()

        # Verify error was logged
        self.logger.error.assert_called()

    async def test_handle_webhook_payment_update_error(self):
        """Test webhook fails when payment update raises exception"""
        payment = Mock()
        payment.id = 10
        self.repo.get_payment_by_order_id.return_value = payment
        self.repo.update_payment.side_effect = Exception("Update failed")

        with pytest.raises(PaymentError) as exc_info:
            await self.service.handle_webhook(
                self.webhook_payload, self.raw_body, self.signature
            )

        assert "Update failed" in str(exc_info.value)

        # Verify all steps were attempted
        self.client.verify_webhook_signature.assert_called_once()
        self.client.handle_callback.assert_called_once()
        self.repo.get_payment_by_order_id.assert_called_once()
        self.repo.update_payment.assert_called_once()

        # Verify error was logged
        self.logger.error.assert_called_with("Error processing webhook: Update failed")

    async def test_handle_webhook_with_different_payment_status(self):
        """Test webhook processing with FAILED status"""
        payment = Mock()
        payment.id = 15
        self.repo.get_payment_by_order_id.return_value = payment

        self.client.handle_callback.return_value = {
            "order_id": "order_test456",
            "status": PaymentStatusEnum.FAILED,
            "payment_id": "pay_456",
            "payment_method": "netbanking",
        }

        result = await self.service.handle_webhook(
            self.webhook_payload, self.raw_body, self.signature
        )

        # Verify payment was updated with FAILED status
        self.repo.update_payment.assert_called_once_with(
            15,
            {
                "payment_status": PaymentStatusEnum.FAILED,
                "payment_method": "netbanking",
                "payment_id": "pay_456",
                "additional_info": self.webhook_payload,
            },
        )

        assert result["status"] == PaymentStatusEnum.FAILED

    async def test_handle_webhook_with_empty_order_id_string(self):
        """Test webhook processing when order_id is empty string"""
        self.client.handle_callback.return_value = {
            "order_id": "",
            "status": PaymentStatusEnum.SUCCESS,
            "payment_id": "pay_789",
            "payment_method": "wallet",
        }

        result = await self.service.handle_webhook(
            self.webhook_payload, self.raw_body, self.signature
        )

        # Verify payment lookup was NOT attempted (empty string is falsy)
        self.repo.get_payment_by_order_id.assert_not_called()

        # Verify payment was NOT updated
        self.repo.update_payment.assert_not_called()

        assert result["order_id"] == ""
        assert result["status"] == PaymentStatusEnum.SUCCESS

    async def test_handle_webhook_preserves_full_payload_in_additional_info(self):
        """Test that the full webhook payload is stored in additional_info"""
        payment = Mock()
        payment.id = 20
        self.repo.get_payment_by_order_id.return_value = payment

        complex_payload = {
            "event": "payment.captured",
            "payload": {
                "payment": {
                    "entity": {
                        "id": "pay_complex",
                        "amount": 50000,
                        "currency": "INR",
                        "method": "card",
                        "card": {"network": "Visa", "last4": "1234"},
                    }
                }
            },
            "created_at": 1234567890,
        }

        await self.service.handle_webhook(
            complex_payload, self.raw_body, self.signature
        )

        # Verify the full payload is passed to additional_info
        call_args = self.repo.update_payment.call_args
        assert call_args[0][1]["additional_info"] == complex_payload


@pytest.mark.asyncio
class TestReconcilePendingPayments:

    @pytest.fixture(autouse=True)
    def setup(self, mock_get_payment_client):
        self.repo = AsyncMock()
        self.logger = AsyncMock(spec=ConsoleServiceLogger)
        self.client = Mock()
        mock_get_payment_client.return_value = self.client
        self.service = PaymentService(repository=self.repo, logger=self.logger)

    async def test_no_pending_payments_is_a_noop(self):
        self.repo.get_stale_pending_payments.return_value = []

        result = await self.service.reconcile_pending_payments()

        assert result == {"checked": 0, "succeeded": 0, "failed": 0}
        self.client.fetch_order.assert_not_called()
        self.repo.update_payment.assert_not_called()

    async def test_captured_payment_is_marked_success(self):
        payment = Mock()
        payment.id = 1
        payment.order_id= UUID("10010010-0100-1001-0010-010010010010")
        payment.merchant_transaction_id = "order_abc"
        self.repo.get_stale_pending_payments.return_value = [payment]

        self.client.fetch_order.return_value = {"status": "paid"}
        self.client.fetch_order_payments.return_value = {
            "items": [{"id": "pay_abc", "status": "captured", "method": "upi"}]
        }

        result = await self.service.reconcile_pending_payments()

        assert result == {"checked": 1, "succeeded": 1, "failed": 0}
        self.repo.update_payment.assert_called_once_with(
            1,
            {
                "payment_status": PaymentStatusEnum.SUCCESS,
                "payment_id": "pay_abc",
                "payment_method": "upi",
            },
        )

    async def test_no_attempt_yet_is_left_alone(self):
        """Order still 'created': customer hasn't tried paying yet."""
        payment = Mock()
        payment.id = 2
        payment.order_id= UUID("20020020-0200-2002-0020-020020020020")
        payment.merchant_transaction_id = "order_def"
        self.repo.get_stale_pending_payments.return_value = [payment]

        self.client.fetch_order.return_value = {"status": "created"}

        result = await self.service.reconcile_pending_payments()

        assert result == {"checked": 1, "succeeded": 0, "failed": 0}
        self.client.fetch_order_payments.assert_not_called()
        self.repo.update_payment.assert_not_called()

    async def test_all_attempts_failed_is_marked_failed(self):
        """Order 'attempted' with every charge attempt failed: a genuine
        gateway failure, not a lost webhook for a success."""
        payment = Mock()
        payment.id = 5
        payment.order_id= UUID("50050050-0500-5005-0050-050050050050")
        payment.merchant_transaction_id = "order_ghi"
        self.repo.get_stale_pending_payments.return_value = [payment]

        self.client.fetch_order.return_value = {"status": "attempted"}
        self.client.fetch_order_payments.return_value = {
            "items": [{"id": "pay_ghi", "status": "failed"}]
        }

        result = await self.service.reconcile_pending_payments()

        assert result == {"checked": 1, "succeeded": 0, "failed": 1}
        self.repo.update_payment.assert_called_once_with(
            5,
            {
                "payment_status": PaymentStatusEnum.FAILED,
                "payment_id": "pay_ghi",
            },
        )

    async def test_attempted_with_one_still_in_flight_is_left_alone(self):
        """Order 'attempted' but one attempt is still authorized/created:
        a retry is still possible, so don't call it FAILED yet."""
        payment = Mock()
        payment.id = 6
        payment.order_id= UUID("60060060-0600-6006-0060-060060060060")
        payment.merchant_transaction_id = "order_jkl"
        self.repo.get_stale_pending_payments.return_value = [payment]

        self.client.fetch_order.return_value = {"status": "attempted"}
        self.client.fetch_order_payments.return_value = {
            "items": [
                {"id": "pay_jkl_1", "status": "failed"},
                {"id": "pay_jkl_2", "status": "authorized"},
            ]
        }

        result = await self.service.reconcile_pending_payments()

        assert result == {"checked": 1, "succeeded": 0, "failed": 0}
        self.repo.update_payment.assert_not_called()

    async def test_one_failure_does_not_abort_the_batch(self):
        bad_payment = Mock()
        bad_payment.id = 3
        bad_payment.order_id= UUID("30030030-0300-3003-0030-030030030030")
        bad_payment.merchant_transaction_id = "order_bad"

        good_payment = Mock()
        good_payment.id = 4
        good_payment.order_id= UUID("40040040-0400-4004-0040-040040040040")
        good_payment.merchant_transaction_id = "order_good"

        self.repo.get_stale_pending_payments.return_value = [
            bad_payment,
            good_payment,
        ]

        def fetch_order_side_effect(order_id):
            if order_id == "order_bad":
                raise Exception("gateway timeout")
            return {"status": "paid"}

        self.client.fetch_order.side_effect = fetch_order_side_effect
        self.client.fetch_order_payments.return_value = {
            "items": [{"id": "pay_good", "status": "captured", "method": "card"}]
        }

        result = await self.service.reconcile_pending_payments()

        assert result == {"checked": 2, "succeeded": 1, "failed": 0}
        self.repo.update_payment.assert_called_once_with(
            4,
            {
                "payment_status": PaymentStatusEnum.SUCCESS,
                "payment_id": "pay_good",
                "payment_method": "card",
            },
        )
