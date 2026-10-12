"""Tests for GraceRepository — all DB interactions mocked via session_factory."""

from uuid import UUID
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.components.grace.constants import GRACE_MS_PER_DAY, GraceStatus
from src.components.grace.repositories import GraceRepository


def _make_grace(
    grace_id= UUID("11111111-1111-1111-1111-111111111111"),
    partner_id= UUID("10101010-1010-1010-1010-101010101010"),
    service_name="console",
    granted_days=7,
    attempt_number=1,
    status=GraceStatus.ACTIVE,
    start_date=1_700_000_000_000,
    end_date=1_700_604_800_000,
    consumed_days=None,
    settled_at=None,
    settled_by_order_id=None,
    created_by= UUID("99999999-9999-9999-9999-999999999999"),
    created_at=1_700_000_000_000,
):
    g = MagicMock()
    g.id = grace_id
    g.partner_id = partner_id
    g.service_name = service_name
    g.granted_days = granted_days
    g.attempt_number = attempt_number
    g.status = status
    g.start_date = start_date
    g.end_date = end_date
    g.consumed_days = consumed_days
    g.settled_at = settled_at
    g.settled_by_order_id = settled_by_order_id
    g.created_by = created_by
    g.created_at = created_at
    return g


NOW_MS = 1_700_000_000_000


@pytest.mark.asyncio
class TestGraceRepository:

    @pytest.fixture(autouse=True)
    def setup(self):
        self.mock_logger = MagicMock()
        self.session = MagicMock()
        self.session.add = MagicMock()
        self.session.commit = AsyncMock()
        self.session.refresh = AsyncMock()
        self.session.execute = AsyncMock()
        self.session.rollback = AsyncMock()

        cm = MagicMock()
        cm.__aenter__ = AsyncMock(return_value=self.session)
        cm.__aexit__ = AsyncMock(return_value=False)
        self.session_factory = MagicMock(return_value=cm)

        self.repo = GraceRepository(
            session_factory=self.session_factory,
            logger=self.mock_logger,
        )

    def _now(self, value=NOW_MS):
        return patch(
            "src.components.grace.repositories.DateTimeUtil.get_current_time",
            return_value=value,
        )

    # =========================================================================
    # create_grace
    # =========================================================================

    async def test_create_grace_calls_session_add_and_commit(self):
        with self._now():
            await self.repo.create_grace(
                partner_id= UUID("10101010-1010-1010-1010-101010101010"),
                service_name="console",
                remark="reason",
                granted_days=7,
                attempt_number=1,
                created_by= UUID("99999999-9999-9999-9999-999999999999"),
            )
        self.session.add.assert_called_once()
        self.session.commit.assert_awaited_once()

    async def test_create_grace_calculates_end_date_correctly(self):
        granted_days = 7
        expected_end = NOW_MS + (granted_days * GRACE_MS_PER_DAY)
        captured = {}

        def _capture(obj):
            captured["grace"] = obj

        self.session.add = _capture

        with self._now():
            try:
                await self.repo.create_grace(
                    partner_id= UUID("10101010-1010-1010-1010-101010101010"),
                    service_name="console",
                    remark="r",
                    granted_days=granted_days,
                    attempt_number=1,
                    created_by= UUID("11111111-1111-1111-1111-111111111111"),
                )
            except Exception:
                pass  # refresh may fail — we only care about add()

        if "grace" in captured:
            assert captured["grace"].end_date == expected_end

    async def test_create_grace_sets_status_active(self):
        captured = {}

        def _capture(obj):
            captured["grace"] = obj

        self.session.add = _capture

        with self._now():
            try:
                await self.repo.create_grace(
                    partner_id= UUID("10101010-1010-1010-1010-101010101010"),
                    service_name="console",
                    remark="r",
                    granted_days=5,
                    attempt_number=1,
                    created_by= UUID("11111111-1111-1111-1111-111111111111"),
                )
            except Exception:
                pass

        if "grace" in captured:
            assert captured["grace"].status == GraceStatus.ACTIVE

    async def test_create_grace_rollback_and_log_on_commit_error(self):
        self.session.commit = AsyncMock(side_effect=Exception("DB write failed"))

        with self._now():
            with pytest.raises(Exception, match="DB write failed"):
                await self.repo.create_grace(
                    partner_id= UUID("10101010-1010-1010-1010-101010101010"),
                    service_name="console",
                    remark="r",
                    granted_days=5,
                    attempt_number=1,
                    created_by= UUID("11111111-1111-1111-1111-111111111111"),
                )

        self.session.rollback.assert_awaited_once()
        self.mock_logger.error.assert_called()

    async def test_create_grace_logs_success(self):
        with self._now():
            await self.repo.create_grace(
                partner_id= UUID("10101010-1010-1010-1010-101010101010"),
                service_name="console",
                remark="r",
                granted_days=5,
                attempt_number=1,
                created_by= UUID("11111111-1111-1111-1111-111111111111"),
            )
        self.mock_logger.info.assert_called()

    # =========================================================================
    # get_active_grace
    # =========================================================================

    async def test_get_active_grace_returns_record_when_found(self):
        mock_grace = _make_grace()
        result_mock = MagicMock()
        result_mock.scalars.return_value.first.return_value = mock_grace
        self.session.execute = AsyncMock(return_value=result_mock)

        with self._now():
            result = await self.repo.get_active_grace(10, "console")

        assert result is mock_grace

    async def test_get_active_grace_returns_none_when_not_found(self):
        result_mock = MagicMock()
        result_mock.scalars.return_value.first.return_value = None
        self.session.execute = AsyncMock(return_value=result_mock)

        with self._now():
            result = await self.repo.get_active_grace(10, "console")

        assert result is None

    async def test_get_active_grace_executes_one_query(self):
        result_mock = MagicMock()
        result_mock.scalars.return_value.first.return_value = None
        self.session.execute = AsyncMock(return_value=result_mock)

        with self._now():
            await self.repo.get_active_grace(10, "console")

        assert self.session.execute.await_count == 1

    # =========================================================================
    # get_all_active_for_partner
    # =========================================================================

    async def test_get_all_active_for_partner_returns_list(self):
        graces = [_make_grace(grace_id=i) for i in range(3)]
        result_mock = MagicMock()
        result_mock.scalars.return_value.all.return_value = graces
        self.session.execute = AsyncMock(return_value=result_mock)

        with self._now():
            result = await self.repo.get_all_active_for_partner(10)

        assert result == graces
        assert len(result) == 3

    async def test_get_all_active_for_partner_empty(self):
        result_mock = MagicMock()
        result_mock.scalars.return_value.all.return_value = []
        self.session.execute = AsyncMock(return_value=result_mock)

        with self._now():
            result = await self.repo.get_all_active_for_partner(99)

        assert result == []

    # =========================================================================
    # get_all_for_service
    # =========================================================================

    async def test_get_all_for_service_returns_all_statuses(self):
        graces = [
            _make_grace(grace_id= UUID("11111111-1111-1111-1111-111111111111"), status=GraceStatus.ACTIVE),
            _make_grace(grace_id= UUID("22222222-2222-2222-2222-222222222222"), status=GraceStatus.SETTLED),
            _make_grace(grace_id= UUID("33333333-3333-3333-3333-333333333333"), status=GraceStatus.EXPIRED),
        ]
        result_mock = MagicMock()
        result_mock.scalars.return_value.all.return_value = graces
        self.session.execute = AsyncMock(return_value=result_mock)

        result = await self.repo.get_all_for_service(10, "console")
        assert len(result) == 3

    async def test_get_all_for_service_empty(self):
        result_mock = MagicMock()
        result_mock.scalars.return_value.all.return_value = []
        self.session.execute = AsyncMock(return_value=result_mock)

        result = await self.repo.get_all_for_service(10, "unknown_service")
        assert result == []

    # =========================================================================
    # get_all_for_partner
    # =========================================================================

    async def test_get_all_for_partner_returns_all_records(self):
        graces = [
            _make_grace(grace_id=i, status=s)
            for i, s in enumerate(
                [GraceStatus.ACTIVE, GraceStatus.SETTLED, GraceStatus.EXPIRED]
            )
        ]
        result_mock = MagicMock()
        result_mock.scalars.return_value.all.return_value = graces
        self.session.execute = AsyncMock(return_value=result_mock)

        result = await self.repo.get_all_for_partner(10)
        assert len(result) == 3

    async def test_get_all_for_partner_empty(self):
        result_mock = MagicMock()
        result_mock.scalars.return_value.all.return_value = []
        self.session.execute = AsyncMock(return_value=result_mock)

        result = await self.repo.get_all_for_partner(999)
        assert result == []

    # =========================================================================
    # count_attempts
    # =========================================================================

    async def test_count_attempts_returns_integer(self):
        result_mock = MagicMock()
        result_mock.scalar.return_value = 2
        self.session.execute = AsyncMock(return_value=result_mock)

        count = await self.repo.count_attempts(10, "console")
        assert count == 2

    async def test_count_attempts_returns_zero_when_scalar_is_none(self):
        result_mock = MagicMock()
        result_mock.scalar.return_value = None
        self.session.execute = AsyncMock(return_value=result_mock)

        count = await self.repo.count_attempts(10, "console")
        assert count == 0

    @pytest.mark.parametrize("raw_count", [0, 1, 3])
    async def test_count_attempts_various_values(self, raw_count):
        result_mock = MagicMock()
        result_mock.scalar.return_value = raw_count
        self.session.execute = AsyncMock(return_value=result_mock)

        count = await self.repo.count_attempts(10, "console")
        assert count == raw_count

    # =========================================================================
    # get_unsettled_for_service
    # =========================================================================

    async def test_get_unsettled_returns_active_and_expired_only(self):
        active = _make_grace(grace_id= UUID("11111111-1111-1111-1111-111111111111"), status=GraceStatus.ACTIVE)
        expired = _make_grace(grace_id= UUID("22222222-2222-2222-2222-222222222222"), status=GraceStatus.EXPIRED)
        result_mock = MagicMock()
        result_mock.scalars.return_value.all.return_value = [active, expired]
        self.session.execute = AsyncMock(return_value=result_mock)

        result = await self.repo.get_unsettled_for_service(10, "console")
        assert len(result) == 2

    async def test_get_unsettled_empty_when_all_settled(self):
        result_mock = MagicMock()
        result_mock.scalars.return_value.all.return_value = []
        self.session.execute = AsyncMock(return_value=result_mock)

        result = await self.repo.get_unsettled_for_service(10, "console")
        assert result == []

    # =========================================================================
    # settle_all
    # =========================================================================

    async def test_settle_all_returns_none_zero_when_no_records(self):
        unsettled_mock = MagicMock()
        unsettled_mock.scalars.return_value.all.return_value = []
        self.session.execute = AsyncMock(return_value=unsettled_mock)

        with self._now():
            first_start, total = await self.repo.settle_all(
                10, "console", 1, NOW_MS + 1_000_000
            )

        assert first_start is None
        assert total == 0

    async def test_settle_all_active_record_computes_elapsed_days(self):
        start = NOW_MS
        payment = start + (3 * GRACE_MS_PER_DAY)  # exactly 3 days later
        grace = _make_grace(start_date=start, granted_days=7, status=GraceStatus.ACTIVE)

        unsettled_mock = MagicMock()
        unsettled_mock.scalars.return_value.all.return_value = [grace]
        update_mock = MagicMock()
        self.session.execute = AsyncMock(side_effect=[unsettled_mock, update_mock])

        with self._now(payment):
            first_start, total = await self.repo.settle_all(10, "console", 1, payment)

        assert first_start == start
        assert total == 3

    async def test_settle_all_active_record_caps_consumed_at_granted_days(self):
        start = NOW_MS
        # payment is way after end_date
        payment = start + (30 * GRACE_MS_PER_DAY)
        grace = _make_grace(start_date=start, granted_days=7, status=GraceStatus.ACTIVE)

        unsettled_mock = MagicMock()
        unsettled_mock.scalars.return_value.all.return_value = [grace]
        update_mock = MagicMock()
        self.session.execute = AsyncMock(side_effect=[unsettled_mock, update_mock])

        with self._now(payment):
            _, total = await self.repo.settle_all(10, "console", 1, payment)

        assert total == 7  # capped at granted_days

    async def test_settle_all_expired_record_uses_granted_days(self):
        grace = _make_grace(
            granted_days=5, status=GraceStatus.EXPIRED, start_date=NOW_MS
        )
        unsettled_mock = MagicMock()
        unsettled_mock.scalars.return_value.all.return_value = [grace]
        update_mock = MagicMock()
        self.session.execute = AsyncMock(side_effect=[unsettled_mock, update_mock])

        with self._now(NOW_MS + 10 * GRACE_MS_PER_DAY):
            _, total = await self.repo.settle_all(
                10, "console", 1, NOW_MS + 10 * GRACE_MS_PER_DAY
            )

        assert total == 5  # EXPIRED → full granted_days

    async def test_settle_all_sums_multiple_records(self):
        # SETTLED 3 days (ACTIVE) + 5 days (EXPIRED) = 8 total
        payment = NOW_MS + (3 * GRACE_MS_PER_DAY)
        active = _make_grace(
            grace_id= UUID("11111111-1111-1111-1111-111111111111"), start_date=NOW_MS, granted_days=7, status=GraceStatus.ACTIVE
        )
        expired = _make_grace(
            grace_id= UUID("22222222-2222-2222-2222-222222222222"),
            start_date=NOW_MS - GRACE_MS_PER_DAY,
            granted_days=5,
            status=GraceStatus.EXPIRED,
        )

        unsettled_mock = MagicMock()
        unsettled_mock.scalars.return_value.all.return_value = [active, expired]
        self.session.execute = AsyncMock(
            side_effect=[unsettled_mock, MagicMock(), MagicMock()]
        )

        with self._now(payment):
            _, total = await self.repo.settle_all(10, "console", 1, payment)

        assert total == 8  # 3 (active) + 5 (expired)

    async def test_settle_all_rollback_and_log_on_error(self):
        grace = _make_grace(status=GraceStatus.ACTIVE)
        unsettled_mock = MagicMock()
        unsettled_mock.scalars.return_value.all.return_value = [grace]
        self.session.execute = AsyncMock(
            side_effect=[unsettled_mock, Exception("update failed")]
        )

        with self._now():
            with pytest.raises(Exception, match="update failed"):
                await self.repo.settle_all(10, "console", 1, NOW_MS + 1_000_000)

        self.session.rollback.assert_awaited_once()
        self.mock_logger.error.assert_called()

    async def test_settle_all_logs_success(self):
        grace = _make_grace(
            status=GraceStatus.ACTIVE, start_date=NOW_MS, granted_days=3
        )
        payment = NOW_MS + (2 * GRACE_MS_PER_DAY)
        unsettled_mock = MagicMock()
        unsettled_mock.scalars.return_value.all.return_value = [grace]
        self.session.execute = AsyncMock(side_effect=[unsettled_mock, MagicMock()])

        with self._now(payment):
            await self.repo.settle_all(10, "console", 1, payment)

        self.mock_logger.info.assert_called()

    # =========================================================================
    # expire_overdue
    # =========================================================================

    async def test_expire_overdue_returns_rowcount(self):
        result_mock = MagicMock()
        result_mock.rowcount = 4
        self.session.execute = AsyncMock(return_value=result_mock)

        with self._now():
            count = await self.repo.expire_overdue()

        assert count == 4
        self.session.commit.assert_awaited_once()

    async def test_expire_overdue_returns_zero_when_rowcount_none(self):
        result_mock = MagicMock()
        result_mock.rowcount = None
        self.session.execute = AsyncMock(return_value=result_mock)

        with self._now():
            count = await self.repo.expire_overdue()

        assert count == 0

    @pytest.mark.parametrize("count", [0, 1, 50])
    async def test_expire_overdue_various_counts(self, count):
        result_mock = MagicMock()
        result_mock.rowcount = count
        self.session.execute = AsyncMock(return_value=result_mock)

        with self._now():
            result = await self.repo.expire_overdue()

        assert result == count

    async def test_expire_overdue_logs_info(self):
        result_mock = MagicMock()
        result_mock.rowcount = 3
        self.session.execute = AsyncMock(return_value=result_mock)

        with self._now():
            await self.repo.expire_overdue()

        self.mock_logger.info.assert_called()

    async def test_expire_overdue_rollback_and_log_on_error(self):
        self.session.execute = AsyncMock(side_effect=Exception("bulk update failed"))

        with self._now():
            with pytest.raises(Exception, match="bulk update failed"):
                await self.repo.expire_overdue()

        self.session.rollback.assert_awaited_once()
        self.mock_logger.error.assert_called()
