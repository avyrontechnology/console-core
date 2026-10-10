import re
from typing import Any, Dict, List, Optional, Set

from pydantic import (
    BaseModel,
    ConfigDict,
    EmailStr,
    Field,
    field_validator,
    model_validator,
)

from src.components.auth.constant import AuthExceptionMsg, UserNameLength
from src.components.filters.constants import FilterOperator
from src.components.user_tracker.constants import UserTrackerValidation


class Contrasts:
    class UpdateUserData(BaseModel):
        name: Optional[str] = Field(
            None,
            min_length=UserNameLength.NAME_MIN_LENGTH,
            max_length=UserNameLength.NAME_MAX_LENGTH,
        )
        password: Optional[str] = None
        email: Optional[EmailStr] = None
        designation: Optional[str] = None
        phone_number: Optional[str] = None
        parent_id: Optional[int] = None
        partner_id: Optional[int] = None
        role_id: Optional[int] = None
        country_id: Optional[int] = None
        state_id: Optional[int] = None
        city_id: Optional[int] = None
        is_maglo_publisher: Optional[bool] = None
        is_active: Optional[bool] = None
        is_internal: Optional[bool] = False
        is_maglo_enabled: Optional[bool] = False
        is_talko_enabled: Optional[bool] = False
        is_babbler_enabled: Optional[bool] = False
        cloud_agent_number: Optional[str] = None
        current_status: Optional[str] = Field(
            default=None, max_length=UserTrackerValidation.STATUS_MAX_LENGTH
        )

        @field_validator("password")
        def validate_password(cls, password: str) -> str:
            regex = (
                r"^(?=.*[A-Z])(?=.*[a-z])(?=.*\d)(?=.*[!@#$%^&*(),.?\":{}|<>]).{8,}$"
            )
            if not re.match(regex, password):
                raise ValueError(AuthExceptionMsg.PASSWORD_NOT_STRONG)
            return password

        @field_validator("name")
        def validate_name(cls, value):
            # Regex for valid name (allow spaces, hyphens, and apostrophes)
            if not re.match(r"^[A-Za-z]+([ ]?[A-Za-z]+)*$", value):
                raise ValueError("Name contains invalid characters")
            return value

        @field_validator("phone_number")
        def validate_international_phone(cls, value):
            if value is None:
                return value
            pattern = r"^\+[1-9]\d{7,14}$"
            if not re.match(pattern, value):
                raise ValueError("Enter a valid phone number (e.g., +919988776655).")
            return value

        @field_validator("cloud_agent_number")
        def validate_cloud_agent_number(cls, value) -> Any:
            if value is None:
                return value
            return value
        
        @field_validator("is_active", mode="before")
        def validate_is_active_type(cls, value: Any) -> Optional[bool]:
            if value is None:
                return value
            if not isinstance(value, bool):
                raise ValueError(
                    "is_active must be a boolean (true or false), "
                    "got: {}".format(type(value).__name__)
                )
            return value
        
    class ParentUserResponse(BaseModel):
        id: int
        name: str
        designation: Optional[str] = None
        email: Optional[str] = None

        model_config = ConfigDict(
            from_attributes=True,
        )

    class GetUserDetailResponse(BaseModel):
        id: int
        name: str
        email: Optional[str] = None
        designation: Optional[str] = None
        phone_number: Optional[str] = None
        alternate_phone_number: Optional[str] = None
        created_at: Optional[int] = None
        is_active: Optional[bool] = None
        is_walkthrough_completed: Optional[bool] = False

        model_config = ConfigDict(
            from_attributes=True,
        )


class UserRoleCombinedResponse(BaseModel):
    """Schema for combined user and role information."""

    # User fields
    id: int
    name: Optional[str] = None
    email: Optional[str] = None
    phone_number: Optional[str] = None
    is_active: bool
    designation: Optional[str] = None
    description: Optional[str] = None
    created_at: Optional[int] = None
    updated_at: Optional[int] = None
    updated_by: Optional[int] = None
    country_id: Optional[int] = None
    state_id: Optional[int] = None
    city_id: Optional[int] = None
    country_name: Optional[str] = None
    parent_id: Optional[int] = None
    parent_name: Optional[str] = None

    # Availability (user tracker status, stored on console_users)
    current_status: Optional[str] = None
    current_status_icon: Optional[str] = None

    # Role fields
    role_id: int
    role_name: str
    role_description: Optional[str] = None
    role_is_active: bool
    role_created_at: Optional[int] = None

    # Partner reference (for isolation)
    partner_id: int

    model_config = ConfigDict(from_attributes=True)


def _validate_range_filter_value(value: Any, operator: str, field_name: str) -> None:
    """A range operator (e.g. BETWEEN) needs exactly two values, given either
    as a list/tuple or as a comma separated string."""
    values = (
        value if isinstance(value, (list, tuple)) else str(value or "").split(",")
    )
    if len(values) != 2:
        raise ValueError(
            "Operator '{}' on field '{}' expects exactly two values".format(
                operator, field_name
            )
        )


def _validate_filter_entry(entry: Any) -> None:
    """Validate one {field, operator, value} filter entry, raising a
    ValueError with a usable message when it is malformed."""
    if not isinstance(entry, dict):
        raise ValueError(
            "Each filter must be an object with 'field', 'operator' and 'value'"
        )

    field_name = entry.get("field")
    operator = entry.get("operator")
    if not field_name:
        raise ValueError("Filter 'field' is required")
    if not operator:
        raise ValueError(
            "Filter 'operator' is required for field '{}'".format(field_name)
        )

    normalised_operator = FilterOperator.normalise(operator)
    if normalised_operator not in FilterOperator.ALIASES.values():
        raise ValueError(
            "Unsupported operator '{}' for field '{}'. Supported: {}".format(
                operator, field_name, ", ".join(FilterOperator.supported())
            )
        )

    if normalised_operator in FilterOperator.RANGE_OPERATORS:
        _validate_range_filter_value(entry.get("value"), operator, field_name)


class UserRoleFilterRequest(BaseModel):
    """Schema for filtering combined user-role data."""

    partner_id: Optional[int] = None

    filters: Optional[List[Dict[str, Any]]] = Field(
        default=[],
        description=(
            "List of filter criteria, combined with AND. Each entry is "
            "{field, operator, value}, where field is any User Listing column "
            "(status/is_active, role/role_id/role_name, availability/current_status, "
            "created_at, updated_at, ...). Operators accept symbols or words: "
            "EQUALS (=), NOT_EQUALS (!=), BEFORE (<), AFTER (>), <=, >=, "
            "LIKE, IN, BETWEEN. Date fields accept "
            "epoch milliseconds or YYYY-MM-DD / DD-MMM-YYYY, and a date without a "
            "time covers the whole day. BETWEEN takes two values, either as a list "
            "or a comma separated string. Omit filters entirely for the full listing."
        ),
        examples=[
            [
                {"field": "is_active", "operator": "=", "value": True},
                {"field": "role_name", "operator": "=", "value": "Sales Executive"},
                {"field": "current_status", "operator": "=", "value": "Active"},
                {
                    "field": "created_at",
                    "operator": "BETWEEN",
                    "value": ["2026-08-01", "2026-08-10"],
                },
            ]
        ],
    )

    order_by: Optional[List[Dict[str, str]]] = Field(
        default=[],
        description="List of ordering criteria. Example: [{'field': 'user_name', 'direction': 'ASC'}]",
        examples=[[{"field": "", "direction": ""}]],
    )

    limit: Optional[int] = Field(
        default=100,
        ge=1,
        le=500,
        description="Maximum number of records to return (1-1000)",
    )

    offset: Optional[int] = Field(
        default=0,
        ge=0,
        description="Number of records to skip for pagination (0 for first page)",
    )

    @field_validator("filters")
    def validate_filter_structure(cls, filters):
        """Reject malformed filter entries up front, with a usable message."""
        for entry in filters or []:
            _validate_filter_entry(entry)
        return filters

    @field_validator("filters")
    def validate_id_field(cls, filters):
        MAX_INT = 2147483647
        for f in filters or []:
            if isinstance(f, dict) and f.get("field") == "id":
                value = f.get("value")
                try:
                    value_int = int(value)
                except (TypeError, ValueError):
                    raise ValueError("Please enter a valid numeric ID")

                if value_int > MAX_INT:
                    raise ValueError("ID exceeds maximum limit")
                if value_int < 0:
                    raise ValueError("ID cannot be negative")
        return filters

    model_config = ConfigDict(from_attributes=True)


class PaginatedUserRoleResponse(BaseModel):
    """Schema for paginated combined user-role data."""

    data: List[UserRoleCombinedResponse]
    total_count: int
    limit: int
    offset: int

    model_config = ConfigDict(from_attributes=True)


class WalkthroughUpdateRequest(BaseModel):
    is_walkthrough_completed: Optional[bool] = False


class BulkUserEntry(BaseModel):
    """
    A single user in the internal bulk-create payload.

    ``sequence`` is a positive integer unique within the batch — same
    convention as journey_config status/substatus sequences in Maglo.
    ``partner_id`` is injected server-side by Maglo; never supplied by
    the end user.  ``parent_id`` is forbidden — use ``parent_sequence``.
    """

    sequence: int
    name: str
    email: EmailStr
    phone_number: str
    password: str
    role_id: int
    partner_id: int
    designation: Optional[str] = None
    country_id: Optional[int] = None
    state_id: Optional[int] = None
    city_id: Optional[int] = None
    alternate_phone_number: Optional[str] = None
    cloud_agent_number: Optional[str] = None

    # Re-use the exact same validators already on UserBase / UserData
    @field_validator("sequence", "role_id", "partner_id")
    @classmethod
    def must_be_positive(cls, value: int) -> int:
        if value < 1:
            raise ValueError("Must be a positive integer.")
        return value

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        value = value.strip()
        # Same regex as UserBase.validate_name
        if not re.match(r"^[A-Za-z]+([ ]?[A-Za-z]+)*$", value):
            raise ValueError("Name contains invalid characters.")
        if len(value) < 2 or len(value) > 56:
            raise ValueError("Name must be between 2 and 56 characters.")
        return value

    @field_validator("phone_number", "alternate_phone_number", mode="before")
    @classmethod
    def strip_tel_prefix(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return value
        return value.removeprefix("tel:")

    @field_validator("phone_number", "alternate_phone_number")
    @classmethod
    def validate_international_phone(cls, value: Optional[str]) -> Optional[str]:
        # Same validator as UserData.validate_international_phone
        if value is None:
            return value
        if not re.match(r"^\+[1-9]\d{7,14}$", value):
            raise ValueError("Enter a valid phone number (e.g., +919988776655).")
        return value

    @field_validator("password")
    @classmethod
    def validate_password(cls, value: str) -> str:
        # Same regex as UserData.validate_password
        regex = r"^(?=.*[A-Z])(?=.*[a-z])(?=.*\d)(?=.*[!@#$%^&*(),.?\":{}|<>]).{8,}$"
        if not re.match(regex, value):
            raise ValueError(AuthExceptionMsg.PASSWORD_NOT_STRONG)
        return value


class ParentResolutionEntry(BaseModel):
    """
    Maps a user's ``sequence`` to their parent's ``sequence`` in the batch.
    ``parent_sequence`` is None for root users (no parent in this batch).
    """

    sequence: int
    parent_sequence: Optional[int] = None

    @field_validator("sequence")
    @classmethod
    def must_be_positive(cls, value: int) -> int:
        if value < 1:
            raise ValueError("sequence must be a positive integer.")
        return value


class BulkUserCreateRequest(BaseModel):
    """
    Request body for POST /internal/users/bulk.

    ``users`` and ``parent_resolution`` must cover the exact same set of
    sequence numbers.
    """

    users: List[BulkUserEntry]
    parent_resolution: List[ParentResolutionEntry]

    @model_validator(mode="after")
    def validate_consistency(self) -> "BulkUserCreateRequest":
        if not self.users:
            raise ValueError("users list must not be empty.")

        user_sequences: Set[int] = {u.sequence for u in self.users}
        res_sequences: Set[int] = {r.sequence for r in self.parent_resolution}

        # Sequence sets must match exactly
        if user_sequences != res_sequences:
            missing_in_res = user_sequences - res_sequences
            extra_in_res = res_sequences - user_sequences
            parts = []
            if missing_in_res:
                parts.append(
                    "sequences in users but missing in parent_resolution: {}".format(
                        sorted(missing_in_res)
                    )
                )
            if extra_in_res:
                parts.append(
                    "sequences in parent_resolution but not in users: {}".format(
                        sorted(extra_in_res)
                    )
                )
            raise ValueError(
                "Mismatch between users and parent_resolution. " + "; ".join(parts)
            )

        # No duplicate sequences
        if len(user_sequences) != len(self.users):
            raise ValueError("Duplicate sequence numbers found in the users list.")

        if len(res_sequences) != len(self.parent_resolution):
            raise ValueError(
                "Duplicate sequence numbers found in the parent_resolution list."
            )

        # No duplicate emails or phones within the batch
        emails = [str(u.email).lower() for u in self.users]
        if len(emails) != len(set(emails)):
            raise ValueError("Duplicate email addresses in the users list.")

        phones = [u.phone_number for u in self.users]
        if len(phones) != len(set(phones)):
            raise ValueError("Duplicate phone numbers in the users list.")

        # All users must belong to the same partner
        partner_ids = {u.partner_id for u in self.users}
        if len(partner_ids) > 1:
            raise ValueError(
                "All users in the batch must belong to the same partner. "
                "Found multiple partner_ids: {}.".format(sorted(partner_ids))
            )

        # parent_sequence must reference a valid sequence in the same batch
        for entry in self.parent_resolution:
            if entry.parent_sequence is not None:
                if entry.parent_sequence == entry.sequence:
                    raise ValueError(
                        "sequence {} references itself as parent_sequence.".format(
                            entry.sequence
                        )
                    )
                if entry.parent_sequence not in user_sequences:
                    raise ValueError(
                        "parent_sequence {} for sequence {} does not exist "
                        "in the users list. Available sequences: {}.".format(
                            entry.parent_sequence,
                            entry.sequence,
                            sorted(user_sequences),
                        )
                    )

        return self


class BulkCreatedUserEntry(BaseModel):
    """Single entry in the bulk-create response."""

    sequence: int  # echoes the caller's sequence number
    user_id: int  # real DB primary key assigned after creation
    email: str

    
class TaskStartResponse(BaseModel):
    task_id: str | int
    message: str