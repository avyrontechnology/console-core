from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy.exc import IntegrityError

from src.components.payment.enum import (
    EntityNameEnum,
    PaymentClientEnum,
    PaymentStatusEnum,
)
from src.components.payment.errors import PaymentNotFoundError
from src.components.payment.models import Payment
from src.components.payment.repositories import PaymentRepository


@pytest.mark.asyncio
class TestPaymentRepository:
    @pytest.fixture(autouse=True)
    def setup_class(self, mock_session_factory, mock_logger):
        """Setup repository, mock session and logger."""
        # Create new mocks for each test (isolated)
        self.session = MagicMock()
        self.session.add = MagicMock()
        self.session.commit = AsyncMock()
        self.session.rollback = AsyncMock()
        self.session.refresh = AsyncMock()
        self.session.merge = AsyncMock()
        self.session.execute = AsyncMock()

        # Context manager mock for async session
        mock_session_ctx = MagicMock()
        mock_session_ctx.__aenter__.return_value = self.session
        mock_session_ctx.__aexit__.return_value = None

        mock_session_factory.return_value = mock_session_ctx
        self.mock_logger = MagicMock()

        # Repository under test
        self.payment_repo = PaymentRepository(
            session_factory=mock_session_factory,
            logger=self.mock_logger,
        )

        # Sample payment model
        self.mock_payment = Payment(
            partner_id=1,
            amount=100.50,
            order_id="order_123",
            entity_name=EntityNameEnum.BABBLER_WALLET,
            vendor=PaymentClientEnum.RAZORPAY,
            payment_status=PaymentStatusEnum.PENDING,
            additional_info={"note": "test payment"},
        )

    async def test_create_payment_success(self):
        """Test successful payment creation."""
        result = await self.payment_repo.create_payment(self.mock_payment)

        # add() is sync
        self.session.add.assert_called_once_with(self.mock_payment)
        # commit and refresh are async
        self.session.commit.assert_awaited_once()
        self.session.refresh.assert_awaited_once_with(self.mock_payment)

        self.mock_logger.info.assert_called_once_with(
            f"Payment created successfully: {self.mock_payment.order_id}"
        )
        assert result == self.mock_payment

    async def test_create_payment_failure(self):
        """Test payment creation failure triggers rollback."""
        self.session.commit.side_effect = IntegrityError("fail", {}, None)

        with pytest.raises(IntegrityError):
            await self.payment_repo.create_payment(self.mock_payment)

        self.session.rollback.assert_awaited_once()
        self.mock_logger.error.assert_called_once()

    async def test_get_payment_by_order_id_success(self):
        """Test fetching payment by order_id."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = self.mock_payment
        self.session.execute.return_value = mock_result

        result = await self.payment_repo.get_payment_by_order_id("order_123")

        self.session.execute.assert_awaited_once()
        self.mock_logger.info.assert_called_once_with(
            "Fetched payment for order_id: order_123"
        )
        assert result == self.mock_payment

    async def test_get_payment_by_order_id_exception(self):
        """Test error handling in get_payment_by_order_id."""
        self.session.execute.side_effect = Exception("DB Error")

        with pytest.raises(Exception):
            await self.payment_repo.get_payment_by_order_id("order_123")

        self.mock_logger.error.assert_called_once_with(
            "Error fetching payment order_123: DB Error"
        )

    async def test_update_payment_success(self):
        """Test successful payment update."""
        self.session.get = AsyncMock(return_value=self.mock_payment)

        await self.payment_repo.update_payment(
            payment_id=1, data={"payment_status": "SUCCESS"}
        )

        self.session.get.assert_awaited_once_with(Payment, 1)
        self.session.commit.assert_awaited_once()
        self.session.refresh.assert_awaited_once_with(self.mock_payment)

        self.mock_logger.info.assert_called_once_with("Payment updated: 1")

    async def test_update_payment_failure(self):
        """Test update failure triggers rollback."""
        self.session.get = AsyncMock(return_value=self.mock_payment)
        self.session.commit.side_effect = Exception("Update failed")

        with pytest.raises(Exception):
            await self.payment_repo.update_payment(
                payment_id=1, data={"payment_status": "FAILED"}
            )

        self.session.rollback.assert_awaited_once()
        self.mock_logger.error.assert_called_once()

    async def test_get_payments_by_partner_success(self):
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [self.mock_payment]
        mock_result.scalar.return_value = 1

        self.session.execute.side_effect = [
            MagicMock(scalar=MagicMock(return_value=1)),  # count query
            mock_result,  # data query
        ]

        payments, total = await self.payment_repo.get_payments_by_partner(1)

        assert self.session.execute.await_count == 2
        assert payments == [self.mock_payment]
        assert total == 1

    async def test_get_payments_by_partner_failure(self):
        """Test failure while fetching payments by partner."""
        self.session.execute.side_effect = Exception("Query failed")

        with pytest.raises(Exception):
            await self.payment_repo.get_payments_by_partner(1)

        self.mock_logger.error.assert_called_once_with(
            "Error fetching payments for partner 1: Query failed"
        )

    async def test_update_payment_not_found(self):
        """Test update when payment does not exist."""
        self.session.get = AsyncMock(return_value=None)

        with pytest.raises(PaymentNotFoundError):
            await self.payment_repo.update_payment(999, {"payment_status": "FAILED"})

        self.session.get.assert_awaited_once_with(Payment, 999)
        self.mock_logger.error.assert_called_once()

    async def test_create_payment_refresh_failure(self):
        """Test failure during refresh triggers rollback."""
        self.session.refresh.side_effect = Exception("Refresh error")

        with pytest.raises(Exception):
            await self.payment_repo.create_payment(self.mock_payment)

        self.session.rollback.assert_awaited_once()
        self.mock_logger.error.assert_called_once()

    async def test_get_payment_by_order_id_not_found(self):
        """Test get_payment_by_order_id returning None."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        self.session.execute.return_value = mock_result

        result = await self.payment_repo.get_payment_by_order_id("order_123")

        assert result is None
        self.mock_logger.info.assert_called_once_with(
            "Fetched payment for order_id: order_123"
        )

    async def test_get_payments_by_partner_empty(self):
        mock_count_result = MagicMock()
        mock_count_result.scalar.return_value = 0

        mock_data_result = MagicMock()
        mock_data_result.scalars.return_value.all.return_value = []

        self.session.execute.side_effect = [
            mock_count_result,
            mock_data_result,
        ]

        payments, total = await self.payment_repo.get_payments_by_partner(5)

        assert payments == []
        assert total == 0

    async def test_get_stale_pending_payments_success(self):
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [self.mock_payment]
        self.session.execute.return_value = mock_result

        payments = await self.payment_repo.get_stale_pending_payments(
            older_than_ms=2000, newer_than_ms=1000, limit=50
        )

        self.session.execute.assert_awaited_once()
        assert payments == [self.mock_payment]

    async def test_get_stale_pending_payments_empty(self):
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        self.session.execute.return_value = mock_result

        payments = await self.payment_repo.get_stale_pending_payments(
            older_than_ms=2000, newer_than_ms=1000
        )

        assert payments == []

    async def test_get_stale_pending_payments_failure(self):
        self.session.execute.side_effect = Exception("Query failed")

        with pytest.raises(Exception):
            await self.payment_repo.get_stale_pending_payments(
                older_than_ms=2000, newer_than_ms=1000
            )

        self.mock_logger.error.assert_called_once()
