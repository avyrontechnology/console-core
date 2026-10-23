import json
from uuid import UUID

from src.components.notifications.schemas import CommonNotificationMessage
from src.console_celery.celery_app import celery
from src.components.notifications.tasks import dispatch_notification_task
from src.loggers.console_celery_logger import CeleryLogger
from src.components.notifications.constants import NotificationServiceType


celery_logger = CeleryLogger.get_logger()


def _resolve_notification_user_id(message: dict, payload: dict | None = None) -> UUID | None:
    """
    Keep the queue contract tolerant for lead and bulk lead events.
    Some emitters send the recipient under payload.assigned_to, while others
    may already flatten it to payload.user_id or a top-level user_id.
    Queue payloads carry UUIDs as strings: parse to UUID, None when absent.
    """
    payload = payload if isinstance(payload, dict) else (message.get("payload") or {})
    if isinstance(payload, str):
        payload = {}
    raw = (
        payload.get("assigned_to")
        or payload.get("user_id")
        or message.get("user_id")
    )
    if raw is None:
        return None
    try:
        return raw if isinstance(raw, UUID) else UUID(str(raw))
    except ValueError:
        return None


def _normalize_payload(payload):
    if isinstance(payload, str):
        try:
            parsed = json.loads(payload)
        except json.JSONDecodeError:
            return {}
        return parsed if isinstance(parsed, dict) else {}
    return payload or {}

@celery.task(
    name="common_notifications_queue.handle_event",
    queue="common_notifications_queue"
)
def handle_event(message):
    """
    Entry point for the shared queue.

    The payload is intentionally normalized here so the rest of the pipeline
    can rely on one documented contract regardless of which service published it.
    """
    event = CommonNotificationMessage.model_validate(message)
    celery_logger.info(f"Event received: {event.model_dump()}")
    source = message.get("source")
    try:
        service_type = NotificationServiceType(source)
    except (ValueError, TypeError):
        celery_logger.error(f"Unsupported notification source: {source}")
        return

    payload = _normalize_payload(event.payload)
        # Producers send the reference identifiers directly
    # on `payload` (flat), not nested under a second "payload" key. Fall back
    # to the flat payload itself when there is no nested payload, so the
    # lead reference data (lead_request_id, assigned_to, lead_name, etc.)
    # actually reaches data_payload instead of being silently dropped.
    nested_payload = (_normalize_payload(payload.get("payload"))
        if "payload" in payload
        else payload
    )

    dispatch_notification_task.apply(
        kwargs={
            # Queue boundary: console IDs are UUIDs; producers send strings.
            "user_id": _resolve_notification_user_id(message, payload),
            "title": event.heading,
            "body": event.body,
            "data": nested_payload,
            "source": event.source.value,
            "event_name": event.event_name,
            "service_type": service_type.value,
        }
    )


    
    
