from uuid import UUID
import pytest
from unittest.mock import AsyncMock, MagicMock, call

from src.components.notifications.schemas import (
    NotificationPreferenceItem,
    NotificationPreferenceStateEnum,
    NotificationScopeEnum,
    NotificationSourceEnum,
)
from src.components.notifications.services import NotificationService
from src.components.notifications.constants import NotificationServiceType
from src.components.auth.constant import ServiceNames


@pytest.mark.asyncio
class TestNotificationService:

    @pytest.fixture(autouse=True)
    def setup(self):
        # Mock repository
        self.repo = MagicMock()
        self.repo.upsert_subscription = AsyncMock()
        self.repo.get_active_subscriptions = AsyncMock()
        self.repo.deactivate_subscription = AsyncMock()
        self.repo.insert_history = AsyncMock()
        self.repo.get_user_history = AsyncMock()
        self.repo.get_unread_count = AsyncMock()
        self.repo.mark_as_read = AsyncMock()

        # Mock user session service
        self.user_session_service = MagicMock()
        self.user_session_service.has_active_session = AsyncMock()
        self.repo.is_notification_enabled = AsyncMock()
        self.repo.get_notification_preferences = AsyncMock()
        self.repo.upsert_notification_preferences = AsyncMock()

        # Mock logger
        self.logger = MagicMock()

        # Service instance
        self.service = NotificationService(
            self.repo,
            self.logger,
            self.user_session_service,
        )

    # ============================================================
    # REGISTER SUBSCRIPTION
    # ============================================================

    async def test_register_subscription_success(self):
        payload = MagicMock()
        payload.channel_type.value = "FCM"
        payload.identifier = "token123"
        payload.meta_data = {"device": "android"}
        payload.service_type = NotificationServiceType.TALKO

        await self.service.register_subscription(
            user_id= UUID("11111111-1111-1111-1111-111111111111"),
            payload=payload,
        )

        self.repo.upsert_subscription.assert_awaited_once_with(
            user_id= UUID("11111111-1111-1111-1111-111111111111"),
            channel_type="FCM",
            identifier="token123",
            meta_data={"device": "android"},
            service_type=NotificationServiceType.TALKO.value,
        )

    async def test_register_subscription_exception(self):
        payload = MagicMock()
        payload.channel_type.value = "FCM"
        payload.identifier = "token123"
        payload.meta_data = {}
        payload.service_type = NotificationServiceType.TALKO

        self.repo.upsert_subscription.side_effect = Exception("DB error")

        with pytest.raises(Exception, match="DB error"):
            await self.service.register_subscription(
                user_id= UUID("11111111-1111-1111-1111-111111111111"),
                payload=payload,
            )

        self.logger.error.assert_called_once_with(
            "Error registering subscription for user 11111111-1111-1111-1111-111111111111: DB error"
        )

    # ============================================================
    # GET ACTIVE USER SUBSCRIPTIONS
    # ============================================================

    async def test_get_active_user_subscriptions_success(self):
        sub = MagicMock()
        sub.identifier = "token123"

        self.repo.get_active_subscriptions.return_value = [sub]

        result = await self.service.get_active_user_subscriptions(
            user_id= UUID("11111111-1111-1111-1111-111111111111"),
            service_type=NotificationServiceType.TALKO,
        )

        assert result == [sub]

        self.repo.get_active_subscriptions.assert_awaited_once_with(
            user_id= UUID("11111111-1111-1111-1111-111111111111"),
            service_type=NotificationServiceType.TALKO,
        )

        self.logger.info.assert_any_call(
            "Fetching active notification subscriptions for "
            "user 11111111-1111-1111-1111-111111111111, service=talko"
        )

        self.logger.info.assert_any_call(
            "Fetched active notification subscriptions: "
            "user_id=11111111-1111-1111-1111-111111111111, service=talko, count=1"
        )

    async def test_get_active_user_subscriptions_empty(self):
        self.repo.get_active_subscriptions.return_value = []

        result = await self.service.get_active_user_subscriptions(
            user_id= UUID("11111111-1111-1111-1111-111111111111"),
            service_type=NotificationServiceType.TALKO,
        )

        assert result == []

        self.repo.get_active_subscriptions.assert_awaited_once_with(
            user_id= UUID("11111111-1111-1111-1111-111111111111"),
            service_type=NotificationServiceType.TALKO,
        )

        self.logger.info.assert_any_call(
            "Fetched active notification subscriptions: "
            "user_id=11111111-1111-1111-1111-111111111111, service=talko, count=0"
        )

    async def test_get_active_user_subscriptions_exception(self):
        self.repo.get_active_subscriptions.side_effect = Exception("error")

        result = await self.service.get_active_user_subscriptions(
            user_id= UUID("11111111-1111-1111-1111-111111111111"),
            service_type=NotificationServiceType.TALKO,
        )

        assert result == []

        # Production code calls logger.error(), NOT logger.exception()
        self.logger.error.assert_called_once_with(
            "Error fetching subscriptions for user 11111111-1111-1111-1111-111111111111, "
            "service=talko: error"
        )

    async def test_has_active_session_for_push_uses_session_service(self):
        self.user_session_service.has_active_session.return_value = True

        result = await self.service.has_active_session_for_push(
            user_id= UUID("11111111-1111-1111-1111-111111111111"),
            service_type=NotificationServiceType.TALKO,
        )

        assert result is True

        self.user_session_service.has_active_session.assert_awaited_once_with(
            user_id= UUID("11111111-1111-1111-1111-111111111111"),
            service_name="talko",
        )

    # ============================================================
    # DEACTIVATE SUBSCRIPTION
    # ============================================================

    async def test_deactivate_subscription_success(self):
        await self.service.deactivate_subscription(
            user_id= UUID("11111111-1111-1111-1111-111111111111"),
            identifier="token123",
            service_type=NotificationServiceType.TALKO,
        )

        self.repo.deactivate_subscription.assert_awaited_once_with(
            user_id= UUID("11111111-1111-1111-1111-111111111111"),
            identifier="token123",
            service_type=NotificationServiceType.TALKO,
        )

        self.logger.info.assert_called_once_with(
            "Deactivating notification subscription for user: 11111111-1111-1111-1111-111111111111, "
            "identifier: token123, service_type: talko"
        )

    async def test_deactivate_subscription_exception(self):
        self.repo.deactivate_subscription.side_effect = Exception("fail")

        with pytest.raises(Exception, match="fail"):
            await self.service.deactivate_subscription(
                user_id= UUID("11111111-1111-1111-1111-111111111111"),
                identifier="token123",
                service_type=NotificationServiceType.TALKO,
            )

        self.logger.error.assert_called_once_with(
            "Failed to deactivate subscription for user 11111111-1111-1111-1111-111111111111 "
            "for service talko: fail"
        )

    # ============================================================
    # SAVE NOTIFICATION HISTORY
    # ============================================================

    async def test_save_notification_history_success(self):
        await self.service.save_notification_history(
            user_id= UUID("11111111-1111-1111-1111-111111111111"),
            title="Hello",
            body="World",
            data={"key": "value"},
            service_type=NotificationServiceType.TALKO,
        )

        self.repo.insert_history.assert_awaited_once_with(
            UUID("11111111-1111-1111-1111-111111111111"),
            "Hello",
            "World",
            {"key": "value"},
            NotificationServiceType.TALKO,
        )

    async def test_save_notification_history_exception(self):
        self.repo.insert_history.side_effect = Exception("fail")

        # Method catches exception and does NOT re-raise.
        await self.service.save_notification_history(
            user_id= UUID("11111111-1111-1111-1111-111111111111"),
            title="Hello",
            body="World",
            data={},
            service_type=NotificationServiceType.TALKO,
        )

        self.logger.error.assert_called_once_with(
            "Failed to save history for user 11111111-1111-1111-1111-111111111111: fail"
        )

    # ============================================================
    # GET HISTORY
    # ============================================================

    async def test_get_history(self):
        self.repo.get_user_history.return_value = (
            ["h1", "h2"],
            2,
        )

        result = await self.service.get_history(
            user_id= UUID("11111111-1111-1111-1111-111111111111"),
            limit=10,
            offset=0,
        )

        assert result == {
            "notifications": ["h1", "h2"],
            "count": 2,
        }

        self.repo.get_user_history.assert_awaited_once_with(
            UUID("11111111-1111-1111-1111-111111111111"),
            10,
            0,
            None,
            NotificationServiceType.TALKO,
        )

    async def test_get_history_with_state_and_service_type(self):
        self.repo.get_user_history.return_value = (
            ["h1"],
            1,
        )

        result = await self.service.get_history(
            user_id= UUID("11111111-1111-1111-1111-111111111111"),
            limit=10,
            offset=5,
            state="unread",
            service_type=NotificationServiceType.TALKO,
        )

        assert result == {
            "notifications": ["h1"],
            "count": 1,
        }

        self.repo.get_user_history.assert_awaited_once_with(
            UUID("11111111-1111-1111-1111-111111111111"),
            10,
            5,
            "unread",
            NotificationServiceType.TALKO,
        )

    # ============================================================
    # UNREAD COUNT
    # ============================================================

    async def test_get_unread_count(self):
        self.repo.get_unread_count.return_value = 5

        result = await self.service.get_unread_count(
            user_id= UUID("11111111-1111-1111-1111-111111111111"),
            service_type=NotificationServiceType.TALKO,
        )

        assert result == 5

        self.repo.get_unread_count.assert_awaited_once_with(
            UUID("11111111-1111-1111-1111-111111111111"),
            NotificationServiceType.TALKO,
        )

    # ============================================================
    # MARK AS READ
    # ============================================================

    async def test_mark_notifications_read(self):
        await self.service.mark_notifications_read(
            user_id= UUID("11111111-1111-1111-1111-111111111111"),
            notification_ids=[UUID("11111111-1111-1111-1111-111111111111"), UUID("22222222-2222-2222-2222-222222222222")],
        )

        self.repo.mark_as_read.assert_awaited_once_with(UUID("11111111-1111-1111-1111-111111111111"), [UUID("11111111-1111-1111-1111-111111111111"), UUID("22222222-2222-2222-2222-222222222222")])

    async def test_should_send_notification(self):
        self.repo.is_notification_enabled.return_value = False

        result = await self.service.should_send_notification(
            user_id= UUID("11111111-1111-1111-1111-111111111111"),
            source="talko",
            event_name="LEAD_ASSIGNED",
        )

        assert result is False
        self.repo.is_notification_enabled.assert_awaited_once_with(
            user_id= UUID("11111111-1111-1111-1111-111111111111"),
            source="talko",
            event_name="LEAD_ASSIGNED",
        )

    async def test_get_notification_preferences(self):
        prefs = [
            NotificationPreferenceItem(
                source=NotificationSourceEnum.TALKO,
                scope=NotificationScopeEnum.WHATSAPP,
                state=NotificationPreferenceStateEnum.ENABLED,
            )
        ]
        self.repo.get_notification_preferences.return_value = prefs

        result = await self.service.get_notification_preferences(user_id= UUID("11111111-1111-1111-1111-111111111111"))

        assert result.user_id== UUID("11111111-1111-1111-1111-111111111111")
        assert result.preferences == prefs

    async def test_update_notification_preferences(self):
        prefs = [
            NotificationPreferenceItem(
                source=NotificationSourceEnum.TALKO,
                scope=NotificationScopeEnum.WHATSAPP,
                state=NotificationPreferenceStateEnum.DISABLED,
            )
        ]
        self.repo.upsert_notification_preferences.return_value = prefs

        result = await self.service.update_notification_preferences(
            user_id= UUID("11111111-1111-1111-1111-111111111111"), preferences=prefs
        )

        self.repo.upsert_notification_preferences.assert_awaited_once_with(
            user_id= UUID("11111111-1111-1111-1111-111111111111"),
            preferences=prefs,
        )
        assert result.user_id== UUID("11111111-1111-1111-1111-111111111111")
        assert result.preferences == prefs

    async def test_get_active_user_subscriptions_with_active_session(self):
        sub = MagicMock()
        sub.identifier = "token123"

        self.user_session_service.has_active_session.return_value = True
        self.repo.get_active_subscriptions.return_value = [sub]

        result = await self.service.get_active_user_subscriptions(
            user_id= UUID("11111111-1111-1111-1111-111111111111"),
            service_type=NotificationServiceType.TALKO,
        )

        assert result == [sub]

        self.user_session_service.has_active_session.assert_any_await(
            user_id= UUID("11111111-1111-1111-1111-111111111111"),
            service_name="talko",
        )

        self.repo.get_active_subscriptions.assert_awaited_once_with(
            user_id= UUID("11111111-1111-1111-1111-111111111111"),
            service_type=NotificationServiceType.TALKO,
        )
    async def test_get_active_user_subscriptions_no_active_session(self):
        sub = MagicMock()
        sub.identifier = "token123"

        self.user_session_service.has_active_session.return_value = False
        self.repo.get_active_subscriptions.return_value = [sub]

        result = await self.service.get_active_user_subscriptions(
            user_id= UUID("11111111-1111-1111-1111-111111111111"),
            service_type=NotificationServiceType.TALKO,
        )

        assert result == []

        self.user_session_service.has_active_session.assert_any_await(
            user_id= UUID("11111111-1111-1111-1111-111111111111"),
            service_name="talko",
        )

        self.repo.deactivate_subscription.assert_awaited_once_with(
            user_id= UUID("11111111-1111-1111-1111-111111111111"),
            identifier="token123",
            service_type=NotificationServiceType.TALKO,
        )
    async def test_get_active_user_subscriptions_console_expired_returns_empty(self):
        self.user_session_service.has_active_session.return_value = False

        sub = MagicMock()
        sub.identifier = "token123"
        self.repo.get_active_subscriptions.return_value = [sub]

        result = await self.service.get_active_user_subscriptions(
            user_id= UUID("33333333-3333-3333-3333-333333333333"),
            service_type=NotificationServiceType.TALKO,
        )

        assert result == []
        assert self.user_session_service.has_active_session.await_args_list == [
            call(user_id= UUID("33333333-3333-3333-3333-333333333333"), service_name="talko"),
        ]
        self.repo.get_active_subscriptions.assert_awaited_once_with(
            user_id= UUID("33333333-3333-3333-3333-333333333333"),
            service_type=NotificationServiceType.TALKO,
        )
        self.repo.deactivate_subscription.assert_awaited_once_with(
            user_id= UUID("33333333-3333-3333-3333-333333333333"),
            identifier="token123",
            service_type=NotificationServiceType.TALKO,
        )
    
    async def test_get_active_user_subscriptions_console_active_returns_subscriptions(self):
        self.user_session_service.has_active_session.return_value = True

        sub = MagicMock()
        sub.identifier = "token123"
        self.repo.get_active_subscriptions.return_value = [sub]

        result = await self.service.get_active_user_subscriptions(
            user_id= UUID("33333333-3333-3333-3333-333333333333"),
            service_type=NotificationServiceType.TALKO,
        )

        assert result == [sub]
        self.user_session_service.has_active_session.assert_awaited_once_with(
            user_id= UUID("33333333-3333-3333-3333-333333333333"),
            service_name="talko",
        )
        self.repo.get_active_subscriptions.assert_awaited_once_with(
            user_id= UUID("33333333-3333-3333-3333-333333333333"),
            service_type=NotificationServiceType.TALKO,
        )
            
