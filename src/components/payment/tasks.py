import asyncio

from dependency_injector.wiring import Provide, inject

from src.components.payment.services import PaymentService
from src.console_celery.celery_app import celery
from src.core.container import Container
from src.loggers.console_celery_logger import CeleryLogger

logger = CeleryLogger.get_logger()


@celery.task(
    bind=True,
    name="reconcile_pending_payments",
    max_retries=0,
    acks_late=True,
    reject_on_worker_lost=True,
)
@inject
def reconcile_pending_payments(
    self,
    payment_service: PaymentService = Provide[Container.payment_service],
):
    """
    Celery task that:
    - Re-checks payments still PENDING against the gateway directly
    - Fallback for when a webhook never arrives
    - Runs periodically (every 10 minutes via Celery Beat)
    """

    async def run_reconciliation():
        try:
            result = await payment_service.reconcile_pending_payments()
            logger.info(f"Payment reconciliation complete: {result}")
        except Exception as e:
            logger.error(f"Critical error in reconcile_pending_payments: {e}")

    asyncio.run(run_reconciliation())
