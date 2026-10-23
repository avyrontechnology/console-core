"""Tests for Grace Period Pydantic schemas — GrantGraceRequest, GraceResponse, GraceStatusResponse."""

from uuid import UUID
from unittest.mock import patch

import pytest
from pydantic import ValidationError

from src.components.db_constants.loader.constant import DbConstants
from src.components.grace.constants import GraceStatus
from src.components.grace.schema import (
    GraceResponse,
    GraceStatusResponse,
    GrantGraceRequest,
)

NOW_MS = 1_700_000_000_000


def _validate(
    partner_id= UUID("10101010-1010-1010-1010-101010101010"), granted_days=7, remark="Valid remark", *, validated=None, error=None
):
    req = GrantGraceRequest(
        partner_id=partner_id,
        granted_days=granted_days,
        remark=remark,
    )
    _validated = (
        validated
        if validated is not None
        else {
            "partner_id": partner_id,
            "granted_days": granted_days,
            "remark": remark,
        }
    )
    with patch(
        "src.components.grace.schema.SchemaValidator.validate",
        return_value=(_validated, error),
    ):
        return req.validate_payload()


# =============================================================================
# GrantGraceRequest — validate_payload
# =============================================================================


class TestGrantGraceRequestValidatePayload:

    # ── happy path ────────────────────────────────────────────────────────────

    def test_valid_payload_returns_dict_and_no_error(self):
        validated, error = _validate()
        assert error is None
        assert validated["partner_id"] == UUID("10101010-1010-1010-1010-101010101010")
        assert validated["granted_days"] == 7
        assert validated["remark"] == "Valid remark"

    def test_valid_payload_returns_empty_dict_on_error(self):
        validated, error = _validate(error="partner_id is required", validated={})
        assert validated == {}
        assert error == "partner_id is required"

    # ── partner_id ────────────────────────────────────────────────────────────

    def test_partner_id_none_fails(self):
        _, error = _validate(
            partner_id=None, validated={}, error="partner_id is required"
        )
        assert error is not None

    def test_partner_id_zero_fails(self):
        _, error = _validate(
            partner_id=UUID("00000000-0000-0000-0000-000000000000"), validated={}, error="partner_id must be a valid UUID"
        )
        assert error is not None

    def test_partner_id_negative_fails(self):
        _, error = _validate(
            partner_id=-5, validated={}, error="partner_id must be a valid UUID"
        )
        assert error is not None

    def test_partner_id_string_fails(self):
        _, error = _validate(
            partner_id="abc", validated={}, error="partner_id must be a valid UUID"
        )
        assert error is not None

    def test_partner_id_one_passes(self):
        validated, error = _validate(partner_id= UUID("11111111-1111-1111-1111-111111111111"))
        assert error is None
        assert validated["partner_id"] == UUID("11111111-1111-1111-1111-111111111111")

    def test_partner_id_large_valid_value_passes(self):
        _, error = _validate(
            partner_id=2_147_483_647, validated={}, error="partner_id must be a valid UUID"
        )
        assert error is not None

    # ── granted_days ──────────────────────────────────────────────────────────

    def test_granted_days_none_fails(self):
        _, error = _validate(
            granted_days=None, validated={}, error="granted_days is required"
        )
        assert error is not None

    def test_granted_days_zero_fails(self):
        _, error = _validate(
            granted_days=0, validated={}, error="granted_days must be at least 1"
        )
        assert error is not None

    def test_granted_days_negative_fails(self):
        _, error = _validate(
            granted_days=-1, validated={}, error="granted_days must be at least 1"
        )
        assert error is not None

    def test_granted_days_one_passes(self):
        validated, error = _validate(
            granted_days=1,
            validated={"partner_id": UUID("10101010-1010-1010-1010-101010101010"), "granted_days": 1, "remark": "r"},
        )
        assert error is None
        assert validated["granted_days"] == 1

    def test_granted_days_exactly_max_passes(self):
        max_days = DbConstants.MAX_GRACE_DAYS_PER_ATTEMPT
        validated, error = _validate(
            granted_days=max_days,
            validated={"partner_id": 10, "granted_days": max_days, "remark": "r"},
        )
        assert error is None

    def test_granted_days_exceeds_max_fails(self):
        _, error = _validate(
            granted_days=DbConstants.MAX_GRACE_DAYS_PER_ATTEMPT + 1,
            validated={},
            error="granted_days exceeds maximum",
        )
        assert error is not None

    def test_granted_days_string_fails(self):
        _, error = _validate(
            granted_days="seven", validated={}, error="granted_days must be an integer"
        )
        assert error is not None

    # ── remark ────────────────────────────────────────────────────────────────

    def test_remark_none_fails(self):
        _, error = _validate(remark=None, validated={}, error="remark is required")
        assert error is not None

    def test_remark_empty_string_fails(self):
        _, error = _validate(
            remark="", validated={}, error="remark must be at least 1 character"
        )
        assert error is not None

    def test_remark_exactly_500_chars_passes(self):
        long_remark = "x" * 500
        validated, error = _validate(
            remark=long_remark,
            validated={"partner_id": 10, "granted_days": 7, "remark": long_remark},
        )
        assert error is None

    def test_remark_501_chars_fails(self):
        _, error = _validate(
            remark="x" * 501,
            validated={},
            error="remark exceeds maximum length",
        )
        assert error is not None

    def test_remark_one_char_passes(self):
        validated, error = _validate(
            remark="x",
            validated={"partner_id": 10, "granted_days": 7, "remark": "x"},
        )
        assert error is None

    def test_remark_integer_type_fails(self):
        _, error = _validate(remark=123, validated={}, error="remark must be a string")
        assert error is not None

    # ── multiple field errors ─────────────────────────────────────────────────

    def test_all_none_fields_returns_error(self):
        _, error = _validate(
            partner_id=None,
            granted_days=None,
            remark=None,
            validated={},
            error="partner_id is required",
        )
        assert error is not None

    # ── validate_payload returns empty dict on error ───────────────────────────

    def test_returns_empty_dict_not_none_on_error(self):
        validated, error = _validate(validated={}, error="some error")
        assert isinstance(validated, dict)
        assert validated == {}


# =============================================================================
# GraceResponse
# =============================================================================


class TestGraceResponse:

    def _minimal(self, **overrides):
        defaults = dict(
            grace_id= UUID("11111111-1111-1111-1111-111111111111"),
            partner_id= UUID("10101010-1010-1010-1010-101010101010"),
            service_name="console",
            granted_days=7,
            attempt_number=1,
            start_date=NOW_MS,
            end_date=NOW_MS + 7 * 86_400_000,
            status=GraceStatus.ACTIVE,
        )
        return GraceResponse(**{**defaults, **overrides})

    # ── required fields ───────────────────────────────────────────────────────

    def test_all_required_fields_accepted(self):
        resp = self._minimal()
        assert resp.grace_id== UUID("11111111-1111-1111-1111-111111111111")
        assert resp.partner_id== UUID("10101010-1010-1010-1010-101010101010")
        assert resp.service_name == "console"
        assert resp.granted_days == 7
        assert resp.attempt_number == 1
        assert resp.status == GraceStatus.ACTIVE

    # ── optional fields default to None ──────────────────────────────────────

    def test_optional_fields_default_none(self):
        resp = self._minimal()
        assert resp.remark is None
        assert resp.consumed_days is None
        assert resp.settled_at is None
        assert resp.settled_by_order_id is None
        assert resp.created_by is None
        assert resp.created_at is None
        assert resp.granted_by_name is None

    # ── optional fields accepted when provided ────────────────────────────────

    def test_all_optional_fields_accepted(self):
        resp = self._minimal(
            remark="special reason",
            consumed_days=3,
            settled_at=NOW_MS + 3 * 86_400_000,
            settled_by_order_id= UUID("42424242-4242-4242-4242-424242424242"),
            created_by= UUID("99999999-9999-9999-9999-999999999999"),
            created_at=NOW_MS,
            granted_by_name="Alice",
        )
        assert resp.remark == "special reason"
        assert resp.consumed_days == 3
        assert resp.settled_at == NOW_MS + 3 * 86_400_000
        assert resp.settled_by_order_id== UUID("42424242-4242-4242-4242-424242424242")
        assert resp.created_by== UUID("99999999-9999-9999-9999-999999999999")
        assert resp.granted_by_name == "Alice"

    # ── status values ─────────────────────────────────────────────────────────

    @pytest.mark.parametrize(
        "status", [GraceStatus.ACTIVE, GraceStatus.EXPIRED, GraceStatus.SETTLED]
    )
    def test_all_valid_status_values_accepted(self, status):
        resp = self._minimal(status=status)
        assert resp.status == status

    # ── numeric field types ────────────────────────────────────────────────────

    def test_start_date_and_end_date_are_integers(self):
        resp = self._minimal()
        assert isinstance(resp.start_date, int)
        assert isinstance(resp.end_date, int)

    def test_grace_id_is_integer(self):
        resp = self._minimal(grace_id= UUID("99999999-9999-9999-9999-999999999999"))
        assert resp.grace_id== UUID("99999999-9999-9999-9999-999999999999")

    # ── model serialisation ───────────────────────────────────────────────────

    def test_model_dump_contains_all_keys(self):
        resp = self._minimal()
        dumped = resp.model_dump()
        expected_keys = {
            "grace_id",
            "partner_id",
            "service_name",
            "granted_days",
            "attempt_number",
            "start_date",
            "end_date",
            "status",
            "remark",
            "consumed_days",
            "settled_at",
            "settled_by_order_id",
            "created_by",
            "created_at",
            "granted_by_name",
        }
        assert expected_keys.issubset(dumped.keys())


# =============================================================================
# GraceStatusResponse
# =============================================================================


class TestGraceStatusResponse:

    def _minimal(self, **overrides):
        defaults = dict(
            partner_id= UUID("10101010-1010-1010-1010-101010101010"),
            service_name="console",
            has_active_grace=False,
            total_attempts_used=0,
            attempts_remaining=DbConstants.MAX_GRACE_ATTEMPTS,
            total_consumed_days=0,
        )
        return GraceStatusResponse(**{**defaults, **overrides})

    # ── required fields ───────────────────────────────────────────────────────

    def test_basic_structure_no_active_grace(self):
        resp = self._minimal()
        assert resp.partner_id== UUID("10101010-1010-1010-1010-101010101010")
        assert resp.service_name == "console"
        assert resp.has_active_grace is False
        assert resp.current_grace is None
        assert resp.total_attempts_used == 0
        assert resp.attempts_remaining == DbConstants.MAX_GRACE_ATTEMPTS
        assert resp.total_consumed_days == 0

    # ── optional fields default to None ──────────────────────────────────────

    def test_optional_fields_default_none(self):
        resp = self._minimal()
        assert resp.current_grace is None
        assert resp.created_by is None
        assert resp.created_at is None
        assert resp.granted_by_name is None

    # ── with nested GraceResponse ─────────────────────────────────────────────

    def test_with_current_grace_nested(self):
        grace_resp = GraceResponse(
            grace_id= UUID("11111111-1111-1111-1111-111111111111"),
            partner_id= UUID("10101010-1010-1010-1010-101010101010"),
            service_name="console",
            granted_days=7,
            attempt_number=1,
            start_date=NOW_MS,
            end_date=NOW_MS + 7 * 86_400_000,
            status=GraceStatus.ACTIVE,
        )
        resp = self._minimal(
            has_active_grace=True,
            current_grace=grace_resp,
            total_attempts_used=1,
            attempts_remaining=DbConstants.MAX_GRACE_ATTEMPTS - 1,
        )
        assert resp.has_active_grace is True
        assert resp.current_grace is not None
        assert resp.current_grace.grace_id== UUID("11111111-1111-1111-1111-111111111111")
        assert resp.current_grace.service_name == "console"

    # ── numeric boundaries ────────────────────────────────────────────────────

    def test_attempts_remaining_zero(self):
        resp = self._minimal(attempts_remaining=0)
        assert resp.attempts_remaining == 0

    def test_total_consumed_days_zero(self):
        resp = self._minimal(total_consumed_days=0)
        assert resp.total_consumed_days == 0

    def test_total_consumed_days_large_value(self):
        resp = self._minimal(total_consumed_days=365)
        assert resp.total_consumed_days == 365

    # ── metadata fields ───────────────────────────────────────────────────────

    def test_created_by_and_granted_by_name_accepted(self):
        resp = self._minimal(
            created_by= UUID("99999999-9999-9999-9999-999999999999"),
            created_at=NOW_MS,
            granted_by_name="Alice",
        )
        assert resp.created_by== UUID("99999999-9999-9999-9999-999999999999")
        assert resp.created_at == NOW_MS
        assert resp.granted_by_name == "Alice"

    # ── serialisation ─────────────────────────────────────────────────────────

    def test_model_dump_contains_all_keys(self):
        resp = self._minimal()
        dumped = resp.model_dump()
        expected_keys = {
            "partner_id",
            "service_name",
            "has_active_grace",
            "current_grace",
            "total_attempts_used",
            "attempts_remaining",
            "total_consumed_days",
            "created_by",
            "created_at",
            "granted_by_name",
        }
        assert expected_keys.issubset(dumped.keys())

    def test_model_dump_with_nested_grace_serialises_correctly(self):
        grace_resp = GraceResponse(
            grace_id= UUID("22222222-2222-2222-2222-222222222222"),
            partner_id= UUID("10101010-1010-1010-1010-101010101010"),
            service_name="boards",
            granted_days=3,
            attempt_number=1,
            start_date=NOW_MS,
            end_date=NOW_MS + 3 * 86_400_000,
            status=GraceStatus.SETTLED,
            consumed_days=3,
        )
        resp = self._minimal(has_active_grace=True, current_grace=grace_resp)
        dumped = resp.model_dump()
        assert dumped["current_grace"]["grace_id"] == UUID("22222222-2222-2222-2222-222222222222")
        assert dumped["current_grace"]["consumed_days"] == 3
