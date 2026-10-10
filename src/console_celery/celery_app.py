from src.core.container import Container
from src.console_celery.celery_config import APP_NAME, REDIS_URL, TASK_MODULES
from src.console_celery.celery_utils import create_celery
from src.console_celery import celery_config
from kombu import Queue

celery = create_celery(
    app_name=APP_NAME,
    broker_url=REDIS_URL,
    backend_url=REDIS_URL,
    task_modules=TASK_MODULES,
    config_module=celery_config,
)

celery.conf.task_queues = (
    Queue("common_notifications_queue"),
    Queue("notification_queue"),
    Queue("user_queue"),
    Queue('console_default_queue'),
    Queue("report_queue"),
    # Queue("celery"),
    Queue("order_queue"),
    Queue("entitlement_queue"),
    Queue("grace_queue")
)

celery.container = Container()

# Registers worker_process_init / shutdown signals that give each forked worker
# a dedicated event loop and a fresh DB engine (see module docstring).
from src.console_celery import async_utils  # noqa: E402,F401

# To Run Celery Worker
# celery -A console.celery_app.celery worker --loglevel=info -Q console_queue
