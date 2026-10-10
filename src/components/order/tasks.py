import asyncio
from datetime import date, datetime, timedelta, timezone
from typing import List

from dependency_injector.wiring import Provide, inject

from src.components.order.models import Order
from src.components.order.repositories import OrderRepository
from src.components.payment.enum import PaymentStatusEnum
from src.console_celery.celery_app import celery
from src.core.container import Container, OrderService
from src.loggers.console_celery_logger import CeleryLogger

logger = CeleryLogger.get_logger()

TIMEOUT_MINUTES = 20


@celery.task(
    bind=True,
    name="cleanup_abandoned_pending_orders",
    max_retries=0,
    acks_late=True,
    reject_on_worker_lost=True,
)
@inject
def cleanup_abandoned_pending_orders(
    self,
    order_repo: OrderRepository = Provide[Container.order_repository],
):
    """
    Celery task that:
    - Finds pending orders older than 30 minutes
    - Marks them as FAILED (abandoned/expired)
    - Runs periodically (every 12 minutes via Celery Beat)
    """

    async def cleanup_old_pending_orders():
        try:
            cutoff: datetime = datetime.now(timezone.utc) - timedelta(
                minutes=TIMEOUT_MINUTES
            )

            cutoff_ms: int = int(cutoff.timestamp() * 1000)

            logger.info(
                f"Starting cleanup of pending orders older than {TIMEOUT_MINUTES} minutes..."
            )

            updated_count = await order_repo.expire_pending_orders_before(cutoff_ms)

            if updated_count == 0:
                logger.info("No abandoned pending orders found for cleanup.")
            else:
                logger.info(f"Expired {updated_count} abandoned pending orders.")

            logger.info(f"Cleanup completed. Expired {updated_count} pending orders.")

        except Exception as e:
            logger.error(f"Critical error in cleanup_abandoned_pending_orders: {e}")

    asyncio.run(cleanup_old_pending_orders())



@celery.task(
    bind=True,
    name="order_report_generation",
    max_retries=0,
    acks_late=True,
    reject_on_worker_lost=True,
)
@inject
def order_report_generation(
    self,
    order_service: OrderService = Provide[Container.order_service]
):
    try:
        logger.info("Entered in the order report task")
        asyncio.run(order_service.send_daily_order_report())
    except Exception as exp:
        logger.error(f"Got the exception as {exp}")


@celery.task(
    bind=True,
    name="upcoming_expiry_report_genration",
    max_retries=0,
    acks_late=True,
    reject_on_worker_lost=True,
)
@inject
def upcoming_expiry_report_genration(
    self,
    order_service: OrderService = Provide[Container.order_service]
):
    try:
        logger.info("Entered in the order report task")
        
        asyncio.run(order_service.send_approaching_renewal_report())
    except Exception as exp:
        logger.error(f"Got the exception as {exp}")

@celery.task(
    bind=True,
    name="send_expiry_overdue_order_report",
    max_retries=0,
    acks_late=True,
    reject_on_worker_lost=True,
)
@inject
def send_expiry_overdue_order_report(
    self,
    order_service: OrderService = Provide[Container.order_service]
):
    try:
        logger.info("Entered in the order report task")
        today = datetime.utcnow().date()
        reference_date = date(2026, 6, 22)  # any fixed start date
        if (today - reference_date).days % 2 != 0:
            return
        
        
        asyncio.run(order_service.send_expiry_overdue_order_report())
    except Exception as exp:
        logger.error(f"Got the exception as {exp}")