import pytest

from src.components.user.filter_builder import UserRoleFilterBuilder
from src.exceptions import UserException


class TestUserRoleFilterBuilder:

    def test_requires_role_join_true_for_role_field(self):
        assert UserRoleFilterBuilder.requires_role_join(["role_name"]) is True

    def test_requires_role_join_true_when_mixed_with_user_field(self):
        assert UserRoleFilterBuilder.requires_role_join(["email", "role_id"]) is True

    def test_requires_role_join_false_for_user_field(self):
        assert UserRoleFilterBuilder.requires_role_join(["email"]) is False

    def test_requires_role_join_false_for_empty(self):
        assert UserRoleFilterBuilder.requires_role_join([]) is False

    def test_requires_role_join_false_for_none(self):
        assert UserRoleFilterBuilder.requires_role_join(None) is False

    def test_resolve_field_from_models_unknown_field_raises(self):
        builder = UserRoleFilterBuilder(criteria=None, base_query=None)
        with pytest.raises(UserException):
            builder._resolve_field_from_models("not_a_real_field")

    def test_resolve_field_from_models_user_field(self):
        builder = UserRoleFilterBuilder(criteria=None, base_query=None)
        col = builder._resolve_field_from_models("email")
        assert col.key == "email"

    def test_resolve_field_from_models_role_field(self):
        builder = UserRoleFilterBuilder(criteria=None, base_query=None)
        col = builder._resolve_field_from_models("role_name")
        assert col.key == "name"

    def test_resolve_field_from_models_alias_maps_to_same_column_as_canonical_name(self):
        builder = UserRoleFilterBuilder(criteria=None, base_query=None)
        assert builder._resolve_field_from_models("status") is builder._resolve_field_from_models("is_active")

    def test_handle_custom_filter_email_uses_ilike(self):
        from sqlalchemy import select
        from src.components.user.models import User

        builder = UserRoleFilterBuilder(criteria=None, base_query=None)
        query = select(User)
        result = builder.handle_custom_filter(query, "email", "john")

        # .ilike() compiles to lower(col) LIKE lower(value), not a literal "ilike"
        compiled = str(result).lower()
        assert "lower(console_users.email) like" in compiled

    def test_handle_custom_filter_returns_none_for_other_fields(self):
        from sqlalchemy import select
        from src.components.user.models import User

        builder = UserRoleFilterBuilder(criteria=None, base_query=None)
        query = select(User)
        result = builder.handle_custom_filter(query, "name", "john")

        assert result is None

    def test_init_stores_partner_id(self):
        builder = UserRoleFilterBuilder(criteria=None, base_query=None, partner_id=42)
        assert builder.partner_id == 42

    def test_init_defaults_partner_id_to_none(self):
        builder = UserRoleFilterBuilder(criteria=None, base_query=None)
        assert builder.partner_id is None
