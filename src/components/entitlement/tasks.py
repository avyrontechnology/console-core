import asyncio

from dependency_injector.wiring import Provide, inject

from src.components.entitlement.services import EntitlementService
from src.console_celery.celery_app import celery
from src.core.container import Container
from src.loggers.console_celery_logger import CeleryLogger

logger = CeleryLogger.get_logger()


@celery.task(
    bind=True,
    name="activate_pending_entitlements",
    max_retries=3,
    acks_late=True,
    reject_on_worker_lost=True,
)
@inject
def activate_pending_entitlements(
    self,
    entitlement_service: EntitlementService = Provide[Container.entitlement_service],
):
    """
    Celery task that:
    - Finds entitlements whose start_date has arrived
    - Activates them (sets is_active=True)
    - Excludes manually deactivated entitlements
    - Runs periodically via Celery Beat (recommended: every 5-15 minutes)

    Business Logic:
    - start_date <= current_time
    - is_active = False
    - is_manually_deactivated = False
    - end_date is None OR end_date >= current_time
    """
    

    async def activate_entitlements():
        try:
            logger.info("Starting activation of pending entitlements...")

            activated_count: int = (
                await entitlement_service.activate_pending_entitlements()
            )

            if activated_count == 0:
                logger.info("No pending entitlements found to activate.")
            else:
                logger.info(f"Successfully activated {activated_count} entitlement(s).")

            logger.info(
                f"Entitlement activation task completed. Activated count: {activated_count}"
            )

        except Exception as e:
            logger.error(
                f"Critical error in activate_pending_entitlements task: {repr(e)}"
            )
            raise

    asyncio.run(activate_entitlements())
