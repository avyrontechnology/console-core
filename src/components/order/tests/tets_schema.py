from uuid import UUID
import pytest
from pydantic import ValidationError

from src.components.order.constants import OrderSource, OrderType, PaymentMethod
from src.components.order.schema import (
    ManualOrderCreateRequest,
    OrderBase,
    OrderBillingDetailsRequest,
    OrderHistoryItemResponse,
    OrderHistoryPaginatedResponse,
    OrderValidateRequest,
)
from src.components.plan.constants import PlanCustomLimitKeys
from src.components.wallet.enum import Currency

# ============================================================================
# OrderBase
# ============================================================================


def test_order_base_valid():
    order = OrderBase(
        plan_id= UUID("11111111-1111-1111-1111-111111111111"),
        add_ons={},
        amount=100.0,
        currency=Currency.INDIA,
        source=OrderSource.CONSOLE,
    )
    assert order.plan_id== UUID("11111111-1111-1111-1111-111111111111")
    assert order.amount == 100.0
    assert order.source == OrderSource.CONSOLE


def test_order_base_add_ons_only_valid():
    order = OrderBase(
        plan_id=None,
        add_ons={"SERVICE_BOARDS": 5},
        amount=100.0,
        currency=Currency.INDIA,
        source=OrderSource.CONSOLE,
    )
    assert order.add_ons["SERVICE_BOARDS"] == 5


def test_order_base_missing_plan_and_addons():
    with pytest.raises(ValidationError) as exc:
        OrderBase(
            plan_id=None,
            add_ons={},
            amount=100.0,
            currency=Currency.INDIA,
            source=OrderSource.CONSOLE,
        )
    assert "Either plan_id or add_ons is required" in str(exc.value)


def test_order_base_invalid_add_on_value_not_integer():
    with pytest.raises(ValidationError) as exc:
        OrderBase(
            plan_id=None,
            add_ons={"SERVICE_BOARDS": "invalid"},
            amount=100.0,
            currency=Currency.INDIA,
            source=OrderSource.CONSOLE,
        )
    assert "Add-on value for 'SERVICE_BOARDS' must be integer" in str(exc.value)


def test_order_base_amount_less_than_or_equal_99():
    with pytest.raises(ValidationError) as exc:
        OrderBase(
            plan_id= UUID("11111111-1111-1111-1111-111111111111"),
            add_ons={},
            amount=99.0,
            currency=Currency.INDIA,
            source=OrderSource.CONSOLE,
        )
    assert "Amount must be greater than 99" in str(exc.value)


def test_order_base_amount_exactly_50():
    with pytest.raises(ValidationError) as exc:
        OrderBase(
            plan_id= UUID("11111111-1111-1111-1111-111111111111"),
            add_ons={},
            amount=50.0,
            currency=Currency.INDIA,
            source=OrderSource.CONSOLE,
        )
    assert "Amount must be greater than 99" in str(exc.value)


def test_order_base_missing_source():
    with pytest.raises(ValidationError) as exc:
        OrderBase(
            plan_id= UUID("11111111-1111-1111-1111-111111111111"), add_ons={}, amount=100.0, currency=Currency.INDIA, source=None
        )
    assert "source field required" in str(exc.value)


def test_order_base_invalid_source():
    with pytest.raises(ValidationError) as exc:
        OrderBase(
            plan_id= UUID("11111111-1111-1111-1111-111111111111"),
            add_ons={},
            amount=100.0,
            currency=Currency.INDIA,
            source="INVALID_SOURCE",
        )
    assert "invalid source: INVALID_SOURCE" in str(exc.value)


def test_order_base_invalid_addon_key():
    with pytest.raises(ValidationError) as exc:
        OrderBase(
            plan_id=None,
            add_ons={"INVALID_KEY": 5},
            amount=100.0,
            currency=Currency.INDIA,
            source=OrderSource.CONSOLE,
        )
    assert "Invalid limit key 'INVALID_KEY'" in str(exc.value)


def test_order_base_addon_value_zero():
    with pytest.raises(ValidationError) as exc:
        OrderBase(
            plan_id=None,
            add_ons={"SERVICE_BOARDS": 0},
            amount=100.0,
            currency=Currency.INDIA,
            source=OrderSource.CONSOLE,
        )
    assert "must be a positive/negative integer" in str(exc.value)


def test_order_base_addon_negative_value_valid():
    order = OrderBase(
        plan_id=None,
        add_ons={"SERVICE_BOARDS": -5},
        amount=100.0,
        currency=Currency.INDIA,
        source=OrderSource.CONSOLE,
    )
    assert order.add_ons["SERVICE_BOARDS"] == -5


# ============================================================================
# OrderBillingDetailsRequest
# ============================================================================


def test_order_billing_details_valid_plan_and_addons():
    request = OrderBillingDetailsRequest(
        plan_id= UUID("11111111-1111-1111-1111-111111111111"), add_ons={"SERVICE_BOARDS": 2}, coupon="SAVE10"
    )
    assert request.plan_id== UUID("11111111-1111-1111-1111-111111111111")
    assert request.coupon == "SAVE10"


def test_order_billing_details_add_ons_only_valid():
    request = OrderBillingDetailsRequest(plan_id=None, add_ons={"SERVICE_BOARDS": 3})
    assert request.add_ons["SERVICE_BOARDS"] == 3


def test_order_billing_details_plan_only_valid():
    request = OrderBillingDetailsRequest(plan_id= UUID("11111111-1111-1111-1111-111111111111"), add_ons={})
    assert request.plan_id== UUID("11111111-1111-1111-1111-111111111111")


def test_order_billing_details_missing_plan_and_addons():
    with pytest.raises(ValidationError) as exc:
        OrderBillingDetailsRequest(plan_id=None, add_ons={})
    assert "Either plan_id or add_ons must be provided" in str(exc.value)


def test_order_billing_details_invalid_addon_key():
    with pytest.raises(ValidationError) as exc:
        OrderBillingDetailsRequest(plan_id=None, add_ons={"INVALID_KEY": 3})
    assert "Invalid limit key 'INVALID_KEY'" in str(exc.value)


def test_order_billing_details_addon_value_zero():
    with pytest.raises(ValidationError) as exc:
        OrderBillingDetailsRequest(plan_id=None, add_ons={"SERVICE_BOARDS": 0})
    assert "must be a positive integer" in str(exc.value)


def test_order_billing_details_addon_negative_value():
    with pytest.raises(ValidationError) as exc:
        OrderBillingDetailsRequest(plan_id=None, add_ons={"SERVICE_BOARDS": -1})
    assert "must be a positive integer" in str(exc.value)


def test_order_billing_details_addon_non_integer():
    with pytest.raises(ValidationError) as exc:
        OrderBillingDetailsRequest(plan_id=None, add_ons={"SERVICE_BOARDS": "invalid"})
    assert "validation error" in str(exc.value).lower()


# ============================================================================
# OrderValidateRequest
# ============================================================================


def test_order_validate_request_valid():
    request = OrderValidateRequest(
        order_id="order_001", payment_id="pay_001", signature="sig_123"
    )
    assert request.order_id == "order_001"


def test_order_validate_request_missing_fields():
    with pytest.raises(ValidationError):
        OrderValidateRequest(order_id="", payment_id="pay_001", signature="sig_123")


# ============================================================================
# ManualOrderCreateRequest.validate_payload
# ============================================================================


def test_manual_order_validate_payload_success_no_addons():
    req = ManualOrderCreateRequest(
        partner_id= UUID("11111111-1111-1111-1111-111111111111"), plan_id= UUID("22222222-2222-2222-2222-222222222222"), amount=500, payment_method=PaymentMethod.GATEWAY
    )
    validated, error = req.validate_payload()
    assert error is None
    assert validated["partner_id"] == 1
    assert validated["plan_id"] == 2
    assert validated["amount"] == 500
    assert validated["payment_method"] == PaymentMethod.GATEWAY
    assert validated["add_ons"] == {}


def test_manual_order_validate_payload_success_with_valid_addons():
    req = ManualOrderCreateRequest(
        partner_id= UUID("11111111-1111-1111-1111-111111111111"),
        plan_id= UUID("22222222-2222-2222-2222-222222222222"),
        amount=1000,
        payment_method=PaymentMethod.DIRECT,
        add_ons={PlanCustomLimitKeys.Console.ACTIVE_USERS: 3},
    )
    validated, error = req.validate_payload()
    assert error is None
    assert validated["add_ons"][PlanCustomLimitKeys.Console.ACTIVE_USERS] == 3


def test_manual_order_validate_payload_success_with_currency():
    req = ManualOrderCreateRequest(
        partner_id= UUID("11111111-1111-1111-1111-111111111111"),
        plan_id= UUID("22222222-2222-2222-2222-222222222222"),
        amount=500,
        payment_method=PaymentMethod.GATEWAY,
        currency="INR",
    )
    validated, error = req.validate_payload()
    assert error is None
    assert validated["currency"] == "INR"


def test_manual_order_validate_payload_error_missing_partner_id():
    req = ManualOrderCreateRequest(
        partner_id=None, plan_id= UUID("22222222-2222-2222-2222-222222222222"), amount=500, payment_method=PaymentMethod.GATEWAY
    )
    validated, error = req.validate_payload()
    assert error is not None
    assert "partner_id" in error
    assert validated == {}


def test_manual_order_validate_payload_error_partner_id_zero():
    req = ManualOrderCreateRequest(
        partner_id= UUID("00000000-0000-0000-0000-000000000000"), plan_id= UUID("22222222-2222-2222-2222-222222222222"), amount=500, payment_method=PaymentMethod.GATEWAY
    )
    validated, error = req.validate_payload()
    assert error is not None
    assert validated == {}


def test_manual_order_validate_payload_error_missing_plan_id():
    req = ManualOrderCreateRequest(
        partner_id= UUID("11111111-1111-1111-1111-111111111111"), plan_id=None, amount=500, payment_method=PaymentMethod.GATEWAY
    )
    validated, error = req.validate_payload()
    assert error is not None
    assert "plan_id" in error


def test_manual_order_validate_payload_error_amount_too_low():
    req = ManualOrderCreateRequest(
        partner_id= UUID("11111111-1111-1111-1111-111111111111"), plan_id= UUID("22222222-2222-2222-2222-222222222222"), amount=50, payment_method=PaymentMethod.GATEWAY
    )
    validated, error = req.validate_payload()
    assert error is not None
    assert "amount" in error


def test_manual_order_validate_payload_error_invalid_payment_method():
    req = ManualOrderCreateRequest(
        partner_id= UUID("11111111-1111-1111-1111-111111111111"), plan_id= UUID("22222222-2222-2222-2222-222222222222"), amount=500, payment_method="CASH"
    )
    validated, error = req.validate_payload()
    assert error is not None
    assert "payment_method" in error


def test_manual_order_validate_payload_error_add_ons_not_dict():
    req = ManualOrderCreateRequest(
        partner_id= UUID("11111111-1111-1111-1111-111111111111"),
        plan_id= UUID("22222222-2222-2222-2222-222222222222"),
        amount=500,
        payment_method=PaymentMethod.GATEWAY,
        add_ons="not_a_dict",
    )
    validated, error = req.validate_payload()
    assert error is not None
    assert "add_ons" in error


def test_manual_order_validate_payload_error_add_ons_invalid_key():
    req = ManualOrderCreateRequest(
        partner_id= UUID("11111111-1111-1111-1111-111111111111"),
        plan_id= UUID("22222222-2222-2222-2222-222222222222"),
        amount=500,
        payment_method=PaymentMethod.GATEWAY,
        add_ons={"INVALID_ADDON_KEY": 1},
    )
    validated, error = req.validate_payload()
    assert error is not None
    assert "Invalid limit key" in error


def test_manual_order_validate_payload_error_add_ons_value_not_positive():
    req = ManualOrderCreateRequest(
        partner_id= UUID("11111111-1111-1111-1111-111111111111"),
        plan_id= UUID("22222222-2222-2222-2222-222222222222"),
        amount=500,
        payment_method=PaymentMethod.GATEWAY,
        add_ons={PlanCustomLimitKeys.Console.ACTIVE_USERS: 0},
    )
    validated, error = req.validate_payload()
    assert error is not None
    assert "positive integer" in error


def test_manual_order_validate_payload_error_add_ons_value_negative():
    req = ManualOrderCreateRequest(
        partner_id= UUID("11111111-1111-1111-1111-111111111111"),
        plan_id= UUID("22222222-2222-2222-2222-222222222222"),
        amount=500,
        payment_method=PaymentMethod.GATEWAY,
        add_ons={PlanCustomLimitKeys.Console.ACTIVE_USERS: -1},
    )
    validated, error = req.validate_payload()
    assert error is not None


def test_manual_order_validate_payload_error_add_ons_key_empty_string():
    req = ManualOrderCreateRequest(
        partner_id= UUID("11111111-1111-1111-1111-111111111111"),
        plan_id= UUID("22222222-2222-2222-2222-222222222222"),
        amount=500,
        payment_method=PaymentMethod.GATEWAY,
        add_ons={"": 1},
    )
    validated, error = req.validate_payload()
    assert error is not None


def test_manual_order_validate_payload_currency_wrong_length():
    req = ManualOrderCreateRequest(
        partner_id= UUID("11111111-1111-1111-1111-111111111111"),
        plan_id= UUID("22222222-2222-2222-2222-222222222222"),
        amount=500,
        payment_method=PaymentMethod.GATEWAY,
        currency="IN",  # too short
    )
    validated, error = req.validate_payload()
    assert error is not None
    assert "currency" in error


def test_manual_order_validate_payload_add_ons_none_becomes_empty_dict():
    req = ManualOrderCreateRequest(
        partner_id= UUID("11111111-1111-1111-1111-111111111111"),
        plan_id= UUID("22222222-2222-2222-2222-222222222222"),
        amount=500,
        payment_method=PaymentMethod.DIRECT,
        add_ons=None,
    )
    validated, error = req.validate_payload()
    assert error is None
    assert validated["add_ons"] == {}


def test_manual_order_validate_payload_string_partner_id_converted():
    """SchemaValidator auto-converts string to int"""
    req = ManualOrderCreateRequest(
        partner_id="5", plan_id="2", amount="500", payment_method=PaymentMethod.GATEWAY
    )
    validated, error = req.validate_payload()
    assert error is None
    assert validated["partner_id"] == 5
    assert validated["plan_id"] == 2
    assert validated["amount"] == 500


# ============================================================================
# OrderHistoryItemResponse
# ============================================================================


def test_order_history_item_response_full():
    response = OrderHistoryItemResponse(
        order_id= UUID("11111111-1111-1111-1111-111111111111"),
        source=OrderSource.CONSOLE,
        order_status="completed",
        order_currency=Currency.INDIA,
        merchant_transaction_id="txn_123",
        duration=12,
        partner_id= UUID("11111111-1111-1111-1111-111111111111"),
        partner_name="Test",
        partner_email="t@e.com",
        partner_phone_number="123",
        partner_country="India",
        partner_state="Delhi",
        partner_city="New Delhi",
        partner_gst_no="GST123",
        partner_is_active=True,
        plan_id= UUID("11111111-1111-1111-1111-111111111111"),
        plan_name="Premium",
        plan_type="SUB",
        plan_duration_months=12,
        duration_in_days=365,
        plan_limits={},
        add_ons={},
        plan_price=1000.0,
        plan_discount_percentage=10.0,
        total_price=900.0,
        order_created_at=1234567890,
        order_created_by=1,
        order_updated_at=1234567900,
        order_updated_by=1,
        entitlement_start_date=1234567890,
        entitlement_end_date=1266103890,
        entitlement_is_active=True,
        payment_gateway="razorpay",
        payment_status="success",
        payment_date=1234567890,
        payment_method="card",
    )
    assert response.order_id== UUID("11111111-1111-1111-1111-111111111111")
    assert response.total_price == 900.0
    assert response.payment_method == "card"


def test_order_history_item_response_payment_method_defaults_none():
    """payment_method is Optional — null for pre-migration rows"""
    response = OrderHistoryItemResponse(
        order_id= UUID("11111111-1111-1111-1111-111111111111"),
        source=OrderSource.CONSOLE,
        order_status="pending",
        order_currency=Currency.INDIA,
        duration=12,
        total_price=500.0,
        order_created_at=1234567890,
        payment_gateway="razorpay",
    )
    assert response.payment_method is None


def test_order_history_item_response_order_type_defaults_fresh():
    response = OrderHistoryItemResponse(
        order_id= UUID("11111111-1111-1111-1111-111111111111"),
        source=OrderSource.CONSOLE,
        order_status="pending",
        order_currency=Currency.INDIA,
        duration=12,
        total_price=500.0,
        order_created_at=1234567890,
        payment_gateway="razorpay",
    )
    assert response.order_type == OrderType.FRESH


def test_order_history_item_response_is_manually_created_defaults_false():
    response = OrderHistoryItemResponse(
        order_id= UUID("11111111-1111-1111-1111-111111111111"),
        source=OrderSource.CONSOLE,
        order_status="pending",
        order_currency=Currency.INDIA,
        duration=12,
        total_price=500.0,
        order_created_at=1234567890,
        payment_gateway="razorpay",
    )
    assert response.is_manually_created is False


def test_order_history_item_response_minimal():
    response = OrderHistoryItemResponse(
        order_id= UUID("11111111-1111-1111-1111-111111111111"),
        source=OrderSource.CONSOLE,
        order_status="pending",
        order_currency=Currency.INDIA,
        duration=12,
        total_price=500.0,
        order_created_at=1234567890,
        payment_gateway="razorpay",
    )
    assert response.partner_id is None
    assert response.plan_id is None


def test_order_history_item_response_all_order_types():
    for ot in (
        OrderType.FRESH,
        OrderType.RENEWAL,
        OrderType.UPGRADE,
        OrderType.DOWNGRADE,
    ):
        response = OrderHistoryItemResponse(
            order_id= UUID("11111111-1111-1111-1111-111111111111"),
            source=OrderSource.CONSOLE,
            order_status="completed",
            order_currency=Currency.INDIA,
            duration=12,
            total_price=100.0,
            order_created_at=1234567890,
            payment_gateway="razorpay",
            order_type=ot,
        )
        assert response.order_type == ot


def test_order_history_item_response_all_payment_methods():
    for pm in (PaymentMethod.GATEWAY, PaymentMethod.DIRECT, None):
        response = OrderHistoryItemResponse(
            order_id= UUID("11111111-1111-1111-1111-111111111111"),
            source=OrderSource.CONSOLE,
            order_status="completed",
            order_currency=Currency.INDIA,
            duration=12,
            total_price=100.0,
            order_created_at=1234567890,
            payment_gateway="razorpay",
            payment_method=pm,
        )
        assert response.payment_method == pm


# ============================================================================
# OrderHistoryPaginatedResponse
# ============================================================================


def test_order_history_paginated_response():
    item = OrderHistoryItemResponse(
        order_id= UUID("11111111-1111-1111-1111-111111111111"),
        source=OrderSource.CONSOLE,
        order_status="completed",
        order_currency=Currency.INDIA,
        duration=12,
        total_price=900.0,
        order_created_at=1234567890,
        payment_gateway="razorpay",
    )
    response = OrderHistoryPaginatedResponse(
        total_count=100, limit=10, offset=1, data=[item]
    )
    assert response.total_count == 100
    assert len(response.data) == 1


def test_order_history_paginated_response_empty():
    response = OrderHistoryPaginatedResponse(total_count=0, limit=10, offset=1, data=[])
    assert response.total_count == 0
    assert len(response.data) == 0
