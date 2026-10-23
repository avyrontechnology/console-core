from uuid import UUID
from typing import Any, Dict, List, Optional

from sqlalchemy import func, select

from src.components.payment.enum import PaymentStatusEnum
from src.components.payment.errors import PaymentNotFoundError
from src.components.payment.models import Payment
from src.loggers.console_service_logger import ConsoleServiceLogger


class PaymentRepository:
    """Repository for payment DB operations."""

    def __init__(self, session_factory, logger: ConsoleServiceLogger):
        self.session_factory = session_factory
        self.logger: ConsoleServiceLogger = logger

    async def create_payment(self, payment: Payment) -> Payment:
        async with self.session_factory() as session:
            try:
                session.add(payment)
                await session.commit()
                await session.refresh(payment)
                self.logger.info(
                    "Payment created successfully: {}".format(payment.order_id)
                )
                return payment
            except Exception as e:
                await session.rollback()
                self.logger.error(
                    "Error creating payment {}: {}".format(payment.order_id, e)
                )
                raise

    async def get_payment_by_order_id(self, order_id: str) -> Optional[Payment]:
        async with self.session_factory() as session:
            try:
                result = await session.execute(
                    select(Payment).where(Payment.merchant_transaction_id == order_id)
                )
                payment = result.scalar_one_or_none()
                self.logger.info("Fetched payment for order_id: {}".format(order_id))
                return payment
            except Exception as e:
                self.logger.error("Error fetching payment {}: {}".format(order_id, e))
                raise

    async def update_payment(self, payment_id: UUID, data: Dict[str, Any]) -> Payment:
        async with self.session_factory() as session:
            try:
                payment = await session.get(Payment, payment_id)
                if payment is None:
                    raise PaymentNotFoundError(payment_id)

                for key, value in data.items():
                    setattr(payment, key, value)

                await session.commit()
                await session.refresh(payment)
                self.logger.info("Payment updated: {}".format(payment_id))
                return payment
            except Exception as e:
                await session.rollback()
                self.logger.error(
                    "Error updating payment {}: {}".format(payment_id, repr(e))
                )
                raise

    async def get_payments_by_partner(
        self,
        partner_id: UUID,
        limit: Optional[int] = None,
        offset: Optional[int] = None,
    ) -> tuple[List[Payment], int]:
        async with self.session_factory() as session:
            try:
                # Base query (latest first)
                base_query = (
                    select(Payment)
                    .where(Payment.partner_id == partner_id)
                    .order_by(Payment.created_at.desc())
                )

                # Count query
                count_query = select(func.count()).select_from(base_query.subquery())
                total_count = (await session.execute(count_query)).scalar() or 0

                # Pagination (page-based)
                if limit and offset:
                    offset = (offset - 1) * limit
                    base_query = base_query.offset(offset).limit(limit)

                # Execute query
                result = await session.execute(base_query)
                payments = result.scalars().all()

                self.logger.info(
                    "Fetched {} payments (total: {}) for partner {}".format(
                        len(payments), total_count, partner_id
                    )
                )

                return payments, total_count

            except Exception as e:
                self.logger.error(
                    "Error fetching payments for partner {}: {}".format(partner_id, e)
                )
                raise

    async def get_stale_pending_payments(
        self, older_than_ms: int, newer_than_ms: int, limit: int = 100
    ) -> List[Payment]:
        """
        PENDING payments old enough that a webhook should have already
        landed, but not so old they're written off as abandoned — the
        window a reconciliation cron re-checks against the gateway.
        """
        async with self.session_factory() as session:
            try:
                result = await session.execute(
                    select(Payment)
                    .where(
                        Payment.payment_status == PaymentStatusEnum.PENDING,
                        Payment.created_at <= older_than_ms,
                        Payment.created_at >= newer_than_ms,
                    )
                    .order_by(Payment.created_at.asc())
                    .limit(limit)
                )
                payments = list(result.scalars().all())
                self.logger.info(
                    "Fetched {} stale pending payments".format(len(payments))
                )
                return payments
            except Exception as e:
                self.logger.error("Error fetching stale pending payments: {}".format(e))
                raise
