from typing import Optional

from dependency_injector.wiring import Provide, inject
from fastapi import APIRouter, Depends, Request, Query

from src.components.common.constants import CurrentUserMap
from src.components.rbac.permission_injector import permission_check
from src.components.common.response import InternalServerErrorResponse, SuccessResponse
from src.components.notifications.schemas import (
    MarkReadRequest,
    NotificationHistoryResponse,
    NotificationPreferenceRequest,
    NotificationPreferenceResponse,
    RegisterSubscriptionRequest,
    UnreadCountResponse,
)
from src.components.notifications.services import NotificationService

from src.core.container import Container
from src.loggers.console_celery_logger import CeleryLogger
from src.components.notifications.constants import NotificationServiceType

class NotificationController:
    notification_router = APIRouter()

    @notification_router.get(
        "/notification/preferences",
        response_model=NotificationPreferenceResponse,
    )
    @permission_check("console:get_notification_preferences")
    @inject
    async def get_notification_preferences(
        request: Request,
        notification_service: NotificationService = Depends(
            Provide[Container.notification_service]
        ),
        logger: CeleryLogger = Depends(Provide[Container.console_service_logger]),
    ):
        """
        Fetch the current user's notification preferences.

        This keeps the preference state application-owned instead of browser-owned.
        """
        try:
            user_id = request.state.user.get(CurrentUserMap.USER_ID)
            logger.info(f"Fetching notification preferences for user: {user_id}")
            preferences = await notification_service.get_notification_preferences(user_id)
            return SuccessResponse(data=preferences.model_dump())
        except Exception as exc:
            logger.error(f"Unexpected error while fetching notification preferences: {exc}")
            return InternalServerErrorResponse()

    @notification_router.patch(
        "/notification/preferences",
        response_model=NotificationPreferenceResponse,
    )
    @permission_check("console:update_notification_preferences")
    @inject
    async def update_notification_preferences(
        request: Request,
        payload: NotificationPreferenceRequest,
        notification_service: NotificationService = Depends(
            Provide[Container.notification_service]
        ),
        logger: CeleryLogger = Depends(Provide[Container.console_service_logger]),
    ):
        """
        Update the current user's notification preferences.

        The stored state is reused by every service that publishes to the common queue.
        When `scope` is sent, the update targets just that notification
        family (single assign, bulk assign, or followup) instead of the whole source.
        """
        try:
            user_id = request.state.user.get(CurrentUserMap.USER_ID)
            logger.info(f"Updating notification preferences for user: {user_id}")
            updated = await notification_service.update_notification_preferences(
                user_id=user_id,
                preferences=payload.preferences,
            )
            return SuccessResponse(data=updated.model_dump())
        except Exception as exc:
            logger.error(f"Unexpected error while updating notification preferences: {exc}")
            return InternalServerErrorResponse()

    @notification_router.post("/notifications/subscribe")
    @permission_check("console:subscribe_to_notifications")
    @inject
    async def subscribe_to_notifications(
        request: Request,
        payload: RegisterSubscriptionRequest,
        notification_service: NotificationService = Depends(Provide[Container.notification_service]),
        logger: CeleryLogger = Depends(Provide[Container.console_service_logger]),
    ):
        """
        Registers a device token (FCM) or Webhook URL for the current user.
        Should be called by the frontend/mobile app immediately after login.
        """
        try:
            current_user = request.state.user
            user_id = current_user.get(CurrentUserMap.USER_ID)
            
            logger.info(f"Attempting to register {payload.channel_type.value} token for user: {user_id}")
            logger.info(
                    f"""
                Notification Subscribe Request

                user_id={user_id}
                channel_type={payload.channel_type}
                identifier={payload.identifier}
                meta_data={payload.meta_data}
                """
                )
            await notification_service.register_subscription(user_id, payload)
            
            return SuccessResponse(data="Device registered for notifications successfully.")
        except Exception as exc:
            logger.error(f"Unexpected error while registering notification token: {exc}")
            return InternalServerErrorResponse()

    @notification_router.delete("/notifications/unsubscribe")
    @permission_check("console:unsubscribe_from_notifications")
    @inject
    async def unsubscribe_from_notifications(
        request: Request,
        service_type: NotificationServiceType = Query(NotificationServiceType.TALKO),
        identifier: str = Query(..., description="The device token (FCM) or URL to deactivate"),
        notification_service: NotificationService = Depends(Provide[Container.notification_service]),
        logger: CeleryLogger = Depends(Provide[Container.console_service_logger]),
    ):
        """
        Deactivates a specific device token for the current user.
        Must be called by the frontend/mobile app right before logging out.
        """
        try:
            current_user = request.state.user
            user_id = current_user.get(CurrentUserMap.USER_ID)
            
            logger.info(f"Attempting to deactivate notification token for user: {user_id}")
            await notification_service.deactivate_subscription(user_id=user_id, identifier=identifier, service_type=service_type)
            
            return SuccessResponse(data="Device unsubscribed from notifications successfully.")
        except Exception as exc:
            logger.error(f"Unexpected error while deactivating notification token: {exc}")
            return InternalServerErrorResponse()


    @notification_router.get("/notifications/history")
    @permission_check("console:get_notification_history")
    @inject
    async def get_notification_history(
        request: Request,
        service_type: NotificationServiceType = Query(NotificationServiceType.TALKO),
        limit: int = Query(50, ge=1, le=100),
        offset: int = Query(0, ge=0),
        state:Optional[str] = Query(None),
        notification_service: NotificationService = Depends(Provide[Container.notification_service])
    ):
        """Fetches the paginated list of notifications for the bell icon dropdown."""
        user_id = request.state.user.get(CurrentUserMap.USER_ID)
        history = await notification_service.get_history(user_id, limit, offset, state, service_type)
        data = [NotificationHistoryResponse.model_validate(h).model_dump() for h in history['notifications']]
        return SuccessResponse(data={"notifications" : data, "count" : history.get('count')})

    @notification_router.get("/notifications/unread-count")
    @permission_check("console:get_unread_notifications_count")
    @inject
    async def get_unread_notifications_count(
        request: Request,
        service_type: NotificationServiceType = Query(NotificationServiceType.TALKO),
        notification_service: NotificationService = Depends(Provide[Container.notification_service])
    ):
        """Gets the number to display on the red badge over the bell icon."""
        user_id = request.state.user.get(CurrentUserMap.USER_ID)
        count = await notification_service.get_unread_count(user_id,service_type)
        return SuccessResponse(data=UnreadCountResponse(unread_count=count).model_dump())

    @notification_router.patch("/notifications/read")
    @permission_check("console:mark_notifications_as_read")
    @inject
    async def mark_notifications_as_read(
        request: Request,
        payload: MarkReadRequest,
        notification_service: NotificationService = Depends(Provide[Container.notification_service])
    ):
        """Marks specific notifications as read. Pass an empty array [] to mark ALL as read."""
        user_id = request.state.user.get(CurrentUserMap.USER_ID)
        await notification_service.mark_notifications_read(user_id, payload.notification_ids)
        return SuccessResponse(data="Notifications marked as read.")