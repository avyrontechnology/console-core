from uuid import UUID
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from src.components.notifications.repositories import NotificationRepository
from src.components.notifications.schemas import (
    NotificationPreferenceItem,
    NotificationPreferenceStateEnum,
    NotificationScopeEnum,
    NotificationSourceEnum,
)
from src.components.user_config.constants import UserConfigEnum
from src.components.notifications.repositories import NotificationHistory, NotificationRepository
from src.components.notifications.constants import NotificationServiceType


@pytest.mark.asyncio
class TestNotificationRepository:

    @pytest.fixture(autouse=True)
    def setup(self):
        # Mock session
        self.session = AsyncMock()
        self.session.execute = AsyncMock()
        self.session.commit = AsyncMock()

        # Mock session factory (async context manager)
        self.session_factory = MagicMock()
        self.session_factory.return_value.__aenter__.return_value = self.session
        self.session_factory.return_value.__aexit__.return_value = AsyncMock()

        # Mock logger
        self.logger = MagicMock()

        # Repository instance
        self.repo = NotificationRepository(self.session_factory, self.logger)

    # ---------------------------
    # 🧪 upsert_subscription
    # ---------------------------
    @patch("src.components.common.datetime.DateTimeUtil.get_current_time")
    async def test_upsert_subscription(self, mock_time):
        mock_time.return_value = "now"

        await self.repo.upsert_subscription(
            user_id= UUID("11111111-1111-1111-1111-111111111111"),
            channel_type="FCM",
            identifier="token123",
            service_type=NotificationServiceType.TALKO,
            meta_data={"device": "android"}
        )

        assert self.session.execute.called
        self.session.commit.assert_awaited_once()

    # ---------------------------
    # 🧪 get_active_subscriptions
    # ---------------------------
    async def test_get_active_subscriptions(self):
        mock_sub1 = MagicMock()
        mock_sub2 = MagicMock()

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [mock_sub1, mock_sub2]

        self.session.execute.return_value = mock_result

        result = await self.repo.get_active_subscriptions(user_id= UUID("11111111-1111-1111-1111-111111111111"))

        assert len(result) == 2
        assert result[0] == mock_sub1

    # ---------------------------
    # 🧪 get_active_subscriptions (filtered by service_type)
    # ---------------------------
    async def test_get_active_subscriptions_with_service_type(self):
        mock_sub1 = MagicMock()

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [mock_sub1]

        self.session.execute.return_value = mock_result

        result = await self.repo.get_active_subscriptions(
            user_id= UUID("11111111-1111-1111-1111-111111111111"), service_type=NotificationServiceType.TALKO
        )

        assert result == [mock_sub1]
        assert self.session.execute.called

    # ---------------------------
    # 🧪 deactivate_subscription
    # ---------------------------
    @patch("src.components.common.datetime.DateTimeUtil.get_current_time")
    async def test_deactivate_subscription(self, mock_time):
        mock_time.return_value = "now"

        await self.repo.deactivate_subscription(user_id= UUID("11111111-1111-1111-1111-111111111111"), identifier="token123", service_type=NotificationServiceType.TALKO)

        assert self.session.execute.called
        self.session.commit.assert_awaited_once()

    # ---------------------------
    # 🧪 insert_history
    # ---------------------------

    @pytest.mark.asyncio
    async def test_insert_history(self):
        history = await self.repo.insert_history(
            user_id= UUID("11111111-1111-1111-1111-111111111111"),
            title="Hello",
            body="World",
            data={"key": "value"},
            service_type=NotificationServiceType.TALKO,
        )
    
        self.session.add.assert_called_once()
        self.session.commit.assert_awaited_once()
        self.session.refresh.assert_awaited_once_with(history)
    
        assert history.user_id== UUID("11111111-1111-1111-1111-111111111111")
        assert history.title == "Hello"
        assert history.body == "World"
        assert history.data_payload == {"key": "value"}
    
        added_history = self.session.add.call_args.args[0]
    
        assert isinstance(added_history, NotificationHistory)
        assert added_history.user_id== UUID("11111111-1111-1111-1111-111111111111")
        assert added_history.title == "Hello"
        assert added_history.body == "World"
        assert added_history.data_payload == {"key": "value"}
    
        assert history is added_history
    # ---------------------------
    # 🧪 get_user_history
    # ---------------------------
    async def test_get_user_history(self):
        mock_history = [MagicMock(), MagicMock()]

        # First query → data
        mock_result_data = MagicMock()
        mock_result_data.scalars.return_value.all.return_value = mock_history

        # Second query → count
        mock_result_count = MagicMock()
        mock_result_count.scalar_one.return_value = 2

        # Execute is called twice → return different mocks
        self.session.execute.side_effect = [mock_result_data, mock_result_count]

        result = await self.repo.get_user_history(user_id= UUID("11111111-1111-1111-1111-111111111111"))

        assert result == (mock_history, 2)

    # ---------------------------
    # 🧪 get_unread_count (value)
    # ---------------------------
    async def test_get_unread_count(self):
        mock_result = MagicMock()
        mock_result.scalar.return_value = 5

        self.session.execute.return_value = mock_result

        count = await self.repo.get_unread_count(user_id= UUID("11111111-1111-1111-1111-111111111111"), service_type=NotificationServiceType.TALKO)

        assert count == 5

    # ---------------------------
    # 🧪 get_unread_count (None → 0)
    # ---------------------------
    async def test_get_unread_count_none(self):
        mock_result = MagicMock()
        mock_result.scalar.return_value = None

        self.session.execute.return_value = mock_result

        count = await self.repo.get_unread_count(user_id= UUID("11111111-1111-1111-1111-111111111111"), service_type=NotificationServiceType.TALKO)

        assert count == 0

    # ---------------------------
    # 🧪 mark_as_read (specific IDs)
    # ---------------------------
    @patch("src.components.common.datetime.DateTimeUtil.get_current_time")
    async def test_mark_as_read_with_ids(self, mock_time):
        mock_time.return_value = "now"

        await self.repo.mark_as_read(user_id= UUID("11111111-1111-1111-1111-111111111111"), notification_ids=[UUID("11111111-1111-1111-1111-111111111111"), UUID("22222222-2222-2222-2222-222222222222"), UUID("33333333-3333-3333-3333-333333333333")])

        assert self.session.execute.called
        self.session.commit.assert_awaited_once()

    # ---------------------------
    # 🧪 mark_as_read (all unread)
    # ---------------------------
    @patch("src.components.common.datetime.DateTimeUtil.get_current_time")
    async def test_mark_as_read_all(self, mock_time):
        mock_time.return_value = "now"

        await self.repo.mark_as_read(user_id= UUID("11111111-1111-1111-1111-111111111111"), notification_ids=[])

        assert self.session.execute.called
        self.session.commit.assert_awaited_once()

    async def test_get_user_history_unread(self):
        mock_history = [MagicMock()]

        mock_result_data = MagicMock()
        mock_result_data.scalars.return_value.all.return_value = mock_history

        mock_result_count = MagicMock()
        mock_result_count.scalar_one.return_value = 1

        self.session.execute.side_effect = [mock_result_data, mock_result_count]

        result = await self.repo.get_user_history(user_id= UUID("11111111-1111-1111-1111-111111111111"), state="unread")

        assert result == (mock_history, 1)
        assert self.session.execute.call_count == 2

    async def test_get_user_history_read(self):
        mock_history = [MagicMock()]

        mock_result_data = MagicMock()
        mock_result_data.scalars.return_value.all.return_value = mock_history

        mock_result_count = MagicMock()
        mock_result_count.scalar_one.return_value = 1

        self.session.execute.side_effect = [mock_result_data, mock_result_count]

        result = await self.repo.get_user_history(user_id= UUID("11111111-1111-1111-1111-111111111111"), state="read")

        assert result == (mock_history, 1)

    async def test_get_user_history_pagination(self):
        mock_history = []

        mock_result_data = MagicMock()
        mock_result_data.scalars.return_value.all.return_value = mock_history

        mock_result_count = MagicMock()
        mock_result_count.scalar_one.return_value = 0

        self.session.execute.side_effect = [mock_result_data, mock_result_count]

        result = await self.repo.get_user_history(user_id= UUID("11111111-1111-1111-1111-111111111111"), limit=0, offset=100)

        assert result == ([], 0)

    async def test_get_user_history_empty(self):
        mock_result_data = MagicMock()
        mock_result_data.scalars.return_value.all.return_value = []

        mock_result_count = MagicMock()
        mock_result_count.scalar_one.return_value = 0

        self.session.execute.side_effect = [mock_result_data, mock_result_count]

        result = await self.repo.get_user_history(user_id= UUID("11111111-1111-1111-1111-111111111111"))

        assert result == ([], 0)

    async def test_get_unread_count_zero(self):
        mock_result = MagicMock()
        mock_result.scalar.return_value = 0

        self.session.execute.return_value = mock_result

        count = await self.repo.get_unread_count(user_id= UUID("11111111-1111-1111-1111-111111111111"), service_type=NotificationServiceType.TALKO)

        assert count == 0

    async def test_get_notification_preferences_defaults_to_enabled(self):
        self.session.execute.return_value = MagicMock()
        self.session.execute.return_value.scalars.return_value.all.return_value = []

        result = await self.repo.get_notification_preferences(user_id= UUID("11111111-1111-1111-1111-111111111111"))

        expected_preferences = {
            (NotificationSourceEnum.TALKO, None, NotificationPreferenceStateEnum.ENABLED),
            (NotificationSourceEnum.OBOTAAI, None, NotificationPreferenceStateEnum.ENABLED),
        }

        assert len(result) == 2
        assert {
            (item.source, item.scope, item.state) for item in result
        } == expected_preferences

    async def test_get_notification_preferences_talko_disabled(self):
        mock_row = MagicMock()
        mock_row.key = UserConfigEnum.NOTIFICATION_TALKO.value
        mock_row.value = False

        self.session.execute.return_value = MagicMock()
        self.session.execute.return_value.scalars.return_value.all.return_value = [mock_row]

        result = await self.repo.get_notification_preferences(user_id= UUID("11111111-1111-1111-1111-111111111111"))

        talko_entries = [
            item
            for item in result
            if item.source == NotificationSourceEnum.TALKO
        ]

        assert len(talko_entries) == 1
        assert talko_entries[0].state == NotificationPreferenceStateEnum.DISABLED
        assert len(result) == 2

    async def test_is_notification_enabled_defaults_to_true(self):
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        self.session.execute.return_value = mock_result

        result = await self.repo.is_notification_enabled(user_id= UUID("11111111-1111-1111-1111-111111111111"), source="talko")

        assert result is True

    async def test_is_notification_enabled_talko_disabled(self):
        mock_result = MagicMock()
        mock_result.all.return_value = [
            (UserConfigEnum.NOTIFICATION_TALKO.value, False),
        ]

        self.session.execute.return_value = mock_result

        result = await self.repo.is_notification_enabled(
            user_id= UUID("11111111-1111-1111-1111-111111111111"),
            source="talko",
        )

        assert result is False

    async def test_upsert_notification_preferences(self):
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        self.session.execute.return_value = mock_result

        prefs = [
            NotificationPreferenceItem(
                source=NotificationSourceEnum.TALKO,
                scope=None,
                state=NotificationPreferenceStateEnum.DISABLED,
            )
        ]

        self.repo.get_notification_preferences = AsyncMock(return_value=prefs)
        result = await self.repo.upsert_notification_preferences(user_id= UUID("11111111-1111-1111-1111-111111111111"), preferences=prefs)

        assert result == prefs
        self.session.execute.assert_awaited()
        assert self.session.commit.await_count >= 1

    @patch("src.components.common.datetime.DateTimeUtil.get_current_time")
    async def test_mark_as_read_all_unread_only(self, mock_time):
        mock_time.return_value = "now"

        await self.repo.mark_as_read(user_id= UUID("11111111-1111-1111-1111-111111111111"), notification_ids=None)

        assert self.session.execute.called
        self.session.commit.assert_awaited_once()

    @patch("src.components.common.datetime.DateTimeUtil.get_current_time")
    async def test_mark_as_read_with_ids_non_empty(self, mock_time):
        mock_time.return_value = "now"

        await self.repo.mark_as_read(user_id= UUID("11111111-1111-1111-1111-111111111111"), notification_ids=[UUID("10101010-1010-1010-1010-101010101010")])

        assert self.session.execute.called
        self.session.commit.assert_awaited_once()
    
