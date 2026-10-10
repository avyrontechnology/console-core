import pytest
from pydantic import ValidationError

from src.components.user.schema import (
    Contrasts,
    UserRoleFilterRequest,
    _validate_filter_entry,
)


class TestUpdateUserDataIsActive:
    def test_true_and_false_accepted(self):
        assert Contrasts.UpdateUserData(is_active=True).is_active is True
        assert Contrasts.UpdateUserData(is_active=False).is_active is False

    def test_none_accepted(self):
        assert Contrasts.UpdateUserData(is_active=None).is_active is None

    def test_omitted_defaults_to_none(self):
        assert Contrasts.UpdateUserData().is_active is None

    @pytest.mark.parametrize("bad", ["true", "false", 1, 0, "yes"])
    def test_non_bool_rejected(self, bad):
        with pytest.raises(ValidationError, match="is_active must be a boolean"):
            Contrasts.UpdateUserData(is_active=bad)


class TestGetUserDetailResponseIsActive:
    def test_is_active_included(self):
        res = Contrasts.GetUserDetailResponse(id=1, name="A", is_active=False)
        assert res.is_active is False

    def test_is_active_defaults_to_none(self):
        assert Contrasts.GetUserDetailResponse(id=1, name="A").is_active is None


class TestUserRoleFilterValidation:
    def test_no_filters_ok(self):
        assert UserRoleFilterRequest().filters == []

    def test_valid_filter_ok(self):
        req = UserRoleFilterRequest(
            filters=[{"field": "is_active", "operator": "=", "value": True}]
        )
        assert len(req.filters) == 1

    def test_non_dict_entry_rejected(self):
        with pytest.raises(ValueError, match="must be an object"):
            _validate_filter_entry("not-a-dict")

    def test_missing_field_rejected(self):
        with pytest.raises(ValidationError, match="Filter 'field' is required"):
            UserRoleFilterRequest(filters=[{"operator": "=", "value": 1}])

    def test_missing_operator_rejected(self):
        with pytest.raises(ValidationError, match="Filter 'operator' is required"):
            UserRoleFilterRequest(filters=[{"field": "is_active", "value": 1}])

    def test_unsupported_operator_rejected(self):
        with pytest.raises(ValidationError, match="Unsupported operator"):
            UserRoleFilterRequest(
                filters=[{"field": "is_active", "operator": "NOPE", "value": 1}]
            )

    def test_range_operator_with_two_values_list_ok(self):
        UserRoleFilterRequest(
            filters=[
                {
                    "field": "created_at",
                    "operator": "BETWEEN",
                    "value": ["2026-08-01", "2026-08-10"],
                }
            ]
        )

    def test_range_operator_with_comma_string_ok(self):
        UserRoleFilterRequest(
            filters=[
                {
                    "field": "created_at",
                    "operator": "BETWEEN",
                    "value": "2026-08-01,2026-08-10",
                }
            ]
        )

    @pytest.mark.parametrize("value", [["2026-08-01"], "2026-08-01", None])
    def test_range_operator_wrong_value_count_rejected(self, value):
        with pytest.raises(ValidationError, match="expects exactly two values"):
            UserRoleFilterRequest(
                filters=[
                    {"field": "created_at", "operator": "BETWEEN", "value": value}
                ]
            )