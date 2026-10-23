"""
Test suite for src/components/user/tasks.py

Goal: take this module from 0% (no test file existed) to as close to 100%
branch coverage as practical. Organized to mirror the structure of tasks.py:

    1. Small pure helpers (_get_id/_get_name/... , _clean_*, _get_optional_str)
    2. File reading (_read_file, _convert_result_to_bytes)
    3. Row-level validation & building (_validate_basic_fields, _get_role,
       location resolution, _get_extra_fields, _build_user_data)
    4. Row processing (_process_row, _handle_admin_signup)
    5. Celery entrypoint (create_bulk_users)
    6. Admin resolution (_resolve_admin)
    7. Parent dependency graph (_build_email_index, _classify_parent_ref,
       _build_parent_plan, _resolve_external_parents,
       _compute_immediate_failures, _build_dependency_graph,
       _cascade_failures)
    8. Wave execution (_run_waves)
    9. Result merging & collation (_merge_bookkeeping_results, _collate_results)
    10. Orchestrators (_process_rows_with_parent_resolution, process_bulk_users)
    11. process_api_log

Run with:
    pytest test_tasks.py --cov=src.components.user.tasks --cov-report=term-missing -v

NOTE: This suite assumes the standard project layout (tests import from
`src....` exactly as tasks.py itself does) and that ValidationMsg /
UserDefaults / RowProcessResult are the real enums/constants used by the
module under test. Adjust the two import blocks below only if your actual
paths differ from what's shown in the source file you shared.
"""
from uuid import UUID
import base64
import io
from types import SimpleNamespace
from typing import Any, Dict, Optional
from unittest.mock import AsyncMock, MagicMock, patch

import pandas as pd
import pytest

from src.components.user import tasks as tasks_module
from src.components.user.tasks import (
    _build_dependency_graph,
    _build_email_index,
    _build_parent_plan,
    _build_user_data,
    _cascade_failures,
    _classify_parent_ref,
    _clean_email,
    _clean_parent_ref,
    _clean_phone,
    _collate_results,
    _compute_immediate_failures,
    _convert_result_to_bytes,
    _get_country_id,
    _get_extra_fields,
    _get_id,
    _get_location_ids,
    _get_name,
    _get_optional_str,
    _get_password,
    _get_role,
    _get_state_id,
    _handle_admin_signup,
    _merge_bookkeeping_results,
    _process_row,
    _process_rows_with_parent_resolution,
    _read_file,
    _resolve_admin,
    _resolve_city,
    _resolve_country,
    _resolve_external_parents,
    _resolve_state,
    _run_waves,
    _validate_basic_fields,
    _validate_location_fields,
    create_bulk_users,
    process_api_log,
    process_bulk_users,
)
from src.components.auth.error import UserCreatedButEmailFailedError
from src.components.user.constants import ValidationMsg, UserDefaults, RowProcessResult


# =====================================================================
# Small factories / helpers used across many tests
# =====================================================================

def make_row(**overrides) -> pd.Series:
    """A minimally valid row as _process_row / _validate_basic_fields expect."""
    base = {
        "email": "user@example.com",
        "name": "Test User",
        "phone_number": "9876543210",
        "password": None,
        "role": "manager",
        "country": None,
        "state": None,
        "city": None,
        "designation": None,
        "alternate_phone_number": None,
        "cloud_agent_number": None,
        "parent": None,
        "_duplicate_email": False,
        "_row_email": "user@example.com",
        "_parent_ref": None,
    }
    base.update(overrides)
    return pd.Series(base)


def make_role(role_id= UUID("11111111-1111-1111-1111-111111111111")):
    return SimpleNamespace(id=role_id)


# =====================================================================
# 1. _get_id / _get_name / _get_country_id / _get_state_id
# =====================================================================

class TestGetterHelpers:
    def test_get_id_none(self):
        assert _get_id(None) is None

    def test_get_id_dict(self):
        assert _get_id({"id": UUID("77777777-7777-7777-7777-777777777777")}) == UUID("77777777-7777-7777-7777-777777777777")

    def test_get_id_obj(self):
        assert _get_id(SimpleNamespace(id=UUID("99999999-9999-9999-9999-999999999999"))) == UUID("99999999-9999-9999-9999-999999999999")

    def test_get_id_missing_attr(self):
        assert _get_id(SimpleNamespace()) is None

    def test_get_name_none(self):
        assert _get_name(None) is None

    def test_get_name_dict(self):
        assert _get_name({"name": "India"}) == "India"

    def test_get_name_obj(self):
        assert _get_name(SimpleNamespace(name="India")) == "India"

    def test_get_country_id_none(self):
        assert _get_country_id(None) is None

    def test_get_country_id_dict(self):
        assert _get_country_id({"country_id": UUID("33333333-3333-3333-3333-333333333333")}) == UUID("33333333-3333-3333-3333-333333333333")

    def test_get_country_id_obj(self):
        assert _get_country_id(SimpleNamespace(country_id=UUID("33333333-3333-3333-3333-333333333333"))) == UUID("33333333-3333-3333-3333-333333333333")

    def test_get_state_id_none(self):
        assert _get_state_id(None) is None

    def test_get_state_id_dict(self):
        assert _get_state_id({"state_id": UUID("55555555-5555-5555-5555-555555555555")}) == UUID("55555555-5555-5555-5555-555555555555")

    def test_get_state_id_obj(self):
        assert _get_state_id(SimpleNamespace(state_id=UUID("55555555-5555-5555-5555-555555555555"))) == UUID("55555555-5555-5555-5555-555555555555")


# =====================================================================
# 2. _convert_result_to_bytes
# =====================================================================

class TestConvertResultToBytes:
    def test_empty_list_returns_empty_bytes(self):
        assert _convert_result_to_bytes([]) == b""

    def test_drops_row_number_and_parent_columns(self):
        rows = [
            {"row_number": 1, "parent": "admin@x.com", "email": "a@x.com", "status": "Success"},
        ]
        result = _convert_result_to_bytes(rows)
        text = result.decode("utf-8-sig")
        assert "row_number" not in text
        assert "parent" not in text
        assert "email" in text and "a@x.com" in text

    def test_keeps_other_columns(self):
        rows = [{"email": "a@x.com", "status": "Success", "reason": ""}]
        result = _convert_result_to_bytes(rows)
        text = result.decode("utf-8-sig")
        assert "status" in text
        assert "Success" in text


# =====================================================================
# 3. _clean_parent_ref
# =====================================================================

class TestCleanParentRef:
    def test_nan_returns_none(self):
        assert _clean_parent_ref(float("nan")) is None

    def test_empty_string_returns_none(self):
        assert _clean_parent_ref("   ") is None

    def test_none_returns_none(self):
        assert _clean_parent_ref(None) is None

    def test_normalizes_case_and_whitespace(self):
        assert _clean_parent_ref("  Parent@Example.COM  ") == "parent@example.com"


# =====================================================================
# 4. _read_file
# =====================================================================

class TestReadFile:
    def _csv_bytes(self, header="email,phone_number,name,role", rows=None):
        rows = rows or ["a@x.com,9876543210,Alice,Admin"]
        content = header + "\n" + "\n".join(rows) + "\n"
        return content.encode("utf-8")

    def test_reads_valid_csv(self):
        data = self._csv_bytes()
        df = _read_file(data, "users.csv")
        assert len(df) == 1
        assert "parent" in df.columns
        assert "_row_email" in df.columns

    def test_missing_required_column_raises(self):
        data = "email,phone_number,name\na@x.com,123,Alice\n".encode("utf-8")
        with pytest.raises(ValueError, match="Missing required column"):
            _read_file(data, "users.csv")

    def test_empty_file_raises(self):
        data = "email,phone_number,name,role\n".encode("utf-8")
        with pytest.raises(ValueError, match="File is empty"):
            _read_file(data, "users.csv")

    def test_header_case_and_whitespace_insensitive(self):
        data = " Email , Phone_Number ,NAME,Role\na@x.com,9876543210,Alice,Admin\n".encode("utf-8")
        df = _read_file(data, "users.csv")
        assert "email" in df.columns
        assert "phone_number" in df.columns

    def test_duplicate_emails_marked(self):
        data = self._csv_bytes(rows=[
            "a@x.com,9876543210,Alice,Admin",
            "A@X.com,9876543210,Alice2,Manager",
        ])
        df = _read_file(data, "users.csv")
        assert df["_duplicate_email"].tolist() == [False, True]

    def test_parent_column_normalized(self):
        header = "email,phone_number,name,role,parent"
        rows = ["a@x.com,9876543210,Alice,Manager, Boss@Example.com "]
        data = (header + "\n" + "\n".join(rows) + "\n").encode("utf-8")
        df = _read_file(data, "users.csv")
        assert df.loc[0, "_parent_ref"] == "boss@example.com"

    def test_encoding_fallback_latin1(self):
        # \xe9 (é in latin-1) is not valid standalone UTF-8, forcing fallback.
        raw = (
            b"email,phone_number,name,role\n"
            b"a@x.com,9876543210,Jos\xe9,Admin\n"
        )
        df = _read_file(raw, "users.csv")
        assert len(df) == 1

    def test_xlsx_read(self):
        pytest.importorskip("openpyxl")
        df_in = pd.DataFrame([{
            "email": "a@x.com", "phone_number": "9876543210",
            "name": "Alice", "role": "Admin",
        }])
        buf = io.BytesIO()
        df_in.to_excel(buf, index=False)
        df = _read_file(buf.getvalue(), "users.xlsx")
        assert len(df) == 1
        assert df.loc[0, "email"] == "a@x.com"


# =====================================================================
# 5. _clean_email
# =====================================================================

class TestCleanEmail:
    def test_none_raises_required(self):
        with pytest.raises(ValueError, match=str(ValidationMsg.EMAIL_REQUIRED)):
            _clean_email(None)

    def test_blank_raises_required(self):
        with pytest.raises(ValueError, match=str(ValidationMsg.EMAIL_REQUIRED)):
            _clean_email("   ")

    def test_invalid_format_raises(self):
        with pytest.raises(ValueError, match=str(ValidationMsg.INVALID_EMAIL)):
            _clean_email("not-an-email")

    def test_valid_email_is_normalized(self):
        assert _clean_email(" User@EXAMPLE.com \n") == "user@example.com"

    def test_strips_internal_whitespace(self):
        assert _clean_email("us er@example.com") == "user@example.com"


# =====================================================================
# 6. _clean_phone
# =====================================================================

class TestCleanPhone:
    def test_nan_raises(self):
        with pytest.raises(ValueError, match=str(ValidationMsg.PHONE_REQUIRED)):
            _clean_phone(float("nan"))

    def test_no_digits_raises_required(self):
        with pytest.raises(ValueError, match=str(ValidationMsg.PHONE_REQUIRED)):
            _clean_phone("abc")

    def test_ten_digits_gets_91_prefix(self):
        assert _clean_phone("9876543210") == "+919876543210"

    def test_twelve_digits_with_91_prefix(self):
        assert _clean_phone("919876543210") == "+919876543210"

    def test_float_like_string_truncated_at_dot(self):
        assert _clean_phone("9876543210.0") == "+919876543210"

    def test_invalid_length_raises(self):
        with pytest.raises(ValueError, match=str(ValidationMsg.INVALID_PHONE)):
            _clean_phone("12345")


# =====================================================================
# 7. _get_optional_str / _get_password
# =====================================================================

class TestOptionalStrAndPassword:
    def test_get_optional_str_nan(self):
        assert _get_optional_str(float("nan")) is None

    def test_get_optional_str_blank(self):
        assert _get_optional_str("   ") is None

    def test_get_optional_str_value(self):
        assert _get_optional_str("  MixedCase  ") == "mixedcase"

    def test_get_password_default(self):
        assert _get_password(None) == UserDefaults.PASSWORD

    def test_get_password_blank_default(self):
        assert _get_password("   ") == UserDefaults.PASSWORD

    def test_get_password_given(self):
        assert _get_password(" MyPass1! ") == "MyPass1!"


# =====================================================================
# 8. _validate_basic_fields
# =====================================================================

class TestValidateBasicFields:
    def test_valid_row(self):
        row = make_row()
        email, name, phone, password = _validate_basic_fields(row)
        assert email == "user@example.com"
        assert name == "Test User"
        assert phone == "+919876543210"
        assert password == UserDefaults.PASSWORD

    def test_missing_email_raises_first(self):
        row = make_row(email=None, name=None, phone_number=None)
        with pytest.raises(ValueError, match=str(ValidationMsg.EMAIL_REQUIRED)):
            _validate_basic_fields(row)

    def test_missing_name_only_raises_name_required(self):
        row = make_row(name="   ")
        with pytest.raises(ValueError, match=str(ValidationMsg.NAME_REQUIRED)):
            _validate_basic_fields(row)

    def test_missing_phone_only_raises_phone_required(self):
        row = make_row(phone_number=None)
        with pytest.raises(ValueError, match=str(ValidationMsg.PHONE_REQUIRED)):
            _validate_basic_fields(row)


# =====================================================================
# 9. _get_role
# =====================================================================

class TestGetRole:
    def test_missing_role_raises(self):
        row = make_row(role=None)
        with pytest.raises(ValueError, match=str(ValidationMsg.ROLE_REQUIRED)):
            _get_role(row, {})

    def test_invalid_role_raises(self):
        row = make_row(role="ghost")
        with pytest.raises(ValueError, match="Invalid role"):
            _get_role(row, {"admin": make_role()})

    def test_valid_role_returned(self):
        row = make_row(role="Manager")
        role_obj = make_role(5)
        assert _get_role(row, {"manager": role_obj}) is role_obj


# =====================================================================
# 10. Location resolution
# =====================================================================

class TestLocationResolution:
    def test_validate_location_fields_all_none_ok(self):
        _validate_location_fields(None, None, None)  # no raise

    def test_validate_location_fields_partial_raises(self):
        with pytest.raises(ValueError, match="all 3 location fields"):
            _validate_location_fields("india", None, None)

    def test_validate_location_fields_all_present_ok(self):
        _validate_location_fields("india", "up", "ghaziabad")  # no raise

    def test_resolve_country_none_name(self):
        assert _resolve_country(None, {}) is None

    def test_resolve_country_invalid(self):
        with pytest.raises(ValueError, match="Invalid country"):
            _resolve_country("mars", {})

    def test_resolve_country_valid(self):
        country = {"id": UUID("11111111-1111-1111-1111-111111111111")}
        assert _resolve_country("india", {"india": country}) == country

    def test_resolve_state_none_name(self):
        assert _resolve_state(None, {}, None) is None

    def test_resolve_state_invalid(self):
        with pytest.raises(ValueError, match="Invalid state"):
            _resolve_state("up", {}, {"id": UUID("11111111-1111-1111-1111-111111111111")})

    def test_resolve_state_valid(self):
        state = {"id": UUID("22222222-2222-2222-2222-222222222222")}
        assert _resolve_state("up", {("up", UUID("11111111-1111-1111-1111-111111111111")): state}, {"id": UUID("11111111-1111-1111-1111-111111111111")}) == state

    def test_resolve_city_none_name(self):
        assert _resolve_city(None, {}, None) is None

    def test_resolve_city_invalid(self):
        with pytest.raises(ValueError, match="Invalid city"):
            _resolve_city("ghaziabad", {}, {"id": UUID("22222222-2222-2222-2222-222222222222")})

    def test_resolve_city_valid(self):
        city = {"id": UUID("33333333-3333-3333-3333-333333333333")}
        assert _resolve_city("ghaziabad", {("ghaziabad", UUID("22222222-2222-2222-2222-222222222222")): city}, {"id": UUID("22222222-2222-2222-2222-222222222222")}) == city

    def test_get_location_ids_full_flow(self):
        row = make_row(country="India", state="UP", city="Ghaziabad")
        country_map = {"india": {"id": UUID("11111111-1111-1111-1111-111111111111")}}
        state_map = {("up", UUID("11111111-1111-1111-1111-111111111111")): {"id": UUID("22222222-2222-2222-2222-222222222222")}}
        city_map = {("ghaziabad", UUID("22222222-2222-2222-2222-222222222222")): {"id": UUID("33333333-3333-3333-3333-333333333333")}}
        result = _get_location_ids(row, country_map, state_map, city_map)
        assert result == {"country_id": UUID("11111111-1111-1111-1111-111111111111"), "state_id": UUID("22222222-2222-2222-2222-222222222222"), "city_id": UUID("33333333-3333-3333-3333-333333333333")}

    def test_get_location_ids_all_blank(self):
        row = make_row()
        result = _get_location_ids(row, {}, {}, {})
        assert result == {"country_id": None, "state_id": None, "city_id": None}


# =====================================================================
# 11. _get_extra_fields
# =====================================================================

class TestGetExtraFields:
    def test_alternate_phone_cleaned(self):
        row = make_row(alternate_phone_number="9123456780")
        result = _get_extra_fields(row)
        assert result["alternate_phone_number"] == "+919123456780"

    def test_designation_and_cloud_agent_passthrough(self):
        row = make_row(designation="Lead", cloud_agent_number="CA123")
        result = _get_extra_fields(row)
        assert result["designation"] == "lead"
        assert result["cloud_agent_number"] == "ca123"


# =====================================================================
# 12. _build_user_data
# =====================================================================

class TestBuildUserData:
    def test_without_location(self):
        extra = {
            "designation": None,
            "alternate_phone_number": None, "cloud_agent_number": None,
        }
        location = {"country_id": None, "state_id": None, "city_id": None}
        ud = _build_user_data(
            "a@x.com", "Alice", "+919876543210", "TestPass1!", UUID("11111111-1111-1111-1111-111111111111"), UUID("22222222-2222-2222-2222-222222222222"), None, location, extra,
        )
        assert ud.email == "a@x.com"
        assert not hasattr(ud, "country_id") or ud.country_id is None

    def test_with_location(self):
        extra = {
            "designation": "lead",
            "alternate_phone_number": "+911111111111", "cloud_agent_number": "ca1",
        }
        location = {"country_id": UUID("11111111-1111-1111-1111-111111111111"), "state_id": UUID("22222222-2222-2222-2222-222222222222"), "city_id": UUID("33333333-3333-3333-3333-333333333333")}
        ud = _build_user_data(
            "a@x.com", "Alice", "+919876543210", "TestPass1!", UUID("11111111-1111-1111-1111-111111111111"), UUID("22222222-2222-2222-2222-222222222222"), UUID("99999999-9999-9999-9999-999999999999"), location, extra,
        )
        assert ud.parent_id== UUID("99999999-9999-9999-9999-999999999999")
        assert ud.country_id== UUID("11111111-1111-1111-1111-111111111111")
        assert ud.state_id== UUID("22222222-2222-2222-2222-222222222222")
        assert ud.city_id== UUID("33333333-3333-3333-3333-333333333333")


# =====================================================================
# 13. _process_row
# =====================================================================

@pytest.mark.asyncio
class TestProcessRow:
    async def test_success(self):
        row = make_row()
        auth_service = MagicMock()
        auth_service.sing_up = AsyncMock(return_value=SimpleNamespace(id= UUID("42424242-4242-4242-4242-424242424242")))
        role = make_role(UUID("11111111-1111-1111-1111-111111111111"))

        status, user_id = await _process_row(
            row, auth_service, partner_id= UUID("11111111-1111-1111-1111-111111111111"),
            country_map={}, state_map={}, city_map={},
            role=role, parent_id=None,
        )
        assert status == RowProcessResult.SUCCESS
        assert user_id== UUID("42424242-4242-4242-4242-424242424242")

    async def test_email_failed_with_user_on_exception(self):
        row = make_row()
        auth_service = MagicMock()
        exc = UserCreatedButEmailFailedError("email failed")
        exc.user = SimpleNamespace(id= UUID("77777777-7777-7777-7777-777777777777"))
        auth_service.sing_up = AsyncMock(side_effect=exc)
        role = make_role(UUID("11111111-1111-1111-1111-111111111111"))

        status, user_id = await _process_row(
            row, auth_service, partner_id= UUID("11111111-1111-1111-1111-111111111111"),
            country_map={}, state_map={}, city_map={},
            role=role, parent_id=None,
        )
        assert status == RowProcessResult.EMAIL_FAILED
        assert user_id== UUID("77777777-7777-7777-7777-777777777777")

    async def test_email_failed_without_user_on_exception(self):
        row = make_row()
        auth_service = MagicMock()
        exc = UserCreatedButEmailFailedError("email failed")
        auth_service.sing_up = AsyncMock(side_effect=exc)
        role = make_role(UUID("11111111-1111-1111-1111-111111111111"))

        status, user_id = await _process_row(
            row, auth_service, partner_id= UUID("11111111-1111-1111-1111-111111111111"),
            country_map={}, state_map={}, city_map={},
            role=role, parent_id=None,
        )
        assert status == RowProcessResult.EMAIL_FAILED
        assert user_id is None

    async def test_validation_error_propagates(self):
        row = make_row(email=None)
        auth_service = MagicMock()
        auth_service.sing_up = AsyncMock()
        role = make_role(UUID("11111111-1111-1111-1111-111111111111"))

        with pytest.raises(ValueError):
            await _process_row(
                row, auth_service, partner_id= UUID("11111111-1111-1111-1111-111111111111"),
                country_map={}, state_map={}, city_map={},
                role=role, parent_id=None,
            )
        auth_service.sing_up.assert_not_called()


# =====================================================================
# 14. _handle_admin_signup
# =====================================================================

@pytest.mark.asyncio
class TestHandleAdminSignup:
    def _admin_row(self):
        return pd.Series({
            "name": "Admin", "email": "admin@example.com",
            "phone_number": "9876543210", "password": None,
        })

    async def test_success(self):
        auth_service = MagicMock()
        auth_service.sing_up = AsyncMock(return_value=SimpleNamespace(id= UUID("11111111-1111-1111-1111-111111111111")))
        user_repo = MagicMock()
        role_map = {"admin": make_role(UUID("11111111-1111-1111-1111-111111111111"))}

        result = await _handle_admin_signup(
            auth_service, user_repo, self._admin_row(), partner_id= UUID("11111111-1111-1111-1111-111111111111"), role_map=role_map,
        )
        assert result.id == UUID("11111111-1111-1111-1111-111111111111")

    async def test_creation_returns_falsy_raises(self):
        auth_service = MagicMock()
        auth_service.sing_up = AsyncMock(return_value=None)
        user_repo = MagicMock()
        role_map = {"admin": make_role(UUID("11111111-1111-1111-1111-111111111111"))}

        with pytest.raises(ValueError, match="Admin creation failed"):
            await _handle_admin_signup(
                auth_service, user_repo, self._admin_row(), partner_id= UUID("11111111-1111-1111-1111-111111111111"), role_map=role_map,
            )

    async def test_email_failed_with_user_attr(self):
        auth_service = MagicMock()
        exc = UserCreatedButEmailFailedError("fail")
        exc.user = SimpleNamespace(id= UUID("55555555-5555-5555-5555-555555555555"))
        auth_service.sing_up = AsyncMock(side_effect=exc)
        user_repo = MagicMock()
        role_map = {"admin": make_role(UUID("11111111-1111-1111-1111-111111111111"))}

        result = await _handle_admin_signup(
            auth_service, user_repo, self._admin_row(), partner_id= UUID("11111111-1111-1111-1111-111111111111"), role_map=role_map,
        )
        assert result.id == UUID("55555555-5555-5555-5555-555555555555")

    async def test_email_failed_without_user_refetch_success(self):
        auth_service = MagicMock()
        exc = UserCreatedButEmailFailedError("fail")
        auth_service.sing_up = AsyncMock(side_effect=exc)
        user_repo = MagicMock()
        user_repo.get_admin_details_by_partner_id = AsyncMock(
            return_value=SimpleNamespace(id= UUID("99999999-9999-9999-9999-999999999999"))
        )
        role_map = {"admin": make_role(UUID("11111111-1111-1111-1111-111111111111"))}

        result = await _handle_admin_signup(
            auth_service, user_repo, self._admin_row(), partner_id= UUID("11111111-1111-1111-1111-111111111111"), role_map=role_map,
        )
        assert result.id == UUID("99999999-9999-9999-9999-999999999999")

    async def test_email_failed_without_user_refetch_fails(self):
        auth_service = MagicMock()
        exc = UserCreatedButEmailFailedError("fail")
        auth_service.sing_up = AsyncMock(side_effect=exc)
        user_repo = MagicMock()
        user_repo.get_admin_details_by_partner_id = AsyncMock(return_value=None)
        role_map = {"admin": make_role(UUID("11111111-1111-1111-1111-111111111111"))}

        with pytest.raises(ValueError, match="Admin creation failed after email error"):
            await _handle_admin_signup(
                auth_service, user_repo, self._admin_row(), partner_id= UUID("11111111-1111-1111-1111-111111111111"), role_map=role_map,
            )


# =====================================================================
# 15. create_bulk_users (celery task)
# =====================================================================

class TestCreateBulkUsersTask:
    """
    `create_bulk_users` is a `bind=True` celery task, so `self` is supplied
    automatically by Celery's Task descriptor when you call `.run(...)` on
    the task object directly -- you must NOT pass `self` yourself (that's
    what caused the earlier "multiple values for argument" TypeError).
    `self.request` resolves to Celery's default empty Context (id=None)
    outside of a real worker, which is fine since the task only reads
    `self.request.id` for logging.
    """

    def test_missing_user_id_returns_failure_dict(self):
        result = create_bulk_users.run(
            current_user={}, file_data_b64="", partner_id= UUID("11111111-1111-1111-1111-111111111111"), filename="f.csv",
        )
        assert result["total_success_count"] == 0
        assert "user_id is missing" in result["failed_reasons"][0]["reason"]

    def test_invalid_base64_returns_failure_dict(self):
        result = create_bulk_users.run(
            current_user={"user_id": UUID("11111111-1111-1111-1111-111111111111")},
            file_data_b64="not-valid-base64-!!!",
            partner_id= UUID("11111111-1111-1111-1111-111111111111"),
            filename="f.csv",
        )
        assert result["total_success_count"] == 0
        assert "Invalid file data" in result["failed_reasons"][0]["reason"]

    def test_success_delegates_to_process_bulk_users(self):
        expected = {
            "total_success_count": 1,
            "total_failed_count": 0, "failed_reasons": [],
        }
        with patch.object(
            tasks_module, "process_bulk_users", new=AsyncMock(return_value=expected)
        ):
            encoded = base64.b64encode(b"dummy").decode()
            result = create_bulk_users.run(
                current_user={"user_id": UUID("11111111-1111-1111-1111-111111111111")},
                file_data_b64=encoded,
                partner_id= UUID("11111111-1111-1111-1111-111111111111"),
                filename="f.csv",
            )
        assert result == expected

    def test_downstream_exception_is_caught(self):
        with patch.object(
            tasks_module, "process_bulk_users",
            new=AsyncMock(side_effect=RuntimeError("boom")),
        ):
            encoded = base64.b64encode(b"dummy").decode()
            result = create_bulk_users.run(
                current_user={"user_id": UUID("11111111-1111-1111-1111-111111111111")},
                file_data_b64=encoded,
                partner_id= UUID("11111111-1111-1111-1111-111111111111"),
                filename="f.csv",
            )
        assert result["total_success_count"] == 0
        assert "boom" in result["failed_reasons"][0]["reason"]


# =====================================================================
# 16. _resolve_admin
# =====================================================================

@pytest.mark.asyncio
class TestResolveAdmin:
    def _df(self, roles):
        return pd.DataFrame({"role": roles})

    async def test_admin_exists_valid_id_skips_csv_admins(self):
        df = self._df(["admin", "manager"])
        user_repo = MagicMock()
        user_repo.get_admin_details_by_partner_id = AsyncMock(
            return_value=SimpleNamespace(id= UUID("10101010-1010-1010-1010-101010101010"))
        )
        auth_service = MagicMock()
        role_map = {}

        admin_id, skipped, created_idx = await _resolve_admin(
            df, user_repo, auth_service, partner_id= UUID("11111111-1111-1111-1111-111111111111"), role_map=role_map,
        )
        assert admin_id== UUID("10101010-1010-1010-1010-101010101010")
        assert skipped == {0}
        assert created_idx is None

    async def test_no_admin_no_csv_admin_raises(self):
        df = self._df(["manager"])
        user_repo = MagicMock()
        user_repo.get_admin_details_by_partner_id = AsyncMock(return_value=None)
        auth_service = MagicMock()

        with pytest.raises(ValueError, match="Admin is required"):
            await _resolve_admin(df, user_repo, auth_service, partner_id= UUID("11111111-1111-1111-1111-111111111111"), role_map={})

    async def test_no_admin_creates_from_first_csv_admin_row(self):
        df = pd.DataFrame({
            "role": ["admin", "admin", "manager"],
            "name": ["Admin One", "Admin Two", "Manager One"],
            "email": ["a1@x.com", "a2@x.com", "m1@x.com"],
            "phone_number": ["9876543210", "9876543211", "9876543212"],
        })
        user_repo = MagicMock()
        user_repo.get_admin_details_by_partner_id = AsyncMock(return_value=None)
        auth_service = MagicMock()
        auth_service.sing_up = AsyncMock(return_value=SimpleNamespace(id= UUID("99999999-9999-9999-9999-999999999999")))
        role_map = {"admin": make_role(UUID("11111111-1111-1111-1111-111111111111"))}

        admin_id, skipped, created_idx = await _resolve_admin(
            df, user_repo, auth_service, partner_id= UUID("11111111-1111-1111-1111-111111111111"), role_map=role_map,
        )
        assert admin_id== UUID("99999999-9999-9999-9999-999999999999")
        assert skipped == {1}
        assert created_idx == 0

    async def test_admin_invalid_id_falls_through_to_csv_creation(self):
        df = pd.DataFrame({
            "role": ["admin"],
            "name": ["Admin One"],
            "email": ["a1@x.com"],
            "phone_number": ["9876543210"],
        })
        user_repo = MagicMock()
        user_repo.get_admin_details_by_partner_id = AsyncMock(
            return_value=SimpleNamespace(id=None)
        )
        auth_service = MagicMock()
        auth_service.sing_up = AsyncMock(return_value=SimpleNamespace(id= UUID("55555555-5555-5555-5555-555555555555")))
        role_map = {"admin": make_role(UUID("11111111-1111-1111-1111-111111111111"))}

        admin_id, skipped, created_idx = await _resolve_admin(
            df, user_repo, auth_service, partner_id= UUID("11111111-1111-1111-1111-111111111111"), role_map=role_map,
        )
        assert admin_id== UUID("55555555-5555-5555-5555-555555555555")
        assert created_idx == 0


# =====================================================================
# 17. Parent dependency graph helpers
# =====================================================================

class TestParentDependencyGraph:
    def _df(self):
        return pd.DataFrame({
            "_row_email": ["u1@x.com", "u2@x.com", "u3@x.com"],
            "_duplicate_email": [False, False, False],
            "_parent_ref": [None, "u1@x.com", "ghost@x.com"],
        })

    def test_build_email_index_basic(self):
        df = self._df()
        idx = _build_email_index(df, skipped_admin_indexes=set(), created_admin_row_index=None)
        assert idx == {"u1@x.com": 0, "u2@x.com": 1, "u3@x.com": 2}

    def test_build_email_index_excludes_admin_and_duplicates(self):
        df = self._df()
        df.loc[2, "_duplicate_email"] = True
        idx = _build_email_index(df, skipped_admin_indexes={0}, created_admin_row_index=None)
        assert idx == {"u2@x.com": 1}

    def test_classify_default_admin(self):
        row = pd.Series({"_parent_ref": None, "_row_email": "u@x.com"})
        result = _classify_parent_ref(row, admin_id= UUID("11111111-1111-1111-1111-111111111111"), email_to_idx={}, external_lookup={})
        assert result == {"parent_id": UUID("11111111-1111-1111-1111-111111111111"), "source": "default_admin", "depends_on_idx": None}

    def test_classify_self_ref(self):
        row = pd.Series({"_parent_ref": "u@x.com", "_row_email": "u@x.com"})
        result = _classify_parent_ref(row, admin_id= UUID("11111111-1111-1111-1111-111111111111"), email_to_idx={}, external_lookup={})
        assert result["source"] == "self_ref"

    def test_classify_in_batch(self):
        row = pd.Series({"_parent_ref": "p@x.com", "_row_email": "u@x.com"})
        result = _classify_parent_ref(
            row, admin_id= UUID("11111111-1111-1111-1111-111111111111"), email_to_idx={"p@x.com": 3}, external_lookup={},
        )
        assert result == {"parent_id": None, "source": "in_batch", "depends_on_idx": 3}

    def test_classify_external_db(self):
        row = pd.Series({"_parent_ref": "p@x.com", "_row_email": "u@x.com"})
        result = _classify_parent_ref(
            row, admin_id= UUID("11111111-1111-1111-1111-111111111111"), email_to_idx={}, external_lookup={"p@x.com": {"id": UUID("77777777-7777-7777-7777-777777777777")}},
        )
        assert result == {"parent_id": UUID("77777777-7777-7777-7777-777777777777"), "source": "external_db", "depends_on_idx": None}

    def test_classify_not_found(self):
        row = pd.Series({"_parent_ref": "nowhere@x.com", "_row_email": "u@x.com"})
        result = _classify_parent_ref(row, admin_id= UUID("11111111-1111-1111-1111-111111111111"), email_to_idx={}, external_lookup={})
        assert result["source"] == "not_found"

    def test_build_parent_plan_end_to_end(self):
        df = self._df()
        plan = _build_parent_plan(
            df, admin_id= UUID("11111111-1111-1111-1111-111111111111"), skipped_admin_indexes=set(),
            created_admin_row_index=None, external_lookup={},
        )
        assert plan[0]["source"] == "default_admin"
        assert plan[1]["source"] == "in_batch"
        assert plan[2]["source"] == "not_found"

    def test_compute_immediate_failures(self):
        plan = {
            0: {"source": "self_ref"},
            1: {"source": "not_found"},
            2: {"source": "in_batch"},
        }
        df = pd.DataFrame({"_parent_ref": [None, "ghost@x.com", "a@x.com"]})
        failures = _compute_immediate_failures(plan, df)
        assert failures[0] == ValidationMsg.PARENT_SELF_REF
        assert "ghost@x.com" in failures[1]
        assert 2 not in failures

    def test_build_dependency_graph(self):
        plan = {
            0: {"source": "default_admin"},
            1: {"source": "in_batch", "depends_on_idx": 0},
            2: {"source": "in_batch", "depends_on_idx": 1},
        }
        children, in_degree = _build_dependency_graph(plan)
        assert children[0] == [1]
        assert children[1] == [2]
        assert in_degree == {0: 0, 1: 1, 2: 1}

    def test_children_lists_are_independent_objects(self):
        # Regression test for the fromkeys-aliasing bug called out in the
        # source comments: each row's children list must be its own object.
        plan = {0: {"source": "default_admin"}, 1: {"source": "default_admin"}}
        children, _ = _build_dependency_graph(plan)
        children[0].append(99)
        assert children[1] == []

    def test_cascade_failures_multi_level(self):
        children = {0: [1], 1: [2], 2: []}
        failed_idx = {0}
        immediate_failures = {0: "root failure"}
        _cascade_failures([0], children, failed_idx, immediate_failures)
        assert failed_idx == {0, 1, 2}
        assert immediate_failures[1] == ValidationMsg.PARENT_ROW_FAILED
        assert immediate_failures[2] == ValidationMsg.PARENT_ROW_FAILED

    def test_cascade_failures_does_not_revisit(self):
        children = {0: [1], 1: [0]}  # cycle-ish shape, should terminate
        failed_idx = {0}
        immediate_failures = {}
        _cascade_failures([0], children, failed_idx, immediate_failures)
        assert failed_idx == {0, 1}


# =====================================================================
# 18. _resolve_external_parents
# =====================================================================

@pytest.mark.asyncio
class TestResolveExternalParents:
    async def test_only_non_in_batch_refs_are_looked_up(self):
        df = pd.DataFrame({
            "_row_email": ["u1@x.com", "u2@x.com"],
            "_duplicate_email": [False, False],
            "_parent_ref": ["u1@x.com", "external@x.com"],
        })
        user_repo = MagicMock()
        user_repo.get_users_id_hierarchy_by_emails = AsyncMock(
            return_value={"external@x.com": {"id": UUID("55555555-5555-5555-5555-555555555555")}}
        )

        result = await _resolve_external_parents(
            df, user_repo, skipped_admin_indexes=set(), created_admin_row_index=None,
        )
        assert result == {"external@x.com": {"id": UUID("55555555-5555-5555-5555-555555555555")}}
        called_with = user_repo.get_users_id_hierarchy_by_emails.call_args.args[0]
        assert called_with == ["external@x.com"]


# =====================================================================
# 19. _run_waves
# =====================================================================

@pytest.mark.asyncio
class TestRunWaves:
    def _base_kwargs(self, df, plan):
        children, in_degree = _build_dependency_graph(plan)
        return dict(
            plan=plan, df=df, children=children, in_degree=in_degree,
            failed_idx=set(), immediate_failures={},
            partner_id= UUID("11111111-1111-1111-1111-111111111111"), country_map={}, state_map={}, city_map={},
            role_map={"manager": make_role(UUID("11111111-1111-1111-1111-111111111111"))},
            user_repo=MagicMock(),
        )

    async def test_single_row_success(self):
        df = pd.DataFrame([make_row()])
        plan = {0: {"parent_id": None, "source": "default_admin", "depends_on_idx": None}}
        auth_service = MagicMock()
        auth_service.sing_up = AsyncMock(return_value=SimpleNamespace(id= UUID("11111111-1111-1111-1111-111111111111")))

        kwargs = self._base_kwargs(df, plan)
        results = await _run_waves(auth_service=auth_service, **kwargs)

        assert len(results) == 1
        idx, row_out, status, user_id, exc = results[0]
        assert status == RowProcessResult.SUCCESS
        assert user_id== UUID("11111111-1111-1111-1111-111111111111")
        assert exc is None

    async def test_chain_resolves_parent_id_across_waves(self):
        df = pd.DataFrame([
            make_row(email="parent@x.com", _row_email="parent@x.com"),
            make_row(email="child@x.com", _row_email="child@x.com"),
        ])
        plan = {
            0: {"parent_id": None, "source": "default_admin", "depends_on_idx": None},
            1: {"parent_id": None, "source": "in_batch", "depends_on_idx": 0},
        }
        auth_service = MagicMock()
        auth_service.sing_up = AsyncMock(
            side_effect=[SimpleNamespace(id= UUID("10010010-0100-1001-0010-010010010010")), SimpleNamespace(id= UUID("20020020-0200-2002-0020-020020020020"))]
        )
        kwargs = self._base_kwargs(df, plan)
        results = await _run_waves(auth_service=auth_service, **kwargs)

        by_idx = {r[0]: r for r in results}
        assert by_idx[1][1]["_resolved_parent_id"] == UUID("10010010-0100-1001-0010-010010010010")

    async def test_row_creation_failure_cascades_to_children(self):
        df = pd.DataFrame([
            make_row(email="parent@x.com", _row_email="parent@x.com"),
            make_row(email="child@x.com", _row_email="child@x.com"),
        ])
        plan = {
            0: {"parent_id": None, "source": "default_admin", "depends_on_idx": None},
            1: {"parent_id": None, "source": "in_batch", "depends_on_idx": 0},
        }
        auth_service = MagicMock()
        auth_service.sing_up = AsyncMock(side_effect=RuntimeError("db down"))
        kwargs = self._base_kwargs(df, plan)
        results = await _run_waves(auth_service=auth_service, **kwargs)

        by_idx = {r[0]: r for r in results}
        assert by_idx[0][4] is not None  # row 0 itself failed
        # row 1 never got a chance to run (its parent failed) -> not in results,
        # but must show up in immediate_failures via cascade.
        assert kwargs["immediate_failures"].get(1) == ValidationMsg.PARENT_ROW_FAILED

    async def test_cycle_detected_as_parent_cycle(self):
        # Two rows that depend on each other -> in_degree never reaches 0 for either.
        df = pd.DataFrame([
            make_row(email="a@x.com", _row_email="a@x.com"),
            make_row(email="b@x.com", _row_email="b@x.com"),
        ])
        plan = {
            0: {"parent_id": None, "source": "in_batch", "depends_on_idx": 1},
            1: {"parent_id": None, "source": "in_batch", "depends_on_idx": 0},
        }
        auth_service = MagicMock()
        auth_service.sing_up = AsyncMock()
        kwargs = self._base_kwargs(df, plan)
        results = await _run_waves(auth_service=auth_service, **kwargs)

        assert results == []
        assert kwargs["immediate_failures"][0] == ValidationMsg.PARENT_CYCLE
        assert kwargs["immediate_failures"][1] == ValidationMsg.PARENT_CYCLE

    async def test_role_lookup_failure_is_caught_per_row(self):
        df = pd.DataFrame([make_row(role="ghost-role")])
        plan = {0: {"parent_id": None, "source": "default_admin", "depends_on_idx": None}}
        auth_service = MagicMock()
        auth_service.sing_up = AsyncMock()
        kwargs = self._base_kwargs(df, plan)
        results = await _run_waves(auth_service=auth_service, **kwargs)

        idx, row_out, status, user_id, exc = results[0]
        assert exc is not None
        assert status is None
        auth_service.sing_up.assert_not_called()


# =====================================================================
# 20. _merge_bookkeeping_results
# =====================================================================

class TestMergeBookkeepingResults:
    def test_duplicate_email_row_gets_bookkeeping_entry(self):
        df = pd.DataFrame([make_row(_duplicate_email=True)])
        result = _merge_bookkeeping_results(
            df, all_results=[], immediate_failures={},
            skipped_admin_indexes=set(), created_admin_row_index=None, admin_id= UUID("11111111-1111-1111-1111-111111111111"),
        )
        assert "already appears earlier" in str(result[0][4])

    def test_skipped_admin_row_message_when_admin_created_in_file(self):
        df = pd.DataFrame([make_row(), make_row()])
        result = _merge_bookkeeping_results(
            df, all_results=[], immediate_failures={},
            skipped_admin_indexes={1}, created_admin_row_index=0, admin_id= UUID("11111111-1111-1111-1111-111111111111"),
        )
        assert "extra Admin row was skipped" in str(result[1][4])

    def test_skipped_admin_row_message_when_admin_pre_existing(self):
        df = pd.DataFrame([make_row()])
        result = _merge_bookkeeping_results(
            df, all_results=[], immediate_failures={},
            skipped_admin_indexes={0}, created_admin_row_index=None, admin_id= UUID("11111111-1111-1111-1111-111111111111"),
        )
        assert "Admin already exists" in str(result[0][4])

    def test_created_admin_row_marked_success(self):
        df = pd.DataFrame([make_row()])
        result = _merge_bookkeeping_results(
            df, all_results=[], immediate_failures={},
            skipped_admin_indexes=set(), created_admin_row_index=0, admin_id= UUID("42424242-4242-4242-4242-424242424242"),
        )
        idx, row_out, status, user_id, exc = result[0]
        assert status == RowProcessResult.SUCCESS
        assert user_id== UUID("42424242-4242-4242-4242-424242424242")
        assert exc is None

    def test_wave_results_take_precedence_over_bookkeeping(self):
        df = pd.DataFrame([make_row()])
        wave_result = (0, {"email": "x"}, RowProcessResult.SUCCESS, 1, None)
        result = _merge_bookkeeping_results(
            df, all_results=[wave_result], immediate_failures={},
            skipped_admin_indexes=set(), created_admin_row_index=None, admin_id= UUID("11111111-1111-1111-1111-111111111111"),
        )
        assert result[0] == wave_result

    def test_immediate_failure_not_in_wave_results_gets_entry(self):
        df = pd.DataFrame([make_row()])
        result = _merge_bookkeeping_results(
            df, all_results=[], immediate_failures={0: "cycle"},
            skipped_admin_indexes=set(), created_admin_row_index=None, admin_id= UUID("11111111-1111-1111-1111-111111111111"),
        )
        assert "cycle" in str(result[0][4])


# =====================================================================
# 21. _collate_results
# =====================================================================

class TestCollateResults:
    def test_success_row(self):
        result_map = {
            0: (0, {"email": "a@x.com", "name": "A"}, RowProcessResult.SUCCESS, 1, None),
        }
        rows, success, failed, reasons = _collate_results(result_map)
        assert success == 1 and failed == 0
        assert rows[0]["status"] == "Success"
        assert rows[0]["user_id"] == 1
        assert reasons == []

    def test_email_failed_reason_set(self):
        result_map = {
            0: (0, {"email": "a@x.com"}, RowProcessResult.EMAIL_FAILED, 1, None),
        }
        rows, success, failed, reasons = _collate_results(result_map)
        assert "welcome email could not be sent" in rows[0]["reason"]
        assert success == 1

    def test_failure_row(self):
        result_map = {
            0: (0, {"email": "a@x.com", "name": "A"}, None, None, ValueError("bad email")),
        }
        rows, success, failed, reasons = _collate_results(result_map)
        assert failed == 1 and success == 0
        assert rows[0]["status"] == "Failure"
        assert rows[0]["reason"] == "bad email"
        assert reasons[0]["email"] == "a@x.com"

    def test_internal_columns_stripped(self):
        row_dict = {
            "email": "a@x.com", "_duplicate_email": False,
            "_row_email": "a@x.com", "_parent_ref": None,
            "_resolved_parent_id": UUID("55555555-5555-5555-5555-555555555555"),
        }
        result_map = {0: (0, row_dict, RowProcessResult.SUCCESS, 1, None)}
        rows, *_ = _collate_results(result_map)
        assert "_duplicate_email" not in rows[0]
        assert "_row_email" not in rows[0]
        assert "_parent_ref" not in rows[0]
        assert rows[0]["parent_id"] == UUID("55555555-5555-5555-5555-555555555555")

    def test_sorted_by_index(self):
        result_map = {
            2: (2, {"email": "c@x.com"}, RowProcessResult.SUCCESS, 3, None),
            0: (0, {"email": "a@x.com"}, RowProcessResult.SUCCESS, 1, None),
            1: (1, {"email": "b@x.com"}, RowProcessResult.SUCCESS, 2, None),
        }
        rows, *_ = _collate_results(result_map)
        assert [r["email"] for r in rows] == ["a@x.com", "b@x.com", "c@x.com"]


# =====================================================================
# 22. _process_rows_with_parent_resolution (orchestrator)
# =====================================================================

@pytest.mark.asyncio
class TestProcessRowsWithParentResolution:
    async def test_end_to_end_simple_success(self):
        df = pd.DataFrame([make_row()])
        auth_service = MagicMock()
        auth_service.sing_up = AsyncMock(return_value=SimpleNamespace(id= UUID("11111111-1111-1111-1111-111111111111")))
        user_repo = MagicMock()
        user_repo.get_users_id_hierarchy_by_emails = AsyncMock(return_value={})

        rows, success, failed, reasons = await _process_rows_with_parent_resolution(
            df, auth_service, user_repo, partner_id= UUID("11111111-1111-1111-1111-111111111111"),
            country_map={}, state_map={}, city_map={},
            role_map={"manager": make_role(UUID("11111111-1111-1111-1111-111111111111"))}, admin_id= UUID("11111111-1111-1111-1111-111111111111"),
            skipped_admin_indexes=set(), created_admin_row_index=None,
        )
        assert success == 1
        assert failed == 0
        assert reasons == []

    async def test_end_to_end_self_ref_fails(self):
        df = pd.DataFrame([make_row(parent="user@example.com", _parent_ref="user@example.com")])
        auth_service = MagicMock()
        auth_service.sing_up = AsyncMock()
        user_repo = MagicMock()
        user_repo.get_users_id_hierarchy_by_emails = AsyncMock(return_value={})

        rows, success, failed, reasons = await _process_rows_with_parent_resolution(
            df, auth_service, user_repo, partner_id= UUID("11111111-1111-1111-1111-111111111111"),
            country_map={}, state_map={}, city_map={},
            role_map={"manager": make_role(UUID("11111111-1111-1111-1111-111111111111"))}, admin_id= UUID("11111111-1111-1111-1111-111111111111"),
            skipped_admin_indexes=set(), created_admin_row_index=None,
        )
        assert failed == 1
        assert success == 0
        auth_service.sing_up.assert_not_called()


# =====================================================================
# 23. process_bulk_users (top-level orchestrator)
# =====================================================================

@pytest.mark.asyncio
class TestProcessBulkUsers:
    async def test_full_flow(self):
        csv_bytes = (
            b"email,phone_number,name,role\n"
            b"admin@example.com,9876543210,Admin,Admin\n"
        )

        auth_service = MagicMock()
        auth_service.sing_up = AsyncMock(return_value=SimpleNamespace(id= UUID("11111111-1111-1111-1111-111111111111")))

        location_repo = MagicMock()
        location_repo.get_all_countries = AsyncMock(return_value=[])
        location_repo.get_all_states = AsyncMock(return_value=[])
        location_repo.get_all_cities = AsyncMock(return_value=[])

        user_repo = MagicMock()
        user_repo.get_admin_details_by_partner_id = AsyncMock(return_value=None)
        user_repo.get_users_id_hierarchy_by_emails = AsyncMock(return_value={})

        auth_repo = MagicMock()
        auth_repo.get_all_role = AsyncMock(return_value=[make_role_with_name("admin", UUID("11111111-1111-1111-1111-111111111111"))])

        container = SimpleNamespace(
            auth_service=SimpleNamespace(async_=AsyncMock(return_value=auth_service)),
            auth_repository=lambda: auth_repo,
            location_repository=lambda: location_repo,
            console_service=AsyncMock(return_value=user_repo),
        )

        with patch.object(tasks_module.celery, "container", container):
            result = await process_bulk_users(
                csv_bytes, partner_id= UUID("11111111-1111-1111-1111-111111111111"), user_id= UUID("11111111-1111-1111-1111-111111111111"), filename="users.csv",
            )

        assert result["total_success_count"] == 1
        assert result["total_failed_count"] == 0


def make_role_with_name(name: str, role_id):
    return SimpleNamespace(id=role_id, name=name)


# =====================================================================
# 24. process_api_log
# =====================================================================

class TestProcessApiLog:
    def test_returns_ignored_status(self):
        # No bind=True here, so no `self` to worry about -- call .run() directly.
        result = process_api_log.run({"some": "payload"})
        assert result == {"status": "ignored"}