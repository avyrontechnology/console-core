from typing import List, Optional
import asyncio
from src.components.notifications.constants import SERVICES
from src.components.notifications.repositories import NotificationRepository
from src.components.notifications.schemas import (
    NotificationPreferenceItem,
    NotificationPreferenceResponse,
    RegisterSubscriptionRequest,
)
from src.components.notifications.repositories import NotificationHistory, NotificationRepository
from src.components.notifications.schemas import RegisterSubscriptionRequest
from src.loggers.console_celery_logger import CeleryLogger
from src.components.notifications.models import NotificationSubscription
from src.components.session_mangement.services import UserSessionService
from src.components.notifications.constants import NotificationServiceType
from src.components.auth.constant import ServiceNames
class NotificationService:
    ...
    def __init__(
        self,
        notification_repository: NotificationRepository,
        maglo_service_logger: CeleryLogger,
        user_session_service: UserSessionService
    ):
        self.__repository = notification_repository
        self.__logger = maglo_service_logger
        self.__user_session_service = user_session_service

    def _get_session_service_names(
        self,
        service_type: NotificationServiceType,
    ) -> List[str]:
        return {
            NotificationServiceType.MAGLO: [
                ServiceNames.MAGLO.value,      # web/postman login with svc_name="maglo"
                ServiceNames.MAGLO_APP.value,  # mobile app login (svc_name="maglo_app")
            ],
            NotificationServiceType.BABBLER: ["babbler", "babbler_app"],
        }.get(service_type, [service_type.value])

    async def _has_active_session(
        self,
        user_id: int,
        service_type: NotificationServiceType,
    ) -> bool:
        service_names = self._get_session_service_names(service_type)

        self.__logger.debug(
            f"Resolved session services for session check: user_id={user_id}, "
            f"service={service_type.value}, session_services={service_names}"
        )

        for service_name in service_names:
            self.__logger.debug(
                f"Checking active session: user_id={user_id}, session_service={service_name}"
            )

            if await self.__user_session_service.has_active_session(
                user_id=user_id,
                service_name=service_name,
            ):
                self.__logger.debug(
                    f"Active session found: user_id={user_id}, session_service={service_name}"
                )
                return True

        return False

    async def has_active_session_for_push(
        self,
        user_id: int,
        service_type: NotificationServiceType,
    ) -> bool:
        return await self._has_active_session(user_id, service_type)

    async def register_subscription(self, user_id: int, payload: RegisterSubscriptionRequest) -> None:
        try:
            await self.__repository.upsert_subscription(
                user_id=user_id,
                channel_type=payload.channel_type.value,
                identifier=payload.identifier,
                service_type=payload.service_type.value,
                meta_data=payload.meta_data
            )
        except Exception as exc:
            self.__logger.error(f"Error registering subscription for user {user_id}: {exc}")
            raise exc
        
            
    async def get_active_user_subscriptions(
        self,
        user_id: int,
        service_type: NotificationServiceType,
    ) -> List[NotificationSubscription]:
        try:
            self.__logger.info(f"Fetching active notification subscriptions for user {user_id}, service={service_type.value}")

            service_names = self._get_session_service_names(service_type)
            has_active_session = await self._has_active_session(user_id, service_type)

            if not has_active_session:
                self.__logger.info(
                    f"No active session found. Deactivating active subscriptions: "
                    f"user_id={user_id}, service={service_type.value}, checked_services={service_names}"
                )
                subscriptions = await self.__repository.get_active_subscriptions(
                    user_id=user_id,
                    service_type=service_type,
                )

                self.__logger.info(f"Found {len(subscriptions)} active subscriptions to deactivate: user_id={user_id}, service={service_type.value}")

                for subscription in subscriptions:
                    self.__logger.debug(f"Deactivating subscription: user_id={user_id}, service={service_type.value}, identifier={subscription.identifier}")
                    await self.__repository.deactivate_subscription(
                        user_id=user_id,
                        identifier=subscription.identifier,
                        service_type=service_type,
                    )

                self.__logger.info(f"Deactivated {len(subscriptions)} subscriptions due to no active session: user_id={user_id}, service={service_type.value}")
                return []

            self.__logger.debug(f"Active session validation passed: user_id={user_id}, service={service_type.value}")
            subscriptions: List[NotificationSubscription] = (
                await self.__repository.get_active_subscriptions( user_id=user_id, service_type=service_type,))

            self.__logger.info(
                f"Fetched active notification subscriptions: user_id={user_id}, service={service_type.value}, count={len(subscriptions)}")

            return subscriptions

        except Exception as exc:
            self.__logger.error(f"Error fetching subscriptions for user {user_id}, service={service_type.value}: {exc}")
            return []
                
    async def deactivate_subscription(self, user_id: int, identifier: str, service_type: NotificationServiceType) -> None:
        """
        Deactivates a specific device token/subscription. 
        Called when a user logs out or a token becomes unregistered.
        """
        try:
            self.__logger.info(
                f"Deactivating notification subscription for user: {user_id}, identifier: {identifier}, service_type: {service_type.value}"
            )
            await self.__repository.deactivate_subscription(
                user_id=user_id, 
                identifier=identifier,
                service_type=service_type
            )
        except Exception as exc:
            self.__logger.error(
                f"Failed to deactivate subscription for user {user_id} for service {service_type.value}: {exc}"
            )
            raise exc

    async def save_notification_history(self, user_id: int, title: str, body: str, data: dict, service_type: NotificationServiceType) -> None:
        try:
            await self.__repository.insert_history(user_id, title, body, data, service_type)
        except Exception as exc:
            self.__logger.error(f"Failed to save history for user {user_id}: {exc}")

    async def get_history(self, user_id: int, limit: int, offset: int, state:Optional[str] = None, service_type: NotificationServiceType = NotificationServiceType.MAGLO):
        res = await self.__repository.get_user_history(user_id, limit, offset, state,service_type)
        return {
            "notifications" : res[0],
            "count" : res[1]
        }

    async def get_unread_count(self, user_id: int, service_type: NotificationServiceType) -> int:
        return await self.__repository.get_unread_count(user_id, service_type)

    async def mark_notifications_read(self, user_id: int, notification_ids: List[int]) -> None:
        await self.__repository.mark_as_read(user_id, notification_ids)
        
    async def should_send_notification(
        self, user_id: int, source: str, event_name: Optional[str] = None
    ) -> bool:
        return await self.__repository.is_notification_enabled(
            user_id=user_id,
            source=source,
            event_name=event_name,
        )

    async def get_notification_preferences(
        self, user_id: int
    ) -> NotificationPreferenceResponse:
        """
        Read the current per-source notification state for the current user.

        Missing rows are treated as enabled so existing users keep the current
        delivery behavior until they explicitly opt out.
        """
        preferences = await self.__repository.get_notification_preferences(user_id)
        return NotificationPreferenceResponse(user_id=user_id, preferences=preferences)

    async def update_notification_preferences(
        self, user_id: int, preferences: List[NotificationPreferenceItem]
    ) -> NotificationPreferenceResponse:
        """
        Persist the user's application-level notification choices.

        The repository stores the state in the shared user-config table, which
        keeps the preference synced across devices and sessions.
        """
        updated_preferences = await self.__repository.upsert_notification_preferences(
            user_id=user_id,
            preferences=preferences,
        )
        return NotificationPreferenceResponse(
            user_id=user_id,
            preferences=updated_preferences,
        )
