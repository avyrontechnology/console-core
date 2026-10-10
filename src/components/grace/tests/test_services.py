"""Tests for GraceService — all repos and dependencies fully mocked."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.components.db_constants.loader.constant import DbConstants
from src.components.grace.constants import GraceStatus
from src.components.grace.errors import (
    GraceAlreadyActiveError,
    GraceMaxAttemptsError,
    GraceNoPriorOrderError,
    GraceNotEligibleError,
)
from src.components.grace.services import GraceService
from src.components.partner.error import PartnerNotFoundError


def _make_grace(
    grace_id=1,
    partner_id=10,
    service_name="console",
    granted_days=7,
    attempt_number=1,
    status=GraceStatus.ACTIVE,
    start_date=1_700_000_000_000,
    end_date=1_700_604_800_000,
    consumed_days=None,
    settled_at=None,
    settled_by_order_id=None,
    created_by=99,
    created_at=1_700_000_000_000,
    granted_by_name="Alice",
    remark="Test remark",
):
    """
    Build a MagicMock that mimics a GracePeriod ORM object.
    All Pydantic-touched fields are real Python values (not nested MagicMocks)
    so GraceResponse validation never fails.
    """
    g = MagicMock(spec=None)
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
    g.granted_by_name = granted_by_name
    g.remark = remark
    return g


NOW_MS = 1_700_000_000_000
_MAX_ATTEMPTS = DbConstants.MAX_GRACE_ATTEMPTS


@pytest.mark.asyncio
class TestGraceService:

    @pytest.fixture(autouse=True)
    def setup(self):
        self.grace_repo = AsyncMock()
        self.logger = MagicMock()
        self.entitlement_repo = AsyncMock()
        self.order_repo = AsyncMock()
        self.partner_repo = AsyncMock()

        self.service = GraceService(
            grace_repository=self.grace_repo,
            logger=self.logger,
        )

        self.internal_user = {"user_id": 99, "is_internal": True}
        self.external_user = {"user_id": 88, "is_internal": False}
        self.mock_grace = _make_grace()

        # Default: partner exists
        self.partner_repo.get_by_id = AsyncMock(return_value=MagicMock())

        # Default last order with one module
        mock_module = MagicMock()
        mock_plan = MagicMock()
        mock_plan.modules = [mock_module]
        mock_order = MagicMock()
        mock_order.id = 1
        mock_order.plan = mock_plan
        self.order_repo.get_latest_order_by_partner = AsyncMock(return_value=mock_order)

        # Default: no blocking entitlements
        self.entitlement_repo.get_active_entitlement = AsyncMock(return_value=None)
        self.entitlement_repo.get_scheduled_entitlements = AsyncMock(return_value=[])

        # Default: 0 prior attempts (safely below any MAX_GRACE_ATTEMPTS value)
        self.grace_repo.count_attempts = AsyncMock(return_value=0)
        self.grace_repo.get_active_grace = AsyncMock(return_value=None)
        self.grace_repo.create_grace = AsyncMock(return_value=self.mock_grace)

        self.valid_payload = {
            "partner_id": 10,
            "granted_days": 7,
            "remark": "Test remark",
        }

    def _patch_services(self, services):
        return patch(
            "src.components.grace.services.PlanUtils.split_modules_by_service",
            return_value={s: [] for s in services},
        )

    # =========================================================================
    # grant_grace — Guard 2: no prior order
    # =========================================================================

    async def test_raises_no_prior_order_when_no_last_order(self):
        self.order_repo.get_latest_order_by_partner = AsyncMock(return_value=None)
        with pytest.raises(GraceNoPriorOrderError):
            await self.service.grant_grace(
                payload=self.valid_payload,
                current_user=self.internal_user,
                entitlement_repo=self.entitlement_repo,
                order_repo=self.order_repo,
                partner_repo=self.partner_repo,
            )

    async def test_raises_no_prior_order_when_plan_is_none(self):
        mock_order = MagicMock()
        mock_order.plan = None
        self.order_repo.get_latest_order_by_partner = AsyncMock(return_value=mock_order)
        with pytest.raises(GraceNoPriorOrderError):
            await self.service.grant_grace(
                payload=self.valid_payload,
                current_user=self.internal_user,
                entitlement_repo=self.entitlement_repo,
                order_repo=self.order_repo,
                partner_repo=self.partner_repo,
            )

    async def test_raises_no_prior_order_when_modules_is_none(self):
        mock_plan = MagicMock()
        mock_plan.modules = None
        mock_order = MagicMock()
        mock_order.plan = mock_plan
        self.order_repo.get_latest_order_by_partner = AsyncMock(return_value=mock_order)
        with pytest.raises(GraceNoPriorOrderError):
            await self.service.grant_grace(
                payload=self.valid_payload,
                current_user=self.internal_user,
                entitlement_repo=self.entitlement_repo,
                order_repo=self.order_repo,
                partner_repo=self.partner_repo,
            )

    async def test_raises_no_prior_order_when_no_service_names_derived(self):
        with self._patch_services([]):
            with pytest.raises(GraceNoPriorOrderError):
                await self.service.grant_grace(
                    payload=self.valid_payload,
                    current_user=self.internal_user,
                    entitlement_repo=self.entitlement_repo,
                    order_repo=self.order_repo,
                    partner_repo=self.partner_repo,
                )

    async def test_no_prior_order_error_is_not_swallowed(self):
        self.order_repo.get_latest_order_by_partner = AsyncMock(return_value=None)
        with pytest.raises(GraceNoPriorOrderError):
            await self.service.grant_grace(
                payload=self.valid_payload,
                current_user=self.internal_user,
                entitlement_repo=self.entitlement_repo,
                order_repo=self.order_repo,
                partner_repo=self.partner_repo,
            )

    # =========================================================================
    # grant_grace — Guard 3: no active entitlement
    # =========================================================================

    async def test_raises_not_eligible_when_active_entitlement_exists(self):
        self.entitlement_repo.get_active_entitlement = AsyncMock(
            return_value=MagicMock()
        )
        with self._patch_services(["console"]):
            with pytest.raises(GraceNotEligibleError):
                await self.service.grant_grace(
                    payload=self.valid_payload,
                    current_user=self.internal_user,
                    entitlement_repo=self.entitlement_repo,
                    order_repo=self.order_repo,
                    partner_repo=self.partner_repo,
                )

    async def test_not_eligible_error_is_not_swallowed(self):
        self.entitlement_repo.get_active_entitlement = AsyncMock(
            return_value=MagicMock()
        )
        with self._patch_services(["console"]):
            with pytest.raises(GraceNotEligibleError):
                await self.service.grant_grace(
                    payload=self.valid_payload,
                    current_user=self.internal_user,
                    entitlement_repo=self.entitlement_repo,
                    order_repo=self.order_repo,
                    partner_repo=self.partner_repo,
                )

    # =========================================================================
    # grant_grace — Guard 4: no scheduled entitlement
    # =========================================================================

    async def test_raises_not_eligible_when_scheduled_entitlement_exists(self):
        scheduled = MagicMock()
        scheduled.service_name = "console"
        self.entitlement_repo.get_scheduled_entitlements = AsyncMock(
            return_value=[scheduled]
        )
        with self._patch_services(["console"]):
            with pytest.raises(GraceNotEligibleError):
                await self.service.grant_grace(
                    payload=self.valid_payload,
                    current_user=self.internal_user,
                    entitlement_repo=self.entitlement_repo,
                    order_repo=self.order_repo,
                    partner_repo=self.partner_repo,
                )

    async def test_scheduled_entitlement_for_different_service_does_not_block(self):
        scheduled = MagicMock()
        scheduled.service_name = "boards"
        self.entitlement_repo.get_scheduled_entitlements = AsyncMock(
            return_value=[scheduled]
        )
        with self._patch_services(["console"]):
            result = await self.service.grant_grace(
                payload=self.valid_payload,
                current_user=self.internal_user,
                entitlement_repo=self.entitlement_repo,
                order_repo=self.order_repo,
                partner_repo=self.partner_repo,
            )
        assert result is not None

    # =========================================================================
    # grant_grace — Guard 5: max attempts
    # =========================================================================

    async def test_raises_max_attempts_when_limit_reached(self):
        self.grace_repo.count_attempts = AsyncMock(return_value=_MAX_ATTEMPTS)
        with self._patch_services(["console"]):
            with pytest.raises(GraceMaxAttemptsError):
                await self.service.grant_grace(
                    payload=self.valid_payload,
                    current_user=self.internal_user,
                    entitlement_repo=self.entitlement_repo,
                    order_repo=self.order_repo,
                    partner_repo=self.partner_repo,
                )

    async def test_max_attempts_error_is_not_swallowed(self):
        self.grace_repo.count_attempts = AsyncMock(return_value=_MAX_ATTEMPTS)
        with self._patch_services(["console"]):
            with pytest.raises(GraceMaxAttemptsError):
                await self.service.grant_grace(
                    payload=self.valid_payload,
                    current_user=self.internal_user,
                    entitlement_repo=self.entitlement_repo,
                    order_repo=self.order_repo,
                    partner_repo=self.partner_repo,
                )

    async def test_does_not_raise_when_one_below_max_attempts(self):
        if _MAX_ATTEMPTS <= 1:
            pytest.skip("MAX_GRACE_ATTEMPTS=1, no room for 'one below' scenario")

        self.grace_repo.count_attempts = AsyncMock(return_value=_MAX_ATTEMPTS - 1)
        with self._patch_services(["console"]):
            result = await self.service.grant_grace(
                payload=self.valid_payload,
                current_user=self.internal_user,
                entitlement_repo=self.entitlement_repo,
                order_repo=self.order_repo,
                partner_repo=self.partner_repo,
            )
        assert result is not None

    # =========================================================================
    # grant_grace — Guard 6: no existing active grace
    # =========================================================================

    async def test_raises_already_active_when_grace_exists(self):
        self.grace_repo.get_active_grace = AsyncMock(return_value=self.mock_grace)
        with self._patch_services(["console"]):
            with pytest.raises(GraceAlreadyActiveError):
                await self.service.grant_grace(
                    payload=self.valid_payload,
                    current_user=self.internal_user,
                    entitlement_repo=self.entitlement_repo,
                    order_repo=self.order_repo,
                    partner_repo=self.partner_repo,
                )

    async def test_already_active_error_is_not_swallowed(self):
        self.grace_repo.get_active_grace = AsyncMock(return_value=self.mock_grace)
        with self._patch_services(["console"]):
            with pytest.raises(GraceAlreadyActiveError):
                await self.service.grant_grace(
                    payload=self.valid_payload,
                    current_user=self.internal_user,
                    entitlement_repo=self.entitlement_repo,
                    order_repo=self.order_repo,
                    partner_repo=self.partner_repo,
                )

    # =========================================================================
    # grant_grace — unexpected error path (logs + re-raises)
    # =========================================================================

    async def test_unexpected_error_is_logged_and_reraised(self):
        self.grace_repo.count_attempts = AsyncMock(
            side_effect=RuntimeError("DB exploded")
        )
        with self._patch_services(["console"]):
            with pytest.raises(RuntimeError, match="DB exploded"):
                await self.service.grant_grace(
                    payload=self.valid_payload,
                    current_user=self.internal_user,
                    entitlement_repo=self.entitlement_repo,
                    order_repo=self.order_repo,
                    partner_repo=self.partner_repo,
                )
        self.logger.error.assert_called_once()
        assert "grant_grace" in self.logger.error.call_args[0][0]

    async def test_unexpected_error_log_contains_partner_id(self):
        self.grace_repo.count_attempts = AsyncMock(side_effect=RuntimeError("boom"))
        with self._patch_services(["console"]):
            with pytest.raises(RuntimeError):
                await self.service.grant_grace(
                    payload=self.valid_payload,
                    current_user=self.internal_user,
                    entitlement_repo=self.entitlement_repo,
                    order_repo=self.order_repo,
                    partner_repo=self.partner_repo,
                )
        log_msg = self.logger.error.call_args[0][0]
        assert "10" in log_msg  # partner_id

    # =========================================================================
    # grant_grace — happy path
    # =========================================================================

    async def test_success_single_service_creates_one_record(self):
        with self._patch_services(["console"]):
            result = await self.service.grant_grace(
                payload=self.valid_payload,
                current_user=self.internal_user,
                entitlement_repo=self.entitlement_repo,
                order_repo=self.order_repo,
                partner_repo=self.partner_repo,
            )
        self.grace_repo.create_grace.assert_awaited_once()
        assert result.grace_id == self.mock_grace.id
        assert result.partner_id == self.mock_grace.partner_id

    async def test_success_multi_service_creates_one_record_per_service(self):
        graces = [
            _make_grace(grace_id=i, service_name=s)
            for i, s in enumerate(["console", "boards", "reports"], start=1)
        ]
        self.grace_repo.create_grace = AsyncMock(side_effect=graces)
        with self._patch_services(["console", "boards", "reports"]):
            await self.service.grant_grace(
                payload=self.valid_payload,
                current_user=self.internal_user,
                entitlement_repo=self.entitlement_repo,
                order_repo=self.order_repo,
                partner_repo=self.partner_repo,
            )
        assert self.grace_repo.create_grace.await_count == 3

    async def test_attempt_number_is_prior_count_plus_one(self):
        safe_prior = max(0, _MAX_ATTEMPTS - 2) if _MAX_ATTEMPTS > 1 else 0
        self.grace_repo.count_attempts = AsyncMock(return_value=safe_prior)
        with self._patch_services(["console"]):
            await self.service.grant_grace(
                payload=self.valid_payload,
                current_user=self.internal_user,
                entitlement_repo=self.entitlement_repo,
                order_repo=self.order_repo,
                partner_repo=self.partner_repo,
            )
        kwargs = self.grace_repo.create_grace.call_args.kwargs
        assert kwargs["attempt_number"] == safe_prior + 1

    async def test_created_by_is_taken_from_current_user(self):
        with self._patch_services(["console"]):
            await self.service.grant_grace(
                payload=self.valid_payload,
                current_user=self.internal_user,
                entitlement_repo=self.entitlement_repo,
                order_repo=self.order_repo,
                partner_repo=self.partner_repo,
            )
        kwargs = self.grace_repo.create_grace.call_args.kwargs
        assert kwargs["created_by"] == 99

    async def test_remark_is_passed_to_repo(self):
        with self._patch_services(["console"]):
            await self.service.grant_grace(
                payload={**self.valid_payload, "remark": "special reason"},
                current_user=self.internal_user,
                entitlement_repo=self.entitlement_repo,
                order_repo=self.order_repo,
                partner_repo=self.partner_repo,
            )
        kwargs = self.grace_repo.create_grace.call_args.kwargs
        assert kwargs["remark"] == "special reason"

    async def test_returns_first_created_grace_response(self):
        first = _make_grace(grace_id=1, service_name="console")
        second = _make_grace(grace_id=2, service_name="boards")
        self.grace_repo.create_grace = AsyncMock(side_effect=[first, second])
        with self._patch_services(["console", "boards"]):
            result = await self.service.grant_grace(
                payload=self.valid_payload,
                current_user=self.internal_user,
                entitlement_repo=self.entitlement_repo,
                order_repo=self.order_repo,
                partner_repo=self.partner_repo,
            )
        assert result.grace_id == 1

    async def test_no_error_log_on_success(self):
        with self._patch_services(["console"]):
            await self.service.grant_grace(
                payload=self.valid_payload,
                current_user=self.internal_user,
                entitlement_repo=self.entitlement_repo,
                order_repo=self.order_repo,
                partner_repo=self.partner_repo,
            )
        self.logger.error.assert_not_called()

    # =========================================================================
    # settle_grace — happy path
    # =========================================================================

    async def test_settle_grace_returns_tuple_from_repo(self):
        self.grace_repo.settle_all = AsyncMock(return_value=(NOW_MS, 5))
        first_start, consumed = await self.service.settle_grace(
            partner_id=10, service_name="console", order_id=1
        )
        assert first_start == NOW_MS
        assert consumed == 5

    async def test_settle_grace_no_records_returns_none_zero(self):
        self.grace_repo.settle_all = AsyncMock(return_value=(None, 0))
        first_start, consumed = await self.service.settle_grace(
            partner_id=10, service_name="console", order_id=1
        )
        assert first_start is None
        assert consumed == 0

    async def test_settle_grace_uses_current_time_when_payment_date_none(self):
        self.grace_repo.settle_all = AsyncMock(return_value=(None, 0))
        with patch(
            "src.components.grace.services.DateTimeUtil.get_current_time",
            return_value=NOW_MS + 999,
        ):
            await self.service.settle_grace(
                partner_id=10, service_name="console", order_id=1, payment_date_ms=None
            )
        kwargs = self.grace_repo.settle_all.call_args.kwargs
        assert kwargs["payment_date_ms"] == NOW_MS + 999

    async def test_settle_grace_uses_provided_payment_date(self):
        self.grace_repo.settle_all = AsyncMock(return_value=(None, 0))
        await self.service.settle_grace(
            partner_id=10,
            service_name="console",
            order_id=1,
            payment_date_ms=NOW_MS + 50_000,
        )
        kwargs = self.grace_repo.settle_all.call_args.kwargs
        assert kwargs["payment_date_ms"] == NOW_MS + 50_000

    async def test_settle_grace_passes_order_id_to_repo(self):
        self.grace_repo.settle_all = AsyncMock(return_value=(None, 0))
        await self.service.settle_grace(
            partner_id=10, service_name="console", order_id=42
        )
        kwargs = self.grace_repo.settle_all.call_args.kwargs
        assert kwargs["order_id"] == 42

    async def test_settle_grace_logs_start_and_completion(self):
        self.grace_repo.settle_all = AsyncMock(return_value=(NOW_MS, 3))
        await self.service.settle_grace(
            partner_id=10, service_name="console", order_id=1
        )
        assert self.logger.info.call_count >= 2

    async def test_settle_grace_no_error_log_on_success(self):
        self.grace_repo.settle_all = AsyncMock(return_value=(NOW_MS, 3))
        await self.service.settle_grace(
            partner_id=10, service_name="console", order_id=1
        )
        self.logger.error.assert_not_called()

    # =========================================================================
    # settle_grace — unexpected error (logs + re-raises)
    # =========================================================================

    async def test_settle_grace_unexpected_error_is_logged_and_reraised(self):
        self.grace_repo.settle_all = AsyncMock(side_effect=RuntimeError("settle fail"))
        with pytest.raises(RuntimeError, match="settle fail"):
            await self.service.settle_grace(
                partner_id=10, service_name="console", order_id=1
            )
        self.logger.error.assert_called_once()
        log_msg = self.logger.error.call_args[0][0]
        assert "settle_grace" in log_msg

    async def test_settle_grace_error_log_contains_partner_service_order(self):
        self.grace_repo.settle_all = AsyncMock(side_effect=RuntimeError("boom"))
        with pytest.raises(RuntimeError):
            await self.service.settle_grace(
                partner_id=10, service_name="console", order_id=42
            )
        log_msg = self.logger.error.call_args[0][0]
        assert "10" in log_msg
        assert "console" in log_msg
        assert "42" in log_msg

    # =========================================================================
    # get_grace_status — happy path
    # =========================================================================

    async def test_status_no_records_all_defaults(self):
        self.grace_repo.get_all_for_partner = AsyncMock(return_value=[])
        self.grace_repo.get_all_active_for_partner = AsyncMock(return_value=[])
        result = await self.service.get_grace_status(10, partner_repo=self.partner_repo)
        assert result.has_active_grace is False
        assert result.current_grace is None
        assert result.total_attempts_used == 0
        assert result.attempts_remaining == _MAX_ATTEMPTS
        assert result.total_consumed_days == 0
        assert result.created_by is None
        assert result.granted_by_name is None

    async def test_status_with_one_active_grace(self):
        active = _make_grace()
        self.grace_repo.get_all_for_partner = AsyncMock(return_value=[active])
        self.grace_repo.get_all_active_for_partner = AsyncMock(return_value=[active])
        result = await self.service.get_grace_status(10, partner_repo=self.partner_repo)
        assert result.has_active_grace is True
        assert result.current_grace is not None
        assert result.total_attempts_used == 1
        assert result.attempts_remaining == max(_MAX_ATTEMPTS - 1, 0)

    async def test_status_counts_only_settled_consumed_days(self):
        settled = _make_grace(grace_id=1, status=GraceStatus.SETTLED, consumed_days=5)
        active = _make_grace(grace_id=2, status=GraceStatus.ACTIVE, consumed_days=None)
        expired = _make_grace(grace_id=3, status=GraceStatus.EXPIRED, consumed_days=3)
        self.grace_repo.get_all_for_partner = AsyncMock(
            return_value=[settled, active, expired]
        )
        self.grace_repo.get_all_active_for_partner = AsyncMock(return_value=[active])
        result = await self.service.get_grace_status(10, partner_repo=self.partner_repo)
        assert result.total_consumed_days == 5

    async def test_status_attempts_remaining_floored_at_zero(self):
        records = [_make_grace(grace_id=i) for i in range(_MAX_ATTEMPTS + 2)]
        self.grace_repo.get_all_for_partner = AsyncMock(return_value=records)
        self.grace_repo.get_all_active_for_partner = AsyncMock(return_value=[])
        result = await self.service.get_grace_status(10, partner_repo=self.partner_repo)
        assert result.attempts_remaining == 0

    async def test_status_uses_latest_record_for_metadata(self):
        first = _make_grace(
            grace_id=1, created_by=1, created_at=100, granted_by_name="Alice"
        )
        latest = _make_grace(
            grace_id=2, created_by=2, created_at=200, granted_by_name="Bob"
        )
        self.grace_repo.get_all_for_partner = AsyncMock(return_value=[first, latest])
        self.grace_repo.get_all_active_for_partner = AsyncMock(return_value=[])
        result = await self.service.get_grace_status(10, partner_repo=self.partner_repo)
        assert result.created_by == 2
        assert result.granted_by_name == "Bob"

    async def test_status_service_name_from_active_grace(self):
        active = _make_grace(service_name="boards")
        self.grace_repo.get_all_for_partner = AsyncMock(return_value=[active])
        self.grace_repo.get_all_active_for_partner = AsyncMock(return_value=[active])
        result = await self.service.get_grace_status(10, partner_repo=self.partner_repo)
        assert result.service_name == "boards"

    async def test_status_service_name_empty_when_no_active(self):
        settled = _make_grace(status=GraceStatus.SETTLED, consumed_days=3)
        self.grace_repo.get_all_for_partner = AsyncMock(return_value=[settled])
        self.grace_repo.get_all_active_for_partner = AsyncMock(return_value=[])
        result = await self.service.get_grace_status(10, partner_repo=self.partner_repo)
        assert result.service_name == ""

    async def test_status_no_error_log_on_success(self):
        self.grace_repo.get_all_for_partner = AsyncMock(return_value=[])
        self.grace_repo.get_all_active_for_partner = AsyncMock(return_value=[])
        await self.service.get_grace_status(10, partner_repo=self.partner_repo)
        self.logger.error.assert_not_called()

    # =========================================================================
    # get_grace_status — unexpected error (logs + re-raises)
    # =========================================================================

    async def test_status_unexpected_error_is_logged_and_reraised(self):
        self.grace_repo.get_all_for_partner = AsyncMock(
            side_effect=RuntimeError("DB down")
        )
        with pytest.raises(RuntimeError, match="DB down"):
            await self.service.get_grace_status(10, partner_repo=self.partner_repo)
        self.logger.error.assert_called_once()
        assert "get_grace_status" in self.logger.error.call_args[0][0]

    async def test_status_error_log_contains_partner_id(self):
        self.grace_repo.get_all_for_partner = AsyncMock(
            side_effect=RuntimeError("boom")
        )
        with pytest.raises(RuntimeError):
            await self.service.get_grace_status(10, partner_repo=self.partner_repo)
        log_msg = self.logger.error.call_args[0][0]
        assert "10" in log_msg

    # =========================================================================
    # _to_response — verified via grant_grace result
    # =========================================================================

    async def test_to_response_maps_all_fields_correctly(self):
        grace = _make_grace(
            grace_id=5,
            partner_id=10,
            service_name="boards",
            granted_days=7,
            attempt_number=1,
            status=GraceStatus.ACTIVE,
            start_date=NOW_MS,
            end_date=NOW_MS + 7 * 86_400_000,
            consumed_days=None,
            settled_at=None,
            settled_by_order_id=None,
            created_by=99,
            created_at=NOW_MS,
            granted_by_name="Alice",
            remark="check remark",
        )
        self.grace_repo.create_grace = AsyncMock(return_value=grace)

        with self._patch_services(["boards"]):
            result = await self.service.grant_grace(
                payload=self.valid_payload,
                current_user=self.internal_user,
                entitlement_repo=self.entitlement_repo,
                order_repo=self.order_repo,
                partner_repo=self.partner_repo,
            )

        assert result.grace_id == 5
        assert result.partner_id == 10
        assert result.service_name == "boards"
        assert result.granted_days == 7
        assert result.attempt_number == 1
        assert result.status == GraceStatus.ACTIVE
        assert result.start_date == NOW_MS
        assert result.end_date == NOW_MS + 7 * 86_400_000
        assert result.consumed_days is None
        assert result.settled_at is None
        assert result.settled_by_order_id is None
        assert result.created_by == 99
        assert result.created_at == NOW_MS
        assert result.granted_by_name == "Alice"
        assert result.remark == "check remark"

    # =========================================================================
    # grant_grace — Guard 1: partner validation
    # =========================================================================

    async def test_raises_partner_not_found_when_partner_does_not_exist(self):
        self.partner_repo.get_by_id = AsyncMock(return_value=None)
        with pytest.raises(PartnerNotFoundError):
            await self.service.grant_grace(
                payload=self.valid_payload,
                current_user=self.internal_user,
                entitlement_repo=self.entitlement_repo,
                order_repo=self.order_repo,
                partner_repo=self.partner_repo,
            )

    async def test_partner_not_found_error_is_not_swallowed_in_grant(self):
        self.partner_repo.get_by_id = AsyncMock(return_value=None)
        with pytest.raises(PartnerNotFoundError):
            await self.service.grant_grace(
                payload=self.valid_payload,
                current_user=self.internal_user,
                entitlement_repo=self.entitlement_repo,
                order_repo=self.order_repo,
                partner_repo=self.partner_repo,
            )

    async def test_partner_not_found_checked_before_order_lookup_in_grant(self):
        """partner check must fire before any order repo call."""
        self.partner_repo.get_by_id = AsyncMock(return_value=None)
        with pytest.raises(PartnerNotFoundError):
            await self.service.grant_grace(
                payload=self.valid_payload,
                current_user=self.internal_user,
                entitlement_repo=self.entitlement_repo,
                order_repo=self.order_repo,
                partner_repo=self.partner_repo,
            )
        self.order_repo.get_latest_order_by_partner.assert_not_awaited()

    async def test_grant_proceeds_when_partner_exists(self):
        self.partner_repo.get_by_id = AsyncMock(return_value=MagicMock())
        with self._patch_services(["console"]):
            result = await self.service.grant_grace(
                payload=self.valid_payload,
                current_user=self.internal_user,
                entitlement_repo=self.entitlement_repo,
                order_repo=self.order_repo,
                partner_repo=self.partner_repo,
            )
        assert result is not None

    # =========================================================================
    # get_grace_status — Guard 1: partner validation
    # =========================================================================

    async def test_status_raises_partner_not_found_when_partner_does_not_exist(self):
        self.partner_repo.get_by_id = AsyncMock(return_value=None)
        with pytest.raises(PartnerNotFoundError):
            await self.service.get_grace_status(10, partner_repo=self.partner_repo)

    async def test_status_partner_not_found_error_is_not_swallowed(self):
        self.partner_repo.get_by_id = AsyncMock(return_value=None)
        with pytest.raises(PartnerNotFoundError):
            await self.service.get_grace_status(10, partner_repo=self.partner_repo)

    async def test_status_partner_not_found_checked_before_repo_calls(self):
        """partner check must fire before any grace repo call."""
        self.partner_repo.get_by_id = AsyncMock(return_value=None)
        with pytest.raises(PartnerNotFoundError):
            await self.service.get_grace_status(10, partner_repo=self.partner_repo)
        self.grace_repo.get_all_for_partner.assert_not_awaited()
        self.grace_repo.get_all_active_for_partner.assert_not_awaited()

    async def test_status_proceeds_when_partner_exists(self):
        self.grace_repo.get_all_for_partner = AsyncMock(return_value=[])
        self.grace_repo.get_all_active_for_partner = AsyncMock(return_value=[])
        result = await self.service.get_grace_status(10, partner_repo=self.partner_repo)
        assert result is not None

    async def test_status_partner_not_found_is_logged_as_unexpected_error(self):
        """PartnerNotFoundError is not in the grace-specific allow-list, so it
        falls through to the generic except block and gets logged."""
        self.partner_repo.get_by_id = AsyncMock(return_value=None)
        with pytest.raises(PartnerNotFoundError):
            await self.service.get_grace_status(10, partner_repo=self.partner_repo)
        self.logger.error.assert_called_once()
        assert "get_grace_status" in self.logger.error.call_args[0][0]
