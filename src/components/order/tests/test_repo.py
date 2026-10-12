from uuid import UUID
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy.exc import SQLAlchemyError

from src.components.entitlement.models import Entitlement
from src.components.order.constants import OrderType, PaymentMethod
from src.components.order.errors import OrderNotFoundError
from src.components.order.models import Order
from src.components.order.repositories import OrderRepository
from src.components.partner.models import Partner
from src.components.partner_address.schema import AddressType
from src.components.payment.enum import PaymentStatusEnum
from src.components.payment.models import Payment
from src.components.plan.models import Plan
from src.components.user.models import User


@pytest.mark.asyncio
class TestOrderRepository:

    @pytest.fixture(autouse=True)
    def setup_repo(self, mock_session_factory, mock_logger):
        self.order_repo = OrderRepository(
            session_factory=mock_session_factory,
            logger=mock_logger,
        )
        self.session = mock_session_factory.return_value.__aenter__.return_value
        self.mock_logger = mock_logger

    # -------------------------------------------------------------------------
    # Shared helpers
    # -------------------------------------------------------------------------

    def _make_mock_order(
        self, order_id= UUID("11111111-1111-1111-1111-111111111111"), partner_id= UUID("11111111-1111-1111-1111-111111111111"), partner=None, plan=None, payment=None
    ):
        mock_order = MagicMock(spec=Order)
        mock_order.id = order_id
        mock_order.partner_id = partner_id
        mock_order.plan_id= UUID("11111111-1111-1111-1111-111111111111")
        mock_order.add_ons = []
        mock_order.amount = 1000
        mock_order.currency = "INR"
        mock_order.status = "completed"
        mock_order.merchant_transaction_id = f"TXN{order_id}"
        mock_order.duration = 30
        mock_order.source = "web"
        mock_order.created_at = datetime(2024, 1, 1)
        mock_order.created_by= UUID("11111111-1111-1111-1111-111111111111")
        mock_order.updated_at = datetime(2024, 1, 1)
        mock_order.updated_by= UUID("11111111-1111-1111-1111-111111111111")
        mock_order.partner = partner
        mock_order.plan = plan
        mock_order.payment = payment
        return mock_order

    async def _run_order_history(
        self, filters, orders, entitlements=None, admin_users=None, limit=10, offset=1
    ):
        mock_count_result = MagicMock()
        mock_count_result.scalar.return_value = len(orders)
        mock_result = MagicMock()
        mock_result.unique.return_value.scalars.return_value.all.return_value = orders
        mock_entitlement_result = MagicMock()
        mock_entitlement_result.scalars.return_value.all.return_value = (
            entitlements or []
        )
        mock_admin_result = MagicMock()
        mock_admin_result.unique.return_value.scalars.return_value.all.return_value = (
            admin_users or []
        )
        self.session.execute = AsyncMock(
            side_effect=[
                mock_count_result,
                mock_result,
                mock_entitlement_result,
                mock_admin_result,
            ]
        )
        return await self.order_repo.get_order_history(
            filters=filters, limit=limit, offset=offset
        )

    # -------------------------------------------------------------------------
    # initiate_order
    # -------------------------------------------------------------------------

    async def test_initiate_order_success(self):
        mock_order_data = MagicMock(
            plan_id= UUID("11111111-1111-1111-1111-111111111111"), add_ons=["A"], amount=500, currency="INR"
        )
        self.session.add = MagicMock()
        self.session.commit = AsyncMock()
        self.session.refresh = AsyncMock()
        order = await self.order_repo.initiate_order(
            mock_order_data, user_id= UUID("10101010-1010-1010-1010-101010101010"), partner_id= UUID("99999999-9999-9999-9999-999999999999"), duration=30
        )
        self.session.add.assert_called_once()
        self.session.commit.assert_awaited_once()
        assert isinstance(order, Order)

    async def test_initiate_order_with_order_type(self):
        mock_order_data = MagicMock(plan_id= UUID("11111111-1111-1111-1111-111111111111"), add_ons=[], amount=500, currency="INR")
        self.session.add = MagicMock()
        self.session.commit = AsyncMock()
        self.session.refresh = AsyncMock()
        order = await self.order_repo.initiate_order(
            mock_order_data,
            user_id= UUID("10101010-1010-1010-1010-101010101010"),
            partner_id= UUID("99999999-9999-9999-9999-999999999999"),
            duration=30,
            order_type=OrderType.RENEWAL,
        )
        # Verify the Order was constructed with payment_method=GATEWAY
        call_kwargs = self.session.add.call_args[0][0]
        assert call_kwargs.payment_method == PaymentMethod.GATEWAY
        assert call_kwargs.is_manually_created is False

    async def test_initiate_order_failure(self):
        mock_order_data = MagicMock(plan_id= UUID("11111111-1111-1111-1111-111111111111"), add_ons=[], amount=500, currency="INR")
        self.session.add = MagicMock()
        self.session.commit = AsyncMock(side_effect=Exception("DB failure"))
        self.session.rollback = AsyncMock()
        with pytest.raises(Exception):
            await self.order_repo.initiate_order(
                mock_order_data, user_id= UUID("10101010-1010-1010-1010-101010101010"), partner_id= UUID("99999999-9999-9999-9999-999999999999"), duration=30
            )
        self.session.rollback.assert_awaited_once()

    # -------------------------------------------------------------------------
    # create_manual_order
    # -------------------------------------------------------------------------

    async def test_create_manual_order_success_direct(self):
        self.session.add = MagicMock()
        self.session.commit = AsyncMock()
        self.session.refresh = AsyncMock()
        order = await self.order_repo.create_manual_order(
            partner_id= UUID("11111111-1111-1111-1111-111111111111"),
            plan_id= UUID("22222222-2222-2222-2222-222222222222"),
            add_ons={},
            amount=5000,
            currency="INR",
            duration_days=30,
            created_by= UUID("99999999-9999-9999-9999-999999999999"),
            order_type=OrderType.FRESH,
            payment_method=PaymentMethod.DIRECT,
        )
        self.session.add.assert_called_once()
        self.session.commit.assert_awaited_once()
        constructed = self.session.add.call_args[0][0]
        assert constructed.is_manually_created is True
        assert constructed.payment_method == PaymentMethod.DIRECT
        assert constructed.order_type == OrderType.FRESH
        assert constructed.original_order_id is None

    async def test_create_manual_order_with_renewal_original_order_id(self):
        self.session.add = MagicMock()
        self.session.commit = AsyncMock()
        self.session.refresh = AsyncMock()
        await self.order_repo.create_manual_order(
            partner_id= UUID("11111111-1111-1111-1111-111111111111"),
            plan_id= UUID("22222222-2222-2222-2222-222222222222"),
            add_ons={},
            amount=5000,
            currency="INR",
            duration_days=30,
            created_by= UUID("99999999-9999-9999-9999-999999999999"),
            order_type=OrderType.RENEWAL,
            payment_method=PaymentMethod.GATEWAY,
            original_order_id= UUID("77777777-7777-7777-7777-777777777777"),
        )
        constructed = self.session.add.call_args[0][0]
        assert constructed.order_type == OrderType.RENEWAL
        assert constructed.original_order_id== UUID("77777777-7777-7777-7777-777777777777")

    async def test_create_manual_order_failure_rolls_back(self):
        self.session.add = MagicMock()
        self.session.commit = AsyncMock(side_effect=Exception("insert fail"))
        self.session.rollback = AsyncMock()
        with pytest.raises(Exception, match="insert fail"):
            await self.order_repo.create_manual_order(
                partner_id= UUID("11111111-1111-1111-1111-111111111111"),
                plan_id= UUID("22222222-2222-2222-2222-222222222222"),
                add_ons={},
                amount=100,
                currency="INR",
                duration_days=30,
                created_by= UUID("11111111-1111-1111-1111-111111111111"),
            )
        self.session.rollback.assert_awaited_once()

    # -------------------------------------------------------------------------
    # update_order
    # -------------------------------------------------------------------------

    async def test_update_order_success(self):
        mock_order = MagicMock(spec=Order)
        mock_order.id = 101
        mock_result = MagicMock()
        mock_result.scalars.return_value.first.return_value = mock_order
        self.session.execute = AsyncMock(return_value=mock_result)
        self.session.commit = AsyncMock()
        self.session.refresh = AsyncMock()
        updated = await self.order_repo.update_order(
            101, {"amount": 999, "currency": "USD"}, user_id= UUID("22222222-2222-2222-2222-222222222222")
        )
        assert updated == mock_order
        assert mock_order.amount == 999

    async def test_update_order_not_found(self):
        mock_result = MagicMock()
        mock_result.scalars.return_value.first.return_value = None
        self.session.execute = AsyncMock(return_value=mock_result)
        with pytest.raises(OrderNotFoundError):
            await self.order_repo.update_order(555, {"status": "X"}, user_id= UUID("11111111-1111-1111-1111-111111111111"))

    async def test_update_order_failure(self):
        mock_order = MagicMock(spec=Order)
        mock_result = MagicMock()
        mock_result.scalars.return_value.first.return_value = mock_order
        self.session.execute = AsyncMock(return_value=mock_result)
        self.session.commit = AsyncMock(side_effect=Exception("commit fail"))
        self.session.rollback = AsyncMock()
        with pytest.raises(Exception):
            await self.order_repo.update_order(10, {"amount": 123}, user_id= UUID("11111111-1111-1111-1111-111111111111"))
        self.session.rollback.assert_awaited_once()

    # -------------------------------------------------------------------------
    # update_order_if_not_finalized
    # -------------------------------------------------------------------------

    async def test_update_order_if_not_finalized_success(self):
        mock_order = MagicMock(spec=Order)
        mock_order.id = 101

        update_result = MagicMock()
        update_result.rowcount = 1

        select_result = MagicMock()
        select_result.scalars.return_value.first.return_value = mock_order

        self.session.execute = AsyncMock(side_effect=[update_result, select_result])
        self.session.commit = AsyncMock()

        updated = await self.order_repo.update_order_if_not_finalized(
            101, {"status": PaymentStatusEnum.SUCCESS}, user_id= UUID("22222222-2222-2222-2222-222222222222")
        )

        assert updated == mock_order
        assert self.session.execute.await_count == 2

    async def test_update_order_if_not_finalized_lost_race_returns_none(self):
        """Another concurrent call already finalized the order first: the
        WHERE clause matches zero rows, so this must return None instead of
        re-fetching/re-provisioning."""
        update_result = MagicMock()
        update_result.rowcount = 0

        self.session.execute = AsyncMock(return_value=update_result)
        self.session.commit = AsyncMock()

        updated = await self.order_repo.update_order_if_not_finalized(
            101, {"status": PaymentStatusEnum.SUCCESS}, user_id= UUID("22222222-2222-2222-2222-222222222222")
        )

        assert updated is None
        # Lost the race: no need to re-select the row.
        assert self.session.execute.await_count == 1

    async def test_update_order_if_not_finalized_failure(self):
        self.session.execute = AsyncMock(side_effect=Exception("db error"))
        self.session.rollback = AsyncMock()

        with pytest.raises(Exception):
            await self.order_repo.update_order_if_not_finalized(
                101, {"status": PaymentStatusEnum.SUCCESS}, user_id= UUID("22222222-2222-2222-2222-222222222222")
            )

        self.session.rollback.assert_awaited_once()

    # -------------------------------------------------------------------------
    # get_order_by_id
    # -------------------------------------------------------------------------

    async def test_get_order_by_id_success(self):
        mock_order = MagicMock(spec=Order)
        mock_result = MagicMock()
        mock_result.scalars.return_value.first.return_value = mock_order
        self.session.execute = AsyncMock(return_value=mock_result)
        result = await self.order_repo.get_order_by_id(1)
        assert result == mock_order

    async def test_get_order_by_id_not_found(self):
        mock_result = MagicMock()
        mock_result.scalars.return_value.first.return_value = None
        self.session.execute = AsyncMock(return_value=mock_result)
        with pytest.raises(OrderNotFoundError, match="1"):
            await self.order_repo.get_order_by_id(1)

    async def test_get_order_by_id_exception(self):
        self.session.execute = AsyncMock(side_effect=Exception("DB error"))
        with pytest.raises(Exception):
            await self.order_repo.get_order_by_id(1)
        self.mock_logger.error.assert_called()

    # -------------------------------------------------------------------------
    # get_latest_order_by_partner
    # -------------------------------------------------------------------------

    async def test_get_latest_order_by_partner_found(self):
        mock_order = MagicMock(spec=Order)
        mock_result = MagicMock()
        mock_result.scalars.return_value.first.return_value = mock_order
        self.session.execute = AsyncMock(return_value=mock_result)
        result = await self.order_repo.get_latest_order_by_partner(1)
        assert result == mock_order

    async def test_get_latest_order_by_partner_none(self):
        mock_result = MagicMock()
        mock_result.scalars.return_value.first.return_value = None
        self.session.execute = AsyncMock(return_value=mock_result)
        result = await self.order_repo.get_latest_order_by_partner(999)
        assert result is None

    async def test_get_latest_order_by_partner_exception(self):
        self.session.execute = AsyncMock(side_effect=Exception("DB fail"))
        with pytest.raises(Exception):
            await self.order_repo.get_latest_order_by_partner(1)
        self.mock_logger.error.assert_called()

    # -------------------------------------------------------------------------
    # get_order_by_merchant_transaction_id
    # -------------------------------------------------------------------------

    async def test_get_order_by_merchant_transaction_id_found(self):
        mock_order = MagicMock(spec=Order)
        mock_result = MagicMock()
        mock_result.scalars.return_value.first.return_value = mock_order
        self.session.execute = AsyncMock(return_value=mock_result)
        assert (
            await self.order_repo.get_order_by_merchant_transaction_id("TX123")
            == mock_order
        )

    async def test_get_order_by_merchant_transaction_id_not_found(self):
        mock_result = MagicMock()
        mock_result.scalars.return_value.first.return_value = None
        self.session.execute = AsyncMock(return_value=mock_result)
        with pytest.raises(OrderNotFoundError):
            await self.order_repo.get_order_by_merchant_transaction_id("TX999")

    async def test_get_order_by_merchant_transaction_id_unexpected_error(self):
        self.session.execute = AsyncMock(side_effect=Exception("Unexpected"))
        self.session.rollback = AsyncMock()
        with pytest.raises(Exception):
            await self.order_repo.get_order_by_merchant_transaction_id("BAD")
        self.session.rollback.assert_awaited_once()

    # -------------------------------------------------------------------------
    # _build_order_conditions — filter branches
    # -------------------------------------------------------------------------

    async def test_get_order_history_with_partner_ids_filter(self):
        mock_order = self._make_mock_order()
        order_data_list, total_count = await self._run_order_history(
            {"partner_ids": [UUID("11111111-1111-1111-1111-111111111111"), UUID("22222222-2222-2222-2222-222222222222")]}, [mock_order]
        )
        assert total_count == 1

    async def test_get_order_history_with_source_filter(self):
        mock_order = self._make_mock_order()
        order_data_list, total = await self._run_order_history(
            {"source": "mobile"}, [mock_order]
        )
        assert total == 1

    async def test_get_order_history_with_status_filter(self):
        mock_order = self._make_mock_order()
        order_data_list, total = await self._run_order_history(
            {"status": "completed"}, [mock_order]
        )
        assert total == 1

    async def test_get_order_history_with_order_created_at_filters(self):
        mock_order = self._make_mock_order()
        filters = {
            "order_created_at_from": datetime(2024, 1, 1),
            "order_created_at_to": datetime(2024, 12, 31),
        }
        order_data_list, total = await self._run_order_history(filters, [mock_order])
        assert total == 1

    async def test_get_order_history_with_all_entitlement_date_filters(self):
        mock_order = self._make_mock_order()
        filters = {
            "entitlement_start_date_from": datetime(2024, 1, 1),
            "entitlement_start_date_to": datetime(2024, 6, 30),
            "entitlement_end_date_from": datetime(2024, 2, 1),
            "entitlement_end_date_to": datetime(2024, 7, 31),
        }
        order_data_list, total = await self._run_order_history(filters, [mock_order])
        assert total == 1

    async def test_get_order_history_with_is_manually_created_true(self):
        mock_order = self._make_mock_order()
        order_data_list, total = await self._run_order_history(
            {"is_manually_created": True}, [mock_order]
        )
        assert total == 1

    async def test_get_order_history_with_is_manually_created_false(self):
        mock_order = self._make_mock_order()
        order_data_list, total = await self._run_order_history(
            {"is_manually_created": False}, [mock_order]
        )
        assert total == 1

    # -------------------------------------------------------------------------
    # _build_order_type_condition — all 4 operators
    # -------------------------------------------------------------------------

    def test_build_order_type_condition_eq(self):
        cond = self.order_repo._build_order_type_condition(
            {"op": "eq", "values": [OrderType.FRESH]}
        )
        assert cond is not None

    def test_build_order_type_condition_ne(self):
        cond = self.order_repo._build_order_type_condition(
            {"op": "ne", "values": [OrderType.FRESH]}
        )
        assert cond is not None

    def test_build_order_type_condition_in(self):
        cond = self.order_repo._build_order_type_condition(
            {"op": "in", "values": [OrderType.FRESH, OrderType.RENEWAL]}
        )
        assert cond is not None

    def test_build_order_type_condition_not_in(self):
        cond = self.order_repo._build_order_type_condition(
            {"op": "not_in", "values": [OrderType.UPGRADE, OrderType.DOWNGRADE]}
        )
        assert cond is not None

    def test_build_order_type_condition_defaults_to_eq(self):
        # Missing "op" key should default to eq
        cond = self.order_repo._build_order_type_condition(
            {"values": [OrderType.RENEWAL]}
        )
        assert cond is not None

    async def test_get_order_history_with_order_type_eq_filter(self):
        mock_order = self._make_mock_order()
        filters = {"order_type": {"op": "eq", "values": [OrderType.FRESH]}}
        order_data_list, total = await self._run_order_history(filters, [mock_order])
        assert total == 1

    async def test_get_order_history_with_order_type_in_filter(self):
        mock_order = self._make_mock_order()
        filters = {
            "order_type": {"op": "in", "values": [OrderType.FRESH, OrderType.RENEWAL]}
        }
        order_data_list, total = await self._run_order_history(filters, [mock_order])
        assert total == 1

    async def test_get_order_history_with_order_type_ne_filter(self):
        mock_order = self._make_mock_order()
        filters = {"order_type": {"op": "ne", "values": [OrderType.UPGRADE]}}
        order_data_list, total = await self._run_order_history(filters, [mock_order])
        assert total == 1

    async def test_get_order_history_with_order_type_not_in_filter(self):
        mock_order = self._make_mock_order()
        filters = {"order_type": {"op": "not_in", "values": [OrderType.DOWNGRADE]}}
        order_data_list, total = await self._run_order_history(filters, [mock_order])
        assert total == 1

    # -------------------------------------------------------------------------
    # get_order_history — edge cases
    # -------------------------------------------------------------------------

    async def test_get_order_history_no_filters(self):
        mock_order = self._make_mock_order(
            order_id= UUID("33333333-3333-3333-3333-333333333333"),
            partner_id= UUID("33333333-3333-3333-3333-333333333333"),
            partner=MagicMock(spec=Partner),
            plan=MagicMock(spec=Plan),
            payment=MagicMock(spec=Payment),
        )
        order_data_list, total = await self._run_order_history({}, [mock_order])
        assert total == 1

    async def test_get_order_history_no_pagination(self):
        mock_order = self._make_mock_order(
            partner=MagicMock(spec=Partner),
            plan=MagicMock(spec=Plan),
            payment=MagicMock(spec=Payment),
        )
        order_data_list, total = await self._run_order_history(
            {}, [mock_order], limit=None, offset=None
        )
        assert total == 1

    async def test_get_order_history_no_orders_found(self):
        mock_count_result = MagicMock()
        mock_count_result.scalar.return_value = 0
        mock_result = MagicMock()
        mock_result.unique.return_value.scalars.return_value.all.return_value = []
        self.session.execute = AsyncMock(side_effect=[mock_count_result, mock_result])
        order_data_list, total = await self.order_repo.get_order_history(
            filters={}, limit=10, offset=1
        )
        assert total == 0
        assert len(order_data_list) == 0

    async def test_get_order_history_count_returns_none(self):
        mock_order = self._make_mock_order(
            partner=MagicMock(spec=Partner),
            plan=MagicMock(spec=Plan),
            payment=MagicMock(spec=Payment),
        )
        mock_count_result = MagicMock()
        mock_count_result.scalar.return_value = None
        mock_result = MagicMock()
        mock_result.unique.return_value.scalars.return_value.all.return_value = [
            mock_order
        ]
        mock_ent_result = MagicMock()
        mock_ent_result.scalars.return_value.all.return_value = []
        mock_admin_result = MagicMock()
        mock_admin_result.unique.return_value.scalars.return_value.all.return_value = []
        self.session.execute = AsyncMock(
            side_effect=[
                mock_count_result,
                mock_result,
                mock_ent_result,
                mock_admin_result,
            ]
        )
        order_data_list, total = await self.order_repo.get_order_history(
            filters={}, limit=10, offset=1
        )
        assert total == 0
        assert len(order_data_list) == 1

    async def test_get_order_history_exception(self):
        self.session.execute = AsyncMock(side_effect=Exception("Database error"))
        with pytest.raises(Exception, match="Database error"):
            await self.order_repo.get_order_history(filters={}, limit=10, offset=1)
        assert self.mock_logger.error.called

    # -------------------------------------------------------------------------
    # Partner location priority
    # -------------------------------------------------------------------------

    async def test_get_partner_location_billing_address(self):
        mock_billing = MagicMock()
        mock_billing.address_type = AddressType.BILLING
        mock_billing.city, mock_billing.state, mock_billing.country = (
            "Mumbai",
            "Maharashtra",
            "India",
        )
        mock_partner = MagicMock(spec=Partner)
        mock_partner.id = 1
        mock_partner.name = "P"
        mock_partner.gst_no = "G"
        mock_partner.is_active = True
        mock_partner.addresses = [mock_billing]
        mock_order = self._make_mock_order(partner=mock_partner)
        order_data_list, _ = await self._run_order_history(
            {"partner_ids": [UUID("11111111-1111-1111-1111-111111111111")]}, [mock_order]
        )
        assert order_data_list[0]["partner"]["city"] == "Mumbai"

    async def test_get_partner_location_communication_and_billing(self):
        mock_addr = MagicMock()
        mock_addr.address_type = AddressType.COMMUNICATION_AND_BILLING
        mock_addr.city, mock_addr.state, mock_addr.country = (
            "Pune",
            "Maharashtra",
            "India",
        )
        mock_partner = MagicMock(spec=Partner)
        mock_partner.id = 1
        mock_partner.name = "P"
        mock_partner.gst_no = "G"
        mock_partner.is_active = True
        mock_partner.addresses = [mock_addr]
        mock_order = self._make_mock_order(partner=mock_partner)
        order_data_list, _ = await self._run_order_history(
            {"partner_ids": [UUID("11111111-1111-1111-1111-111111111111")]}, [mock_order]
        )
        assert order_data_list[0]["partner"]["city"] == "Pune"

    async def test_get_partner_location_communication(self):
        mock_addr = MagicMock()
        mock_addr.address_type = AddressType.COMMUNICATION
        mock_addr.city, mock_addr.state, mock_addr.country = (
            "Nagpur",
            "Maharashtra",
            "India",
        )
        mock_partner = MagicMock(spec=Partner)
        mock_partner.id = 1
        mock_partner.name = "P"
        mock_partner.gst_no = "G"
        mock_partner.is_active = True
        mock_partner.addresses = [mock_addr]
        mock_order = self._make_mock_order(partner=mock_partner)
        order_data_list, _ = await self._run_order_history(
            {"partner_ids": [UUID("11111111-1111-1111-1111-111111111111")]}, [mock_order]
        )
        assert order_data_list[0]["partner"]["city"] == "Nagpur"

    async def test_get_partner_location_no_matching_address(self):
        mock_partner = MagicMock(spec=Partner)
        mock_partner.id = 1
        mock_partner.name = "P"
        mock_partner.gst_no = "G"
        mock_partner.is_active = True
        mock_partner.addresses = []
        mock_order = self._make_mock_order(partner=mock_partner)
        order_data_list, _ = await self._run_order_history(
            {"partner_ids": [UUID("11111111-1111-1111-1111-111111111111")]}, [mock_order]
        )
        assert order_data_list[0]["partner"]["city"] is None

    # -------------------------------------------------------------------------
    # Entitlement is_active logic
    # -------------------------------------------------------------------------

    async def test_map_entitlement_is_active_true(self):
        fixed_now = datetime(2024, 5, 15).timestamp() * 1000
        mock_ent = MagicMock(spec=Entitlement)
        mock_ent.order_id= UUID("11111111-1111-1111-1111-111111111111")
        mock_ent.start_date = datetime(2024, 5, 1).timestamp() * 1000
        mock_ent.end_date = datetime(2024, 5, 31).timestamp() * 1000
        mock_ent.is_active = True
        mock_order = self._make_mock_order()
        with patch(
            "src.components.common.datetime.DateTimeUtil.get_current_time",
            return_value=fixed_now,
        ):
            order_data_list, _ = await self._run_order_history(
                {"partner_ids": [UUID("11111111-1111-1111-1111-111111111111")]}, [mock_order], entitlements=[mock_ent]
            )
        assert order_data_list[0]["entitlement"]["is_active"] is True

    async def test_map_entitlement_end_date_none(self):
        mock_ent = MagicMock(spec=Entitlement)
        mock_ent.order_id= UUID("11111111-1111-1111-1111-111111111111")
        mock_ent.start_date = datetime(2024, 5, 1).timestamp() * 1000
        mock_ent.end_date = None
        mock_ent.is_active = True
        mock_order = self._make_mock_order()
        order_data_list, _ = await self._run_order_history(
            {"partner_ids": [UUID("11111111-1111-1111-1111-111111111111")]}, [mock_order], entitlements=[mock_ent]
        )
        assert order_data_list[0]["entitlement"]["is_active"] is False

    async def test_map_entitlement_is_active_false_on_model(self):
        fixed_now = datetime(2024, 5, 15).timestamp() * 1000
        mock_ent = MagicMock(spec=Entitlement)
        mock_ent.order_id= UUID("11111111-1111-1111-1111-111111111111")
        mock_ent.start_date = datetime(2024, 5, 1).timestamp() * 1000
        mock_ent.end_date = datetime(2024, 5, 31).timestamp() * 1000
        mock_ent.is_active = False
        mock_order = self._make_mock_order()
        with patch(
            "src.components.common.datetime.DateTimeUtil.get_current_time",
            return_value=fixed_now,
        ):
            order_data_list, _ = await self._run_order_history(
                {"partner_ids": [UUID("11111111-1111-1111-1111-111111111111")]}, [mock_order], entitlements=[mock_ent]
            )
        assert order_data_list[0]["entitlement"]["is_active"] is False

    async def test_map_admin_user_with_location(self):
        mock_order = self._make_mock_order(
            order_id= UUID("20202020-2020-2020-2020-202020202020"),
            partner_id= UUID("66666666-6666-6666-6666-666666666666"),
            partner=MagicMock(spec=Partner),
            plan=MagicMock(spec=Plan),
            payment=MagicMock(spec=Payment),
        )
        mock_admin = MagicMock(spec=User)
        mock_admin.partner_id= UUID("66666666-6666-6666-6666-666666666666")
        mock_admin.email = "admin@p.com"
        mock_admin.phone_number = "+91"
        mock_admin.country = None
        mock_admin.state = None
        mock_admin.city = None
        order_data_list, _ = await self._run_order_history(
            {"partner_ids": [UUID("66666666-6666-6666-6666-666666666666")]}, [mock_order], admin_users=[mock_admin]
        )
        assert order_data_list[0]["admin_user"]["country"] is None

    # -------------------------------------------------------------------------
    # expire_pending_orders_before
    # -------------------------------------------------------------------------

    async def test_expire_pending_orders_success_with_updates(self):
        mock_result = MagicMock()
        mock_result.rowcount = 5
        self.session.execute = AsyncMock(return_value=mock_result)
        self.session.commit = AsyncMock()
        count = await self.order_repo.expire_pending_orders_before(1704067200000)
        assert count == 5
        self.session.commit.assert_awaited_once()

    async def test_expire_pending_orders_success_no_updates(self):
        mock_result = MagicMock()
        mock_result.rowcount = 0
        self.session.execute = AsyncMock(return_value=mock_result)
        self.session.commit = AsyncMock()
        count = await self.order_repo.expire_pending_orders_before(1704067200000)
        assert count == 0
        debug_calls = [
            c for c in self.mock_logger.debug.call_args_list if "No pending" in str(c)
        ]
        assert len(debug_calls) >= 1

    async def test_expire_pending_orders_rowcount_none(self):
        mock_result = MagicMock()
        mock_result.rowcount = None
        self.session.execute = AsyncMock(return_value=mock_result)
        self.session.commit = AsyncMock()
        count = await self.order_repo.expire_pending_orders_before(1704067200000)
        assert count == 0

    async def test_expire_pending_orders_sqlalchemy_error(self):
        self.session.execute = AsyncMock(side_effect=SQLAlchemyError("DB conn error"))
        self.session.rollback = AsyncMock()
        with pytest.raises(SQLAlchemyError):
            await self.order_repo.expire_pending_orders_before(1704067200000)
        self.session.rollback.assert_awaited_once()
        error_calls = [
            c for c in self.mock_logger.error.call_args_list if "bulk-expire" in str(c)
        ]
        assert len(error_calls) >= 1
        assert error_calls[0].kwargs.get("exc_info") is True

    async def test_expire_pending_orders_commit_failure(self):
        mock_result = MagicMock()
        mock_result.rowcount = 10
        self.session.execute = AsyncMock(return_value=mock_result)
        self.session.commit = AsyncMock(side_effect=SQLAlchemyError("Commit failed"))
        self.session.rollback = AsyncMock()
        with pytest.raises(SQLAlchemyError):
            await self.order_repo.expire_pending_orders_before(1704067200000)
        self.session.rollback.assert_awaited_once()

    async def test_expire_pending_orders_various_cutoffs(self):
        for cutoff in [0, 1704067200000, 9999999999999]:
            mock_result = MagicMock()
            mock_result.rowcount = 1
            self.session.execute = AsyncMock(return_value=mock_result)
            self.session.commit = AsyncMock()
            count = await self.order_repo.expire_pending_orders_before(cutoff)
            assert count == 1

    @pytest.mark.asyncio
    async def test_get_report_for_created_orders_manual(self):
        current_ts = 1000000000

        mock_row = MagicMock()
        mock_row._mapping = {
            "partner_id": 1,
            "partner": "Test Partner",
            "plan_name": "Growth",
            "plan_type": "MONTHLY",
            "order_type": "FRESH",
            "order_source": "CONSOLE",
            "amount": 1000,
        }

        execute_result = MagicMock()
        execute_result.fetchall.return_value = [mock_row]

        self.session.execute.return_value = execute_result

        result = await self.order_repo.get_report_for_created_orders(
            current_ts=current_ts,
            is_manually_created=True,
        )

        assert len(result) == 1
        assert result[0]["partner"] == "Test Partner"
        assert result[0]["amount"] == 1000
        assert "payment_method" not in result[0]


    @pytest.mark.asyncio
    async def test_get_report_for_created_orders_non_manual(self):
        current_ts = 1000000000

        mock_row = MagicMock()
        mock_row._mapping = {
            "partner_id": 1,
            "partner": "Test Partner",
            "plan_name": "Growth",
            "plan_type": "MONTHLY",
            "order_type": "FRESH",
            "order_source": "CONSOLE",
            "amount": 1000,
            "payment_method": "GATEWAY",
            "payment_status": "SUCCESS",
        }

        execute_result = MagicMock()
        execute_result.fetchall.return_value = [mock_row]

        self.session.execute.return_value = execute_result

        result = await self.order_repo.get_report_for_created_orders(
            current_ts=current_ts,
            is_manually_created=False,
        )

        assert len(result) == 1
        assert result[0]["payment_method"] == "GATEWAY"
        assert result[0]["payment_status"] == "SUCCESS"


    @pytest.mark.asyncio
    async def test_get_report_for_created_orders_empty_result(self):
        execute_result = MagicMock()
        execute_result.fetchall.return_value = []

        self.session.execute.return_value = execute_result

        result = await self.order_repo.get_report_for_created_orders(
            current_ts=1000000000,
            is_manually_created=True,
        )

        assert result == []


    @pytest.mark.asyncio
    async def test_get_approaching_renewal_report_success(self):
        mock_row = MagicMock()
        mock_row._mapping = {
            "partner": "Partner A",
            "plan_name": "Premium",
            "plan_type": "YEARLY",
            "order_id": 101,
            "order_type": "RENEWAL",
            "order_source": "CONSOLE",
            "payment_method": "GATEWAY",
            "amount": 5000,
            "start_date": 1000,
            "end_date": 2000,
        }

        execute_result = MagicMock()
        execute_result.fetchall.return_value = [mock_row]

        self.session.execute.return_value = execute_result

        result = await self.order_repo.get_approaching_renewal_report(
            current_ts=1000,
        )

        assert len(result) == 1
        assert result[0]["partner"] == "Partner A"
        assert result[0]["order_id"] == 101
        assert result[0]["end_date"] == 2000


    @pytest.mark.asyncio
    async def test_get_approaching_renewal_report_empty(self):
        execute_result = MagicMock()
        execute_result.fetchall.return_value = []

        self.session.execute.return_value = execute_result

        result = await self.order_repo.get_approaching_renewal_report(
            current_ts=1000,
        )

        assert result == []


    @pytest.mark.asyncio
    async def test_get_expired_and_overdue_report_expired(self):
        current_ts = 10 * 24 * 60 * 60 * 1000

        mock_row = MagicMock()
        mock_row._mapping = {
            "partner": "Partner A",
            "plan_name": "Growth",
            "plan_type": "MONTHLY",
            "order_id": 101,
            "order_type": "FRESH",
            "amount": 1500,
            "end_date": current_ts - (2 * 24 * 60 * 60 * 1000),
            "subscription_status": "EXPIRED",
        }

        execute_result = MagicMock()
        execute_result.fetchall.return_value = [mock_row]

        self.session.execute.return_value = execute_result

        result = await self.order_repo.get_expired_and_overdue_report(
            current_ts=current_ts,
        )

        assert len(result) == 1
        assert result[0]["subscription_status"] == "EXPIRED"
        assert result[0]["days_since_expiry"] == 2


    @pytest.mark.asyncio
    async def test_get_expired_and_overdue_report_overdue(self):
        current_ts = 20 * 24 * 60 * 60 * 1000

        mock_row = MagicMock()
        mock_row._mapping = {
            "partner": "Partner B",
            "plan_name": "Enterprise",
            "plan_type": "YEARLY",
            "order_id": 202,
            "order_type": "RENEWAL",
            "amount": 10000,
            "end_date": current_ts - (10 * 24 * 60 * 60 * 1000),
            "subscription_status": "OVERDUE",
        }

        execute_result = MagicMock()
        execute_result.fetchall.return_value = [mock_row]

        self.session.execute.return_value = execute_result

        result = await self.order_repo.get_expired_and_overdue_report(
            current_ts=current_ts,
        )

        assert len(result) == 1
        assert result[0]["subscription_status"] == "OVERDUE"
        assert result[0]["days_since_expiry"] == 10


    @pytest.mark.asyncio
    async def test_get_expired_and_overdue_report_empty(self):
        execute_result = MagicMock()
        execute_result.fetchall.return_value = []

        self.session.execute.return_value = execute_result

        result = await self.order_repo.get_expired_and_overdue_report(
            current_ts=1000,
        )

        assert result == []

