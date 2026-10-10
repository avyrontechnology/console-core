from unittest.mock import AsyncMock, MagicMock, call, patch

import pytest

from src.components.notifications.constants import NotificationServiceType


class TestDispatchNotificationTask:
    """
    Tests for dispatch_notification_task.

    The task itself is synchronous and calls run_async(main()).
    Inside main(), the task resolves the notification dependencies from
    Container.notification_channel_factory() and
    Container.notification_service(), so those providers must be mocked.
    """

    @pytest.fixture(autouse=True)
    def setup(self):
        self.logger = MagicMock()

        # -----------------------------
        # Subscription mock
        # -----------------------------
        self.sub = MagicMock()
        self.sub.channel_type = "FCM"
        self.sub.identifier = "token123"
        self.sub.user_id = 1

        # -----------------------------
        # Channel handler
        # send() is synchronous in tasks.py
        # -----------------------------
        self.channel_handler = MagicMock()
        self.channel_factory = MagicMock()
        self.channel_factory.get_channel.return_value = self.channel_handler

        # -----------------------------
        # Notification service
        # These methods are awaited by tasks.py
        # -----------------------------
        self.notification_service = MagicMock()

        self.notification_service.save_notification_history = AsyncMock()
        self.notification_service.should_send_notification = AsyncMock(
            return_value=True
        )
        self.notification_service.get_active_user_subscriptions = AsyncMock(
            return_value=[self.sub]
        )
        self.notification_service.has_active_session_for_push = AsyncMock(
            return_value=True
        )
        self.notification_service.deactivate_subscription = AsyncMock()

    def _run_task(
        self,
        *,
        service_type="maglo",
        subscriptions=None,
        channel_send_return="SUCCESS",
        channel_send_side_effect=None,
        save_history_side_effect=None,
        should_send_return=True,
        get_subscriptions_side_effect=None,
        session_active_return=True,
        session_active_side_effect=None,
        deactivate_side_effect=None,
        container_factory_side_effect=None,
        container_service_side_effect=None,
    ):
        """
        Execute the Celery task while mocking the actual dependency
        resolution performed inside tasks.py.
        """

        if subscriptions is not None:
            self.notification_service.get_active_user_subscriptions = AsyncMock(
                return_value=subscriptions,
                side_effect=get_subscriptions_side_effect,
            )
        elif get_subscriptions_side_effect is not None:
            self.notification_service.get_active_user_subscriptions = AsyncMock(
                side_effect=get_subscriptions_side_effect
            )

        if session_active_side_effect is not None:
            self.notification_service.has_active_session_for_push = AsyncMock(
                side_effect=session_active_side_effect,
            )
        else:
            self.notification_service.has_active_session_for_push = AsyncMock(
                return_value=session_active_return,
            )

        self.notification_service.save_notification_history = AsyncMock(
            side_effect=save_history_side_effect
        )
        self.notification_service.should_send_notification = AsyncMock(
            return_value=should_send_return
        )

        self.notification_service.deactivate_subscription = AsyncMock(
            side_effect=deactivate_side_effect
        )

        if channel_send_side_effect is not None:
            self.channel_handler.send.side_effect = channel_send_side_effect
        else:
            self.channel_handler.send.return_value = channel_send_return

        # The actual task calls:
        #
        # Container.notification_channel_factory()
        # Container.notification_service()
        #
        # Therefore mock those providers.
        container_factory = MagicMock(
            return_value=self.channel_factory,
            side_effect=container_factory_side_effect,
        )

        container_service = MagicMock(
            return_value=self.notification_service,
            side_effect=container_service_side_effect,
        )

        with (
            patch(
                "src.components.notifications.tasks.celery_logger",
                self.logger,
            ),
            patch(
                "src.components.notifications.tasks.Container.notification_channel_factory",
                container_factory,
            ),
            patch(
                "src.components.notifications.tasks.Container.notification_service",
                container_service,
            ),
            patch(
                "src.components.notifications.tasks.run_async",
                side_effect=lambda coroutine: self._execute_coroutine(coroutine),
            ),
        ):
            from src.components.notifications.tasks import (
                dispatch_notification_task,
            )

            dispatch_notification_task.run(
                1,
                "Hello",
                "World",
                {"key": "value"},
                "maglo",
                "LEAD_ASSIGNED",
                service_type,
                self.channel_factory,
                self.notification_service,
            )

        expected_service_type = NotificationServiceType(service_type)

        return (
            self.logger,
            self.notification_service,
            self.channel_factory,
            self.channel_handler,
            self.sub,
            expected_service_type,
        )

    def _assert_save_history_calls(self, notification_service, service_type):
        assert notification_service.save_notification_history.await_args_list == [
            call(
                user_id=1,
                title="Hello",
                body="World",
                data={"key": "value"},
                service_type=service_type,
            ),
        ]

    @staticmethod
    def _execute_coroutine(coroutine):
        """
        Execute the coroutine used by run_async.

        All awaited operations in these tests are AsyncMocks, so the
        coroutine can be driven to completion synchronously.
        """
        try:
            while True:
                coroutine.send(None)
        except StopIteration:
            return

    # ============================================================
    # SUCCESS
    # ============================================================

    def test_dispatch_success_sends_notification(self):
        (
            logger,
            notification_service,
            channel_factory,
            channel_handler,
            sub,
            service_type,
        ) = self._run_task(
            channel_send_return="SUCCESS",
        )

        self._assert_save_history_calls(notification_service, service_type)

        notification_service.should_send_notification.assert_awaited_once_with(
            user_id=1,
            source="maglo",
            event_name="LEAD_ASSIGNED",
        )

        notification_service.get_active_user_subscriptions.assert_awaited_once_with(
            1,
            service_type,
        )

        notification_service.has_active_session_for_push.assert_awaited_once_with(
            1,
            service_type,
        )

        channel_factory.get_channel.assert_called_once_with(
            sub.channel_type,
        )

        channel_handler.send.assert_called_once_with(
            identifier=sub.identifier,
            title="Hello",
            body="World",
            data={"key": "value"},
            service_type=service_type,
        )

        logger.info.assert_any_call(
            f"Notification sent successfully via "
            f"{sub.channel_type} to {sub.identifier} "
            f"for service {service_type}"
        )

    def test_dispatch_enabled_three_subscriptions_saves_one_history(self):
        sub1 = MagicMock()
        sub1.channel_type = "FCM"
        sub1.identifier = "token1"
        sub1.user_id = 1

        sub2 = MagicMock()
        sub2.channel_type = "FCM"
        sub2.identifier = "token2"
        sub2.user_id = 1

        sub3 = MagicMock()
        sub3.channel_type = "FCM"
        sub3.identifier = "token3"
        sub3.user_id = 1

        (
            logger,
            notification_service,
            channel_factory,
            channel_handler,
            _sub,
            service_type,
        ) = self._run_task(
            subscriptions=[sub1, sub2, sub3],
            channel_send_return="SUCCESS",
        )

        self._assert_save_history_calls(notification_service, service_type)

        notification_service.get_active_user_subscriptions.assert_awaited_once_with(
            1,
            service_type,
        )

        assert channel_factory.get_channel.call_count == 3
        assert channel_handler.send.call_count == 3
        assert [call.kwargs["identifier"] for call in channel_handler.send.call_args_list] == [
            "token1",
            "token2",
            "token3",
        ]

        logger.info.assert_any_call(
            f"Found 3 active subscriptions for service {service_type} Pushing..."
        )

    # ============================================================
    # UNREGISTERED
    # ============================================================

    def test_dispatch_unregistered_deactivates_subscription(self):
        (
            logger,
            notification_service,
            channel_factory,
            channel_handler,
            sub,
            service_type,
        ) = self._run_task(
            channel_send_return="UNREGISTERED",
        )

        self._assert_save_history_calls(notification_service, service_type)

        notification_service.deactivate_subscription.assert_awaited_once_with(
            sub.user_id,
            sub.identifier,
            service_type,
        )

        logger.info.assert_any_call(
            "Dispatching notification to user 1"
        )

    # ============================================================
    # FAILED
    # ============================================================

    def test_dispatch_failure_logs_warning(self):
        (
            logger,
            notification_service,
            channel_factory,
            channel_handler,
            sub,
            service_type,
        ) = self._run_task(
            channel_send_return="FAILED",
        )

        self._assert_save_history_calls(notification_service, service_type)

        notification_service.deactivate_subscription.assert_not_awaited()

        logger.warning.assert_called_with(
            f"Failed to send notification via "
            f"{sub.channel_type} to {sub.identifier} "
            f"for service {service_type}"
        )

    # ============================================================
    # VALUE ERROR
    # ============================================================

    def test_dispatch_channel_value_error_logs_warning(self):
        (
            logger,
            notification_service,
            channel_factory,
            channel_handler,
            sub,
            service_type,
        ) = self._run_task(
            channel_send_side_effect=ValueError("bad config"),
        )

        self._assert_save_history_calls(notification_service, service_type)

        logger.warning.assert_called_with(
            "Configuration Error: bad config"
        )

    # ============================================================
    # UNEXPECTED CHANNEL ERROR
    # ============================================================

    def test_dispatch_channel_unexpected_error_logs_error(self):
        (
            logger,
            notification_service,
            channel_factory,
            channel_handler,
            sub,
            service_type,
        ) = self._run_task(
            channel_send_side_effect=RuntimeError("boom"),
        )

        self._assert_save_history_calls(notification_service, service_type)

        assert any(
            "Unexpected error sending via FCM: boom" in str(call)
            for call in logger.error.call_args_list
        )

    # ============================================================
    # NO ACTIVE SUBSCRIPTIONS
    # ============================================================

    def test_dispatch_no_active_subscriptions(self):
        (
            logger,
            notification_service,
            channel_factory,
            channel_handler,
            sub,
            service_type,
        ) = self._run_task(
            subscriptions=[],
        )

        self._assert_save_history_calls(notification_service, service_type)

        notification_service.get_active_user_subscriptions.assert_awaited_once_with(
            1,
            service_type,
        )

        assert notification_service.has_active_session_for_push.await_count == 0

        channel_factory.get_channel.assert_not_called()
        channel_handler.send.assert_not_called()

        logger.info.assert_any_call(
            f"No active devices to push to for user 1 "
            f"services {service_type}. Saved to history only."
        )

    def test_dispatch_disabled_skips_history_and_delivery(self):
        sub = MagicMock()
        sub.channel_type = "FCM"
        sub.identifier = "token1"
        sub.user_id = 1

        (
            logger,
            notification_service,
            channel_factory,
            channel_handler,
            _sub,
            service_type,
        ) = self._run_task(
            subscriptions=[sub, MagicMock(), MagicMock()],
            should_send_return=False,
        )

        notification_service.save_notification_history.assert_not_awaited()
        notification_service.get_active_user_subscriptions.assert_not_awaited()
        channel_factory.get_channel.assert_not_called()
        channel_handler.send.assert_not_called()

        logger.info.assert_any_call(
            "maglo notifications for LEAD_ASSIGNED disabled for user 1"
        )

    def test_dispatch_disabled_ten_subscriptions_skips_history_and_delivery(self):
        subscriptions = []
        for index in range(10):
            sub = MagicMock()
            sub.channel_type = "FCM"
            sub.identifier = f"token{index}"
            sub.user_id = 1
            subscriptions.append(sub)

        (
            _logger,
            notification_service,
            channel_factory,
            channel_handler,
            _sub,
            _service_type,
        ) = self._run_task(
            subscriptions=subscriptions,
            should_send_return=False,
        )

        notification_service.save_notification_history.assert_not_awaited()
        notification_service.get_active_user_subscriptions.assert_not_awaited()
        channel_factory.get_channel.assert_not_called()
        channel_handler.send.assert_not_called()

    # ============================================================
    # FOUND SUBSCRIPTIONS
    # ============================================================

    def test_dispatch_logs_found_subscriptions(self):
        (
            logger,
            notification_service,
            channel_factory,
            channel_handler,
            sub,
            service_type,
        ) = self._run_task(
            channel_send_return="SUCCESS",
        )

        logger.info.assert_any_call(
            f"Found 1 active subscriptions for service "
            f"{service_type} Pushing..."
        )

    def test_dispatch_session_expired_before_send_skips_push(self):
        (
            logger,
            notification_service,
            channel_factory,
            channel_handler,
            sub,
            service_type,
        ) = self._run_task(
            session_active_return=False,
        )

        assert notification_service.save_notification_history.await_args_list == [
            call(
                user_id=1,
                title="Hello",
                body="World",
                data={"key": "value"},
                service_type=service_type,
            )
        ]

        notification_service.get_active_user_subscriptions.assert_awaited_once_with(
            1,
            service_type,
        )

        assert notification_service.has_active_session_for_push.await_args_list == [
            call(1, service_type)
        ]

        channel_factory.get_channel.assert_not_called()
        channel_handler.send.assert_not_called()

        logger.info.assert_any_call(
            f"Session expired before delivery — skipping push for user 1, "
            f"service {service_type}."
        )

    # ============================================================
    # HISTORY EXCEPTION
    # ============================================================

    def test_dispatch_outer_exception_logs_error(self):
        (
            logger,
            notification_service,
            channel_factory,
            channel_handler,
            sub,
            service_type,
        ) = self._run_task(
            save_history_side_effect=Exception("db down"),
        )

        assert any(
            f"Failed to dispatch notifications for user 1, "
            f"service {service_type}: db down" in str(call)
            for call in logger.error.call_args_list
        )

        notification_service.get_active_user_subscriptions.assert_not_awaited()
        channel_factory.get_channel.assert_not_called()

    # ============================================================
    # BABBLER
    # ============================================================

    def test_dispatch_babbler_service_type(self):
        (
            logger,
            notification_service,
            channel_factory,
            channel_handler,
            sub,
            service_type,
        ) = self._run_task(
            service_type="babbler",
            channel_send_return="SUCCESS",
        )

        assert service_type == NotificationServiceType.BABBLER

        self._assert_save_history_calls(
            notification_service,
            NotificationServiceType.BABBLER,
        )

        notification_service.should_send_notification.assert_awaited_once_with(
            user_id=1,
            source="maglo",
            event_name="LEAD_ASSIGNED",
        )

        notification_service.get_active_user_subscriptions.assert_awaited_once_with(
            1,
            NotificationServiceType.BABBLER,
        )

        channel_handler.send.assert_called_once_with(
            identifier=sub.identifier,
            title="Hello",
            body="World",
            data={"key": "value"},
            service_type=NotificationServiceType.BABBLER,
        )

        logger.info.assert_any_call(
            f"Notification sent successfully via "
            f"{sub.channel_type} to {sub.identifier} "
            f"for service {NotificationServiceType.BABBLER}"
        )

    # ============================================================
    # USER ID = NONE
    # ============================================================

    def test_dispatch_none_user_id_skips_dispatch(self):
        container_factory = MagicMock(return_value=self.channel_factory)
        container_service = MagicMock(return_value=self.notification_service)

        with (
            patch(
                "src.components.notifications.tasks.celery_logger",
                self.logger,
            ),
            patch(
                "src.components.notifications.tasks.Container.notification_channel_factory",
                container_factory,
            ),
            patch(
                "src.components.notifications.tasks.Container.notification_service",
                container_service,
            ),
            patch(
                "src.components.notifications.tasks.run_async",
                side_effect=lambda coroutine: self._execute_coroutine(coroutine),
            ),
        ):
            from src.components.notifications.tasks import (
                dispatch_notification_task,
            )

            dispatch_notification_task.run(
                None,
                "Hello",
                "World",
                {"key": "value"},
                "maglo",
                "LEAD_ASSIGNED",
                "maglo",
                self.channel_factory,
                self.notification_service,
            )

        self.logger.warning.assert_called_once_with(
            "Skipping notification dispatch with empty user_id"
        )

        self.notification_service.save_notification_history.assert_not_awaited()
        self.notification_service.get_active_user_subscriptions.assert_not_awaited()
        self.channel_factory.get_channel.assert_not_called()

    # ============================================================
    # GET SUBSCRIPTIONS EXCEPTION
    # ============================================================

    def test_dispatch_get_subscriptions_exception_logs_outer_error(self):
        (
            logger,
            notification_service,
            channel_factory,
            channel_handler,
            sub,
            service_type,
        ) = self._run_task(
            get_subscriptions_side_effect=Exception("subscription db down"),
        )

        self._assert_save_history_calls(notification_service, service_type)

        assert any(
            f"Failed to dispatch notifications for user 1, "
            f"service {service_type}: subscription db down" in str(call)
            for call in logger.error.call_args_list
        )

        channel_factory.get_channel.assert_not_called()

    # ============================================================
    # MULTIPLE SUBSCRIPTIONS
    # ============================================================

    def test_dispatch_multiple_subscriptions(self):
        sub1 = MagicMock()
        sub1.channel_type = "FCM"
        sub1.identifier = "token1"
        sub1.user_id = 1

        sub2 = MagicMock()
        sub2.channel_type = "FCM"
        sub2.identifier = "token2"
        sub2.user_id = 1

        self._run_task(
            subscriptions=[sub1, sub2],
            channel_send_return="SUCCESS",
        )

        self._assert_save_history_calls(
            self.notification_service,
            NotificationServiceType.MAGLO,
        )

        assert self.channel_factory.get_channel.call_count == 2
        assert self.channel_handler.send.call_count == 2

        calls = self.channel_handler.send.call_args_list

        assert calls[0].kwargs["identifier"] == "token1"
        assert calls[1].kwargs["identifier"] == "token2"

    # ============================================================
    # ONE SUBSCRIPTION FAILS, NEXT ONE STILL PROCESSES
    # ============================================================

    def test_dispatch_one_subscription_error_does_not_stop_next(self):
        sub1 = MagicMock()
        sub1.channel_type = "FCM"
        sub1.identifier = "token1"
        sub1.user_id = 1

        sub2 = MagicMock()
        sub2.channel_type = "FCM"
        sub2.identifier = "token2"
        sub2.user_id = 1

        self.notification_service.get_active_user_subscriptions = AsyncMock(
            return_value=[sub1, sub2]
        )

        self.channel_handler.send.side_effect = [
            RuntimeError("first failed"),
            "SUCCESS",
        ]

        container_factory = MagicMock(return_value=self.channel_factory)
        container_service = MagicMock(return_value=self.notification_service)

        with (
            patch(
                "src.components.notifications.tasks.celery_logger",
                self.logger,
            ),
            patch(
                "src.components.notifications.tasks.Container.notification_channel_factory",
                container_factory,
            ),
            patch(
                "src.components.notifications.tasks.Container.notification_service",
                container_service,
            ),
            patch(
                "src.components.notifications.tasks.run_async",
                side_effect=lambda coroutine: self._execute_coroutine(coroutine),
            ),
        ):
            from src.components.notifications.tasks import (
                dispatch_notification_task,
            )

            dispatch_notification_task.run(
                1,
                "Hello",
                "World",
                {"key": "value"},
                "maglo",
                "LEAD_ASSIGNED",
                "maglo",
                self.channel_factory,
                self.notification_service,
            )

        assert self.channel_handler.send.call_count == 2

        assert any(
            "Unexpected error sending via FCM: first failed" in str(call)
            for call in self.logger.error.call_args_list
        )

        self.logger.info.assert_any_call(
            "Notification sent successfully via FCM to token2 "
            "for service NotificationServiceType.MAGLO"
        )

    # ============================================================
    # CONTAINER SERVICE RESOLVES TO FUTURE
    # ============================================================

    def test_dispatch_notification_service_future_is_awaited(self):
        """
        Covers:

            if asyncio.isfuture(notification_service):
                notification_service = await notification_service
        """

        async def get_service():
            return self.notification_service

        future = asyncio_future = None

        # Create a real Future using the current event loop.
        import asyncio

        future = asyncio.get_event_loop().create_future()
        future.set_result(self.notification_service)

        container_factory = MagicMock(return_value=self.channel_factory)
        container_service = MagicMock(return_value=future)

        self.notification_service.get_active_user_subscriptions = AsyncMock(
            return_value=[]
        )

        with (
            patch(
                "src.components.notifications.tasks.celery_logger",
                self.logger,
            ),
            patch(
                "src.components.notifications.tasks.Container.notification_channel_factory",
                container_factory,
            ),
            patch(
                "src.components.notifications.tasks.Container.notification_service",
                container_service,
            ),
            patch(
                "src.components.notifications.tasks.run_async",
                side_effect=lambda coroutine: self._execute_coroutine(coroutine),
            ),
        ):
            from src.components.notifications.tasks import (
                dispatch_notification_task,
            )

            dispatch_notification_task.run(
                1,
                "Hello",
                "World",
                {"key": "value"},
                "maglo",
                "LEAD_ASSIGNED",
                "maglo",
                self.channel_factory,
                self.notification_service,
            )

        self.notification_service.save_notification_history.assert_awaited_once()
        self.notification_service.get_active_user_subscriptions.assert_awaited_once()
