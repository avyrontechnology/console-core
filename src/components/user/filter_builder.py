from typing import List, Optional
from sqlalchemy import select, and_
from sqlalchemy.orm import Query

from src.components.filters.builder import BaseFilterBuilder
from src.components.filters.criteria import BaseFilterCriteria
from src.components.user.models import User
from src.components.auth.models import Role
from src.exceptions import UserException


class UserRoleFilterBuilder(BaseFilterBuilder):
    """
    Resolves User Listing filter/sort fields onto the User and Role columns.

    Adding a new filterable listing column is a one line change: add its name to
    FIELD_ALIASES (plus DATE_FIELDS if it is an epoch millisecond column). The
    map doubles as the allow list, so nothing is filterable unless it is a real
    listing column.

    NOTE (follow up, out of scope here): the frequently filtered columns want
    indexes. console_users.is_active, .role_id, .partner_id and .is_internal are
    already indexed; console_users.created_at, .updated_at and .current_status
    are not and should get one in a migration.
    """

    # Listing field name -> (model, column). Friendly aliases (status,
    # availability, role, created_date...) point at the same columns so the UI
    # can send either the column name or the listing label.
    FIELD_ALIASES = {
        # User fields
        "id": ("User", "id"),
        "name": ("User", "name"),
        "email": ("User", "email"),
        "phone_number": ("User", "phone_number"),
        "alternate_phone_number": ("User", "alternate_phone_number"),
        "is_active": ("User", "is_active"),
        "status": ("User", "is_active"),
        "designation": ("User", "designation"),
        "description": ("User", "description"),
        "is_maglo_enabled": ("User", "is_maglo_enabled"),
        "is_talko_enabled": ("User", "is_talko_enabled"),
        "is_babbler_enabled": ("User", "is_babbler_enabled"),
        "is_maglo_publisher": ("User", "is_maglo_publisher"),
        "is_internal": ("User", "is_internal"),
        "is_staff": ("User", "is_staff"),
        "is_admin": ("User", "is_admin"),
        "is_suspended": ("User", "is_suspended"),
        "is_email_verified": ("User", "is_email_verified"),
        "is_phone_number_verified": ("User", "is_phone_number_verified"),
        "created_at": ("User", "created_at"),
        "created_date": ("User", "created_at"),
        "updated_at": ("User", "updated_at"),
        "updated_date": ("User", "updated_at"),
        "is_deleted": ("User", "is_deleted"),
        "country_id": ("User", "country_id"),
        "state_id": ("User", "state_id"),
        "city_id": ("User", "city_id"),
        "parent_id": ("User", "parent_id"),
        "partner_id": ("User", "partner_id"),
        "created_by": ("User", "created_by"),
        "updated_by": ("User", "updated_by"),
        "cloud_agent_number": ("User", "cloud_agent_number"),
        # Availability lives on console_users itself: the user tracker endpoints
        # read and write this same column, so no join or extra call is needed.
        "current_status": ("User", "current_status"),
        "availability": ("User", "current_status"),

        # Role fields
        "role_id": ("Role", "id"),
        "role": ("Role", "name"),
        "role_name": ("Role", "name"),
        "role_slug": ("Role", "slug"),
        "role_hierarchy": ("Role", "hierarchy"),
        "role_description": ("Role", "description"),
        "role_is_active": ("Role", "is_active"),
        "role_is_internal": ("Role", "is_internal"),
        "role_created_at": ("Role", "created_at"),
        "role_updated_at": ("Role", "updated_at"),
        "role_is_deleted": ("Role", "is_deleted"),
    }

    # Epoch millisecond columns, compared against day boundaries.
    DATE_FIELDS = {
        "created_at",
        "created_date",
        "updated_at",
        "updated_date",
        "role_created_at",
        "role_updated_at",
    }

    date_fields = DATE_FIELDS

    @classmethod
    def requires_role_join(cls, field_names) -> bool:
        """
        True when any of the given filter fields resolves to a Role column.

        The hierarchy based user listing selects from User alone, so it only
        joins console_role when a role_* filter actually needs it.
        """
        return any(
            cls.FIELD_ALIASES.get(field_name, (None, None))[0] == "Role"
            for field_name in field_names or []
        )

    def __init__(self, criteria: BaseFilterCriteria, base_query: Query, partner_id: int | None = None):
        # Pass both User and Role models to the base class
        super().__init__([User, Role], criteria, base_query)
        self.partner_id = partner_id

    def handle_custom_filter(self, query, field_name, value):
        if field_name == "email":
            return query.filter(User.email.ilike(f"%{value}%"))

    def _resolve_field_from_models(self, field_name: str):
        if field_name not in self.FIELD_ALIASES:
            raise UserException(
                f"Field '{field_name}' does not exist in User or Role models"
            )

        model_name, actual_field_name = self.FIELD_ALIASES[field_name]

        if model_name == "User":
            return getattr(User, actual_field_name)
        return getattr(Role, actual_field_name)
