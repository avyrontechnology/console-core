"""Celery task for daily grace period expiry."""

import asyncio

from dependency_injector.wiring import Provide, inject

from src.components.grace.repositories import GraceRepository
from src.console_celery.celery_app import celery
from src.core.container import Container
from src.loggers.console_celery_logger import CeleryLogger

logger = CeleryLogger.get_logger()


@celery.task(
    bind=True,
    name="expire_active_grace_periods",
    max_retries=0,
    acks_late=True,
    reject_on_worker_lost=True,
)
@inject
def expire_active_grace_periods(
    self,
    grace_repo: GraceRepository = Provide[Container.grace_repository],
):
    """
    Celery task that runs daily and marks all ACTIVE grace records whose
    end_date < now as EXPIRED, setting consumed_days = granted_days.

    Schedule: daily (configure via Celery Beat, e.g. every day at 00:05 UTC).
    Idempotent: re-running has no effect on already-EXPIRED records.
    """

    async def _run():
        try:
            logger.info("expire_active_grace_periods: starting")
            expired_count = await grace_repo.expire_overdue()
            if expired_count == 0:
                logger.info(
                    "expire_active_grace_periods: no overdue grace records found"
                )
            else:
                logger.info(
                    "expire_active_grace_periods: expired {} grace record(s)".format(
                        expired_count
                    )
                )
        except Exception as e:
            logger.error("expire_active_grace_periods: critical error — {}".format(e))

    asyncio.run(_run())
