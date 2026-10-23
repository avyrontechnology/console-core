import asyncio
from celery import shared_task
from dependency_injector.wiring import Provide, inject

from src.components.wallet.services import WalletService
from src.core.container import Container


from src.loggers.console_celery_logger import CeleryLogger
from src.console_celery.celery_app import celery


from datetime import timezone, datetime

logger = CeleryLogger.get_logger()


@celery.task(
    bind=True,
    name="send_wallet_email",
    max_retries=0,
    acks_late=True,
    reject_on_worker_lost=True
)
@inject
def send_wallet_email(
    self,
    wallet_service: WalletService = Provide[Container.wallet_service]
):
    try:
        logger.info("Entered in the task")
        asyncio.run(wallet_service.send_partner_wallet_balance_email())
    except Exception as exp:
        logger.error(f"Got the exception as {exp}")

