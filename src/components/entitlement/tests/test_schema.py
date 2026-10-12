from uuid import UUID
from datetime import datetime
from unittest.mock import Mock, patch

import pytest
from pydantic import ValidationError

from src.components.common.datetime import DateTimeUtil
from src.components.entitlement.schema import (
    MAX_INT_32,
    EntitlementCreate,
    EntitlementResponse,
    EntitlementUpdate,
    UpdateEntitlementStartDateRequest,
    UpdateEntitlementStartDateResponse,
)


class TestUpdateEntitlementStartDateRequest:
    """Test UpdateEntitlementStartDateRequest validation."""

    def test_validate_order_id_valid(self):
        """Should accept valid order_id."""
        current_time_ms = int(datetime.now().timestamp() * 1000)
        future_time_ms = current_time_ms + (7 * 24 * 60 * 60 * 1000)  # 7 days future

        with patch.object(
            DateTimeUtil, "get_current_time", return_value=current_time_ms
        ):
            request = UpdateEntitlementStartDateRequest(
                order_id= UUID("12312312-3123-1231-2312-312312312312"), start_date=future_time_ms
            )
            assert request.order_id== UUID("12312312-3123-1231-2312-312312312312")

    def test_validate_order_id_max_value(self):
        """Should accept a UUID string order_id (parsed to UUID)."""
        current_time_ms = int(datetime.now().timestamp() * 1000)
        future_time_ms = current_time_ms + (7 * 24 * 60 * 60 * 1000)

        with patch.object(
            DateTimeUtil, "get_current_time", return_value=current_time_ms
        ):
            request = UpdateEntitlementStartDateRequest(
                order_id="12312312-3123-1231-2312-312312312312", start_date=future_time_ms
            )
            assert request.order_id == UUID("12312312-3123-1231-2312-312312312312")

    def test_validate_order_id_none(self):
        """Should raise error when order_id is None."""
        current_time_ms = int(datetime.now().timestamp() * 1000)
        future_time_ms = current_time_ms + (7 * 24 * 60 * 60 * 1000)

        with patch.object(
            DateTimeUtil, "get_current_time", return_value=current_time_ms
        ):
            with pytest.raises(ValidationError) as exc_info:
                UpdateEntitlementStartDateRequest(
                    order_id=None, start_date=future_time_ms
                )

            assert "order_id is required" in str(exc_info.value)

    def test_validate_order_id_not_integer(self):
        """Should raise error when order_id is not an integer."""
        current_time_ms = int(datetime.now().timestamp() * 1000)
        future_time_ms = current_time_ms + (7 * 24 * 60 * 60 * 1000)

        with patch.object(
            DateTimeUtil, "get_current_time", return_value=current_time_ms
        ):
            with pytest.raises(ValidationError) as exc_info:
                UpdateEntitlementStartDateRequest(
                    order_id="123", start_date=future_time_ms
                )

            assert "order_id must be a valid UUID" in str(exc_info.value)

    def test_validate_order_id_not_integer_float(self):
        """Should raise error when order_id is a float."""
        current_time_ms = int(datetime.now().timestamp() * 1000)
        future_time_ms = current_time_ms + (7 * 24 * 60 * 60 * 1000)

        with patch.object(
            DateTimeUtil, "get_current_time", return_value=current_time_ms
        ):
            with pytest.raises(ValidationError) as exc_info:
                UpdateEntitlementStartDateRequest(
                    order_id=123.45, start_date=future_time_ms
                )

            assert "order_id must be a valid UUID" in str(exc_info.value)

    def test_validate_order_id_zero(self):
        """Zero UUID is well-formed and passes (UUIDs carry no ordering)."""
        current_time_ms = int(datetime.now().timestamp() * 1000)
        future_time_ms = current_time_ms + (7 * 24 * 60 * 60 * 1000)

        with patch.object(
            DateTimeUtil, "get_current_time", return_value=current_time_ms
        ):
            request = UpdateEntitlementStartDateRequest(order_id=UUID("00000000-0000-0000-0000-000000000000"), start_date=future_time_ms)
            assert request.order_id == UUID("00000000-0000-0000-0000-000000000000")

    def test_validate_order_id_negative(self):
        """Should raise error when order_id is negative."""
        current_time_ms = int(datetime.now().timestamp() * 1000)
        future_time_ms = current_time_ms + (7 * 24 * 60 * 60 * 1000)

        with patch.object(
            DateTimeUtil, "get_current_time", return_value=current_time_ms
        ):
            with pytest.raises(ValidationError) as exc_info:
                UpdateEntitlementStartDateRequest(
                    order_id=-1, start_date=future_time_ms
                )

            assert "order_id must be a valid UUID" in str(exc_info.value)

    def test_validate_order_id_exceeds_max(self):
        """Should raise error when order_id exceeds MAX_INT_32."""
        current_time_ms = int(datetime.now().timestamp() * 1000)
        future_time_ms = current_time_ms + (7 * 24 * 60 * 60 * 1000)

        with patch.object(
            DateTimeUtil, "get_current_time", return_value=current_time_ms
        ):
            with pytest.raises(ValidationError) as exc_info:
                UpdateEntitlementStartDateRequest(
                    order_id=MAX_INT_32 + 1, start_date=future_time_ms
                )

            assert "order_id must be a valid UUID" in str(exc_info.value)

    def test_validate_start_date_valid(self):
        """Should accept valid future start_date."""
        current_time_ms = int(datetime.now().timestamp() * 1000)
        future_time_ms = current_time_ms + (7 * 24 * 60 * 60 * 1000)

        with patch.object(
            DateTimeUtil, "get_current_time", return_value=current_time_ms
        ):
            request = UpdateEntitlementStartDateRequest(
                order_id= UUID("12312312-3123-1231-2312-312312312312"), start_date=future_time_ms
            )
            assert request.start_date == future_time_ms

    def test_validate_start_date_one_millisecond_future(self):
        """Should accept start_date that is 1ms in the future."""
        current_time_ms = 1000000000000
        future_time_ms = current_time_ms + 1

        with patch.object(
            DateTimeUtil, "get_current_time", return_value=current_time_ms
        ):
            request = UpdateEntitlementStartDateRequest(
                order_id= UUID("12312312-3123-1231-2312-312312312312"), start_date=future_time_ms
            )
            assert request.start_date == future_time_ms

    def test_validate_start_date_none(self):
        """Should raise error when start_date is None."""
        with pytest.raises(ValidationError) as exc_info:
            UpdateEntitlementStartDateRequest(order_id= UUID("12312312-3123-1231-2312-312312312312"), start_date=None)

        assert "start_date is required and cannot be null" in str(exc_info.value)

    def test_validate_start_date_not_integer(self):
        """Should raise error when start_date is not an integer."""
        current_time_ms = int(datetime.now().timestamp() * 1000)

        with patch.object(
            DateTimeUtil, "get_current_time", return_value=current_time_ms
        ):
            with pytest.raises(ValidationError) as exc_info:
                UpdateEntitlementStartDateRequest(order_id= UUID("12312312-3123-1231-2312-312312312312"), start_date="1234567890")

            assert "start_date must be an integer timestamp in milliseconds" in str(
                exc_info.value
            )

    def test_validate_start_date_float(self):
        """Should raise error when start_date is a float."""
        current_time_ms = int(datetime.now().timestamp() * 1000)

        with patch.object(
            DateTimeUtil, "get_current_time", return_value=current_time_ms
        ):
            with pytest.raises(ValidationError) as exc_info:
                UpdateEntitlementStartDateRequest(order_id= UUID("12312312-3123-1231-2312-312312312312"), start_date=1234567890.5)

            assert "start_date must be an integer timestamp in milliseconds" in str(
                exc_info.value
            )

    def test_validate_start_date_zero(self):
        """Should raise error when start_date is zero."""
        with pytest.raises(ValidationError) as exc_info:
            UpdateEntitlementStartDateRequest(order_id= UUID("12312312-3123-1231-2312-312312312312"), start_date=0)

        assert "start_date must be a positive integer timestamp" in str(exc_info.value)

    def test_validate_start_date_negative(self):
        """Should raise error when start_date is negative."""
        with pytest.raises(ValidationError) as exc_info:
            UpdateEntitlementStartDateRequest(order_id= UUID("12312312-3123-1231-2312-312312312312"), start_date=-1000)

        assert "start_date must be a positive integer timestamp" in str(exc_info.value)

    def test_both_fields_valid(self):
        """Should accept when both fields are valid."""
        current_time_ms = int(datetime.now().timestamp() * 1000)
        future_time_ms = current_time_ms + (30 * 24 * 60 * 60 * 1000)  # 30 days

        with patch.object(
            DateTimeUtil, "get_current_time", return_value=current_time_ms
        ):
            request = UpdateEntitlementStartDateRequest(
                order_id= UUID("99999999-9999-9999-9999-999999999999"), start_date=future_time_ms
            )
            assert request.order_id== UUID("99999999-9999-9999-9999-999999999999")
            assert request.start_date == future_time_ms

    def test_both_fields_invalid(self):
        """Should raise error for first invalid field encountered."""
        with pytest.raises(ValidationError) as exc_info:
            UpdateEntitlementStartDateRequest(order_id=None, start_date=None)

        # Should fail on order_id validation first
        assert "order_id is required" in str(exc_info.value)


class TestEntitlementCreate:
    """Test EntitlementCreate schema."""

    def test_create_valid_minimal(self):
        """Should create with minimal required fields."""
        entitlement = EntitlementCreate(
            order_id= UUID("10010010-0100-1001-0010-010010010010"),
            partner_id= UUID("20020020-0200-2002-0020-020020020020"),
            service_name="console",
            modules=["module1", "module2"],
            limits={"limit1": 10},
            end_date=1234567890000,
        )

        assert entitlement.order_id== UUID("10010010-0100-1001-0010-010010010010")
        assert entitlement.partner_id== UUID("20020020-0200-2002-0020-020020020020")
        assert entitlement.service_name == "console"
        assert entitlement.modules == ["module1", "module2"]
        assert entitlement.limits == {"limit1": 10}
        assert entitlement.created_by is None
        assert entitlement.end_date == 1234567890000

    def test_create_valid_with_created_by(self):
        """Should create with created_by field."""
        entitlement = EntitlementCreate(
            order_id= UUID("10010010-0100-1001-0010-010010010010"),
            partner_id= UUID("20020020-0200-2002-0020-020020020020"),
            service_name="console",
            modules=["module1"],
            limits={},
            created_by= UUID("50505050-5050-5050-5050-505050505050"),
            end_date=1234567890000,
        )

        assert entitlement.created_by== UUID("50505050-5050-5050-5050-505050505050")

    def test_create_empty_modules(self):
        """Should accept empty modules list."""
        entitlement = EntitlementCreate(
            order_id= UUID("10010010-0100-1001-0010-010010010010"),
            partner_id= UUID("20020020-0200-2002-0020-020020020020"),
            service_name="console",
            modules=[],
            limits={"limit1": 10},
            end_date=1234567890000,
        )

        assert entitlement.modules == []

    def test_create_empty_limits(self):
        """Should accept empty limits dict."""
        entitlement = EntitlementCreate(
            order_id= UUID("10010010-0100-1001-0010-010010010010"),
            partner_id= UUID("20020020-0200-2002-0020-020020020020"),
            service_name="console",
            modules=["module1"],
            limits={},
            end_date=1234567890000,
        )

        assert entitlement.limits == {}

    def test_create_complex_limits(self):
        """Should accept complex limits structure."""
        entitlement = EntitlementCreate(
            order_id= UUID("10010010-0100-1001-0010-010010010010"),
            partner_id= UUID("20020020-0200-2002-0020-020020020020"),
            service_name="console",
            modules=["module1"],
            limits={"limit1": 10, "limit2": "unlimited", "limit3": {"nested": True}},
            end_date=1234567890000,
        )

        assert entitlement.limits["limit1"] == 10
        assert entitlement.limits["limit2"] == "unlimited"
        assert entitlement.limits["limit3"] == {"nested": True}


class TestEntitlementUpdate:
    """Test EntitlementUpdate schema."""

    def test_update_all_fields_none(self):
        """Should create with all optional fields as None."""
        update = EntitlementUpdate()

        assert update.modules is None
        assert update.limits is None
        assert update.start_date is None
        assert update.end_date is None
        assert update.is_active is None
        assert update.updated_by is None

    def test_update_only_modules(self):
        """Should update only modules field."""
        update = EntitlementUpdate(modules=["new_module1", "new_module2"])

        assert update.modules == ["new_module1", "new_module2"]
        assert update.limits is None

    def test_update_only_limits(self):
        """Should update only limits field."""
        update = EntitlementUpdate(limits={"new_limit": 100})

        assert update.limits == {"new_limit": 100}
        assert update.modules is None

    def test_update_only_start_date(self):
        """Should update only start_date field."""
        update = EntitlementUpdate(start_date=1234567890000)

        assert update.start_date == 1234567890000

    def test_update_only_end_date(self):
        """Should update only end_date field."""
        update = EntitlementUpdate(end_date=9876543210000)

        assert update.end_date == 9876543210000

    def test_update_only_is_active(self):
        """Should update only is_active field."""
        update = EntitlementUpdate(is_active=False)

        assert update.is_active is False

    def test_update_only_updated_by(self):
        """Should update only updated_by field."""
        update = EntitlementUpdate(updated_by= UUID("42424242-4242-4242-4242-424242424242"))

        assert update.updated_by== UUID("42424242-4242-4242-4242-424242424242")

    def test_update_all_fields(self):
        """Should update all fields together."""
        update = EntitlementUpdate(
            modules=["module1"],
            limits={"limit1": 50},
            start_date=1111111111111,
            end_date=2222222222222,
            is_active=True,
            updated_by= UUID("99999999-9999-9999-9999-999999999999"),
        )

        assert update.modules == ["module1"]
        assert update.limits == {"limit1": 50}
        assert update.start_date == 1111111111111
        assert update.end_date == 2222222222222
        assert update.is_active is True
        assert update.updated_by== UUID("99999999-9999-9999-9999-999999999999")

    def test_update_empty_modules(self):
        """Should accept empty modules list."""
        update = EntitlementUpdate(modules=[])

        assert update.modules == []

    def test_update_empty_limits(self):
        """Should accept empty limits dict."""
        update = EntitlementUpdate(limits={})

        assert update.limits == {}


class TestEntitlementResponse:
    """Test EntitlementResponse schema."""

    def test_response_all_fields(self):
        """Should create response with all required fields."""
        response = EntitlementResponse(
            id= UUID("11111111-1111-1111-1111-111111111111"),
            order_id= UUID("10010010-0100-1001-0010-010010010010"),
            partner_id= UUID("20020020-0200-2002-0020-020020020020"),
            service_name="console",
            modules=["module1", "module2"],
            limits={"limit1": 10, "limit2": 20},
            start_date=1234567890000,
            end_date=9876543210000,
            is_active=True,
        )

        assert response.id == UUID("11111111-1111-1111-1111-111111111111")
        assert response.order_id== UUID("10010010-0100-1001-0010-010010010010")
        assert response.partner_id== UUID("20020020-0200-2002-0020-020020020020")
        assert response.service_name == "console"
        assert response.modules == ["module1", "module2"]
        assert response.limits == {"limit1": 10, "limit2": 20}
        assert response.start_date == 1234567890000
        assert response.end_date == 9876543210000
        assert response.is_active is True

    def test_response_is_active_false(self):
        """Should handle is_active=False."""
        response = EntitlementResponse(
            id= UUID("11111111-1111-1111-1111-111111111111"),
            order_id= UUID("10010010-0100-1001-0010-010010010010"),
            partner_id= UUID("20020020-0200-2002-0020-020020020020"),
            service_name="console",
            modules=[],
            limits={},
            start_date=1234567890000,
            end_date=9876543210000,
            is_active=False,
        )

        assert response.is_active is False

    def test_response_from_attributes_config(self):
        """Should have from_attributes config enabled."""
        assert EntitlementResponse.model_config.get("from_attributes") is True


class TestUpdateEntitlementStartDateResponse:
    """Test UpdateEntitlementStartDateResponse schema."""

    def test_response_all_fields(self):
        """Should create response with all required fields."""
        response = UpdateEntitlementStartDateResponse(
            id= UUID("11111111-1111-1111-1111-111111111111"),
            order_id= UUID("10010010-0100-1001-0010-010010010010"),
            partner_id= UUID("20020020-0200-2002-0020-020020020020"),
            service_name="console",
            start_date=1234567890000,
            end_date=9876543210000,
            is_active=True,
            start_date_update_count=2,
        )

        assert response.id == UUID("11111111-1111-1111-1111-111111111111")
        assert response.order_id== UUID("10010010-0100-1001-0010-010010010010")
        assert response.partner_id== UUID("20020020-0200-2002-0020-020020020020")
        assert response.service_name == "console"
        assert response.start_date == 1234567890000
        assert response.end_date == 9876543210000
        assert response.is_active is True
        assert response.start_date_update_count == 2

    def test_response_update_count_zero(self):
        """Should handle update_count of zero."""
        response = UpdateEntitlementStartDateResponse(
            id= UUID("11111111-1111-1111-1111-111111111111"),
            order_id= UUID("10010010-0100-1001-0010-010010010010"),
            partner_id= UUID("20020020-0200-2002-0020-020020020020"),
            service_name="console",
            start_date=1234567890000,
            end_date=9876543210000,
            is_active=True,
            start_date_update_count=0,
        )

        assert response.start_date_update_count == 0

    def test_response_is_active_false(self):
        """Should handle is_active=False."""
        response = UpdateEntitlementStartDateResponse(
            id= UUID("11111111-1111-1111-1111-111111111111"),
            order_id= UUID("10010010-0100-1001-0010-010010010010"),
            partner_id= UUID("20020020-0200-2002-0020-020020020020"),
            service_name="console",
            start_date=1234567890000,
            end_date=9876543210000,
            is_active=False,
            start_date_update_count=1,
        )

        assert response.is_active is False

    def test_response_from_attributes_config(self):
        """Should have from_attributes config enabled."""
        assert (
            UpdateEntitlementStartDateResponse.model_config.get("from_attributes")
            is True
        )


class TestMaxInt32Constant:
    """Test MAX_INT_32 constant."""

    def test_max_int_32_value(self):
        """Should have correct max int32 value."""
        assert MAX_INT_32 == 2_147_483_647

    def test_max_int_32_is_max_signed_32bit(self):
        """Should be exactly 2^31 - 1."""
        assert MAX_INT_32 == (2**31) - 1


class TestDateTimeUtil:
    """Test DateTimeUtil class."""

    def test_get_current_time_returns_float(self):
        """Should return a float value."""
        result = DateTimeUtil.get_current_time()
        assert isinstance(result, float)

    def test_get_current_time_in_milliseconds(self):
        """Should return time in milliseconds."""
        result = DateTimeUtil.get_current_time()
        # Current time should be reasonable (after year 2000, before year 2100)
        assert 946684800000 < result < 4102444800000  # Jan 1, 2000 to Jan 1, 2100

    def test_get_current_time_is_positive(self):
        """Should return positive value."""
        result = DateTimeUtil.get_current_time()
        assert result > 0

    def test_get_current_time_increases(self):
        """Should return increasing values when called multiple times."""
        time1 = DateTimeUtil.get_current_time()
        time2 = DateTimeUtil.get_current_time()
        # Second call should be equal or slightly greater
        assert time2 >= time1

    @patch("src.components.common.datetime.datetime")
    def test_get_current_time_uses_datetime_now(self, mock_datetime):
        """Should use datetime.now() to get current time."""
        mock_now = Mock()
        mock_now.timestamp.return_value = 1234567890.123
        mock_datetime.now.return_value = mock_now

        result = DateTimeUtil.get_current_time()

        mock_datetime.now.assert_called_once()
        mock_now.timestamp.assert_called_once()
        assert result == 1234567890123.0

    @patch("src.components.common.datetime.datetime")
    def test_get_current_time_converts_to_milliseconds(self, mock_datetime):
        """Should multiply timestamp by 1000 to convert to milliseconds."""
        mock_now = Mock()
        mock_now.timestamp.return_value = 1000.5  # 1000.5 seconds
        mock_datetime.now.return_value = mock_now

        result = DateTimeUtil.get_current_time()

        assert result == 1000500.0  # 1000.5 * 1000

    def test_get_current_time_is_static_method(self):
        """Should be callable without instance."""
        # Should not raise any errors
        result = DateTimeUtil.get_current_time()
        assert isinstance(result, float)

    def test_get_current_time_precision(self):
        """Should have millisecond precision."""
        result = DateTimeUtil.get_current_time()
        # Should be a float with decimal places (milliseconds)
        assert isinstance(result, float)
        # When converted to int, should be a large number (milliseconds since epoch)
        assert int(result) > 1000000000000
