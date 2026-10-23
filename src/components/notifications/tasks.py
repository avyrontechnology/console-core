from uuid import UUID
import asyncio
import inspect
from typing import List
from dependency_injector.wiring import Provide, inject
import asyncio

from src.console_celery.celery_app import celery, Container
from src.console_celery.async_utils import run_async
# from src.core.container import Container
from dependency_injector.wiring import Provide, inject
from src.loggers.console_celery_logger import CeleryLogger
from src.components.notifications.factory import NotificationChannelFactory
from src.components.notifications.services import NotificationService
from src.components.notifications.models import NotificationHistory, NotificationSubscription
from src.components.notifications.constants import NotificationServiceType

celery_logger = CeleryLogger.get_logger()

# TODO Need a different queue for notifications tasks


@celery.task(bind=True, name="dispatch_notification", acks_late=True, reject_on_worker_lost=True)
def dispatch_notification_task(
    self,
    user_id: UUID, 
    title: str, 
    body: str, 
    data: dict,
    source: str,
    event_name: str,
    service_type: str,
    channel_factory: NotificationChannelFactory = Provide[Container.notification_channel_factory],
    notification_service: NotificationService = Provide[Container.notification_service]
):
    service_type = NotificationServiceType(service_type)

    async def process_single_subscription(sub: NotificationSubscription):
        try:
            channel_handler = channel_factory.get_channel(sub.channel_type)
            
            # Execute the strategy
            status: str = channel_handler.send(
                identifier=sub.identifier, title=title, body=body, data=data, service_type=service_type
            )
            
            if status == "SUCCESS":
                celery_logger.info(f"Notification sent successfully via {sub.channel_type} to {sub.identifier} for service {service_type}")
            elif status == "UNREGISTERED":
                # Automatically clean up the database!
                await notification_service.deactivate_subscription(sub.user_id, sub.identifier, service_type)
            else:
                celery_logger.warning(f"Failed to send notification via {sub.channel_type} to {sub.identifier} for service {service_type}")
                
        except ValueError as e:
            celery_logger.warning(f"Configuration Error: {str(e)}")

        except Exception as e:
            celery_logger.error(f"Unexpected error sending via {sub.channel_type}: {e}")
            # If you want Celery to retry on failure, you can trigger self.retry(exc=e) here.

    async def main():
        nonlocal channel_factory, notification_service

        try:
            celery_logger.info(f"Dispatching notification to user {user_id}")

            if user_id is None:
                # Guard the worker from creating history rows with an invalid
                # recipient when an upstream event payload is malformed.
                celery_logger.warning("Skipping notification dispatch with empty user_id")
                return

            # Resolve the service objects only after the worker loop is active.
            # Dependency-injector can touch async resources during sync task
            # wiring, which breaks Celery startup on Python 3.11.
            channel_factory = Container.notification_channel_factory()
            notification_service = Container.notification_service()
            
            if asyncio.isfuture(notification_service):
            # if inspect.isawaitable(notification_service):
                # Keep dependency-injector compatibility if the provider resolves lazily.
                notification_service = await notification_service

            # Preference gate lives before history creation so disabled
            # source/scope combinations do not create inbox rows or fan out.
            enabled = await notification_service.should_send_notification(
                user_id=user_id,
                source=source,
                event_name=event_name,
            )

            if not enabled:
                # Explicit opt-out means we ignore the event completely.
                celery_logger.info(
                    f"{source} notifications for {event_name} disabled for user {user_id}"
                )
                return

            # Persist exactly one logical notification record before delivery.
            await notification_service.save_notification_history(
                user_id=user_id,
                title=title,
                body=body,
                data=data,
                service_type=service_type,
            )

            # Deliver to every active device after history has been recorded.
            # 2. THEN SENDING PUSH NOTIFICATIONS
            subscriptions = await notification_service.get_active_user_subscriptions(user_id, service_type)

            if not subscriptions:
                celery_logger.info(f"No active devices to push to for user {user_id} services {service_type}. Saved to history only.")
                return

            # Re-validate immediately before dispatch — the earlier check can go stale by
            # the time delivery actually happens (blocking FCM calls, worker backlog, etc).
            if not await notification_service.has_active_session_for_push(user_id, service_type):
                celery_logger.info(f"Session expired before delivery — skipping push for user {user_id}, service {service_type}.")
                return

            celery_logger.info(f"Found {len(subscriptions)} active subscriptions for service {service_type} Pushing...")
            for sub in subscriptions:
                await process_single_subscription(sub)
                                 
        except Exception as exp:
            celery_logger.error(f"Failed to dispatch notifications for user {user_id}, service {service_type}: {exp}")

    run_async(main())


# @celery_app.task(name="console.notifications.handle_event")
# def handle_notification_event(event):

#     event_name = event.get("event_name")
#     payload = event.get("payload")

#     if event_name == "LEAD_CREATED":
#         print("Handle lead created notification", payload)
