from uuid import UUID
from unittest.mock import MagicMock, patch

from src.components.notifications.constants import NotificationServiceType


class TestHandleEvent:

    @staticmethod
    def _mock_event(
        *,
        source="talko",
        event_name="LEAD_ASSIGNED",
        heading="New lead",
        body="You have a new lead",
        payload=None,
    ):
        event = MagicMock()
        event.source.value = source
        event.event_name = event_name
        event.heading = heading
        event.body = body
        event.payload = payload if payload is not None else {"assigned_to": "55555555-5555-5555-5555-555555555555", "payload": {"lead_id": 10}}
        event.model_dump.return_value = {
            "source": source,
            "event_name": event_name,
            "heading": heading,
            "body": body,
            "payload": event.payload,
        }
        return event

    def test_handle_event_valid_source_dispatches_task(self):
        message = {
            "source": "talko",
            "event_name": "LEAD_ASSIGNED",
            "created_at": 1,
            "heading": "New lead",
            "body": "You have a new lead",
            "payload": {"assigned_to": "55555555-5555-5555-5555-555555555555", "payload": {"lead_id": 10}},
        }
        mock_logger = MagicMock()
        mock_event = self._mock_event(
            heading=message["heading"],
            body=message["body"],
            payload=message["payload"],
        )

        with patch(
            "src.components.notifications.listeners.celery_logger", mock_logger
        ), patch(
            "src.components.notifications.listeners.CommonNotificationMessage.model_validate",
            return_value=mock_event,
        ), patch(
            "src.components.notifications.listeners.dispatch_notification_task.apply"
        ) as mock_apply:
            from src.components.notifications.listeners import handle_event

            handle_event(message)

            mock_apply.assert_called_once_with(
                kwargs={
                    "user_id": UUID("55555555-5555-5555-5555-555555555555"),
                    "title": "New lead",
                    "body": "You have a new lead",
                    "data": {"lead_id": 10},
                    "source": NotificationServiceType.TALKO.value,
                    "event_name": "LEAD_ASSIGNED",
                    "service_type": NotificationServiceType.TALKO.value,
                }
            )

    def test_handle_event_string_payload_is_parsed(self):
        message = {
            "source": "talko",
            "event_name": "LEAD_ASSIGNED",
            "created_at": 1,
            "heading": "New lead",
            "body": "You have a new lead",
            "payload": '{"assigned_to": "55555555-5555-5555-5555-555555555555", "payload": {"lead_id": 10}}',
        }
        mock_logger = MagicMock()
        mock_event = self._mock_event(
            heading=message["heading"],
            body=message["body"],
            payload=message["payload"],
        )

        with patch(
            "src.components.notifications.listeners.celery_logger", mock_logger
        ), patch(
            "src.components.notifications.listeners.CommonNotificationMessage.model_validate",
            return_value=mock_event,
        ), patch(
            "src.components.notifications.listeners.dispatch_notification_task.apply"
        ) as mock_apply:
            from src.components.notifications.listeners import handle_event

            handle_event(message)

            mock_apply.assert_called_once_with(
                kwargs={
                    "user_id": UUID("55555555-5555-5555-5555-555555555555"),
                    "title": "New lead",
                    "body": "You have a new lead",
                    "data": {"lead_id": 10},
                    "source": NotificationServiceType.TALKO.value,
                    "event_name": "LEAD_ASSIGNED",
                    "service_type": NotificationServiceType.TALKO.value,
                }
            )
    def test_handle_event_flat_payload_is_preserved(self):
        message = {
            "source": "talko",
            "event_name": "LEAD_ASSIGNED",
            "created_at": 1,
            "heading": "New lead",
            "body": "You have a new lead",
            "payload": {
                "time": 1787574899088,
                "lead_name": "Meenakshi Chauhan",
                "event_type": "LEAD_ASSIGNED",
                "lead_email": "meenakshi6931@gmail.com",
                "lead_phone": "+916219614894",
                "assigned_to": "33333333-3333-3333-3333-333333333333",
                "lead_request_id": 71567,
                "service_board_id": 70,
            },
        }
        mock_logger = MagicMock()
        mock_event = self._mock_event(
            heading=message["heading"],
            body=message["body"],
            payload=message["payload"],
        )

        with patch(
            "src.components.notifications.listeners.celery_logger", mock_logger
        ), patch(
            "src.components.notifications.listeners.CommonNotificationMessage.model_validate",
            return_value=mock_event,
        ), patch(
            "src.components.notifications.listeners.dispatch_notification_task.apply"
        ) as mock_apply:
            from src.components.notifications.listeners import handle_event

            handle_event(message)

            mock_apply.assert_called_once_with(
                kwargs={
                    "user_id": UUID("33333333-3333-3333-3333-333333333333"),
                    "title": "New lead",
                    "body": "You have a new lead",
                    "data": message["payload"],
                    "source": NotificationServiceType.TALKO.value,
                    "event_name": "LEAD_ASSIGNED",
                    "service_type": NotificationServiceType.TALKO.value,
                }
            )
            
    def test_handle_event_talko_source_dispatches_task(self):
        message = {
            "source": "talko",
            "event_name": "WHATSAPP_MESSAGE_RECEIVED",
            "created_at": 1,
            "heading": "New lead",
            "body": "You have a new lead",
            "payload": {"assigned_to": "77777777-7777-7777-7777-777777777777", "payload": {}},
        }
        mock_logger = MagicMock()
        mock_event = self._mock_event(
            source="talko",
            event_name="WHATSAPP_MESSAGE_RECEIVED",
            heading=message["heading"],
            body=message["body"],
            payload=message["payload"],
        )

        with patch(
            "src.components.notifications.listeners.celery_logger", mock_logger
        ), patch(
            "src.components.notifications.listeners.CommonNotificationMessage.model_validate",
            return_value=mock_event,
        ), patch(
            "src.components.notifications.listeners.dispatch_notification_task.apply"
        ) as mock_apply:
            from src.components.notifications.listeners import handle_event

            handle_event(message)

            mock_apply.assert_called_once_with(
                kwargs={
                    "user_id": UUID("77777777-7777-7777-7777-777777777777"),
                    "title": "New lead",
                    "body": "You have a new lead",
                    "data": {},
                    "source": NotificationServiceType.TALKO.value,
                    "event_name": "WHATSAPP_MESSAGE_RECEIVED",
                    "service_type": NotificationServiceType.TALKO.value,
                }
            )

    def test_handle_event_unsupported_source_logs_and_skips(self):
        message = {
            "source": "unknown_service",
            "event_name": "LEAD_ASSIGNED",
            "created_at": 1,
            "heading": "H",
            "body": "B",
            "payload": {},
        }
        mock_logger = MagicMock()
        mock_event = self._mock_event(
            source="unknown_service",
            heading=message["heading"],
            body=message["body"],
            payload={},
        )

        with patch(
            "src.components.notifications.listeners.celery_logger", mock_logger
        ), patch(
            "src.components.notifications.listeners.CommonNotificationMessage.model_validate",
            return_value=mock_event,
        ), patch(
            "src.components.notifications.listeners.dispatch_notification_task.apply"
        ) as mock_apply:
            from src.components.notifications.listeners import handle_event

            handle_event(message)

            mock_apply.assert_not_called()
            mock_logger.error.assert_called_once_with(
                "Unsupported notification source: unknown_service"
            )

    def test_handle_event_missing_source_logs_and_skips(self):
        message = {
            "event_name": "LEAD_ASSIGNED",
            "created_at": 1,
            "heading": "H",
            "body": "B",
            "payload": {},
        }
        mock_logger = MagicMock()
        mock_event = self._mock_event(
            source="talko",
            heading=message["heading"],
            body=message["body"],
            payload={},
        )
        mock_event.source = None

        with patch(
            "src.components.notifications.listeners.celery_logger", mock_logger
        ), patch(
            "src.components.notifications.listeners.CommonNotificationMessage.model_validate",
            return_value=mock_event,
        ), patch(
            "src.components.notifications.listeners.dispatch_notification_task.apply"
        ) as mock_apply:
            from src.components.notifications.listeners import handle_event

            handle_event(message)

            mock_apply.assert_not_called()
            mock_logger.error.assert_called_once_with(
                "Unsupported notification source: None"
            )

    def test_handle_event_missing_payload_defaults_to_empty_dict(self):
        message = {
            "source": "talko",
            "event_name": "LEAD_ASSIGNED",
            "created_at": 1,
            "heading": "H",
            "body": "B",
        }
        mock_logger = MagicMock()
        mock_event = self._mock_event(
            heading=message["heading"],
            body=message["body"],
            payload={},
        )

        with patch(
            "src.components.notifications.listeners.celery_logger", mock_logger
        ), patch(
            "src.components.notifications.listeners.CommonNotificationMessage.model_validate",
            return_value=mock_event,
        ), patch(
            "src.components.notifications.listeners.dispatch_notification_task.apply"
        ) as mock_apply:
            from src.components.notifications.listeners import handle_event

            handle_event(message)

            mock_apply.assert_called_once_with(
                kwargs={
                    "user_id": None,
                    "title": "H",
                    "body": "B",
                    "data": {},
                    "source": NotificationServiceType.TALKO.value,
                    "event_name": "LEAD_ASSIGNED",
                    "service_type": NotificationServiceType.TALKO.value,
                }
            )

    def test_handle_event_logs_received_event(self):
        message = {
            "source": "talko",
            "event_name": "LEAD_ASSIGNED",
            "created_at": 1,
            "heading": "H",
            "body": "B",
            "payload": {},
        }
        mock_logger = MagicMock()
        mock_event = self._mock_event(
            heading=message["heading"],
            body=message["body"],
            payload={},
        )

        with patch(
            "src.components.notifications.listeners.celery_logger", mock_logger
        ), patch(
            "src.components.notifications.listeners.CommonNotificationMessage.model_validate",
            return_value=mock_event,
        ), patch(
            "src.components.notifications.listeners.dispatch_notification_task.apply"
        ):
            from src.components.notifications.listeners import handle_event

            handle_event(message)

            mock_logger.info.assert_called_once_with(
                f"Event received: {mock_event.model_dump.return_value}"
            )
