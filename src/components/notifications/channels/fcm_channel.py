import firebase_admin
from firebase_admin import messaging
from .base import BaseNotificationChannel
from src.loggers.console_celery_logger import CeleryLogger
from src.core.firebase import firebase_init
from src.components.notifications.constants import NotificationServiceType

logger = CeleryLogger.get_logger()

class FCMChannel(BaseNotificationChannel):
    ...
    def send(self, identifier: str, title: str, body: str, data: dict = None, service_type: NotificationServiceType = None,) -> str:
        try:
            app = firebase_init(service_type)
            logger.info(f"Sending FCM notification -> service={service_type.value}, firebase_app={app.name}")

            # Firebase requires all data payload values to be strings
            str_data = ({str(k): str(v) for k, v in data.items()} if data else {})

            message = messaging.Message(
                notification=messaging.Notification(title=title, body=body),
                data=str_data,
                token=identifier,
            )
            response = messaging.send(message,app=app)
            logger.info(f"FCM message sent successfully for service={service_type.value}: {response}")
            return "SUCCESS"
        except messaging.UnregisteredError:
            # Token is dead (App uninstalled or token expired)
            logger.info(
                f"Token {identifier} is unregistered. "
                f"service={service_type.value if service_type else 'unknown'}"
            )
            return "UNREGISTERED"
        except Exception as e:
            logger.error(f"Failed to send FCM message: {e} , service={service_type.value if service_type else 'unknown'}")
                        
            return "ERROR"