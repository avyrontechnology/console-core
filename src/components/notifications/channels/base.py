from abc import ABC, abstractmethod
from src.components.notifications.constants import NotificationServiceType

class BaseNotificationChannel(ABC):
    @abstractmethod
    def send(self, identifier: str, title: str, body: str, data: dict = None, service_type: NotificationServiceType = NotificationServiceType.TALKO) -> str:
        pass