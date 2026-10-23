from uuid import UUID
import time
from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, Mock, patch

import pytest

from src.components.entitlement.repositories import EntitlementRepository
from src.components.entitlement.services import EntitlementService
from src.components.order.constants import (
    OrderType,
    PaymentMethod,
    ServiceSubscriptionStatus,
)
from src.components.order.errors import (
    AuthenticationRequiredError,
    InvalidUpgradeError,
    MissingPlanIdError,
    NoActiveEntitlementError,
    NoBillingForWalletError,
    OrderAlreadyProcessedError,
    OrderNotFoundError,
    PlanInactiveError,
    SelfServeManualOrderError,
)
from src.components.order.models import Order
from src.components.order.repositories import OrderRepository
from src.components.order.schema import OrderBase, OrderBillingDetailsRequest
from src.components.order.services import OrderService
from src.components.partner.error import PartnerNotFoundError
from src.components.partner.repositories import PartnerRepository
from src.components.partner_config.constants import SubscriptionModeEnum
from src.components.partner_config.schemas import PartnerConfigResponse
from src.components.payment.enum import PaymentStatusEnum
from src.components.payment.services import PaymentService
from src.components.plan.constants import PlanCustomLimitKeys, PlanType
from src.components.plan.models import Plan
from src.components.plan.repositories import PlanRepository
from src.components.wallet.enum import Currency
from src.components.wallet.services import WalletService
from src.loggers.console_service_logger import ConsoleServiceLogger


@pytest.mark.asyncio
class TestOrderService:

    @pytest.fixture(autouse=True)
    def setup(self):
        self.order_repo = AsyncMock(spec=OrderRepository)
        self.payment_service = AsyncMock(spec=PaymentService)
        self.logger = AsyncMock(spec=ConsoleServiceLogger)
        self.plan_repo = AsyncMock(spec=PlanRepository)
        self.partner_repo = AsyncMock(spec=PartnerRepository)
        self.entitlement_repo = AsyncMock(spec=EntitlementRepository)
        self.entitlement_service = AsyncMock(spec=EntitlementService)
        self.wallet_service = AsyncMock(spec=WalletService)
        self.partner_config_service = AsyncMock()
        self.partner_config_service.get_partner_config_by_key = AsyncMock()

        self.service = OrderService(
            order_repo=self.order_repo,
            payment_service=self.payment_service,
            logger=self.logger,
        )

        self.user_context = {"partner_id": UUID("11111111-1111-1111-1111-111111111111"), "user_id": UUID("11111111-1111-1111-1111-111111111111")}
        self.order_data = OrderBase(
            plan_id= UUID("11111111-1111-1111-1111-111111111111"), amount=100.0, currency="INR", source="console"
        )

        self.mock_plan = Mock(spec=Plan)
        self.mock_plan.id = UUID("11111111-1111-1111-1111-111111111111")
        self.mock_plan.name = "Test Plan"
        self.mock_plan.is_free_trial = False
        self.mock_plan.plan_type = PlanType.STANDARD
        self.mock_plan.price = 100
        self.mock_plan.discount_percentage = 10.0
        self.mock_plan.service_name = "console"
        self.mock_plan.tag = "basic"
        self.mock_plan.currency = Currency.INDIA
        self.mock_plan.modules = ["console:dashboard"]
        self.mock_plan.duration = 1
        self.mock_plan.hierarchy = 1

        self.mock_order = Mock(spec=Order)
        self.mock_order.id = UUID("11111111-1111-1111-1111-111111111111")
        self.mock_order.plan_id= UUID("11111111-1111-1111-1111-111111111111")
        self.mock_order.plan = self.mock_plan
        self.mock_order.amount = 100.0
        self.mock_order.status = PaymentStatusEnum.PENDING
        self.mock_order.partner_id= UUID("11111111-1111-1111-1111-111111111111")
        self.mock_order.created_by= UUID("11111111-1111-1111-1111-111111111111")
        self.mock_order.currency = "INR"

        # Default sales_managed config mock
        self.mock_sales_managed_config = Mock(spec=PartnerConfigResponse)
        self.mock_sales_managed_config.value = SubscriptionModeEnum.SALES_MANAGED
        self.partner_config_service.get_partner_config_by_key.return_value = (
            self.mock_sales_managed_config
        )

    # =========================================================================
    # VALIDATION METHODS
    # =========================================================================

    async def test_validate_plan_success(self):
        self.plan_repo.get_plan_by_id.return_value = self.mock_plan
        result = await self.service._validate_plan(1, self.plan_repo)
        assert result == self.mock_plan
        self.plan_repo.get_plan_by_id.assert_called_once_with(1, active_only=True)

    async def test_validate_plan_inactive(self):
        self.plan_repo.get_plan_by_id.return_value = None
        with pytest.raises(PlanInactiveError, match="Plan not found or inactive"):
            await self.service._validate_plan(1, self.plan_repo)

    async def test_validate_plan_free_trial(self):
        self.mock_plan.is_free_trial = True
        self.plan_repo.get_plan_by_id.return_value = self.mock_plan
        with pytest.raises(InvalidUpgradeError, match="free trial plans"):
            await self.service._validate_plan(1, self.plan_repo)

    def test_validate_authentication_unauthenticated_with_plan_id(self):
        order_data = OrderBillingDetailsRequest(plan_id= UUID("11111111-1111-1111-1111-111111111111"))
        # Should not raise
        self.service._validate_authentication(order_data, None)

    def test_validate_authentication_unauthenticated_without_plan_id(self):
        order_data = OrderBillingDetailsRequest(
            plan_id=None, add_ons={"ACTIVE_USERS": 1}
        )
        with pytest.raises(AuthenticationRequiredError):
            self.service._validate_authentication(order_data, None)

    def test_validate_addons_entitlement_with_active_entitlement(self):
        add_ons = {"ACTIVE_USERS": 2}
        active_entitlements = {"console": Mock()}
        with patch.object(self.service, "_split_addons_by_service") as mock_split:
            mock_split.return_value = {"console": {"ACTIVE_USERS": 2}}
            self.service._validate_addons_entitlement(add_ons, active_entitlements)

    def test_validate_addons_entitlement_no_entitlements(self):
        with pytest.raises(NoActiveEntitlementError):
            self.service._validate_addons_entitlement({"ACTIVE_USERS": 2}, {})

    def test_validate_addons_entitlement_missing_service_entitlement(self):
        add_ons = {"ACTIVE_USERS": 2}
        active_entitlements = {"console": Mock()}
        with patch.object(self.service, "_split_addons_by_service") as mock_split:
            mock_split.return_value = {"talko": {"ACTIVE_USERS": 2}}
            with pytest.raises(NoActiveEntitlementError):
                self.service._validate_addons_entitlement(add_ons, active_entitlements)

    # =========================================================================
    # _validate_partner
    # =========================================================================

    async def test_validate_partner_success(self):
        mock_partner = Mock()
        mock_partner.is_active = True
        self.partner_repo.get_by_id.return_value = mock_partner
        # Should not raise
        await self.service._validate_partner(1, self.partner_repo)

    async def test_validate_partner_not_found(self):
        self.partner_repo.get_by_id.return_value = None
        with pytest.raises(PartnerNotFoundError, match="does not exist"):
            await self.service._validate_partner(99, self.partner_repo)

    async def test_validate_partner_inactive(self):
        mock_partner = Mock()
        mock_partner.is_active = False
        self.partner_repo.get_by_id.return_value = mock_partner
        with pytest.raises(PartnerNotFoundError, match="inactive"):
            await self.service._validate_partner(1, self.partner_repo)

    # =========================================================================
    # _classify_manual_order
    # =========================================================================

    async def test_classify_fresh_no_history(self):
        self.order_repo.get_latest_order_by_partner.return_value = None
        order_type, latest = await self.service._classify_manual_order(
            partner_id= UUID("11111111-1111-1111-1111-111111111111"), new_plan=self.mock_plan
        )
        assert order_type == OrderType.FRESH
        assert latest is None

    async def test_classify_upgrade(self):
        self.mock_plan.hierarchy = 5
        mock_latest = Mock(spec=Order)
        mock_latest.id = 5
        mock_latest.plan = Mock()
        mock_latest.plan.id = 99  # different plan
        mock_latest.plan.hierarchy = 2
        self.order_repo.get_latest_order_by_partner.return_value = mock_latest
        order_type, latest = await self.service._classify_manual_order(
            partner_id= UUID("11111111-1111-1111-1111-111111111111"), new_plan=self.mock_plan
        )
        assert order_type == OrderType.UPGRADE

    async def test_classify_deleted_plan_falls_back_to_fresh(self):
        mock_latest = Mock(spec=Order)
        mock_latest.id = 5
        mock_latest.plan = None  # plan deleted
        self.order_repo.get_latest_order_by_partner.return_value = mock_latest
        order_type, latest = await self.service._classify_manual_order(
            partner_id= UUID("11111111-1111-1111-1111-111111111111"), new_plan=self.mock_plan
        )
        assert order_type == OrderType.FRESH

    async def test_classify_renewal_same_plan_id(self):
        """Same plan id always classifies as RENEWAL regardless of hierarchy."""
        mock_latest = Mock(spec=Order)
        mock_latest.id = 10
        mock_latest.plan = Mock()
        mock_latest.plan.id = self.mock_plan.id  # same plan id → RENEWAL
        mock_latest.plan.hierarchy = 1
        self.order_repo.get_latest_order_by_partner.return_value = mock_latest
        order_type, latest = await self.service._classify_manual_order(
            partner_id= UUID("11111111-1111-1111-1111-111111111111"), new_plan=self.mock_plan
        )
        assert order_type == OrderType.RENEWAL
        assert latest == mock_latest

    async def test_classify_downgrade(self):
        """Lower hierarchy with different plan.id classifies as DOWNGRADE."""
        self.mock_plan.hierarchy = 1
        mock_latest = Mock(spec=Order)
        mock_latest.id = 10
        mock_latest.plan = Mock()
        mock_latest.plan.id = 999  # different plan
        mock_latest.plan.hierarchy = 5  # higher → new plan is a downgrade
        self.order_repo.get_latest_order_by_partner.return_value = mock_latest
        order_type, latest = await self.service._classify_manual_order(
            partner_id= UUID("11111111-1111-1111-1111-111111111111"), new_plan=self.mock_plan
        )
        assert order_type == OrderType.DOWNGRADE
        assert latest == mock_latest

    # =========================================================================
    # _assert_no_active_entitlement
    # =========================================================================

    async def test_assert_no_active_entitlement_passes_when_none(self):
        self.entitlement_repo.get_all_active_entitlements.return_value = []
        # Should not raise
        await self.service._assert_no_active_entitlement(self.entitlement_repo, 1)

    async def test_assert_no_active_entitlement_raises_when_active(self):
        self.entitlement_repo.get_all_active_entitlements.return_value = [Mock()]
        with pytest.raises(InvalidUpgradeError, match="active entitlement"):
            await self.service._assert_no_active_entitlement(self.entitlement_repo, 1)

    # =========================================================================
    # _assert_duration_within_scheduled_window
    # =========================================================================

    async def test_assert_duration_no_scheduled_entitlements(self):
        self.entitlement_repo.get_scheduled_entitlements.return_value = []
        # Should not raise
        await self.service._assert_duration_within_scheduled_window(
            self.entitlement_repo, 1, 30
        )

    async def test_assert_duration_within_window_allowed(self):
        # Activates in 60 days → 30 days duration is allowed (30 < 60)
        future_ts = (datetime.now(timezone.utc).timestamp() + 86400 * 60) * 1000
        mock_ent = Mock()
        mock_ent.start_date = future_ts
        self.entitlement_repo.get_scheduled_entitlements.return_value = [mock_ent]
        await self.service._assert_duration_within_scheduled_window(
            self.entitlement_repo, 1, 30
        )

    async def test_assert_duration_exceeds_window_blocked(self):
        # Activates in 30 days → requesting 30 days is blocked (must be strictly less)
        future_ts = (datetime.now(timezone.utc).timestamp() + 86400 * 30) * 1000
        mock_ent = Mock()
        mock_ent.start_date = future_ts
        self.entitlement_repo.get_scheduled_entitlements.return_value = [mock_ent]
        with pytest.raises(InvalidUpgradeError, match="overlap"):
            await self.service._assert_duration_within_scheduled_window(
                self.entitlement_repo, 1, 30
            )

    async def test_assert_duration_multiple_scheduled_uses_nearest(self):
        # Two scheduled: 25 days and 60 days → nearest is 25.
        # Add a 12-hour buffer (43200s) so timedelta.days truncation never shaves a day.
        ts_near = (datetime.now(timezone.utc).timestamp() + 86400 * 25 + 43200) * 1000
        ts_far = (datetime.now(timezone.utc).timestamp() + 86400 * 60 + 43200) * 1000
        ent_near, ent_far = Mock(), Mock()
        ent_near.start_date = ts_near
        ent_far.start_date = ts_far
        self.entitlement_repo.get_scheduled_entitlements.return_value = [
            ent_near,
            ent_far,
        ]

        # 24 < 25 → allowed
        await self.service._assert_duration_within_scheduled_window(
            self.entitlement_repo, 1, 24
        )
        # 26 >= 25 → blocked
        with pytest.raises(InvalidUpgradeError):
            await self.service._assert_duration_within_scheduled_window(
                self.entitlement_repo, 1, 26
            )

    # =========================================================================
    # _resolve_manual_order_amount
    # =========================================================================

    def test_resolve_manual_order_amount_with_override(self):
        result = self.service._resolve_manual_order_amount(50000, self.mock_plan)
        assert result == 50000

    def test_resolve_manual_order_amount_fallback_to_plan(self):
        self.mock_plan.price = 99900
        result = self.service._resolve_manual_order_amount(None, self.mock_plan)
        assert result == 99900

    def test_resolve_manual_order_amount_zero_override_is_honoured(self):
        # 0 is a valid override (free order)
        result = self.service._resolve_manual_order_amount(0, self.mock_plan)
        assert result == 0

    # =========================================================================
    # _approve_and_provision_manual_order
    # =========================================================================

    async def test_approve_and_provision_manual_order(self):
        approved = Mock(spec=Order)
        # Ensure grace settlement is skipped (no modules on plan)
        approved.plan = Mock()
        approved.plan.modules = None
        self.order_repo.update_order.return_value = approved
        result = await self.service._approve_and_provision_manual_order(
            self.mock_order,
            sales_user_id= UUID("11111111-1111-1111-1111-111111111111"),
            entitlement_service=self.entitlement_service,
        )
        assert result == approved
        self.order_repo.update_order.assert_called_once_with(
            order_id=self.mock_order.id,
            update_data={"status": PaymentStatusEnum.SUCCESS},
            user_id= UUID("11111111-1111-1111-1111-111111111111"),
        )
        self.entitlement_service.upsert_entitlement.assert_called_once_with(approved, UUID("11111111-1111-1111-1111-111111111111"))

    # =========================================================================
    # _resolve_order_type
    # =========================================================================

    def test_resolve_order_type_valid_values(self):
        for ot in (
            OrderType.FRESH,
            OrderType.RENEWAL,
            OrderType.UPGRADE,
            OrderType.DOWNGRADE,
        ):
            assert self.service._resolve_order_type(ot) == ot

    def test_resolve_order_type_invalid_falls_back_to_fresh(self):
        assert self.service._resolve_order_type("UNKNOWN") == OrderType.FRESH

    def test_resolve_order_type_empty_string(self):
        assert self.service._resolve_order_type("") == OrderType.FRESH

    # =========================================================================
    # _get_addon_price
    # =========================================================================

    def test_get_addon_price_empty_table_returns_zero(self):
        # Priced add-on table is empty (only priced add-on retired).
        assert self.service._get_addon_price("ACTIVE_USERS") == 0

    def test_get_addon_price_unknown_key_returns_zero(self):
        result = self.service._get_addon_price("UNKNOWN_ADDON_KEY")
        assert result == 0

    # =========================================================================
    # _resolve_services
    # =========================================================================

    def test_resolve_services_with_plan_and_addons(self):
        self.mock_plan.modules = {"console": ["dashboard"], "talko": ["boards"]}
        add_ons_by_service = {"console": {"ACTIVE_USERS": 1}, "talko": {"ACTIVE_USERS": 1}}
        with patch(
            "src.components.order.services.PlanUtils.split_modules_by_service"
        ) as mock_split:
            mock_split.return_value = {"console": [], "talko": []}
            result = self.service._resolve_services(self.mock_plan, add_ons_by_service)
        assert "console" in result
        assert "talko" in result

    def test_resolve_services_no_plan(self):
        add_ons_by_service = {"console": {"ACTIVE_USERS": 1}}
        result = self.service._resolve_services(None, add_ons_by_service)
        assert result == {"console"}

    def test_resolve_services_no_addons_no_plan(self):
        result = self.service._resolve_services(None, {})
        assert result == set()

    # =========================================================================
    # _validate_services_entitlements
    # =========================================================================

    def test_validate_services_entitlements_addons_only_no_plan(self):
        order_data = OrderBillingDetailsRequest(
            plan_id=None, add_ons={"ACTIVE_USERS": 1}
        )
        active_entitlements = {"console": Mock()}
        with patch.object(self.service, "_validate_addons_entitlement") as mock_val:
            self.service._validate_services_entitlements(
                active_entitlements, order_data
            )
            mock_val.assert_called_once()

    def test_validate_services_entitlements_plan_and_addons_service_present(self):
        order_data = OrderBillingDetailsRequest(
            plan_id= UUID("11111111-1111-1111-1111-111111111111"), add_ons={"ACTIVE_USERS": 1}
        )
        active_entitlements = {"console": Mock()}
        with patch.object(self.service, "_split_addons_by_service") as mock_split:
            mock_split.return_value = {"console": {"ACTIVE_USERS": 1}}
            # Should not raise
            self.service._validate_services_entitlements(
                active_entitlements, order_data
            )

    def test_validate_services_entitlements_plan_only_no_addons(self):
        order_data = OrderBillingDetailsRequest(plan_id= UUID("11111111-1111-1111-1111-111111111111"))
        # Neither branch executes with empty add_ons
        self.service._validate_services_entitlements({}, order_data)

    # =========================================================================
    # _get_current_plan_from_entitlement
    # =========================================================================

    def test_get_current_plan_from_entitlement_found(self):
        mock_plan = Mock(spec=Plan)
        mock_ent = Mock()
        mock_ent.order = Mock()
        mock_ent.order.plan = mock_plan
        active_entitlements = {"console": mock_ent}
        result = self.service._get_current_plan_from_entitlement(
            "console", active_entitlements
        )
        assert result == mock_plan

    def test_get_current_plan_from_entitlement_service_not_found(self):
        result = self.service._get_current_plan_from_entitlement("console", {})
        assert result is None

    def test_get_current_plan_from_entitlement_order_has_no_plan(self):
        mock_ent = Mock()
        mock_ent.order = Mock()
        mock_ent.order.plan = None
        result = self.service._get_current_plan_from_entitlement(
            "console", {"console": mock_ent}
        )
        assert result is None

    def test_get_current_plan_from_entitlement_no_order(self):
        mock_ent = Mock()
        mock_ent.order = None
        result = self.service._get_current_plan_from_entitlement(
            "console", {"console": mock_ent}
        )
        assert result is None

    # =========================================================================
    # _create_gateway_order
    # =========================================================================

    async def test_create_gateway_order_with_dict_payload(self):
        self.payment_service.create_order.return_value = {"id": "gw_001"}
        payload_dict = {"amount": 5000, "currency": "INR"}
        result = await self.service._create_gateway_order(
            order=self.mock_order,
            order_data=payload_dict,
            user_context={"partner_id": UUID("11111111-1111-1111-1111-111111111111"), "user_id": UUID("11111111-1111-1111-1111-111111111111")},
        )
        assert result == {"id": "gw_001"}
        self.payment_service.create_order.assert_called_once()

    async def test_create_gateway_order_with_dict_payload_no_currency_uses_order(self):
        self.payment_service.create_order.return_value = {"id": "gw_002"}
        # currency omitted → fallback to order.currency
        payload_dict = {"amount": 5000}
        await self.service._create_gateway_order(
            order=self.mock_order,
            order_data=payload_dict,
            user_context={"partner_id": UUID("11111111-1111-1111-1111-111111111111"), "user_id": UUID("11111111-1111-1111-1111-111111111111")},
        )
        call_args = self.payment_service.create_order.call_args[0][0]
        assert call_args.currency == self.mock_order.currency

    async def test_create_gateway_order_with_schema_object(self):
        self.payment_service.create_order.return_value = {"id": "gw_003"}
        result = await self.service._create_gateway_order(
            order=self.mock_order,
            order_data=self.order_data,  # OrderBase instance
            user_context={"partner_id": UUID("11111111-1111-1111-1111-111111111111"), "user_id": UUID("11111111-1111-1111-1111-111111111111")},
        )
        assert result == {"id": "gw_003"}
        call_args = self.payment_service.create_order.call_args[0][0]
        assert call_args.amount == self.order_data.amount
        assert call_args.currency == self.order_data.currency

    # =========================================================================
    # _handle_wallet_transaction
    # =========================================================================

    async def test_handle_wallet_transaction_non_wallet_plan_skipped(self):
        self.mock_order.plan.plan_type = PlanType.STANDARD
        await self.service._handle_wallet_transaction(
            self.mock_order, user_id= UUID("11111111-1111-1111-1111-111111111111"), partner_id= UUID("11111111-1111-1111-1111-111111111111"), wallet_service=self.wallet_service
        )
        self.wallet_service.perform_transaction.assert_not_called()

    async def test_handle_wallet_transaction_no_plan_id_skipped(self):
        self.mock_order.plan_id = None
        await self.service._handle_wallet_transaction(
            self.mock_order, user_id= UUID("11111111-1111-1111-1111-111111111111"), partner_id= UUID("11111111-1111-1111-1111-111111111111"), wallet_service=self.wallet_service
        )
        self.wallet_service.perform_transaction.assert_not_called()

    # =========================================================================
    # _provision_on_payment_success
    # =========================================================================

    async def test_provision_on_payment_success_standard_plan_upserts_entitlement(self):
        self.mock_order.plan.plan_type = PlanType.STANDARD
        self.mock_order.plan.modules = None  # skip grace settlement
        await self.service._provision_on_payment_success(
            order=self.mock_order,
            user_id= UUID("11111111-1111-1111-1111-111111111111"),
            entitlement_service=self.entitlement_service,
            wallet_service=self.wallet_service,
        )
        self.entitlement_service.upsert_entitlement.assert_called_once_with(
            self.mock_order, UUID("11111111-1111-1111-1111-111111111111")
        )
        self.wallet_service.perform_transaction.assert_not_called()

    async def test_handle_wallet_transaction_wallet_plan_executes(self):
        self.mock_order.plan_id= UUID("11111111-1111-1111-1111-111111111111")
        self.mock_order.plan.plan_type = PlanType.WALLET
        self.mock_order.additional_info = None
        self.mock_order.amount = 10000
        await self.service._handle_wallet_transaction(
            self.mock_order, user_id= UUID("11111111-1111-1111-1111-111111111111"), partner_id= UUID("11111111-1111-1111-1111-111111111111"), wallet_service=self.wallet_service
        )
        self.wallet_service.perform_transaction.assert_called_once()

    async def test_provision_on_payment_success_wallet_plan_tops_up_wallet(self):
        self.mock_order.plan_id= UUID("11111111-1111-1111-1111-111111111111")
        self.mock_order.plan.plan_type = PlanType.WALLET
        self.mock_order.additional_info = None
        self.mock_order.amount = 10000
        await self.service._provision_on_payment_success(
            order=self.mock_order,
            user_id= UUID("11111111-1111-1111-1111-111111111111"),
            entitlement_service=self.entitlement_service,
            wallet_service=self.wallet_service,
        )
        self.wallet_service.perform_transaction.assert_called_once()
        self.entitlement_service.upsert_entitlement.assert_not_called()
        
    async def test_provision_on_payment_success_no_plan_id_upserts_entitlement(self):
        self.mock_order.plan_id = None
        self.mock_order.plan = Mock()
        self.mock_order.plan.plan_type = PlanType.STANDARD
        self.mock_order.plan.modules = None  # skip grace settlement
        await self.service._provision_on_payment_success(
            order=self.mock_order,
            user_id= UUID("11111111-1111-1111-1111-111111111111"),
            entitlement_service=self.entitlement_service,
            wallet_service=self.wallet_service,
        )
        self.entitlement_service.upsert_entitlement.assert_called_once()

    # =========================================================================
    # handle_webhook
    # =========================================================================

    async def test_handle_webhook_skips_non_pending_order(self):
        self.mock_order.status = PaymentStatusEnum.SUCCESS
        processed = {"status": "success", "payment_id": "pay_123"}
        self.payment_service.handle_webhook.return_value = processed
        self.order_repo.get_order_by_merchant_transaction_id.return_value = (
            self.mock_order
        )

        result = await self.service.handle_webhook(
            payload={"payload": {"payment": {"entity": {"order_id": "TXN001"}}}},
            raw_body=b"",
            signature="sig",
            entitlement_service=self.entitlement_service,
            wallet_service=self.wallet_service,
        )

        assert result == processed
        self.order_repo.update_order.assert_not_called()
        self.entitlement_service.upsert_entitlement.assert_not_called()

    async def test_handle_webhook_pending_order_provisions(self):
        self.mock_order.status = PaymentStatusEnum.PENDING
        processed = {
            "status": "success",
            "payment_id": "pay_123",
            "payment_method": "card",
        }
        self.payment_service.handle_webhook.return_value = processed
        self.order_repo.get_order_by_merchant_transaction_id.return_value = (
            self.mock_order
        )
        updated = Mock(spec=Order)
        updated.status = PaymentStatusEnum.SUCCESS
        updated.plan_id= UUID("11111111-1111-1111-1111-111111111111")
        updated.plan = Mock()
        updated.plan.plan_type = PlanType.STANDARD
        updated.plan.modules = None  # skip grace settlement
        updated.partner_id= UUID("11111111-1111-1111-1111-111111111111")
        self.order_repo.update_order.return_value = updated

        await self.service.handle_webhook(
            payload={"payload": {"payment": {"entity": {"order_id": "TXN001"}}}},
            raw_body=b"",
            signature="sig",
            entitlement_service=self.entitlement_service,
            wallet_service=self.wallet_service,
        )

        self.order_repo.update_order.assert_called_once()
        self.entitlement_service.upsert_entitlement.assert_called_once()

    async def test_handle_webhook_unrecognized_order_acknowledged_gracefully(self):
        """A validly-signed webhook for an order we have no local record of
        (e.g. created manually in the Razorpay Dashboard, not through our
        own checkout flow) must be acknowledged, not raise/500 -- Razorpay
        fires account-level webhooks for orders we never created too."""
        processed = {"status": "failed", "payment_id": "pay_999"}
        self.payment_service.handle_webhook.return_value = processed
        self.order_repo.get_order_by_merchant_transaction_id.side_effect = (
            OrderNotFoundError("order_unknown123")
        )

        result = await self.service.handle_webhook(
            payload={"payload": {"payment": {"entity": {"order_id": "order_unknown123"}}}},
            raw_body=b"",
            signature="sig",
            entitlement_service=self.entitlement_service,
            wallet_service=self.wallet_service,
        )

        assert result["order_id"] == "order_unknown123"
        assert result["status"] == "failed"
        self.order_repo.update_order.assert_not_called()
        self.entitlement_service.upsert_entitlement.assert_not_called()

    # =========================================================================
    # create_manual_order (service)
    # =========================================================================

    async def test_create_manual_order_direct_payment(self):
        mock_partner = Mock()
        mock_partner.is_active = True
        self.partner_repo.get_by_id.return_value = mock_partner
        self.plan_repo.get_plan_by_id.return_value = self.mock_plan
        self.order_repo.get_latest_order_by_partner.return_value = None
        self.entitlement_repo.get_all_active_entitlements.return_value = []
        self.entitlement_repo.get_scheduled_entitlements.return_value = []
        self.order_repo.create_manual_order.return_value = self.mock_order

        approved = Mock(spec=Order)
        approved.id = 1
        approved.plan = Mock()
        approved.plan.modules = None  # skip grace settlement
        self.order_repo.update_order.return_value = approved

        payload = {
            "partner_id": 1,
            "plan_id": 1,
            "amount": 10000,
            "payment_method": PaymentMethod.DIRECT,
            "add_ons": {},
            "currency": "INR",
        }

        with patch.object(
            self.service, "_build_order_response", return_value={"order": {}}
        ):
            result = await self.service.create_manual_order(
                payload=payload,
                current_user={"user_id": 1},
                plan_repo=self.plan_repo,
                partner_repo=self.partner_repo,
                entitlement_repo=self.entitlement_repo,
                entitlement_service=self.entitlement_service,
                partner_config_service=self.partner_config_service,
            )
        assert result is not None

    async def test_create_manual_order_gateway_payment(self):
        mock_partner = Mock()
        mock_partner.is_active = True
        self.partner_repo.get_by_id.return_value = mock_partner
        self.plan_repo.get_plan_by_id.return_value = self.mock_plan
        self.order_repo.get_latest_order_by_partner.return_value = None
        self.entitlement_repo.get_all_active_entitlements.return_value = []
        self.entitlement_repo.get_scheduled_entitlements.return_value = []
        self.order_repo.create_manual_order.return_value = self.mock_order
        self.order_repo.update_order.return_value = self.mock_order
        self.payment_service.create_order.return_value = {"id": "gw_001"}

        payload = {
            "partner_id": UUID("11111111-1111-1111-1111-111111111111"),
            "plan_id": UUID("11111111-1111-1111-1111-111111111111"),
            "amount": 10000,
            "payment_method": PaymentMethod.GATEWAY,
            "add_ons": {},
        }
    
        with patch.object(
            self.service, "_build_order_response", return_value={"order": {}}
        ):
            result = await self.service.create_manual_order(
                payload=payload,
                current_user={"user_id": UUID("11111111-1111-1111-1111-111111111111")},
                plan_repo=self.plan_repo,
                partner_repo=self.partner_repo,
                entitlement_repo=self.entitlement_repo,
                entitlement_service=self.entitlement_service,
                partner_config_service=self.partner_config_service,
            )
        assert result is not None
        self.payment_service.create_order.assert_called_once()

    async def test_create_manual_order_blocked_for_self_served_partner(self):
        """SelfServeManualOrderError raised when subscription mode is SELF_SERVED."""
        mock_partner = Mock()
        mock_partner.is_active = True
        self.partner_repo.get_by_id.return_value = mock_partner

        self_served_config = Mock(spec=PartnerConfigResponse)
        self_served_config.value = SubscriptionModeEnum.SELF_SERVED
        self.partner_config_service.get_partner_config_by_key.return_value = (
            self_served_config
        )

        payload = {
            "partner_id": 1,
            "plan_id": 1,
            "amount": 10000,
            "payment_method": PaymentMethod.DIRECT,
            "add_ons": {},
        }

        with pytest.raises(SelfServeManualOrderError):
            await self.service.create_manual_order(
                payload=payload,
                current_user={"user_id": 1},
                plan_repo=self.plan_repo,
                partner_repo=self.partner_repo,
                entitlement_repo=self.entitlement_repo,
                entitlement_service=self.entitlement_service,
                partner_config_service=self.partner_config_service,
            )

    async def test_create_manual_order_blocked_when_subscription_mode_is_none(self):
        """SelfServeManualOrderError raised when subscription_mode config is missing."""
        mock_partner = Mock()
        mock_partner.is_active = True
        self.partner_repo.get_by_id.return_value = mock_partner
        self.partner_config_service.get_partner_config_by_key.return_value = None

        payload = {
            "partner_id": 1,
            "plan_id": 1,
            "amount": 10000,
            "payment_method": PaymentMethod.DIRECT,
            "add_ons": {},
        }

        with pytest.raises(SelfServeManualOrderError):
            await self.service.create_manual_order(
                payload=payload,
                current_user={"user_id": 1},
                plan_repo=self.plan_repo,
                partner_repo=self.partner_repo,
                entitlement_repo=self.entitlement_repo,
                entitlement_service=self.entitlement_service,
                partner_config_service=self.partner_config_service,
            )

    async def test_create_manual_order_partner_not_found_raises(self):
        self.partner_repo.get_by_id.return_value = None
        payload = {
            "partner_id": 99,
            "plan_id": 1,
            "amount": 100,
            "payment_method": PaymentMethod.DIRECT,
        }
        with pytest.raises(PartnerNotFoundError):
            await self.service.create_manual_order(
                payload=payload,
                current_user={"user_id": 1},
                plan_repo=self.plan_repo,
                partner_repo=self.partner_repo,
                entitlement_repo=self.entitlement_repo,
                entitlement_service=self.entitlement_service,
            )

    async def test_create_manual_order_with_renewal_sets_original_order_id(self):
        mock_partner = Mock()
        mock_partner.is_active = True
        self.partner_repo.get_by_id.return_value = mock_partner
        self.plan_repo.get_plan_by_id.return_value = self.mock_plan

        mock_latest = Mock(spec=Order)
        mock_latest.id = 42
        mock_latest.plan = Mock()
        mock_latest.plan.id = self.mock_plan.id  # same plan id → RENEWAL
        mock_latest.plan.hierarchy = 1
        self.order_repo.get_latest_order_by_partner.return_value = mock_latest

        self.entitlement_repo.get_all_active_entitlements.return_value = []
        self.entitlement_repo.get_scheduled_entitlements.return_value = []
        self.order_repo.create_manual_order.return_value = self.mock_order

        approved = Mock(spec=Order)
        approved.id = 1
        approved.plan = Mock()
        approved.plan.modules = None
        self.order_repo.update_order.return_value = approved

        payload = {
            "partner_id": 1,
            "plan_id": 1,
            "amount": 10000,
            "payment_method": PaymentMethod.DIRECT,
            "add_ons": {},
        }

        with patch.object(
            self.service, "_build_order_response", return_value={"order": {}}
        ):
            await self.service.create_manual_order(
                payload=payload,
                current_user={"user_id": 1},
                plan_repo=self.plan_repo,
                partner_repo=self.partner_repo,
                entitlement_repo=self.entitlement_repo,
                entitlement_service=self.entitlement_service,
                partner_config_service=self.partner_config_service,
            )

        call_kwargs = self.order_repo.create_manual_order.call_args[1]
        assert call_kwargs["original_order_id"] == 42
        assert call_kwargs["order_type"] == OrderType.RENEWAL

    # =========================================================================
    # BILLING CALCULATIONS
    # =========================================================================

    def test_resolve_billing_days_no_partner_no_entitlements(self):
        result = self.service._resolve_billing_days(self.mock_plan, {}, None)
        assert result == 30

    def test_resolve_billing_days_with_entitlements(self):
        future_timestamp = (datetime.now(timezone.utc).timestamp() + 86400 * 45) * 1000
        mock_entitlement = Mock()
        mock_entitlement.end_date = future_timestamp
        active_entitlements = {"console": mock_entitlement}
        result = self.service._resolve_billing_days(None, active_entitlements, 1)
        assert 44 <= result <= 45

    def test_resolve_billing_days_no_plan_no_entitlements_raises(self):
        with pytest.raises(NoActiveEntitlementError):
            self.service._resolve_billing_days(None, {}, 1)

    def test_resolve_billing_days_expired_entitlement_raises(self):
        """Zero remaining days raises NoActiveEntitlementError."""
        past_timestamp = (datetime.now(timezone.utc).timestamp() - 86400) * 1000
        mock_entitlement = Mock()
        mock_entitlement.end_date = past_timestamp
        active_entitlements = {"console": mock_entitlement}
        with pytest.raises(NoActiveEntitlementError):
            self.service._resolve_billing_days(None, active_entitlements, 1)

    def test_build_billing_breakdown_plan_only(self):
        # mock_plan.price=100, duration=1 (30 days), discount=10%
        # subtotal = (100/30)*30 ≈ 100, discount = 10% ≈ 10, after_discount ≈ 90
        result = self.service._build_billing_breakdown(
            plan=self.mock_plan,
            billing_days=30,
            add_ons_by_service={},
            services={"console"},
            active_entitlements={},
        )
        # Use pytest.approx because Decimal division introduces sub-paisa rounding
        assert float(result["plan_subtotal_before_credit"]) == pytest.approx(
            100.0, abs=0.01
        )
        assert result["plan_upgrade_credit"] == 0
        assert result["plan_discount_amount"] == 10
        assert float(result["plan_subtotal_after_discount"]) == pytest.approx(
            90.0, abs=0.01
        )
        assert result["addons_total"] == 0

    def test_build_billing_breakdown_addons_only(self):
        with patch.object(self.service, "_calculate_service_addons") as mock_calc:
            mock_calc.return_value = {
                "service_name": "console",
                "items": [],
                "service_total": Decimal("600"),
                "total_discount": Decimal("0"),
            }
            result = self.service._build_billing_breakdown(
                plan=None,
                billing_days=30,
                add_ons_by_service={"console": {"ACTIVE_USERS": 2}},
                services={"console"},
                active_entitlements={},
            )
        assert result["plan_details"] is None
        assert result["addons_total"] == 600

    def test_calculate_service_addons_active_users(self):
        # price=100, qty=3, billing_days=30
        # price_per_day_per_unit = Decimal(100)/Decimal(30)
        # subtotal = Decimal(100)/Decimal(30) * 3 * 30 = 300
        result = self.service._calculate_service_addons(
            service="console",
            add_ons={PlanCustomLimitKeys.Console.ACTIVE_USERS: 3},
            billing_days=30,
            plan=self.mock_plan,
        )
        item = result["items"][0]
        expected_price_per_day = Decimal("100") / Decimal("30")
        assert item["price_per_day_per_unit"] == expected_price_per_day
        assert float(item["subtotal"]) == pytest.approx(300.0, abs=0.01)
        assert float(result["service_total"]) == pytest.approx(300.0, abs=0.01)

    def test_calculate_service_addons_unknown_addon_zero(self):
        # No priced add-ons remain (only priced add-on retired):
        # unknown keys price 0 via the real table (no mock).
        result = self.service._calculate_service_addons(
            service="console",
            add_ons={"UNKNOWN_ADDON": 2},
            billing_days=30,
            plan=self.mock_plan,
        )
        assert result["service_total"] == 0

    def test_calculate_service_addons_active_users_no_plan_raises(self):
        with pytest.raises(MissingPlanIdError):
            self.service._calculate_service_addons(
                service="console",
                add_ons={PlanCustomLimitKeys.Console.ACTIVE_USERS: 1},
                billing_days=30,
                plan=None,
            )

    def test_calculate_service_addons_with_discount_on_active_users(self):
        """ACTIVE_USERS addon gets discount when discount_percentage > 0."""
        result = self.service._calculate_service_addons(
            service="console",
            add_ons={PlanCustomLimitKeys.Console.ACTIVE_USERS: 2},
            billing_days=30,
            plan=self.mock_plan,
            discount_percentage=Decimal("10.0"),
        )
        item = result["items"][0]
        # subtotal = (100/30) * 2 * 30 ≈ 200, discount = 10% of 200 = 20
        assert item["discount_amount"] == 20
        assert float(item["total"]) == pytest.approx(180.0, abs=0.01)
        assert result["total_discount"] == 20

    def test_calculate_service_addons_non_active_users_no_discount(self):
        """Non-ACTIVE_USERS addons receive no discount even when percentage is set."""
        result = self.service._calculate_service_addons(
            service="console",
            add_ons={"UNKNOWN_ADDON": 1},
            billing_days=30,
            plan=self.mock_plan,
            discount_percentage=Decimal("50.0"),
        )
        item = result["items"][0]
        assert item["discount_amount"] == 0
        assert item["discount_percentage"] == Decimal("0")

    @patch("src.components.order.services.DbConstants")
    def test_calculate_final_totals_with_gst(self, mock_db_constants):
        mock_db_constants.IS_GST_ENABLED = True
        mock_db_constants.GST_PERCENTAGE = 18.0
        # Billing breakdown values must be Decimal to match the service's internal contract
        billing_breakdown = {
            "plan_subtotal_before_credit": Decimal("3000"),
            "plan_upgrade_credit": Decimal("0"),
            "plan_subtotal_after_credit": Decimal("3000"),
            "plan_discount_amount": Decimal("300"),
            "plan_subtotal_after_discount": Decimal("2700"),
            "addons_total": Decimal("600"),
            "addons_discount_amount": Decimal("0"),
        }
        result = self.service._calculate_final_totals(
            billing_days=30, plan=self.mock_plan, billing_breakdown=billing_breakdown
        )
        # subtotal = 2700 + 600 = 3300; GST = ceil(3300 * 18 / 100) = 594
        assert result["summary"]["total_payable"] == 3894
        assert result["summary"]["total_savings"] == 300

    @patch("src.components.order.services.DbConstants")
    def test_calculate_final_totals_without_gst(self, mock_db_constants):
        mock_db_constants.IS_GST_ENABLED = False
        billing_breakdown = {
            "plan_subtotal_before_credit": Decimal("3000"),
            "plan_upgrade_credit": Decimal("0"),
            "plan_subtotal_after_credit": Decimal("3000"),
            "plan_discount_amount": Decimal("300"),
            "plan_subtotal_after_discount": Decimal("2700"),
            "addons_total": Decimal("600"),
            "addons_discount_amount": Decimal("0"),
        }
        result = self.service._calculate_final_totals(
            billing_days=30, plan=self.mock_plan, billing_breakdown=billing_breakdown
        )
        assert result["summary"]["gst"]["enabled"] is False
        assert result["summary"]["total_payable"] == 3300

    @patch("src.components.order.services.DbConstants")
    def test_calculate_final_totals_with_addon_discount(self, mock_db_constants):
        mock_db_constants.IS_GST_ENABLED = True
        mock_db_constants.GST_PERCENTAGE = 18.0
        billing_breakdown = {
            "plan_subtotal_before_credit": Decimal("3000"),
            "plan_upgrade_credit": Decimal("0"),
            "plan_subtotal_after_credit": Decimal("3000"),
            "plan_discount_amount": Decimal("300"),
            "plan_subtotal_after_discount": Decimal("2700"),
            "addons_total": Decimal("540"),
            "addons_discount_amount": Decimal("60"),
        }
        result = self.service._calculate_final_totals(
            billing_days=30, plan=self.mock_plan, billing_breakdown=billing_breakdown
        )
        assert result["summary"]["addons_discount"] == 60
        assert result["summary"]["total_savings"] == 360

    @patch("src.components.order.services.DbConstants")
    def test_calculate_final_totals_no_plan_uses_india_currency(
        self, mock_db_constants
    ):
        mock_db_constants.IS_GST_ENABLED = False
        billing_breakdown = {
            "plan_subtotal_before_credit": Decimal("0"),
            "plan_upgrade_credit": Decimal("0"),
            "plan_subtotal_after_credit": Decimal("0"),
            "plan_discount_amount": Decimal("0"),
            "plan_subtotal_after_discount": Decimal("0"),
            "addons_total": Decimal("600"),
            "addons_discount_amount": Decimal("0"),
        }
        result = self.service._calculate_final_totals(
            billing_days=30, plan=None, billing_breakdown=billing_breakdown
        )
        assert result["currency"] == Currency.INDIA

    @patch("src.components.order.services.DbConstants")
    def test_calculate_final_totals_per_month_fields_present(self, mock_db_constants):
        """Verify per-month normalisation fields are included in the summary."""
        mock_db_constants.IS_GST_ENABLED = False
        billing_breakdown = {
            "plan_subtotal_before_credit": Decimal("3000"),
            "plan_upgrade_credit": Decimal("0"),
            "plan_subtotal_after_credit": Decimal("3000"),
            "plan_discount_amount": Decimal("0"),
            "plan_subtotal_after_discount": Decimal("3000"),
            "addons_total": Decimal("0"),
            "addons_discount_amount": Decimal("0"),
        }
        result = self.service._calculate_final_totals(
            billing_days=30, plan=self.mock_plan, billing_breakdown=billing_breakdown
        )
        assert "total_payable_per_month" in result["summary"]
        assert "total_without_discount_per_month" in result["summary"]

    # =========================================================================
    # _calculate_plan_pricing_with_upgrade — upgrade credit path
    # =========================================================================

    def test_calculate_plan_pricing_with_upgrade_applies_credit(self):
        current_plan = Mock(spec=Plan)
        current_plan.price = 60
        current_plan.name = "Old Plan"

        mock_ent = Mock()
        mock_ent.order = Mock()
        mock_ent.order.plan = current_plan

        self.mock_plan.service_name = "console"
        active_entitlements = {"console": mock_ent}

        with patch.object(
            self.service,
            "_get_current_plan_from_entitlement",
            return_value=current_plan,
        ):
            result = self.service._calculate_plan_pricing_with_upgrade(
                self.mock_plan, billing_days=30, active_entitlements=active_entitlements
            )

        # new plan: 100/30 * 30 ≈ 100, credit: 60/30 * 30 = 60, net ≈ 40
        assert float(result["upgrade_credit"]) == pytest.approx(60.0, abs=0.01)
        assert float(result["subtotal_after_credit"]) == pytest.approx(40.0, abs=0.01)
        assert result["current_plan_name"] == "Old Plan"

    def test_calculate_plan_pricing_no_current_plan_no_credit(self):
        """No active entitlement for the service → zero upgrade credit."""
        with patch.object(
            self.service,
            "_get_current_plan_from_entitlement",
            return_value=None,
        ):
            result = self.service._calculate_plan_pricing_with_upgrade(
                self.mock_plan, billing_days=30, active_entitlements={}
            )
        assert result["upgrade_credit"] == 0
        assert result["current_plan_name"] is None

    # =========================================================================
    # INITIATE ORDER
    # =========================================================================

    async def test_initiate_order_success(self):
        self.plan_repo.get_plan_by_id.return_value = self.mock_plan
        self.entitlement_repo.get_all_active_entitlements.return_value = []
        self.order_repo.get_latest_order_by_partner.return_value = None  # → FRESH
        self.order_repo.initiate_order.return_value = self.mock_order
        self.order_repo.update_order.return_value = self.mock_order
        self.payment_service.create_order.return_value = {"id": "gateway_123"}

        with patch.object(
            self.service,
            "_build_order_response",
            return_value={"order": {}, "payment_gateway_order": {}},
        ):
            result = await self.service.initiate_order(
                self.order_data,
                self.user_context,
                entitlement_repo=self.entitlement_repo,
                plan_repo=self.plan_repo,
                wallet_service=self.wallet_service,
            )
        assert result is not None

    async def test_initiate_order_with_active_entitlement_uses_remaining_days(self):
        """Plan + active entitlement → duration taken from remaining entitlement days."""
        future_timestamp = (datetime.now(timezone.utc).timestamp() + 86400 * 15) * 1000
        mock_ent = Mock()
        mock_ent.end_date = future_timestamp
        mock_ent.service_name = "console"

        self.plan_repo.get_plan_by_id.return_value = self.mock_plan
        self.entitlement_repo.get_all_active_entitlements.return_value = [mock_ent]
        self.order_repo.get_latest_order_by_partner.return_value = None  # → FRESH
        self.order_repo.initiate_order.return_value = self.mock_order
        self.order_repo.update_order.return_value = self.mock_order
        self.payment_service.create_order.return_value = {"id": "gw_x"}

        with patch.object(self.service, "_check_hierarchy_downgrade"), patch.object(
            self.service, "_build_order_response", return_value={"order": {}}
        ):
            await self.service.initiate_order(
                self.order_data,
                self.user_context,
                entitlement_repo=self.entitlement_repo,
                plan_repo=self.plan_repo,
                wallet_service=self.wallet_service,
            )

        call_kwargs = self.order_repo.initiate_order.call_args
        # duration_in_days (4th positional arg) should NOT equal full plan duration (30)
        assert call_kwargs[0][3] != self.mock_plan.duration * 30

    async def test_initiate_order_with_add_ons(self):
        order_data = OrderBase(
            plan_id=None,
            amount=100.0,
            currency="INR",
            add_ons={"ACTIVE_USERS": 1},
            source="console",
        )
        future_timestamp = (datetime.now(timezone.utc).timestamp() + 86400 * 30) * 1000
        mock_entitlement = Mock()
        mock_entitlement.end_date = future_timestamp
        self.entitlement_repo.get_all_active_entitlements.return_value = [
            mock_entitlement
        ]
        self.order_repo.initiate_order.return_value = self.mock_order
        self.order_repo.update_order.return_value = self.mock_order
        self.payment_service.create_order.return_value = {"id": "gateway_123"}

        with patch.object(
            self.service,
            "_build_order_response",
            return_value={"order": {}, "payment_gateway_order": {}},
        ), patch.object(self.service, "_validate_addons_entitlement"):
            result = await self.service.initiate_order(
                order_data,
                self.user_context,
                entitlement_repo=self.entitlement_repo,
                plan_repo=self.plan_repo,
                wallet_service=self.wallet_service,
            )
        assert result is not None

    # =========================================================================
    # VALIDATE ORDER
    # =========================================================================

    async def test_validate_order_success_standard_plan(self):
        self.order_repo.get_order_by_merchant_transaction_id.return_value = (
            self.mock_order
        )
        updated_order = Mock(spec=Order)
        updated_order.status = PaymentStatusEnum.SUCCESS
        updated_order.plan_id= UUID("11111111-1111-1111-1111-111111111111")
        updated_order.plan = Mock()
        updated_order.plan.plan_type = PlanType.STANDARD
        updated_order.plan.modules = None  # skip grace settlement
        updated_order.partner_id= UUID("11111111-1111-1111-1111-111111111111")
        self.order_repo.update_order_if_not_finalized.return_value = updated_order
        self.payment_service.validate_order.return_value = {
            "status": "success",
            "payment_id": "pay_123",
        }
        result = await self.service.validate_order(
            "merchant_123",
            "pay_123",
            "sig",
            self.user_context,
            entitlement_service=self.entitlement_service,
            wallet_service=self.wallet_service,
        )
        assert result["status"] == "success"
        self.entitlement_service.upsert_entitlement.assert_called_once()

    async def test_validate_order_already_processed(self):
        self.mock_order.status = PaymentStatusEnum.SUCCESS
        self.order_repo.get_order_by_merchant_transaction_id.return_value = (
            self.mock_order
        )
        with pytest.raises(OrderAlreadyProcessedError):
            await self.service.validate_order(
                "merchant_123",
                "pay_123",
                "sig",
                self.user_context,
                entitlement_service=self.entitlement_service,
                wallet_service=self.wallet_service,
            )

    async def test_validate_order_refunded_is_blocked(self):
        self.mock_order.status = PaymentStatusEnum.REFUNDED
        self.order_repo.get_order_by_merchant_transaction_id.return_value = (
            self.mock_order
        )
        with pytest.raises(OrderAlreadyProcessedError):
            await self.service.validate_order(
                "merchant_123",
                "pay_123",
                "sig",
                self.user_context,
                entitlement_service=self.entitlement_service,
                wallet_service=self.wallet_service,
            )

    async def test_validate_order_retries_after_failed_and_succeeds(self):
        """A late-arriving genuine success must be able to recover an order
        that was previously marked FAILED (e.g. by the abandoned-order
        cleanup cron racing a slow checkout) instead of being permanently
        stuck."""
        self.mock_order.status = PaymentStatusEnum.FAILED
        self.order_repo.get_order_by_merchant_transaction_id.return_value = (
            self.mock_order
        )
        updated_order = Mock(spec=Order)
        updated_order.status = PaymentStatusEnum.SUCCESS
        updated_order.plan_id= UUID("11111111-1111-1111-1111-111111111111")
        updated_order.plan = Mock()
        updated_order.plan.plan_type = PlanType.STANDARD
        updated_order.plan.modules = None
        updated_order.partner_id= UUID("11111111-1111-1111-1111-111111111111")
        self.order_repo.update_order_if_not_finalized.return_value = updated_order
        self.payment_service.validate_order.return_value = {
            "status": "success",
            "payment_id": "pay_123",
        }

        result = await self.service.validate_order(
            "merchant_123",
            "pay_123",
            "sig",
            self.user_context,
            entitlement_service=self.entitlement_service,
            wallet_service=self.wallet_service,
        )

        assert result["status"] == "success"
        self.entitlement_service.upsert_entitlement.assert_called_once()

    async def test_validate_order_failed_payment_does_not_provision(self):
        self.order_repo.get_order_by_merchant_transaction_id.return_value = (
            self.mock_order
        )
        failed_order = Mock(spec=Order)
        failed_order.status = PaymentStatusEnum.FAILED
        self.order_repo.update_order_if_not_finalized.return_value = failed_order
        self.payment_service.validate_order.return_value = {"status": "failed"}
        await self.service.validate_order(
            "merchant_123",
            "pay_123",
            "sig",
            self.user_context,
            entitlement_service=self.entitlement_service,
            wallet_service=self.wallet_service,
        )
        self.entitlement_service.upsert_entitlement.assert_not_called()

    async def test_validate_order_concurrent_duplicate_skips_reprovisioning(self):
        """Two concurrent validate_order calls for the same order: the
        loser's update_order_if_not_finalized call returns None (the DB's
        WHERE clause found the row already finalized by the winner) and
        must not provision a second time."""
        self.order_repo.get_order_by_merchant_transaction_id.return_value = (
            self.mock_order
        )
        self.order_repo.update_order_if_not_finalized.return_value = None
        self.payment_service.validate_order.return_value = {
            "status": "success",
            "payment_id": "pay_123",
        }

        result = await self.service.validate_order(
            "merchant_123",
            "pay_123",
            "sig",
            self.user_context,
            entitlement_service=self.entitlement_service,
            wallet_service=self.wallet_service,
        )

        assert result["status"] == "success"
        self.entitlement_service.upsert_entitlement.assert_not_called()
        self.wallet_service.perform_transaction.assert_not_called()

    # =========================================================================
    # GET BILLING DETAILS
    # =========================================================================

    async def test_get_billing_details_unauthenticated_success(self):
        self.plan_repo.get_plan_by_id.return_value = self.mock_plan
        with patch.object(self.service, "_calculate_final_totals") as mock_calc:
            mock_calc.return_value = {"summary": {"total_payable": 10000}}
            result = await self.service.get_billing_details(
                OrderBillingDetailsRequest(plan_id= UUID("11111111-1111-1111-1111-111111111111")),
                partner_id=None,
                plan_repo=self.plan_repo,
                entitlement_repo=self.entitlement_repo,
            )
        assert result["summary"]["total_payable"] == 10000

    async def test_get_billing_details_wallet_plan_error(self):
        self.mock_plan.plan_type = PlanType.WALLET
        self.plan_repo.get_plan_by_id.return_value = self.mock_plan
        with pytest.raises(NoBillingForWalletError):
            await self.service.get_billing_details(
                OrderBillingDetailsRequest(plan_id= UUID("11111111-1111-1111-1111-111111111111")),
                partner_id=None,
                plan_repo=self.plan_repo,
                entitlement_repo=self.entitlement_repo,
            )

    async def test_get_billing_details_free_trial_error(self):
        self.mock_plan.is_free_trial = True
        self.plan_repo.get_plan_by_id.return_value = self.mock_plan
        with pytest.raises(NoBillingForWalletError):
            await self.service.get_billing_details(
                OrderBillingDetailsRequest(plan_id= UUID("11111111-1111-1111-1111-111111111111")),
                partner_id=None,
                plan_repo=self.plan_repo,
                entitlement_repo=self.entitlement_repo,
            )

    # =========================================================================
    # HIERARCHY VALIDATION
    # =========================================================================

    async def test_check_hierarchy_downgrade_prevented(self):
        current_plan = Mock()
        current_plan.hierarchy = 5
        current_plan.name = "Premium"
        mock_ent = Mock()
        mock_ent.order = Mock()
        mock_ent.order.plan = current_plan
        self.entitlement_repo.get_all_active_entitlements.return_value = [mock_ent]
        new_plan = Mock()
        new_plan.hierarchy = 1
        new_plan.name = "Basic"
        with pytest.raises(InvalidUpgradeError, match="cannot downgrade"):
            await self.service._check_hierarchy_downgrade(
                1, new_plan, self.entitlement_repo
            )

    async def test_check_hierarchy_upgrade_allowed(self):
        current_plan = Mock()
        current_plan.hierarchy = 1
        mock_ent = Mock()
        mock_ent.order = Mock()
        mock_ent.order.plan = current_plan
        self.entitlement_repo.get_all_active_entitlements.return_value = [mock_ent]
        new_plan = Mock()
        new_plan.hierarchy = 5
        # Should not raise
        await self.service._check_hierarchy_downgrade(
            1, new_plan, self.entitlement_repo
        )

    async def test_check_hierarchy_no_active_entitlements_allows_any(self):
        self.entitlement_repo.get_all_active_entitlements.return_value = []
        new_plan = Mock()
        new_plan.hierarchy = 1
        await self.service._check_hierarchy_downgrade(
            1, new_plan, self.entitlement_repo
        )

    async def test_check_hierarchy_entitlement_plan_none_skipped(self):
        """Deleted plan on existing entitlement must not block hierarchy check."""
        mock_ent = Mock()
        mock_ent.order = Mock()
        mock_ent.order.plan = None  # plan deleted
        self.entitlement_repo.get_all_active_entitlements.return_value = [mock_ent]
        new_plan = Mock()
        new_plan.hierarchy = 1
        # Should not raise — no valid hierarchy to compare against
        await self.service._check_hierarchy_downgrade(
            1, new_plan, self.entitlement_repo
        )

    # =========================================================================
    # GET ORDER HISTORY
    # =========================================================================

    async def test_get_order_history_success(self, monkeypatch):
        monkeypatch.setenv("PAYMENT_CLIENT", "razorpay")

        past_ms = 1704067200000  # 2024-01-01 UTC
        future_ms = int(time.time() * 1000) + (365 * 24 * 60 * 60 * 1000)

        order_data = [
            {
                "order": {
                    "id": 1,
                    "source": "web",
                    "status": "completed",
                    "currency": "INR",
                    "merchant_transaction_id": "TXN123",
                    "duration": 12,
                    "add_ons": {},
                    "amount": 1000.0,
                    "created_at": "2024-01-01",
                    "created_by": 1,
                    "updated_at": "2024-01-02",
                    "updated_by": 1,
                    "is_manually_created": False,
                    "order_type": "FRESH",
                    "payment_method": None,
                    "original_order_id": None,
                },
                "partner": {
                    "id": 1,
                    "name": "Test Partner",
                    "gst_no": "GST123",
                    "is_active": True,
                    "country": None,
                    "state": None,
                    "city": None,
                },
                "plan": {
                    "id": 1,
                    "name": "Basic Plan",
                    "plan_type": "STANDARD",
                    "duration": 12,
                    "limits": {},
                    "price": 1000,
                    "discount_percentage": 10.0,
                },
                "payment": {
                    "payment_status": "success",
                    "created_at": "2024-01-01",
                    "payment_method": "card",
                },
                "entitlement": {
                    "start_date": past_ms,
                    "end_date": future_ms,
                    "is_active": True,
                    "is_manually_deactivated": False,
                },
                "admin_user": {"email": "admin@test.com", "phone_number": "+91123"},
            }
        ]
        self.order_repo.get_order_history.return_value = (order_data, 1)
        result, count = await self.service.get_order_history(
            filters={"partner_id": 1}, limit=10, offset=0
        )
        assert count == 1
        assert result[0]["order_id"] == 1
        assert result[0]["subscription_status"] == ServiceSubscriptionStatus.ACTIVE

    async def test_get_order_history_empty_results(self, monkeypatch):
        monkeypatch.setenv("PAYMENT_CLIENT", "RAZORPAY")
        self.order_repo.get_order_history.return_value = ([], 0)
        result, count = await self.service.get_order_history(
            filters={}, limit=10, offset=0
        )
        assert count == 0
        assert len(result) == 0

    async def test_get_order_history_exception_handling(self, monkeypatch):
        monkeypatch.setenv("PAYMENT_CLIENT", "RAZORPAY")
        self.order_repo.get_order_history.side_effect = Exception("DB fail")
        with pytest.raises(Exception, match="DB fail"):
            await self.service.get_order_history(filters={})
        self.logger.error.assert_called()

    # =========================================================================
    # UTILITY
    # =========================================================================

    async def test_load_plan_success(self):
        self.plan_repo.get_plan_by_id.return_value = self.mock_plan
        result = await self.service._load_plan(
            OrderBillingDetailsRequest(plan_id= UUID("11111111-1111-1111-1111-111111111111")), self.plan_repo
        )
        assert result == self.mock_plan

    async def test_load_plan_not_found(self):
        self.plan_repo.get_plan_by_id.return_value = None
        with pytest.raises(PlanInactiveError):
            await self.service._load_plan(
                OrderBillingDetailsRequest(plan_id= UUID("99999999-9999-9999-9999-999999999999")), self.plan_repo
            )

    async def test_load_plan_no_plan_id(self):
        result = await self.service._load_plan(
            OrderBillingDetailsRequest(plan_id=None, add_ons={"ACTIVE_USERS": 1}),
            self.plan_repo,
        )
        assert result is None

    def test_split_addons_by_service_success(self):
        result = self.service._split_addons_by_service(
            {
                PlanCustomLimitKeys.Console.ACTIVE_USERS: 2,
                PlanCustomLimitKeys.Console.ACTIVE_USERS: 1,
            }
        )
        assert "console" in result
        assert "console" in result

    def test_split_addons_by_service_empty(self):
        assert self.service._split_addons_by_service({}) == {}

    def test_split_addons_by_service_unknown_key_skipped(self):
        result = self.service._split_addons_by_service({"UNKNOWN_KEY": 1})
        assert result == {}
        self.logger.warning.assert_called()

    # =========================================================================
    # MAPPING HELPERS (full coverage)
    # =========================================================================

    def test_map_order_fields_all_present(self):
        order = {
            "id": 100,
            "source": "dashboard",
            "status": "completed",
            "currency": "EUR",
            "merchant_transaction_id": "MERC-789",
            "duration": 24,
            "add_ons": {},
            "amount": 2400.0,
            "created_at": "2023-12-01",
            "created_by": 5,
            "updated_at": "2023-12-02",
            "updated_by": 6,
            "is_manually_created": True,
            "order_type": OrderType.RENEWAL,
            "payment_method": PaymentMethod.DIRECT,
            "original_order_id": 50,
        }
        result = self.service._map_order_fields(order)
        assert result["order_id"] == 100
        assert result["is_manually_created"] is True
        assert result["order_type"] == OrderType.RENEWAL
        assert result["payment_method"] == PaymentMethod.DIRECT
        assert result["original_order_id"] == 50

    def test_map_order_fields_missing_fields(self):
        result = self.service._map_order_fields({"id": 200})
        assert result["order_id"] == 200
        assert result["source"] is None

    def test_map_order_fields_empty_dict(self):
        result = self.service._map_order_fields({})
        none_fields = [
            "order_id",
            "source",
            "order_status",
            "order_currency",
            "merchant_transaction_id",
            "duration",
            "add_ons",
            "total_price",
            "order_created_at",
            "order_created_by",
            "order_updated_at",
            "order_updated_by",
            "payment_method",
            "original_order_id",
        ]
        for field in none_fields:
            assert result[field] is None, f"Expected {field} to be None"
        assert result["is_manually_created"] is False
        assert result["order_type"] == OrderType.FRESH

    def test_map_partner_fields_with_partner_and_admin(self):
        result = self.service._map_partner_fields(
            {
                "id": 50,
                "name": "Tech",
                "gst_no": "GST999",
                "is_active": True,
                "country": "UK",
                "state": "London",
                "city": "Westminster",
            },
            {"email": "a@b.com", "phone_number": "+44123"},
        )
        assert result["partner_id"] == 50
        assert result["partner_email"] == "a@b.com"

    def test_map_partner_fields_none_partner(self):
        result = self.service._map_partner_fields(None, {"email": "x@y.com"})
        assert result["partner_id"] is None
        assert result["partner_email"] == "x@y.com"

    def test_map_partner_fields_none_admin(self):
        result = self.service._map_partner_fields({"id": 1, "name": "P"}, None)
        assert result["partner_id"] == 1
        assert result["partner_email"] is None

    def test_map_partner_fields_both_none(self):
        result = self.service._map_partner_fields(None, None)
        for v in result.values():
            assert v is None

    def test_map_plan_fields_with_plan(self):
        result = self.service._map_plan_fields(
            {
                "id": 5,
                "name": "S",
                "plan_type": "B",
                "duration": 3,
                "limits": {},
                "price": 100,
                "discount_percentage": 5.0,
            },
            90,
        )
        assert result["plan_duration_months"] == 3
        assert result["duration_in_days"] == 90

    def test_map_plan_fields_none_plan(self):
        result = self.service._map_plan_fields(None, 60)
        assert result["plan_id"] is None
        assert result["duration_in_days"] == 60
        assert result["plan_limits"] == {}
        assert result["plan_price"] == 0

    def test_map_entitlement_fields_with_entitlement(self):
        result = self.service._map_entitlement_fields(
            {"start_date": 111, "end_date": 222, "is_active": True}
        )
        assert result["entitlement_is_active"] is True

    def test_map_entitlement_fields_none(self):
        result = self.service._map_entitlement_fields(None)
        assert result["entitlement_start_date"] is None

    def test_map_payment_fields_with_payment(self):
        result = self.service._map_payment_fields(
            {
                "payment_status": "refunded",
                "created_at": "2024",
                "payment_method": "netbanking",
            },
            "PAYTM",
        )
        assert result["payment_gateway"] == "PAYTM"
        assert result["payment_status"] == "refunded"

    def test_map_payment_fields_none(self):
        result = self.service._map_payment_fields(None, "CASHFREE")
        assert result["payment_gateway"] == "CASHFREE"
        assert result["payment_status"] is None

    def test_map_payment_fields_direct_success_order_derives_status(self):
        """DIRECT orders without a payment record should still show SUCCESS."""
        result = self.service._map_payment_fields(
            None,
            "GATEWAY",
            order={
                "payment_method": PaymentMethod.DIRECT,
                "status": PaymentStatusEnum.SUCCESS,
                "created_at": "2024-01-01",
            },
        )
        assert result["payment_status"] == PaymentStatusEnum.SUCCESS
        assert result["payment_method"] == PaymentMethod.DIRECT
        assert result["payment_gateway"] is None

    def test_calculate_plan_duration_days_with_plan(self):
        assert self.service._calculate_plan_duration_days({"duration": 12}) == 360

    def test_calculate_plan_duration_days_zero(self):
        assert self.service._calculate_plan_duration_days({"duration": 0}) == 0

    def test_calculate_plan_duration_days_none(self):
        assert self.service._calculate_plan_duration_days(None) == 0

    def test_calculate_plan_duration_days_missing_key(self):
        assert self.service._calculate_plan_duration_days({"id": 1}) == 0

    def test_build_order_history_response_complete(self):
        order_dict = {
            "order": {
                "id": 1,
                "source": "mobile",
                "status": "pending",
                "currency": "USD",
                "merchant_transaction_id": "TXN456",
                "duration": 6,
                "add_ons": {},
                "amount": 500.0,
                "created_at": "2024-01-01",
                "created_by": 2,
                "updated_at": "2024-01-02",
                "updated_by": 3,
            },
            "partner": {
                "id": 10,
                "name": "ABC",
                "gst_no": "G",
                "is_active": False,
                "country": "USA",
                "state": "CA",
                "city": "SF",
            },
            "plan": {
                "id": 5,
                "name": "Premium",
                "plan_type": "E",
                "duration": 6,
                "limits": {},
                "price": 5000,
                "discount_percentage": 15.0,
            },
            "payment": {
                "payment_status": "pending",
                "created_at": "2024-01-01",
                "payment_method": "upi",
            },
            "entitlement": {"start_date": 111, "end_date": 222, "is_active": True},
            "admin_user": {"email": "admin@abc.com", "phone_number": "+91"},
        }
        result = self.service._build_order_history_response(order_dict, "STRIPE")
        assert result["order_id"] == 1
        assert result["payment_gateway"] == "STRIPE"
        assert result["duration_in_days"] == 180

    def test_build_order_history_response_minimal(self):
        order_dict = {
            "order": {"id": 1},
            "partner": None,
            "plan": None,
            "payment": None,
            "entitlement": None,
            "admin_user": None,
        }
        result = self.service._build_order_history_response(order_dict, "PAYPAL")
        assert result["order_id"] == 1
        assert result["payment_gateway"] == "PAYPAL"
        assert result["duration_in_days"] == 0

    # =========================================================================
    # _resolve_order_subscription_status
    # =========================================================================

    def test_resolve_subscription_status_active(self):
        now_ms = int(time.time() * 1000)
        order = {
            "status": PaymentStatusEnum.SUCCESS,
            "payment_method": PaymentMethod.GATEWAY,
        }
        entitlement = {
            "is_manually_deactivated": False,
            "is_active": True,
            "start_date": now_ms - 1000,
            "end_date": now_ms + 86400000,
        }
        result = self.service._resolve_order_subscription_status(order, entitlement)
        assert result == ServiceSubscriptionStatus.ACTIVE

    def test_resolve_subscription_status_payment_failed(self):
        order = {
            "status": PaymentStatusEnum.FAILED,
            "payment_method": PaymentMethod.GATEWAY,
        }
        result = self.service._resolve_order_subscription_status(order, None)
        assert result == ServiceSubscriptionStatus.PAYMENT_FAILED

    def test_resolve_subscription_status_pending_gateway(self):
        order = {
            "status": PaymentStatusEnum.PENDING,
            "payment_method": PaymentMethod.GATEWAY,
        }
        result = self.service._resolve_order_subscription_status(order, None)
        assert result == ServiceSubscriptionStatus.PENDING_ACTIVATION

    def test_resolve_subscription_status_canceled(self):
        now_ms = int(time.time() * 1000)
        order = {
            "status": PaymentStatusEnum.SUCCESS,
            "payment_method": PaymentMethod.GATEWAY,
        }
        entitlement = {
            "is_manually_deactivated": True,
            "is_active": False,
            "start_date": now_ms - 1000,
            "end_date": now_ms + 86400000,
        }
        result = self.service._resolve_order_subscription_status(order, entitlement)
        assert result == ServiceSubscriptionStatus.CANCELED

    def test_resolve_subscription_status_suspended_no_entitlement(self):
        order = {
            "status": PaymentStatusEnum.SUCCESS,
            "payment_method": PaymentMethod.GATEWAY,
        }
        result = self.service._resolve_order_subscription_status(order, None)
        assert result == ServiceSubscriptionStatus.SUSPENDED

    def test_resolve_subscription_status_direct_failed(self):
        order = {
            "status": PaymentStatusEnum.FAILED,
            "payment_method": PaymentMethod.DIRECT,
        }
        result = self.service._resolve_order_subscription_status(order, None)
        assert result == ServiceSubscriptionStatus.PAYMENT_FAILED


    @pytest.mark.asyncio
    async def test_send_daily_order_report_success(self):

        self.order_repo.get_report_for_created_orders.side_effect = [
            [{"partner": "manual"}],
            [{"partner": "custom"}],
        ]

        self.wallet_service.create_tranaction_csv.side_effect = [
            "manual_csv",
            "custom_csv",
        ]

        with patch.object(
            self.service,
            "_OrderService__send_order_report_to_internal_partner",
        ) as mock_send_email:

            await self.service.send_daily_order_report(
                wallet_service=self.wallet_service
            )

            assert (
                self.order_repo.get_report_for_created_orders.await_count
                == 2
            )

            assert (
                self.wallet_service.create_tranaction_csv.await_count
                == 2
            )

            mock_send_email.assert_called_once()

            attachments = mock_send_email.call_args.kwargs["attachments"]

            assert len(attachments) == 2

    @pytest.mark.asyncio
    async def test_send_daily_order_report_only_manual_orders(self):

        self.order_repo.get_report_for_created_orders.side_effect = [
            [{"partner": "manual"}],
            [],
        ]

        self.wallet_service.create_tranaction_csv.return_value = "manual_csv"

        with patch.object(
            self.service,
            "_OrderService__send_order_report_to_internal_partner",
        ) as mock_send_email:

            await self.service.send_daily_order_report(
                wallet_service=self.wallet_service
            )

            mock_send_email.assert_called_once()

            attachments = mock_send_email.call_args.kwargs["attachments"]

            assert len(attachments) == 2

    @pytest.mark.asyncio
    async def test_send_daily_order_report_no_orders(self):

        self.order_repo.get_report_for_created_orders.side_effect = [
            [],
            [],
        ]

        self.wallet_service.create_tranaction_csv.return_value = None

        with patch.object(
            self.service,
            "_OrderService__send_order_report_to_internal_partner",
        ) as mock_send_email:

            await self.service.send_daily_order_report(
                wallet_service=self.wallet_service
            )

            mock_send_email.assert_not_called()

    @pytest.mark.asyncio
    async def test_send_daily_order_report_exception(self):

        self.order_repo.get_report_for_created_orders.side_effect = Exception(
            "DB Error"
        )

        with pytest.raises(Exception):
            await self.service.send_daily_order_report(
                wallet_service=self.wallet_service
            )

    @pytest.mark.asyncio
    async def test_send_approaching_renewal_report_success(self):

        self.order_repo.get_approaching_renewal_report.return_value = [
            {"partner": "test"}
        ]

        self.wallet_service.create_tranaction_csv.return_value = (
            "renewal_csv"
        )

        with patch.object(
            self.service,
            "_OrderService__send_order_report_to_internal_partner",
        ) as mock_send_email:

            await self.service.send_approaching_renewal_report(
                wallet_service=self.wallet_service
            )

            self.order_repo.get_approaching_renewal_report.assert_awaited_once()

            self.wallet_service.create_tranaction_csv.assert_awaited_once()

            mock_send_email.assert_called_once()

            attachments = mock_send_email.call_args.kwargs["attachments"]

            assert len(attachments) == 1

    @pytest.mark.asyncio
    async def test_send_approaching_renewal_report_no_orders(self):

        self.order_repo.get_approaching_renewal_report.return_value = []

        with patch.object(
            self.service,
            "_OrderService__send_order_report_to_internal_partner",
        ) as mock_send_email:

            await self.service.send_approaching_renewal_report(
                wallet_service=self.wallet_service
            )

            mock_send_email.assert_not_called()

            self.wallet_service.create_tranaction_csv.assert_not_called()

    @pytest.mark.asyncio
    async def test_send_approaching_renewal_report_exception(self):

        self.order_repo.get_approaching_renewal_report.side_effect = Exception(
            "DB Error"
        )

        with pytest.raises(Exception):
            await self.service.send_approaching_renewal_report(
                wallet_service=self.wallet_service
            )

    @pytest.mark.asyncio
    async def test_send_expiry_overdue_order_report_success(self):

        self.order_repo.get_expired_and_overdue_report.return_value = [
            {
                "partner": "test",
                "subscription_status": "EXPIRED",
            }
        ]

        self.wallet_service.create_tranaction_csv.return_value = (
            "expired_csv"
        )

        with patch.object(
            self.service,
            "_OrderService__send_order_report_to_internal_partner",
        ) as mock_send_email:

            await self.service.send_expiry_overdue_order_report(
                wallet_service=self.wallet_service
            )

            self.order_repo.get_expired_and_overdue_report.assert_awaited_once()

            self.wallet_service.create_tranaction_csv.assert_awaited_once()

            mock_send_email.assert_called_once()

            attachments = mock_send_email.call_args.kwargs["attachments"]

            assert len(attachments) == 1

    @pytest.mark.asyncio
    async def test_send_expiry_overdue_order_report_no_orders(self):

        self.order_repo.get_expired_and_overdue_report.return_value = []

        with patch.object(
            self.service,
            "_OrderService__send_order_report_to_internal_partner",
        ) as mock_send_email:

            await self.service.send_expiry_overdue_order_report(
                wallet_service=self.wallet_service
            )

            mock_send_email.assert_not_called()

            self.wallet_service.create_tranaction_csv.assert_not_called()

    @pytest.mark.asyncio
    async def test_send_expiry_overdue_order_report_exception(self):

        self.order_repo.get_expired_and_overdue_report.side_effect = Exception(
            "DB Error"
        )

        with pytest.raises(Exception):
            await self.service.send_expiry_overdue_order_report(
                wallet_service=self.wallet_service
            )
