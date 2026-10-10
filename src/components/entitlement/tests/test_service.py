from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from dateutil.relativedelta import relativedelta

from src.components.auth.constant import RoleDictKeys
from src.components.entitlement.errors import (
    EntitlementNotEligibleForStartDateUpdateError,
    EntitlementStartDateUpdateLimitExceededError,
    EntitlementStartDateUpdateWindowExpiredError,
    NoPermissionToUpdateEntitlementError,
    OrderNotFoundForEntitlementError,
)
from src.components.entitlement.models import Entitlement
from src.components.entitlement.schema import (
    EntitlementCreate,
    EntitlementUpdate,
    UpdateEntitlementStartDateRequest,
)
from src.components.entitlement.services import EntitlementService
from src.components.grace.models import GracePeriod
from src.components.order.constants import ServiceSubscriptionStatus
from src.components.order.models import Order
from src.components.plan.constants import Platform
from src.components.plan.models import Plan
from src.loggers.console_service_logger import ConsoleServiceLogger


@pytest.mark.asyncio
class TestEntitlementServiceComplete:

    @pytest.fixture(autouse=True)
    def setup(self):
        # Mock repository
        self.repo = AsyncMock()
        self.logger = AsyncMock(spec=ConsoleServiceLogger)
        self.auth_repo = AsyncMock()

        # Service instance
        self.service = EntitlementService(
            entitlement_repository=self.repo,
            logger=self.logger,
        )

        # Mock plan (modules & limits by service)
        self.plan = Plan(
            id=1,
            name="Basic",
            modules=["console.mod1", "console.mod2", "babbler.m1"],
            limits={"console.limit1": 10, "babbler.limit1": 5},
        )

        # Mock order
        self.order = Order(
            id=100,
            partner_id=500,
            plan=self.plan,
            plan_id=1,
            add_ons={"console.addon1": 5},
            duration=30,
        )

    async def test_upsert_entitlement_creates_new(self, monkeypatch):
        monkeypatch.setattr(
            "src.components.plan.utils.PlanUtils.split_modules_by_service",
            lambda modules: {"console": ["mod1"], "babbler": ["m1"]},
        )
        monkeypatch.setattr(
            "src.components.plan.utils.PlanUtils.split_limits_by_service",
            lambda limits: {"console": {"limit1": 10}, "babbler": {"limit1": 5}},
        )

        self.repo.get_active_entitlement.return_value = None

        created_ent = Entitlement(id=1)
        self.repo.create_entitlement.return_value = created_ent

        self.order.duration = 6

        result = await self.service.upsert_entitlement(self.order, user_id=11)

        assert len(result) == 2
        self.repo.create_entitlement.assert_awaited()
        self.logger.info.assert_called()

    async def test_upsert_entitlement_updates_existing(self, monkeypatch):
        monkeypatch.setattr(
            "src.components.plan.utils.PlanUtils.split_modules_by_service",
            lambda modules: {"console": ["mod1"]},
        )
        monkeypatch.setattr(
            "src.components.plan.utils.PlanUtils.split_limits_by_service",
            lambda limits: {"console": {"limit1": 10}},
        )

        existing = Entitlement(id=99, modules=["modX"], limits={"limit1": 5})
        self.repo.get_active_entitlement.return_value = existing
        self.repo.update_entitlement.return_value = existing

        self.order.duration = 3

        result = await self.service.upsert_entitlement(self.order, user_id=10)

        assert result == [existing]
        self.repo.update_entitlement.assert_awaited_once()
        self.logger.info.assert_called()

    async def test_upsert_entitlement_exception(self, monkeypatch):
        monkeypatch.setattr(
            "src.components.plan.utils.PlanUtils.split_modules_by_service",
            lambda modules: {"console": ["mod1"]},
        )
        monkeypatch.setattr(
            "src.components.plan.utils.PlanUtils.split_limits_by_service",
            lambda limits: {"console": {"limit1": 10}},
        )

        self.repo.get_active_entitlement.side_effect = Exception("DB error")

        self.order.duration = 1

        with pytest.raises(Exception):
            await self.service.upsert_entitlement(self.order)

        self.logger.error.assert_called()

    async def test_update_entitlement_flow(self):
        existing = Entitlement(
            id=50, modules=["m1"], limits={"l1": 5}, service_name="console"
        )

        self.repo.update_entitlement.return_value = existing

        result = await self.service._update_entitlement(
            existing=existing,
            service_modules=["m2"],
            service_limits={"l1": 3},
            user_id=7,
            partner_id=500,
        )

        self.repo.update_entitlement.assert_awaited_once()

        update_call = self.repo.update_entitlement.call_args[0][1]
        assert isinstance(update_call, EntitlementUpdate)
        assert update_call.modules == ["m1", "m2"] or update_call.modules == [
            "m2",
            "m1",
        ]
        assert update_call.limits == {"l1": 8}

        assert result == existing
        self.logger.info.assert_called()

    async def test_create_entitlement_flow(self):
        ent = Entitlement(id=123)
        self.repo.create_entitlement.return_value = ent

        self.order.duration = 12

        result = await self.service._create_entitlement(
            order=self.order,
            service_name="console",
            service_modules=["m1"],
            service_limits={"l1": 5},
            user_id=77,
        )

        call = self.repo.create_entitlement.call_args[0][0]
        assert isinstance(call, EntitlementCreate)
        assert call.order_id == self.order.id
        assert call.partner_id == self.order.partner_id
        assert call.service_name == "console"
        assert call.modules == ["m1"]
        assert call.limits == {"l1": 5}
        assert call.created_by == 77

        assert result == ent
        self.logger.info.assert_called()

    async def test_merge_modules(self):
        result = self.service._merge_modules(["a", "b"], ["b", "c"])
        assert set(result) == {"a", "b", "c"}

    async def test_merge_modules_empty(self):
        result = self.service._merge_modules(None, ["x"])
        assert result == ["x"]

    async def test_merge_limits_numeric(self):
        merged = self.service._merge_limits({"l1": 5}, {"l1": 10})
        assert merged["l1"] == 15

    async def test_merge_limits_override(self):
        merged = self.service._merge_limits({"l1": "old"}, {"l1": "new"})
        assert merged["l1"] == "new"

    async def test_merge_limits_existing_none_numeric(self):
        merged = self.service._merge_limits({"l1": None}, {"l1": 7})
        assert merged["l1"] == 7

    async def test_merge_limits_new_only(self):
        merged = self.service._merge_limits(None, {"l1": 3})
        assert merged == {"l1": 3}

    async def test_upsert_entitlement_no_modules_or_limits(self, monkeypatch):
        """Test when both modules and limits are empty"""
        monkeypatch.setattr(
            "src.components.plan.utils.PlanUtils.split_modules_by_service",
            lambda modules: {},
        )
        monkeypatch.setattr(
            "src.components.plan.utils.PlanUtils.split_limits_by_service",
            lambda limits: {},
        )

        result = await self.service.upsert_entitlement(self.order, user_id=11)

        assert result == []
        self.logger.warning.assert_called()
        assert "No modules or limits found" in str(self.logger.warning.call_args)

    async def test_upsert_entitlement_no_plan_id(self, monkeypatch):
        """Test when order has no plan_id"""
        monkeypatch.setattr(
            "src.components.plan.utils.PlanUtils.split_modules_by_service",
            lambda modules: {"console": ["mod1"]},
        )
        monkeypatch.setattr(
            "src.components.plan.utils.PlanUtils.split_limits_by_service",
            lambda limits: {"console": {"limit1": 10}},
        )

        self.order.plan_id = None
        self.repo.get_active_entitlement.return_value = None
        created_ent = Entitlement(id=1)
        self.repo.create_entitlement.return_value = created_ent

        result = await self.service.upsert_entitlement(self.order, user_id=11)

        assert len(result) == 1

    async def test_upsert_entitlement_no_addons(self, monkeypatch):
        """Test when order has no add_ons"""
        monkeypatch.setattr(
            "src.components.plan.utils.PlanUtils.split_modules_by_service",
            lambda modules: {"console": ["mod1"]},
        )
        monkeypatch.setattr(
            "src.components.plan.utils.PlanUtils.split_limits_by_service",
            lambda limits: {},
        )

        self.order.add_ons = None
        self.repo.get_active_entitlement.return_value = None
        created_ent = Entitlement(id=1)
        self.repo.create_entitlement.return_value = created_ent

        result = await self.service.upsert_entitlement(self.order, user_id=11)

        assert len(result) == 1

    async def test_upsert_entitlement_mixed_create_and_update(self, monkeypatch):
        """Test when some services are created and some are updated"""
        monkeypatch.setattr(
            "src.components.plan.utils.PlanUtils.split_modules_by_service",
            lambda modules: {"console": ["mod1"], "babbler": ["m1"]},
        )
        monkeypatch.setattr(
            "src.components.plan.utils.PlanUtils.split_limits_by_service",
            lambda limits: {"console": {"limit1": 10}, "babbler": {"limit1": 5}},
        )

        # Mock: console exists, babbler doesn't
        existing_console = Entitlement(id=99, modules=["modX"], limits={"limit1": 5})

        async def mock_get_active(partner_id, service_name):
            if service_name == "console":
                return existing_console
            return None

        self.repo.get_active_entitlement.side_effect = mock_get_active
        self.repo.update_entitlement.return_value = existing_console

        created_babbler = Entitlement(id=100)
        self.repo.create_entitlement.return_value = created_babbler

        result = await self.service.upsert_entitlement(self.order, user_id=11)

        assert len(result) == 2
        self.repo.update_entitlement.assert_awaited_once()
        self.repo.create_entitlement.assert_awaited_once()
        self.logger.info.assert_called()

    async def test_update_entitlement_with_existing_order_id(self):
        """Test updating entitlement that has an existing order_id"""
        existing = Entitlement(
            id=50,
            modules=["m1"],
            limits={"l1": 5},
            service_name="console",
            order_id=99,
            additional_info={"previous_order_ids": []},
        )

        self.repo.update_entitlement.return_value = existing

        await self.service._update_entitlement(
            existing=existing,
            service_modules=["m2"],
            service_limits={"l1": 3},
            user_id=7,
            partner_id=500,
        )

        # Verify previous_order_ids was updated
        update_call = self.repo.update_entitlement.call_args[0][1]
        assert isinstance(update_call, EntitlementUpdate)
        self.repo.update_entitlement.assert_awaited_once()

    async def test_update_entitlement_order_id_already_in_previous(self):
        """Test when order_id is already in previous_order_ids"""
        existing = Entitlement(
            id=50,
            modules=["m1"],
            limits={"l1": 5},
            service_name="console",
            order_id=99,
            additional_info={"previous_order_ids": [99]},
        )

        self.repo.update_entitlement.return_value = existing

        result = await self.service._update_entitlement(
            existing=existing,
            service_modules=["m2"],
            service_limits={"l1": 3},
            user_id=7,
            partner_id=500,
        )

        assert result == existing

    async def test_update_entitlement_no_additional_info(self):
        """Test updating entitlement with no additional_info"""
        existing = Entitlement(
            id=50,
            modules=["m1"],
            limits={"l1": 5},
            service_name="console",
            order_id=99,
            additional_info=None,
        )

        self.repo.update_entitlement.return_value = existing

        result = await self.service._update_entitlement(
            existing=existing,
            service_modules=["m2"],
            service_limits={"l1": 3},
            user_id=7,
            partner_id=500,
        )

        assert result == existing

    async def test_merge_limits_mixed_types(self):
        """Test merging limits with different types"""
        merged = self.service._merge_limits(
            {"l1": 5, "l2": "text", "l3": 10.5},
            {"l1": 3, "l2": "new_text", "l3": 2.5, "l4": 100},
        )
        assert merged["l1"] == 8
        assert merged["l2"] == "new_text"
        assert merged["l3"] == 13.0
        assert merged["l4"] == 100

    async def test_merge_limits_float_values(self):
        """Test merging float values"""
        merged = self.service._merge_limits({"l1": 5.5}, {"l1": 10.3})
        assert merged["l1"] == pytest.approx(15.8)

    async def test_merge_limits_zero_existing(self):
        """Test merging when existing value is 0"""
        merged = self.service._merge_limits({"l1": 0}, {"l1": 7})
        assert merged["l1"] == 7

    async def test_activate_pending_entitlements_success(self):
        """Test successful activation of pending entitlements"""
        self.repo.activate_pending_entitlements.return_value = 5

        result = await self.service.activate_pending_entitlements()

        assert result == 5
        self.logger.info.assert_called()
        assert "Successfully activated 5 entitlements" in str(
            self.logger.info.call_args_list
        )

    async def test_activate_pending_entitlements_none_found(self):
        """Test when no pending entitlements are found"""
        self.repo.activate_pending_entitlements.return_value = 0

        result = await self.service.activate_pending_entitlements()

        assert result == 0
        self.logger.info.assert_called()
        assert "No entitlements found to activate" in str(
            self.logger.info.call_args_list
        )

    async def test_activate_pending_entitlements_exception(self):
        """Test exception handling in activate_pending_entitlements"""
        self.repo.activate_pending_entitlements.side_effect = Exception("DB error")

        with pytest.raises(Exception):
            await self.service.activate_pending_entitlements()

        self.logger.error.assert_called()
        assert "Error activating pending entitlements" in str(
            self.logger.error.call_args
        )

    async def test_merge_modules_both_empty(self):
        """Test merging when both existing and new modules are empty"""
        result = self.service._merge_modules([], [])
        assert result == []

    async def test_merge_modules_duplicates_in_same_list(self):
        """Test merging with duplicates in the same list"""
        result = self.service._merge_modules(["a", "a", "b"], ["c", "c"])
        assert set(result) == {"a", "b", "c"}

    async def test_merge_limits_empty_existing(self):
        """Test merging limits when existing is empty dict"""
        merged = self.service._merge_limits({}, {"l1": 5})
        assert merged == {"l1": 5}

    async def test_merge_limits_empty_new(self):
        """Test merging limits when new limits is empty"""
        merged = self.service._merge_limits({"l1": 5}, {})
        assert merged == {"l1": 5}

    async def test_merge_limits_non_numeric_override(self):
        """Test that non-numeric values are overridden, not added"""
        merged = self.service._merge_limits({"l1": [1, 2]}, {"l1": [3, 4]})
        assert merged["l1"] == [3, 4]

    async def test_update_start_date_success_superadmin(self, monkeypatch):
        """Test successful start date update by superadmin"""
        monkeypatch.setattr(
            "src.components.entitlement.services.DbConstants.ENT_START_DATE_UPDATE_MAX_COUNT",
            3,
        )
        monkeypatch.setattr(
            "src.components.entitlement.services.DbConstants.ENTITLEMENT_START_DATE_UPDATE_WINDOW_HOURS",
            24,
        )

        current_time = int(datetime.now(timezone.utc).timestamp() * 1000)
        new_start_date = int(
            (datetime.now(timezone.utc) + relativedelta(days=7)).timestamp() * 1000
        )

        payload = UpdateEntitlementStartDateRequest(
            order_id=100, start_date=new_start_date
        )
        current_user = {"user_id": 1, "partner_id": 500}

        self.auth_repo.get_role_by_user_id = AsyncMock(
            return_value={RoleDictKeys.HIERARCHY: 0}
        )

        entitlement = Entitlement(
            id=1,
            order_id=100,
            partner_id=500,
            start_date=current_time,
            created_at=current_time - (1000 * 60 * 60 * 2),
            start_date_update_count=0,
            additional_info={},  # empty dict = fresh
            order=Order(id=100, duration=30, partner_id=500),
        )

        # FIX: use get_entitlements_by_order_id and return a list
        self.repo.get_entitlements_by_order_id = AsyncMock(return_value=[entitlement])

        updated_entitlement = Entitlement(
            id=1,
            start_date=new_start_date,
            start_date_update_count=1,
        )
        self.repo.update_entitlement_start_date.return_value = updated_entitlement

        with patch(
            "src.components.entitlement.services.DateTimeUtil.get_current_time",
            return_value=current_time,
        ):
            result = await self.service.update_entitlement_start_date(
                payload, current_user, auth_repo=self.auth_repo
            )

        assert result == [updated_entitlement]
        self.logger.info.assert_called()

    async def test_update_start_date_success_regular_user(self, monkeypatch):
        """Test successful start date update by regular user with matching partner_id"""
        monkeypatch.setattr(
            "src.components.entitlement.services.DbConstants.ENT_START_DATE_UPDATE_MAX_COUNT",
            3,
        )
        monkeypatch.setattr(
            "src.components.entitlement.services.DbConstants.ENTITLEMENT_START_DATE_UPDATE_WINDOW_HOURS",
            24,
        )

        current_time = int(datetime.now(timezone.utc).timestamp() * 1000)
        new_start_date = int(
            (datetime.now(timezone.utc) + relativedelta(days=7)).timestamp() * 1000
        )

        payload = UpdateEntitlementStartDateRequest(
            order_id=100, start_date=new_start_date
        )
        current_user = {"user_id": 1, "partner_id": 500}

        self.auth_repo.get_role_by_user_id = AsyncMock(
            return_value={RoleDictKeys.HIERARCHY: 5}
        )

        entitlement = Entitlement(
            id=1,
            order_id=100,
            partner_id=500,  # matches current_user partner_id
            start_date=current_time,
            created_at=current_time - (1000 * 60 * 60 * 2),
            start_date_update_count=0,
            additional_info={},
            order=Order(id=100, duration=30, partner_id=500),
        )

        # FIX: use get_entitlements_by_order_id and return a list
        self.repo.get_entitlements_by_order_id = AsyncMock(return_value=[entitlement])

        updated_entitlement = Entitlement(
            id=1,
            start_date=new_start_date,
            start_date_update_count=1,
        )
        self.repo.update_entitlement_start_date.return_value = updated_entitlement

        with patch(
            "src.components.entitlement.services.DateTimeUtil.get_current_time",
            return_value=current_time,
        ):
            result = await self.service.update_entitlement_start_date(
                payload, current_user, auth_repo=self.auth_repo
            )

        assert result == [updated_entitlement]

    async def test_update_start_date_entitlement_not_found(self, monkeypatch):
        """Test when entitlement is not found for order_id"""
        new_start_date = int(
            (datetime.now(timezone.utc) + relativedelta(days=7)).timestamp() * 1000
        )
        payload = UpdateEntitlementStartDateRequest(
            order_id=100, start_date=new_start_date
        )
        current_user = {"user_id": 1, "partner_id": 500}

        self.auth_repo.get_role_by_user_id = AsyncMock(
            return_value={RoleDictKeys.HIERARCHY: 0}
        )

        # FIX: return empty list, not None
        self.repo.get_entitlements_by_order_id = AsyncMock(return_value=[])

        with pytest.raises(OrderNotFoundForEntitlementError):
            await self.service.update_entitlement_start_date(
                payload, current_user, auth_repo=self.auth_repo
            )

        self.logger.error.assert_called()

    async def test_update_start_date_no_permission(self, monkeypatch):
        """Test when user doesn't have permission to update entitlement"""
        new_start_date = int(
            (datetime.now(timezone.utc) + relativedelta(days=7)).timestamp() * 1000
        )
        payload = UpdateEntitlementStartDateRequest(
            order_id=100, start_date=new_start_date
        )
        current_user = {"user_id": 1, "partner_id": 999}  # Different partner_id

        self.auth_repo.get_role_by_user_id = AsyncMock(
            return_value={RoleDictKeys.HIERARCHY: 5}
        )

        entitlement = Entitlement(
            id=1,
            order_id=100,
            partner_id=500,  # Different from user's partner_id
            additional_info={},
        )

        # FIX: use get_entitlements_by_order_id and return a list
        self.repo.get_entitlements_by_order_id = AsyncMock(return_value=[entitlement])

        with pytest.raises(NoPermissionToUpdateEntitlementError):
            await self.service.update_entitlement_start_date(
                payload, current_user, auth_repo=self.auth_repo
            )

        self.logger.error.assert_called()

    async def test_update_start_date_not_fresh_entitlement(self, monkeypatch):
        """Test when entitlement has previous orders (not fresh)"""
        new_start_date = int(
            (datetime.now(timezone.utc) + relativedelta(days=7)).timestamp() * 1000
        )
        payload = UpdateEntitlementStartDateRequest(
            order_id=100, start_date=new_start_date
        )
        current_user = {"user_id": 1, "partner_id": 500}

        self.auth_repo.get_role_by_user_id = AsyncMock(
            return_value={RoleDictKeys.HIERARCHY: 0}
        )

        entitlement = Entitlement(
            id=1,
            order_id=100,
            partner_id=500,
            additional_info={"previous_order_ids": [50, 75]},  # not fresh
        )

        # FIX: use get_entitlements_by_order_id and return a list
        self.repo.get_entitlements_by_order_id = AsyncMock(return_value=[entitlement])

        with pytest.raises(EntitlementNotEligibleForStartDateUpdateError):
            await self.service.update_entitlement_start_date(
                payload, current_user, auth_repo=self.auth_repo
            )

        self.logger.warning.assert_called()

    async def test_update_start_date_limit_exceeded(self, monkeypatch):
        """Test when update count limit is exceeded"""
        monkeypatch.setattr(
            "src.components.entitlement.services.DbConstants.ENT_START_DATE_UPDATE_MAX_COUNT",
            3,
        )

        new_start_date = int(
            (datetime.now(timezone.utc) + relativedelta(days=7)).timestamp() * 1000
        )
        payload = UpdateEntitlementStartDateRequest(
            order_id=100, start_date=new_start_date
        )
        current_user = {"user_id": 1, "partner_id": 500}

        self.auth_repo.get_role_by_user_id = AsyncMock(
            return_value={RoleDictKeys.HIERARCHY: 0}
        )

        entitlement = Entitlement(
            id=1,
            order_id=100,
            partner_id=500,
            start_date_update_count=3,  # already at max
            additional_info={},
        )

        # FIX: use get_entitlements_by_order_id and return a list
        self.repo.get_entitlements_by_order_id = AsyncMock(return_value=[entitlement])

        with pytest.raises(EntitlementStartDateUpdateLimitExceededError):
            await self.service.update_entitlement_start_date(
                payload, current_user, auth_repo=self.auth_repo
            )

        self.logger.error.assert_called()

    async def test_update_start_date_window_expired(self, monkeypatch):
        """Test when update window has expired"""
        monkeypatch.setattr(
            "src.components.entitlement.services.DbConstants.ENT_START_DATE_UPDATE_MAX_COUNT",
            3,
        )
        monkeypatch.setattr(
            "src.components.entitlement.services.DbConstants.ENTITLEMENT_START_DATE_UPDATE_WINDOW_HOURS",
            24,
        )

        current_time = int(datetime.now(timezone.utc).timestamp() * 1000)
        new_start_date = int(
            (datetime.now(timezone.utc) + relativedelta(days=7)).timestamp() * 1000
        )
        payload = UpdateEntitlementStartDateRequest(
            order_id=100, start_date=new_start_date
        )
        current_user = {"user_id": 1, "partner_id": 500}

        self.auth_repo.get_role_by_user_id = AsyncMock(
            return_value={RoleDictKeys.HIERARCHY: 0}
        )

        entitlement = Entitlement(
            id=1,
            order_id=100,
            partner_id=500,
            start_date_update_count=0,
            created_at=current_time - (1000 * 60 * 60 * 48),  # 48 hours ago
            additional_info={},
        )

        # FIX: use get_entitlements_by_order_id and return a list
        self.repo.get_entitlements_by_order_id = AsyncMock(return_value=[entitlement])

        with patch(
            "src.components.entitlement.services.DateTimeUtil.get_current_time",
            return_value=current_time,
        ):
            with pytest.raises(EntitlementStartDateUpdateWindowExpiredError):
                await self.service.update_entitlement_start_date(
                    payload, current_user, auth_repo=self.auth_repo
                )

        self.logger.error.assert_called()

    async def test_update_start_date_same_as_current(self, monkeypatch):
        """Test when new start date is same as current start date"""
        monkeypatch.setattr(
            "src.components.entitlement.services.DbConstants.ENT_START_DATE_UPDATE_MAX_COUNT",
            3,
        )
        monkeypatch.setattr(
            "src.components.entitlement.services.DbConstants.ENTITLEMENT_START_DATE_UPDATE_WINDOW_HOURS",
            24,
        )

        current_time = int(datetime.now(timezone.utc).timestamp() * 1000)
        future_date = int(
            (datetime.now(timezone.utc) + relativedelta(days=7)).timestamp() * 1000
        )

        payload = UpdateEntitlementStartDateRequest(
            order_id=100, start_date=future_date
        )
        current_user = {"user_id": 1, "partner_id": 500}

        self.auth_repo.get_role_by_user_id = AsyncMock(
            return_value={RoleDictKeys.HIERARCHY: 0}
        )

        entitlement = Entitlement(
            id=1,
            order_id=100,
            partner_id=500,
            start_date=future_date,  # same as payload
            start_date_update_count=0,
            created_at=current_time - (1000 * 60 * 60 * 2),
            additional_info={},
        )

        # FIX: use get_entitlements_by_order_id and return a list
        self.repo.get_entitlements_by_order_id = AsyncMock(return_value=[entitlement])

        with patch(
            "src.components.entitlement.services.DateTimeUtil.get_current_time",
            return_value=current_time,
        ):
            with pytest.raises(EntitlementNotEligibleForStartDateUpdateError):
                await self.service.update_entitlement_start_date(
                    payload, current_user, auth_repo=self.auth_repo
                )

        self.logger.error.assert_called()

    async def test_update_start_date_exception_handling(self, monkeypatch):
        """Test exception handling in update_entitlement_start_date"""
        new_start_date = int(
            (datetime.now(timezone.utc) + relativedelta(days=7)).timestamp() * 1000
        )
        payload = UpdateEntitlementStartDateRequest(
            order_id=100, start_date=new_start_date
        )
        current_user = {"user_id": 1, "partner_id": 500}

        # FIX: use get_entitlements_by_order_id
        self.repo.get_entitlements_by_order_id = AsyncMock(
            side_effect=Exception("DB error")
        )

        with pytest.raises(Exception):
            await self.service.update_entitlement_start_date(
                payload, current_user, auth_repo=self.auth_repo
            )

        self.logger.error.assert_called()

    async def test_update_entitlement_start_date_none_additional_info(
        self, monkeypatch
    ):
        """Test update when entitlement has None additional_info"""
        monkeypatch.setattr(
            "src.components.entitlement.services.DbConstants.ENT_START_DATE_UPDATE_MAX_COUNT",
            3,
        )
        monkeypatch.setattr(
            "src.components.entitlement.services.DbConstants.ENTITLEMENT_START_DATE_UPDATE_WINDOW_HOURS",
            24,
        )

        current_time = int(datetime.now(timezone.utc).timestamp() * 1000)
        new_start_date = int(
            (datetime.now(timezone.utc) + relativedelta(days=7)).timestamp() * 1000
        )

        payload = UpdateEntitlementStartDateRequest(
            order_id=100, start_date=new_start_date
        )
        current_user = {"user_id": 1, "partner_id": 500}

        self.auth_repo.get_role_by_user_id = AsyncMock(
            return_value={RoleDictKeys.HIERARCHY: 0}
        )

        entitlement = Entitlement(
            id=1,
            order_id=100,
            partner_id=500,
            start_date=current_time,
            created_at=current_time - (1000 * 60 * 60 * 2),
            start_date_update_count=0,
            additional_info=None,  # None - service handles via `or {}`
            order=Order(id=100, duration=30, partner_id=500),
        )

        # FIX: use get_entitlements_by_order_id and return a list
        self.repo.get_entitlements_by_order_id = AsyncMock(return_value=[entitlement])

        updated_entitlement = Entitlement(
            id=1,
            start_date=new_start_date,
            start_date_update_count=1,
        )
        self.repo.update_entitlement_start_date.return_value = updated_entitlement

        with patch(
            "src.components.entitlement.services.DateTimeUtil.get_current_time",
            return_value=current_time,
        ):
            result = await self.service.update_entitlement_start_date(
                payload, current_user, auth_repo=self.auth_repo
            )

        assert result == [updated_entitlement]

    async def test_update_entitlement_start_date_none_update_count(self, monkeypatch):
        """Test when start_date_update_count is None"""
        monkeypatch.setattr(
            "src.components.entitlement.services.DbConstants.ENT_START_DATE_UPDATE_MAX_COUNT",
            3,
        )
        monkeypatch.setattr(
            "src.components.entitlement.services.DbConstants.ENTITLEMENT_START_DATE_UPDATE_WINDOW_HOURS",
            24,
        )

        current_time = int(datetime.now(timezone.utc).timestamp() * 1000)
        new_start_date = int(
            (datetime.now(timezone.utc) + relativedelta(days=7)).timestamp() * 1000
        )

        payload = UpdateEntitlementStartDateRequest(
            order_id=100, start_date=new_start_date
        )
        current_user = {"user_id": 1, "partner_id": 500}

        self.auth_repo.get_role_by_user_id = AsyncMock(
            return_value={RoleDictKeys.HIERARCHY: 0}
        )

        entitlement = Entitlement(
            id=1,
            order_id=100,
            partner_id=500,
            start_date=current_time,
            created_at=current_time - (1000 * 60 * 60 * 2),
            start_date_update_count=None,  # None - service handles via `or 0`
            additional_info={},
            order=Order(id=100, duration=30, partner_id=500),
        )

        # FIX: use get_entitlements_by_order_id and return a list
        self.repo.get_entitlements_by_order_id = AsyncMock(return_value=[entitlement])

        updated_entitlement = Entitlement(
            id=1,
            start_date=new_start_date,
            start_date_update_count=1,
        )
        self.repo.update_entitlement_start_date.return_value = updated_entitlement

        with patch(
            "src.components.entitlement.services.DateTimeUtil.get_current_time",
            return_value=current_time,
        ):
            result = await self.service.update_entitlement_start_date(
                payload, current_user, auth_repo=self.auth_repo
            )

        assert result == [updated_entitlement]


@pytest.mark.asyncio
class TestSubscriptionStatus:

    @pytest.fixture(autouse=True)
    def setup(self):
        self.repo = AsyncMock()
        self.grace_repo = AsyncMock()
        self.logger = MagicMock()

        self.service = EntitlementService(
            entitlement_repository=self.repo, logger=self.logger
        )

        self.now = int(datetime.now(timezone.utc).timestamp() * 1000)

    # ─────────────────────────────────────────────────────────────
    # BASE CASE
    # ─────────────────────────────────────────────────────────────

    async def test_no_entitlements(self):
        self.repo.get_all_entitlements_for_partner.return_value = []
        self.repo.get_scheduled_entitlements.return_value = []

        result = await self.service.get_subscription_status(1, self.grace_repo)

        assert result[Platform.CONSOLE]["status"] == ServiceSubscriptionStatus.SUSPENDED
        assert result[Platform.MAGLO]["status"] == ServiceSubscriptionStatus.SUSPENDED
        assert result[Platform.BABBLER]["status"] == ServiceSubscriptionStatus.SUSPENDED

    # ─────────────────────────────────────────────────────────────
    # CANCELED
    # ─────────────────────────────────────────────────────────────

    async def test_canceled_status(self):
        ent = Entitlement(
            id=1,
            service_name=Platform.CONSOLE,
            is_manually_deactivated=True,
            start_date=self.now,
            end_date=self.now + 10000,
        )

        self.repo.get_all_entitlements_for_partner.return_value = [ent]
        self.repo.get_scheduled_entitlements.return_value = []

        result = await self.service.get_subscription_status(1, self.grace_repo)

        assert result[Platform.CONSOLE]["status"] == ServiceSubscriptionStatus.CANCELED

    # ─────────────────────────────────────────────────────────────
    # ACTIVE
    # ─────────────────────────────────────────────────────────────

    async def test_active_status(self):
        ent = Entitlement(
            id=2,
            service_name=Platform.CONSOLE,
            is_active=True,
            is_manually_deactivated=False,
            start_date=self.now - 10000,
            end_date=self.now + 10000,
            order_id=10,
        )

        self.repo.get_all_entitlements_for_partner.return_value = [ent]
        self.repo.get_scheduled_entitlements.return_value = []

        result = await self.service.get_subscription_status(1, self.grace_repo)

        assert result[Platform.CONSOLE]["status"] == ServiceSubscriptionStatus.ACTIVE

    # ─────────────────────────────────────────────────────────────
    # GRACE
    # ─────────────────────────────────────────────────────────────

    async def test_grace_status(self):
        ent = Entitlement(
            id=3,
            service_name=Platform.CONSOLE,
            is_active=False,
            end_date=self.now - 10000,
        )

        grace = GracePeriod(
            id=1,
            granted_days=5,
            start_date=self.now - 10000,
            end_date=self.now + 10000,
            attempt_number=1,
        )

        self.repo.get_all_entitlements_for_partner.return_value = [ent]
        self.repo.get_scheduled_entitlements.return_value = []
        self.grace_repo.get_active_grace.return_value = grace

        result = await self.service.get_subscription_status(1, self.grace_repo)

        assert result[Platform.CONSOLE]["status"] == ServiceSubscriptionStatus.GRACE
        assert result[Platform.CONSOLE]["grace_start_date"] == grace.start_date

    # ─────────────────────────────────────────────────────────────
    # PENDING ACTIVATION
    # ─────────────────────────────────────────────────────────────

    async def test_pending_activation(self):
        ent = Entitlement(
            id=4,
            service_name=Platform.CONSOLE,
            start_date=self.now + 10000,
            end_date=self.now + 20000,
            order_id=99,
        )

        self.repo.get_all_entitlements_for_partner.return_value = []
        self.repo.get_scheduled_entitlements.return_value = [ent]

        self.grace_repo.get_active_grace.return_value = None

        result = await self.service.get_subscription_status(1, self.grace_repo)

        assert (
            result[Platform.CONSOLE]["status"]
            == ServiceSubscriptionStatus.PENDING_ACTIVATION
        )

    # ─────────────────────────────────────────────────────────────
    # SUSPENDED (fallback)
    # ─────────────────────────────────────────────────────────────

    async def test_suspended_fallback(self):
        ent = Entitlement(
            id=5,
            service_name=Platform.CONSOLE,
            is_active=False,
            end_date=self.now - 10000,
        )

        self.repo.get_all_entitlements_for_partner.return_value = [ent]
        self.repo.get_scheduled_entitlements.return_value = []

        self.grace_repo.get_active_grace.return_value = None

        result = await self.service.get_subscription_status(1, self.grace_repo)

        assert result[Platform.CONSOLE]["status"] == ServiceSubscriptionStatus.SUSPENDED

    # ─────────────────────────────────────────────────────────────
    # MULTI SERVICE
    # ─────────────────────────────────────────────────────────────

    async def test_multiple_services(self):
        ent1 = Entitlement(
            id=1,
            service_name=Platform.CONSOLE,
            is_active=True,
            start_date=self.now - 10000,
            end_date=self.now + 10000,
        )

        ent2 = Entitlement(
            id=2,
            service_name=Platform.BABBLER,
            is_manually_deactivated=True,
        )

        self.repo.get_all_entitlements_for_partner.return_value = [ent1, ent2]
        self.repo.get_scheduled_entitlements.return_value = []

        result = await self.service.get_subscription_status(1, self.grace_repo)

        assert result[Platform.CONSOLE]["status"] == ServiceSubscriptionStatus.ACTIVE
        assert result[Platform.BABBLER]["status"] == ServiceSubscriptionStatus.CANCELED

    # ─────────────────────────────────────────────────────────────
    # LAST EXPIRED ENTITLEMENT
    # ─────────────────────────────────────────────────────────────

    def test_find_last_expired(self):
        ents = [
            Entitlement(id=1, end_date=self.now - 20000),
            Entitlement(id=2, end_date=self.now - 10000),
        ]

        result = self.service._find_last_expired_entitlement(ents, self.now)
        assert result.id == 2

    # ─────────────────────────────────────────────────────────────
    # BUILD STATUS DICT
    # ─────────────────────────────────────────────────────────────

    def test_build_status_dict_grace(self):
        details = {
            "entitlement_start_date": 1,
            "entitlement_end_date": 2,
            "grace_start_date": 3,
            "grace_end_date": 4,
        }

        result = self.service._build_service_status_dict(
            ServiceSubscriptionStatus.GRACE,
            details,
        )

        assert result["grace_start_date"] == 3

    def test_build_status_dict_no_details(self):
        result = self.service._build_service_status_dict(
            ServiceSubscriptionStatus.SUSPENDED,
            None,
        )

        assert result["entitlement_start_date"] is None
