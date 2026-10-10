from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy.exc import IntegrityError

from src.components.plan.constants import PlanType, Platform
from src.components.plan.errors import PlanHierarchyExistsError, WalletPlanExistsError
from src.components.plan.models import Plan
from src.components.plan.repositories import PlanRepository
from src.components.plan.schema import PlanBase, PlanUpdate
from src.components.wallet.enum import Currency


@pytest.mark.asyncio
class TestPlanRepository:

    @pytest.fixture(autouse=True)
    def setup_repo(self, mock_session_factory, mock_logger):
        self.plan_repo = PlanRepository(
            session_factory=mock_session_factory,
            logger=mock_logger,
        )
        self.session = mock_session_factory.return_value.__aenter__.return_value
        self.mock_logger = mock_logger

    # -------------------------------------------------------------------------
    # create_plan
    # -------------------------------------------------------------------------
    async def test_create_plan_success_standard(self):
        """Should create a STANDARD plan successfully."""
        plan_data = PlanBase(
            name="Premium Plan",
            description="Premium features",
            price=1000.0,
            duration=1,
            discount_percentage=10.0,
            currency=Currency.INDIA,
            modules=["maglo:Performance_Overview"],
            plan_type=PlanType.STANDARD,
            tag="premium",
            hierarchy=1,
            service_name=Platform.MAGLO,
        )

        # Mock no existing wallet plan
        wallet_result = MagicMock()
        wallet_result.scalars.return_value.first.return_value = None

        # Mock no existing hierarchy conflict
        hierarchy_result = MagicMock()
        hierarchy_result.scalars.return_value.first.return_value = None

        # Mock no existing name conflict
        name_result = MagicMock()
        name_result.scalars.return_value.first.return_value = None

        self.session.execute = AsyncMock(side_effect=[hierarchy_result, name_result])
        self.session.add = MagicMock()
        self.session.commit = AsyncMock()
        self.session.refresh = AsyncMock()

        plan = await self.plan_repo.create_plan(plan_data, user_id=1)

        self.session.add.assert_called_once()
        self.session.commit.assert_awaited_once()
        assert isinstance(plan, Plan)
        assert plan.name == "Premium Plan"
        assert plan.plan_type == PlanType.STANDARD

    async def test_create_plan_success_wallet(self):
        """Should create a WALLET plan successfully when no active wallet exists."""
        plan_data = PlanBase(
            name="Wallet Plan",
            plan_type=PlanType.WALLET,
            tag="wallet",
            hierarchy=2,
            duration=1,
            service_name=Platform.MAGLO,
        )

        # Mock no existing wallet plan
        wallet_result = MagicMock()
        wallet_result.scalars.return_value.first.return_value = None

        # Mock no existing hierarchy conflict
        hierarchy_result = MagicMock()
        hierarchy_result.scalars.return_value.first.return_value = None

        # Mock no existing name conflict
        name_result = MagicMock()
        name_result.scalars.return_value.first.return_value = None

        self.session.execute = AsyncMock(
            side_effect=[wallet_result, hierarchy_result, name_result]
        )
        self.session.add = MagicMock()
        self.session.commit = AsyncMock()
        self.session.refresh = AsyncMock()

        plan = await self.plan_repo.create_plan(plan_data, user_id=1)

        self.session.add.assert_called_once()
        self.session.commit.assert_awaited_once()
        assert plan.plan_type == PlanType.WALLET

    async def test_create_plan_wallet_already_exists(self):
        """Should raise error when trying to create WALLET plan but one exists."""
        plan_data = PlanBase(
            name="New Wallet",
            plan_type=PlanType.WALLET,
            tag="wallet",
            hierarchy=3,
            duration=1,
            service_name=Platform.MAGLO,
        )

        existing_wallet = MagicMock(spec=Plan)
        existing_wallet.id = 100

        wallet_result = MagicMock()
        wallet_result.scalars.return_value.first.return_value = existing_wallet

        self.session.execute = AsyncMock(return_value=wallet_result)

        with pytest.raises(
            WalletPlanExistsError, match="active wallet plan already exists"
        ):
            await self.plan_repo.create_plan(plan_data, user_id=1)

    async def test_create_plan_hierarchy_already_exists(self):
        """Should raise error when hierarchy already exists."""
        plan_data = PlanBase(
            name="Test Plan",
            plan_type=PlanType.STANDARD,
            price=1000.0,
            tag="test",
            hierarchy=5,
            duration=1,
            service_name=Platform.MAGLO,
        )

        existing_plan = MagicMock(spec=Plan)
        existing_plan.id = 200
        existing_plan.hierarchy = 5

        # Mock no wallet plan check for STANDARD
        hierarchy_result = MagicMock()
        hierarchy_result.scalars.return_value.first.return_value = existing_plan

        self.session.execute = AsyncMock(return_value=hierarchy_result)

        with pytest.raises(PlanHierarchyExistsError):
            await self.plan_repo.create_plan(plan_data, user_id=1)

    async def test_create_plan_integrity_error(self):
        """Should handle IntegrityError and rollback."""
        plan_data = PlanBase(
            name="Test Plan",
            plan_type=PlanType.STANDARD,
            price=1000.0,
            tag="test",
            hierarchy=7,
            duration=1,
            service_name=Platform.MAGLO,
        )

        # Mock all checks pass
        hierarchy_result = MagicMock()
        hierarchy_result.scalars.return_value.first.return_value = None

        name_result = MagicMock()
        name_result.scalars.return_value.first.return_value = None

        self.session.execute = AsyncMock(side_effect=[hierarchy_result, name_result])
        self.session.add = MagicMock()
        self.session.commit = AsyncMock(side_effect=IntegrityError("", "", ""))
        self.session.rollback = AsyncMock()

        with pytest.raises(IntegrityError):
            await self.plan_repo.create_plan(plan_data, user_id=1)

        self.session.rollback.assert_awaited_once()

    async def test_create_plan_unexpected_error(self):
        """Should handle unexpected errors."""
        plan_data = PlanBase(
            name="Test Plan",
            plan_type=PlanType.STANDARD,
            price=1000.0,
            tag="test",
            duration=1,
            hierarchy=8,
            service_name=Platform.MAGLO,
        )

        self.session.execute = AsyncMock(side_effect=Exception("Unexpected error"))

        with pytest.raises(Exception, match="Unexpected error"):
            await self.plan_repo.create_plan(plan_data, user_id=1)

    # -------------------------------------------------------------------------
    # get_plan_by_id
    # -------------------------------------------------------------------------
    async def test_get_plan_by_id_success(self):
        """Should retrieve plan by ID successfully."""
        mock_plan = MagicMock(spec=Plan)
        mock_plan.id = 1
        mock_plan.name = "Test Plan"

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_plan

        self.session.execute = AsyncMock(return_value=mock_result)

        plan = await self.plan_repo.get_plan_by_id(1)

        assert plan == mock_plan
        assert plan.id == 1

    async def test_get_plan_by_id_active_only(self):
        """Should retrieve only active plan when active_only=True."""
        mock_plan = MagicMock(spec=Plan)
        mock_plan.id = 1
        mock_plan.is_active = True

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_plan

        self.session.execute = AsyncMock(return_value=mock_result)

        plan = await self.plan_repo.get_plan_by_id(1, active_only=True)

        assert plan == mock_plan

    async def test_get_plan_by_id_with_partner_purchased(self):
        """Should check purchase status when partner_id provided."""
        mock_plan = MagicMock(spec=Plan)
        mock_plan.id = 1

        # Mock entitlements
        entitlement_result = MagicMock()
        entitlement_result.fetchall.return_value = [(10,)]  # order_id = 10

        # Mock orders
        order_result = MagicMock()
        order_result.fetchall.return_value = [(1,)]  # plan_id = 1

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_plan

        self.session.execute = AsyncMock(
            side_effect=[mock_result, entitlement_result, order_result]
        )

        plan = await self.plan_repo.get_plan_by_id(1, partner_id=100)

        assert plan.is_purchased is True

    async def test_get_plan_by_id_with_partner_not_purchased(self):
        """Should mark as not purchased when partner hasn't purchased."""
        mock_plan = MagicMock(spec=Plan)
        mock_plan.id = 1

        # Mock no active entitlements
        entitlement_result = MagicMock()
        entitlement_result.fetchall.return_value = []

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_plan

        self.session.execute = AsyncMock(side_effect=[mock_result, entitlement_result])

        plan = await self.plan_repo.get_plan_by_id(1, partner_id=100)

        assert plan.is_purchased is False

    async def test_get_plan_by_id_not_found(self):
        """Should return None when plan not found."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None

        self.session.execute = AsyncMock(return_value=mock_result)

        plan = await self.plan_repo.get_plan_by_id(999)

        assert plan is None

    async def test_get_plan_by_id_error(self):
        """Should raise error on database failure."""
        self.session.execute = AsyncMock(side_effect=Exception("DB error"))

        with pytest.raises(Exception, match="DB error"):
            await self.plan_repo.get_plan_by_id(1)

    # -------------------------------------------------------------------------
    # get_active_plans
    # -------------------------------------------------------------------------
    async def test_get_active_plans_success(self):
        """Should retrieve all active plans."""
        mock_plan1 = MagicMock(spec=Plan)
        mock_plan1.id = 1
        mock_plan2 = MagicMock(spec=Plan)
        mock_plan2.id = 2

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [mock_plan1, mock_plan2]

        self.session.execute = AsyncMock(return_value=mock_result)

        plans = await self.plan_repo.get_active_plans()

        assert len(plans) == 2
        assert mock_plan1.is_purchased is False
        assert mock_plan2.is_purchased is False

    async def test_get_active_plans_with_service_filter(self):
        """Should filter plans by service_name."""
        mock_plan = MagicMock(spec=Plan)
        mock_plan.service_name = Platform.MAGLO

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [mock_plan]

        self.session.execute = AsyncMock(return_value=mock_result)

        plans = await self.plan_repo.get_active_plans(service_name=Platform.MAGLO)

        assert len(plans) == 1

    async def test_get_active_plans_with_plan_type_filter(self):
        """Should filter plans by plan_type."""
        mock_plan = MagicMock(spec=Plan)
        mock_plan.plan_type = PlanType.WALLET

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [mock_plan]

        self.session.execute = AsyncMock(return_value=mock_result)

        plans = await self.plan_repo.get_active_plans(plan_type=PlanType.WALLET)

        assert len(plans) == 1

    async def test_get_active_plans_with_partner_id(self):
        """Should check purchase status when partner_id provided."""
        mock_plan = MagicMock(spec=Plan)
        mock_plan.id = 1

        plans_result = MagicMock()
        plans_result.scalars.return_value.all.return_value = [mock_plan]

        # Mock entitlements with active order
        entitlement_result = MagicMock()
        entitlement_result.fetchall.return_value = [(10,)]

        # Mock orders
        order_result = MagicMock()
        order_result.fetchall.return_value = [(1,)]

        self.session.execute = AsyncMock(
            side_effect=[plans_result, entitlement_result, order_result]
        )

        plans = await self.plan_repo.get_active_plans(partner_id=100)

        assert plans[0].is_purchased is True

    async def test_get_active_plans_error(self):
        """Should raise error on database failure."""
        self.session.execute = AsyncMock(side_effect=Exception("DB error"))

        with pytest.raises(Exception, match="DB error"):
            await self.plan_repo.get_active_plans()

    # -------------------------------------------------------------------------
    # update_plan
    # -------------------------------------------------------------------------
    async def test_update_plan_success(self):
        """Should update plan successfully."""
        existing_plan = MagicMock(spec=Plan)
        existing_plan.id = 1
        existing_plan.name = "Old Name"
        existing_plan.plan_type = PlanType.STANDARD

        updated_plan = MagicMock(spec=Plan)
        updated_plan.id = 1
        updated_plan.name = "New Name"

        # Mock get_plan_by_id
        with patch.object(self.plan_repo, "get_plan_by_id", return_value=existing_plan):
            self.session.execute = AsyncMock()
            self.session.commit = AsyncMock()
            self.session.get = AsyncMock(return_value=updated_plan)
            self.session.refresh = AsyncMock()
            self.session.expunge = MagicMock()

            plan_data = PlanUpdate(name="New Name")
            result = await self.plan_repo.update_plan(1, plan_data, user_id=1)

            assert result == updated_plan
            self.session.commit.assert_awaited_once()
            self.session.expunge.assert_called_once()

    async def test_update_plan_not_found(self):
        """Should return None when plan not found."""
        with patch.object(self.plan_repo, "get_plan_by_id", return_value=None):
            plan_data = PlanUpdate(name="New Name")
            result = await self.plan_repo.update_plan(999, plan_data, user_id=1)

            assert result is None

    async def test_update_plan_no_fields_to_update(self):
        """Should return existing plan when no fields to update."""
        existing_plan = MagicMock(spec=Plan)
        existing_plan.id = 1

        with patch.object(self.plan_repo, "get_plan_by_id", return_value=existing_plan):
            plan_data = PlanUpdate()  # No fields
            result = await self.plan_repo.update_plan(1, plan_data, user_id=1)

            assert result == existing_plan

    async def test_update_plan_to_wallet_type_when_one_exists(self):
        """Should raise error when updating to WALLET type but one exists."""
        existing_plan = MagicMock(spec=Plan)
        existing_plan.id = 1
        existing_plan.plan_type = PlanType.STANDARD

        existing_wallet = MagicMock(spec=Plan)
        existing_wallet.id = 2
        existing_wallet.plan_type = PlanType.WALLET

        wallet_result = MagicMock()
        wallet_result.scalars.return_value.first.return_value = existing_wallet

        with patch.object(self.plan_repo, "get_plan_by_id", return_value=existing_plan):
            self.session.execute = AsyncMock(return_value=wallet_result)

            plan_data = PlanUpdate(plan_type=PlanType.WALLET)

            with pytest.raises(WalletPlanExistsError):
                await self.plan_repo.update_plan(1, plan_data, user_id=1)

    async def test_update_plan_activate_wallet_when_one_exists(self):
        """Should raise error when activating WALLET plan but one exists."""
        existing_plan = MagicMock(spec=Plan)
        existing_plan.id = 1
        existing_plan.plan_type = PlanType.WALLET

        other_wallet = MagicMock(spec=Plan)
        other_wallet.id = 2

        wallet_result = MagicMock()
        wallet_result.scalars.return_value.first.return_value = other_wallet

        with patch.object(self.plan_repo, "get_plan_by_id", return_value=existing_plan):
            self.session.execute = AsyncMock(return_value=wallet_result)

            plan_data = PlanUpdate(is_active=True)

            with pytest.raises(WalletPlanExistsError):
                await self.plan_repo.update_plan(1, plan_data, user_id=1)

    async def test_update_plan_hierarchy_conflict(self):
        """Should raise error when updating to existing hierarchy."""
        existing_plan = MagicMock(spec=Plan)
        existing_plan.id = 1
        existing_plan.hierarchy = 5

        conflicting_plan = MagicMock(spec=Plan)
        conflicting_plan.id = 2
        conflicting_plan.hierarchy = 10

        hierarchy_result = MagicMock()
        hierarchy_result.scalars.return_value.first.return_value = conflicting_plan

        with patch.object(self.plan_repo, "get_plan_by_id", return_value=existing_plan):
            self.session.execute = AsyncMock(return_value=hierarchy_result)

            plan_data = PlanUpdate(hierarchy=10)

            with pytest.raises(PlanHierarchyExistsError):
                await self.plan_repo.update_plan(1, plan_data, user_id=1)

    async def test_update_plan_integrity_error(self):
        """Should raise IntegrityError and log error."""
        existing_plan = MagicMock(spec=Plan)
        existing_plan.id = 1
        existing_plan.plan_type = PlanType.STANDARD

        with patch.object(self.plan_repo, "get_plan_by_id", return_value=existing_plan):
            self.session.execute = AsyncMock(side_effect=IntegrityError("", "", ""))

            plan_data = PlanUpdate(name="New Name")

            with pytest.raises(IntegrityError):
                await self.plan_repo.update_plan(1, plan_data, user_id=1)

    async def test_update_plan_unexpected_error(self):
        """Should handle unexpected errors."""
        existing_plan = MagicMock(spec=Plan)
        existing_plan.id = 1

        with patch.object(self.plan_repo, "get_plan_by_id", return_value=existing_plan):
            self.session.execute = AsyncMock(side_effect=Exception("Unexpected error"))

            plan_data = PlanUpdate(name="New Name")

            with pytest.raises(Exception, match="Unexpected error"):
                await self.plan_repo.update_plan(1, plan_data, user_id=1)

    # -------------------------------------------------------------------------
    # delete_plan
    # -------------------------------------------------------------------------
    async def test_delete_plan_success(self):
        """Should soft delete plan successfully."""
        existing_plan = MagicMock(spec=Plan)
        existing_plan.id = 1
        existing_plan.is_active = True

        mock_result = MagicMock()
        mock_result.rowcount = 1

        with patch.object(self.plan_repo, "get_plan_by_id", return_value=existing_plan):
            self.session.execute = AsyncMock(return_value=mock_result)
            self.session.commit = AsyncMock()

            result = await self.plan_repo.delete_plan(1, user_id=1)

            assert result is True
            self.session.commit.assert_awaited_once()

    async def test_delete_plan_not_found(self):
        """Should return False when plan not found."""
        with patch.object(self.plan_repo, "get_plan_by_id", return_value=None):
            result = await self.plan_repo.delete_plan(999, user_id=1)

            assert result is False

    async def test_delete_plan_already_inactive(self):
        """Should return False when plan already inactive."""
        existing_plan = MagicMock(spec=Plan)
        existing_plan.id = 1
        existing_plan.is_active = False

        with patch.object(self.plan_repo, "get_plan_by_id", return_value=existing_plan):
            result = await self.plan_repo.delete_plan(1, user_id=1)

            assert result is False

    async def test_delete_plan_no_rows_affected(self):
        """Should return False when no rows affected."""
        existing_plan = MagicMock(spec=Plan)
        existing_plan.id = 1
        existing_plan.is_active = True

        mock_result = MagicMock()
        mock_result.rowcount = 0

        with patch.object(self.plan_repo, "get_plan_by_id", return_value=existing_plan):
            self.session.execute = AsyncMock(return_value=mock_result)
            self.session.commit = AsyncMock()

            result = await self.plan_repo.delete_plan(1, user_id=1)

            assert result is False

    async def test_delete_plan_error(self):
        """Should raise error on database failure."""
        existing_plan = MagicMock(spec=Plan)
        existing_plan.id = 1
        existing_plan.is_active = True

        with patch.object(self.plan_repo, "get_plan_by_id", return_value=existing_plan):
            self.session.execute = AsyncMock(side_effect=Exception("DB error"))

            with pytest.raises(Exception, match="DB error"):
                await self.plan_repo.delete_plan(1, user_id=1)

    # -------------------------------------------------------------------------
    # _check_purchase_status (helper method)
    # -------------------------------------------------------------------------
    async def test_check_purchase_status_with_partner_multiple_plans(self):
        """Should correctly mark multiple plans' purchase status."""
        plan1 = MagicMock(spec=Plan)
        plan1.id = 1

        plan2 = MagicMock(spec=Plan)
        plan2.id = 2

        # Mock entitlements
        entitlement_result = MagicMock()
        entitlement_result.fetchall.return_value = [(10,), (11,)]

        # Mock orders - only plan1 purchased
        order_result = MagicMock()
        order_result.fetchall.return_value = [(1,), (None,)]

        self.session.execute = AsyncMock(side_effect=[entitlement_result, order_result])

        result = await self.plan_repo._check_purchase_status(
            self.session, [plan1, plan2], partner_id=100
        )

        assert result[0].is_purchased is True
        assert result[1].is_purchased is False

    async def test_check_purchase_status_no_partner_id(self):
        """Should mark all as not purchased when no partner_id."""
        plan1 = MagicMock(spec=Plan)
        plan2 = MagicMock(spec=Plan)

        result = await self.plan_repo._check_purchase_status(
            self.session, [plan1, plan2], partner_id=None
        )

        assert result[0].is_purchased is False
        assert result[1].is_purchased is False

    async def test_check_purchase_status_no_active_entitlements(self):
        """Should mark as not purchased when no active entitlements."""
        plan = MagicMock(spec=Plan)
        plan.id = 1

        entitlement_result = MagicMock()
        entitlement_result.fetchall.return_value = []

        self.session.execute = AsyncMock(return_value=entitlement_result)

        result = await self.plan_repo._check_purchase_status(
            self.session, [plan], partner_id=100
        )

        assert result[0].is_purchased is False
