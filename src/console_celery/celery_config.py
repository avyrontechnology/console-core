"""
task_routes: Routes tasks to specific queues based on their module names (e.g., leads_queue for lead tasks).
task_default_queue: Defines a fallback queue for tasks not matching any route.
task_acks_late: Ensures tasks are acknowledged only after successful execution, improving reliability.
worker_prefetch_multiplier: Controls how many tasks are prefetched by workers at a time (set to 1 for safer, sequential task processing).
result_expires: Specifies how long the task results will be stored in the backend before they expire.
timezone: Sets the timezone for scheduling tasks (typically UTC).
enable_utc: Ensures UTC is used for all time-related operations in Celery.
"""

from src.core.environment import ENV

# Celery configuration constants
REDIS_URL = f"{ENV.CACHE_PROTOCOL}://{ENV.CACHE_USERNAME}:{ENV.CACHE_PASSWORD}@{ENV.CACHE_HOST}:{ENV.CACHE_PORT}/{ENV.CACHE_DB}?ssl_cert_reqs=CERT_NONE"
APP_NAME = ENV.SERVICE_NAME

# Task modules for auto-discovery
TASK_MODULES = [
    "src.components.order.tasks",
    "src.components.entitlement.tasks",
    "src.components.notifications.listeners",
    "src.components.notifications.tasks",
    "src.components.grace.tasks",
    "src.components.user.tasks",
    "src.components.wallet.tasks",
    "src.components.payment.tasks",
]

# task_routes = {
#     "src.components.order.tasks.*": {"queue": "order_queue"},
#     "src.components.entitlement.tasks.*": {"queue": "entitlement_queue"},
#     "src.components.grace.tasks.*": {"queue": "grace_queue"},
#     "src.components.notifications.listeners.*" : {"queue": "common_notifications_queue"},
#     "src.components.notifications.tasks.*" : {"queue" : "notification_queue"},
#     "src.components.user.tasks.*": {"queue": "user_queue"},
#     "src.components.wallet.tasks.*": {"queue" : "report_queue"}
# }

task_routes = {
    "cleanup_abandoned_pending_orders" : {"queue": "order_queue"},
    "activate_pending_entitlements" : {"queue": "entitlement_queue"},
    "expire_active_grace_periods"  : {"queue": "grace_queue"},
    "send_wallet_email" : {"queue" : "report_queue"},
    "order_report_generation" : {"queue" : "report_queue"},
    "upcoming_expiry_report_genration" : {"queue" : "report_queue"},
    "send_expiry_overdue_order_report" : {"queue" : "report_queue"},
    "src.components.notifications.listeners.*" : {"queue": "common_notifications_queue"},
    "src.components.notifications.tasks.*" : {"queue" : "notification_queue"},
}

task_default_queue = "console_default_queue"
task_acks_late = True
worker_prefetch_multiplier = 1
result_expires = 60 * 60 * 60
timezone = "UTC"
enable_utc = True
