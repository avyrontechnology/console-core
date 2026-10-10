"""Tests for Grace Period Celery task — expire_active_grace_periods."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


def _run_coroutine_sync(coro):
    """Drive a simple coroutine that never yields to the event loop."""
    try:
        coro.send(None)
    except StopIteration:
        pass


class TestExpireActiveGracePeriodsTask:
    """
    Strategy: the error-handling try/except lives *inside* the `_run()` coroutine.
    Mocking `run_until_complete` to raise bypasses that coroutine entirely, so
    the logger.error call never happens and the exception propagates out.

    Correct approach:
      - Happy-path / zero / N-expired tests  → mock `run_until_complete` with
        `_run_coroutine_sync` so the coroutine actually executes, and mock
        `grace_repo.expire_overdue` to return the desired count.
      - Error tests → mock `grace_repo.expire_overdue` to *raise*, so the
        exception is caught by the try/except *inside* `_run()` and
        `logger.error` is called correctly.
    """

    def _run_task(self, expired_count=0, repo_raises=None):
        mock_logger = MagicMock()
        mock_loop = MagicMock()
        mock_loop.run_until_complete.side_effect = _run_coroutine_sync

        mock_grace_repo = MagicMock()
        if repo_raises is not None:
            mock_grace_repo.expire_overdue = AsyncMock(side_effect=repo_raises)
        else:
            mock_grace_repo.expire_overdue = AsyncMock(return_value=expired_count)

        with patch("src.components.grace.tasks.logger", mock_logger), patch(
            "src.components.grace.tasks.asyncio.get_event_loop",
            return_value=mock_loop,
        ):
            from src.components.grace.tasks import expire_active_grace_periods

            expire_active_grace_periods(grace_repo=mock_grace_repo)

        return mock_logger

    # -------------------------------------------------------------------------
    # Startup log
    # -------------------------------------------------------------------------

    def test_logs_starting_message(self):
        mock_logger = self._run_task(expired_count=1)
        mock_logger.info.assert_any_call("expire_active_grace_periods: starting")

    def test_logs_starting_message_even_when_zero_expired(self):
        mock_logger = self._run_task(expired_count=0)
        mock_logger.info.assert_any_call("expire_active_grace_periods: starting")

    # -------------------------------------------------------------------------
    # Zero records expired
    # -------------------------------------------------------------------------

    def test_logs_no_overdue_when_count_is_zero(self):
        mock_logger = self._run_task(expired_count=0)
        mock_logger.info.assert_any_call(
            "expire_active_grace_periods: no overdue grace records found"
        )

    def test_does_not_log_expired_count_when_zero(self):
        mock_logger = self._run_task(expired_count=0)
        calls = [str(c) for c in mock_logger.info.call_args_list]
        assert not any("record(s)" in c for c in calls)

    # -------------------------------------------------------------------------
    # N records expired (parametrized)
    # -------------------------------------------------------------------------

    @pytest.mark.parametrize("count", [1, 5, 100, 150])
    def test_logs_expired_count_when_nonzero(self, count):
        mock_logger = self._run_task(expired_count=count)
        mock_logger.info.assert_any_call(
            "expire_active_grace_periods: expired {} grace record(s)".format(count)
        )

    @pytest.mark.parametrize("count", [1, 5, 100])
    def test_does_not_log_no_overdue_when_count_nonzero(self, count):
        mock_logger = self._run_task(expired_count=count)
        calls = [str(c) for c in mock_logger.info.call_args_list]
        assert not any("no overdue" in c for c in calls)

    # -------------------------------------------------------------------------
    # Error handling — repo raises inside _run(), caught by inner try/except
    # -------------------------------------------------------------------------

    def test_logs_critical_error_when_repo_raises(self):
        mock_logger = self._run_task(repo_raises=RuntimeError("DB gone"))
        mock_logger.error.assert_called_once()
        assert "critical error" in mock_logger.error.call_args[0][0]

    def test_task_does_not_raise_when_repo_raises(self):
        """expire_overdue raising must NOT propagate out of the task."""
        try:
            self._run_task(repo_raises=Exception("unexpected"))
        except Exception:
            pytest.fail("Task must swallow exceptions and not propagate them")

    def test_error_message_contains_exception_detail(self):
        mock_logger = self._run_task(repo_raises=RuntimeError("connection refused"))
        error_call = mock_logger.error.call_args[0][0]
        assert "connection refused" in error_call

    def test_no_error_log_on_success(self):
        mock_logger = self._run_task(expired_count=3)
        mock_logger.error.assert_not_called()
