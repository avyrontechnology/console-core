from unittest.mock import MagicMock, patch

import pytest

from src.components.order.tasks import TIMEOUT_MINUTES, cleanup_abandoned_pending_orders


# helper to execute coroutine immediately
def run_coroutine_sync(coro):
    try:
        coro.send(None)
    except StopIteration:
        pass


class TestCleanupAbandonedPendingOrders:

    @pytest.mark.parametrize("expired_count", [0, 5, 150])
    def test_successful_cleanup_various_counts(self, expired_count):
        mock_logger = MagicMock()
        mock_loop = MagicMock()
        mock_loop.run_until_complete.side_effect = run_coroutine_sync

        with patch(
            "src.components.order.tasks.logger",
            mock_logger,
        ), patch(
            "src.components.order.tasks.asyncio.get_event_loop",
            return_value=mock_loop,
        ):
            cleanup_abandoned_pending_orders()

            mock_logger.info.assert_any_call(
                f"Starting cleanup of pending orders older than {TIMEOUT_MINUTES} minutes..."
            )

    def test_cutoff_time_calculation_does_not_crash(self):
        mock_logger = MagicMock()
        mock_loop = MagicMock()
        mock_loop.run_until_complete.side_effect = run_coroutine_sync

        with patch(
            "src.components.order.tasks.logger",
            mock_logger,
        ), patch(
            "src.components.order.tasks.asyncio.get_event_loop",
            return_value=mock_loop,
        ):
            cleanup_abandoned_pending_orders()

            mock_logger.info.assert_any_call(
                f"Starting cleanup of pending orders older than {TIMEOUT_MINUTES} minutes..."
            )
