from src.components.notifications.channels.base import BaseNotificationChannel
from src.components.notifications.channels.fcm_channel import FCMChannel

class NotificationChannelFactory:
    """Factory to retrieve the correct notification channel strategy via DI."""
    
    def __init__(self, fcm_channel: FCMChannel):
        # The container injects the channel singletons here
        self.__channels = {
            "FCM": fcm_channel,
            # "WEBHOOK": webhook_channel  <-- Future channels are injected here
        }

    def get_channel(self, channel_type: str) -> BaseNotificationChannel:
        channel = self.__channels.get(channel_type.upper())
        if not channel:
            raise ValueError(f"Notification channel type '{channel_type}' is not supported.")
        return channel