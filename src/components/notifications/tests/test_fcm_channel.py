from unittest.mock import MagicMock, patch

from firebase_admin import messaging

from src.components.notifications.channels.fcm_channel import FCMChannel
from src.components.notifications.constants import NotificationServiceType


class TestFCMChannelSend:

    def setup_method(self):
        self.channel = FCMChannel()

    def test_send_success_with_data(self):
        mock_app = MagicMock(name="firebase_app")
        mock_app.name = "maglo"

        with patch(
            "src.components.notifications.channels.fcm_channel.firebase_init",
            return_value=mock_app,
        ) as mock_firebase_init, patch(
            "src.components.notifications.channels.fcm_channel.messaging.send",
            return_value="projects/x/messages/1",
        ) as mock_send, patch(
            "src.components.notifications.channels.fcm_channel.messaging.Message"
        ) as mock_message, patch(
            "src.components.notifications.channels.fcm_channel.messaging.Notification"
        ) as mock_notification:
            result = self.channel.send(
                identifier="token123",
                title="Hello",
                body="World",
                data={"key": "value", "count": 3},
                service_type=NotificationServiceType.MAGLO,
            )

        assert result == "SUCCESS"
        mock_firebase_init.assert_called_once_with(NotificationServiceType.MAGLO)
        mock_notification.assert_called_once_with(title="Hello", body="World")
        mock_message.assert_called_once_with(
            notification=mock_notification.return_value,
            data={"key": "value", "count": "3"},
            token="token123",
        )
        mock_send.assert_called_once_with(mock_message.return_value, app=mock_app)

    def test_send_success_without_data(self):
        mock_app = MagicMock()
        mock_app.name = "babbler"

        with patch(
            "src.components.notifications.channels.fcm_channel.firebase_init",
            return_value=mock_app,
        ), patch(
            "src.components.notifications.channels.fcm_channel.messaging.send",
            return_value="ok",
        ), patch(
            "src.components.notifications.channels.fcm_channel.messaging.Message"
        ) as mock_message, patch(
            "src.components.notifications.channels.fcm_channel.messaging.Notification"
        ) as mock_notification:
            result = self.channel.send(
                identifier="token123",
                title="Hello",
                body="World",
                data=None,
                service_type=NotificationServiceType.BABBLER,
            )

        assert result == "SUCCESS"
        mock_message.assert_called_once_with(
            notification=mock_notification.return_value,
            data={},
            token="token123",
        )

    def test_send_unregistered_token(self):
        mock_app = MagicMock()
        mock_app.name = "maglo"

        with patch(
            "src.components.notifications.channels.fcm_channel.firebase_init",
            return_value=mock_app,
        ), patch(
            "src.components.notifications.channels.fcm_channel.messaging.send",
            side_effect=messaging.UnregisteredError("token unregistered"),
        ), patch(
            "src.components.notifications.channels.fcm_channel.messaging.Message"
        ), patch(
            "src.components.notifications.channels.fcm_channel.messaging.Notification"
        ):
            result = self.channel.send(
                identifier="token123",
                title="Hello",
                body="World",
                data={"key": "value"},
                service_type=NotificationServiceType.MAGLO,
            )

        assert result == "UNREGISTERED"

    def test_send_generic_exception(self):
        mock_app = MagicMock()
        mock_app.name = "maglo"

        with patch(
            "src.components.notifications.channels.fcm_channel.firebase_init",
            return_value=mock_app,
        ), patch(
            "src.components.notifications.channels.fcm_channel.messaging.send",
            side_effect=RuntimeError("network error"),
        ), patch(
            "src.components.notifications.channels.fcm_channel.messaging.Message"
        ), patch(
            "src.components.notifications.channels.fcm_channel.messaging.Notification"
        ):
            result = self.channel.send(
                identifier="token123",
                title="Hello",
                body="World",
                data={"key": "value"},
                service_type=NotificationServiceType.MAGLO,
            )

        assert result == "ERROR"

    def test_send_generic_exception_without_service_type(self):
        mock_app = MagicMock()
        mock_app.name = "unknown"

        with patch(
            "src.components.notifications.channels.fcm_channel.firebase_init",
            return_value=mock_app,
        ):
            # service_type is None, so accessing service_type.value inside the
            # try block raises before messaging.send is ever reached, exercising
            # the generic except branch with the "unknown" fallback.
            result = self.channel.send(
                identifier="token123",
                title="Hello",
                body="World",
                data={"key": "value"},
                service_type=None,
            )

        assert result == "ERROR"
