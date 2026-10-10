from celery import Celery
from celery.schedules import crontab

from src.loggers.console_celery_logger import CeleryLogger

celery_logger = CeleryLogger.get_logger()


def create_celery(
    app_name: str,
    broker_url: str,
    backend_url: str = None,
    task_modules: list = None,
    config_module: str = None,
) -> Celery:
    try:
        celery_logger.info(
            f"Creating Celery app '{app_name}' with broker='{broker_url}' and backend='{backend_url}'"
        )

        celery = Celery(app_name, broker=broker_url, backend=backend_url)
        celery.conf.update(
            task_track_started=True,
            worker_concurrency=10,
            task_always_eager=False,
            task_time_limit=1200,  # 20 minutes
        )

        celery.conf.beat_schedule = {
            # Cleanup abandoned pending orders (every 12 minutes)
            "cleanup_abandoned_pending_orders": {
                "task": "cleanup_abandoned_pending_orders",
                "schedule": crontab(minute="*/12"),
            },
            # Activate pending entitlements (every hour)
            "activate_pending_entitlements": {
                "task": "activate_pending_entitlements",
                "schedule": crontab(minute=0),
            },
            # Expire active grace periods (every day at 12:01 AM UTC)
            "expire_active_grace_periods": {
                "task": "expire_active_grace_periods",
                "schedule": crontab(hour=0, minute=1),
            },
            "send_wallet_email" : {
                "task" : "send_wallet_email",
                "schedule" : crontab(hour=9, minute=30)
            },
            "order_report_generation" : {
                "task" : "order_report_generation",
                "schedule" : crontab(hour=9, minute=30)
            },
            "upcoming_expiry_report_genration" : {
                "task" : "upcoming_expiry_report_genration",
                "schedule" : crontab(hour=9, minute=30)
            },
            "send_expiry_overdue_order_report" : {
                "task" : "send_expiry_overdue_order_report",
                "schedule" : crontab(hour=9, minute=30)
            },
            # Fallback for a payment webhook that never arrived: re-checks
            # payments still PENDING directly against the gateway.
            "reconcile_pending_payments" : {
                "task" : "reconcile_pending_payments",
                "schedule" : crontab(minute="*/10")
            },
        }

        if config_module:
            celery.config_from_object(config_module)
            celery_logger.info(f"Loaded Celery config from module: {config_module}")

        if task_modules:
            celery.autodiscover_tasks(task_modules)
            celery_logger.info(f"Autodiscovered tasks from modules: {task_modules}")

        celery_logger.info(f"Celery app '{app_name}' created successfully")
        return celery

    except Exception as e:
        celery_logger.exception(f"Failed to create Celery app '{app_name}': {e}")
        raise
