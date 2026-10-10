from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.components.common.constants import CurrentUserMap
from src.components.user_tracker.services import UserTrackerService
from src.components.user_tracker.constants import StandardStatuses, UserTrackerResponseMsg, UserTrackerValidation
from src.components.user_tracker.errors import (
    CustomStatusAlreadyExistsError,
    CustomStatusValidationError,
    InvalidStatusError,
    UnauthorizedCustomStatusAccessError,
    UserTrackerNotFoundError,
)
from src.components.user_tracker.schema import (
    CustomStatusAddItem,
    CustomStatusEditItem,
    CustomStatusItem,
    StandardStatusItem,
    UpdateCustomStatusesResponse,
    UpdateUserStatusResponse,
    UserAvailabilityStatusResponse,
)


class TestUserTrackerService:

    @pytest.fixture(autouse=True)
    def setup(self):
        self.repository = AsyncMock()
        self.logger = MagicMock()
        self.admin_user = {
            CurrentUserMap.USER_ID: 1,
            CurrentUserMap.ROLE_HIERARCHY_LEVEL: CurrentUserMap.ADMIN_ROLE_HIERARCHY_LEVEL,
        }

        self.service = UserTrackerService(
            user_tracker_repository=self.repository,
            console_service_logger=self.logger,
        )

    # ── Helper method tests ─────────────────────────────────────────────

    def test_validate_status_string_success(self):
        """Test successful status validation"""
        valid_status = "  Working from home  "
        result = self.service._UserTrackerService__validate_status_string(valid_status)
        assert result == "Working from home"

    def test_validate_status_string_empty(self):
        """Test validation with empty status"""
        with pytest.raises(CustomStatusValidationError) as exc_info:
            self.service._UserTrackerService__validate_status_string("")
        assert str(exc_info.value) == UserTrackerResponseMsg.EMPTY_STATUS_NOT_ALLOWED

    def test_validate_status_string_none(self):
        """Test validation with None status"""
        with pytest.raises(CustomStatusValidationError) as exc_info:
            self.service._UserTrackerService__validate_status_string(None)
        assert str(exc_info.value) == UserTrackerResponseMsg.EMPTY_STATUS_NOT_ALLOWED

    def test_validate_status_string_whitespace_only(self):
        """Test validation with whitespace only"""
        with pytest.raises(CustomStatusValidationError) as exc_info:
            self.service._UserTrackerService__validate_status_string("   ")
        assert str(exc_info.value) == UserTrackerResponseMsg.EMPTY_STATUS_NOT_ALLOWED

    def test_validate_status_string_too_short(self):
        """Test validation with status too short"""
        with pytest.raises(CustomStatusValidationError) as exc_info:
            self.service._UserTrackerService__validate_status_string("A")
        assert str(exc_info.value) == UserTrackerResponseMsg.STATUS_TOO_SHORT

    def test_validate_status_string_too_long(self):
        """Test validation with status too long"""
        long_status = "A" * (UserTrackerValidation.STATUS_MAX_LENGTH + 1)
        with pytest.raises(CustomStatusValidationError) as exc_info:
            self.service._UserTrackerService__validate_status_string(long_status)
        assert str(exc_info.value) == UserTrackerResponseMsg.STATUS_TOO_LONG

    def test_validate_status_string_exact_min_length(self):
        """Test validation with exact minimum length"""
        min_status = "A" * UserTrackerValidation.STATUS_MIN_LENGTH
        result = self.service._UserTrackerService__validate_status_string(min_status)
        assert result == min_status

    def test_validate_status_string_exact_max_length(self):
        """Test validation with exact maximum length"""
        max_status = "A" * UserTrackerValidation.STATUS_MAX_LENGTH
        result = self.service._UserTrackerService__validate_status_string(max_status)
        assert result == max_status

    def test_get_next_display_id_empty(self):
        """Test generating next display_id with empty data"""
        result = self.service._UserTrackerService__get_next_display_id({})
        assert result == "custom_1"

    def test_get_next_display_id_with_existing(self):
        """Test generating next display_id with existing custom entries"""
        data = {
            "uuid1": {"display_id": "custom_3", "name": "Status 3"},
            "uuid2": {"display_id": "custom_1", "name": "Status 1"},
            "uuid3": {"display_id": "custom_5", "name": "Status 5"},
        }
        result = self.service._UserTrackerService__get_next_display_id(data)
        assert result == "custom_6"

    def test_get_next_display_id_with_malformed(self):
        """Test generating next display_id with malformed display_ids"""
        data = {
            "uuid1": {"display_id": "custom_abc", "name": "Invalid"},
            "uuid2": {"display_id": "custom_2", "name": "Valid"},
            "uuid3": {"display_id": "not_custom", "name": "Wrong format"},
            "uuid4": {"display_id": "custom_", "name": "Missing number"},
        }
        result = self.service._UserTrackerService__get_next_display_id(data)
        assert result == "custom_3"  # Should find custom_2 and increment

    def test_get_next_display_id_with_no_custom_prefix(self):
        """Test generating next display_id when no entries have custom_ prefix"""
        data = {
            "uuid1": {"display_id": "something_1", "name": "Status"},
            "uuid2": {"display_id": "other_2", "name": "Another"},
        }
        result = self.service._UserTrackerService__get_next_display_id(data)
        assert result == "custom_1"  # Default to custom_1

    def test_get_next_display_id_with_non_integer_suffix(self):
        """Test generating next display_id with non-integer suffixes"""
        data = {
            "uuid1": {"display_id": "custom_abc", "name": "Invalid"},
            "uuid2": {"display_id": "custom_2", "name": "Valid"},
            "uuid3": {"display_id": "custom_xyz", "name": "Also invalid"},
        }
        result = self.service._UserTrackerService__get_next_display_id(data)
        assert result == "custom_3"  # Should ignore non-integer suffixes

    # ── is_valid_status tests ────────────────────────────────────────────

    @pytest.mark.asyncio
    async def test_is_valid_status_standard_status(self):
        """A standard status is always valid, regardless of custom statuses."""
        self.repository.get_custom_statuses.return_value = {}

        result = await self.service.is_valid_status(100, "Active")

        assert result is True

    @pytest.mark.asyncio
    async def test_is_valid_status_active_custom_status(self):
        """An active custom status for the partner is valid."""
        self.repository.get_custom_statuses.return_value = {
            "uuid1": {"display_id": "custom_1", "name": "Meeting"},
        }

        result = await self.service.is_valid_status(100, "Meeting")

        assert result is True

    @pytest.mark.asyncio
    async def test_is_valid_status_soft_deleted_custom_status(self):
        """A soft-deleted custom status is no longer valid."""
        self.repository.get_custom_statuses.return_value = {
            "uuid1": {"display_id": "custom_1", "name": ""},
        }

        result = await self.service.is_valid_status(100, "Meeting")

        assert result is False

    @pytest.mark.asyncio
    async def test_is_valid_status_unknown_status(self):
        """A status that is neither standard nor a custom status is invalid."""
        self.repository.get_custom_statuses.return_value = {}

        result = await self.service.is_valid_status(100, "Made Up Status")

        assert result is False

    # ── get_user_availability_status tests ──────────────────────────────

    @pytest.mark.asyncio
    async def test_get_user_availability_status_success(self):
        """Test successfully getting user availability status"""
        # Arrange
        user_id = 1
        partner_id = 100
        current_status = "Active"
        custom_statuses_data = {
            "uuid1": {"display_id": "custom_1", "name": "Meeting", "status_icon": "📅"},
            "uuid2": {"display_id": "custom_2", "name": ""},  # Soft-deleted
        }

        self.repository.get_user_current_status.return_value = (current_status, None)
        self.repository.get_custom_statuses.return_value = custom_statuses_data

        # Act
        result = await self.service.get_user_availability_status(user_id, partner_id)

        # Assert
        assert isinstance(result, UserAvailabilityStatusResponse)
        assert result.current_status == current_status
        assert result.current_status_icon == StandardStatuses.default_icon("Active")
        assert result.standard_statuses == [
            StandardStatusItem(name=name, status_icon=StandardStatuses.default_icon(name))
            for name in StandardStatuses.all()
        ]
        assert result.custom_statuses == {
            "custom_1": CustomStatusItem(name="Meeting", status_icon="📅"),
        }
        self.logger.info.assert_called_once()
        self.repository.get_user_current_status.assert_awaited_once_with(user_id)
        self.repository.get_custom_statuses.assert_awaited_once_with(partner_id)

    @pytest.mark.asyncio
    async def test_get_user_availability_status_no_custom_statuses(self):
        """Test getting user availability status when no custom statuses exist —
        standard statuses fall back to their system-wide default icon color."""
        # Arrange
        user_id = 1
        partner_id = 100
        current_status = "Active"

        self.repository.get_user_current_status.return_value = (current_status, None)
        self.repository.get_custom_statuses.return_value = {}

        # Act
        result = await self.service.get_user_availability_status(user_id, partner_id)

        # Assert
        assert result.current_status == current_status
        assert result.current_status_icon == StandardStatuses.default_icon("Active")
        assert [item.name for item in result.standard_statuses] == StandardStatuses.all()
        assert [item.status_icon for item in result.standard_statuses] == [
            StandardStatuses.default_icon(name) for name in StandardStatuses.all()
        ]
        assert result.custom_statuses == {}

    @pytest.mark.asyncio
    async def test_get_user_availability_status_custom_status_uses_own_icon_override(self):
        """A user's own icon override for their current custom status takes
        precedence over the partner-wide default icon set by an Admin."""
        user_id = 1
        partner_id = 100
        custom_statuses_data = {
            "uuid1": {"display_id": "custom_1", "name": "Meeting", "status_icon": "#000000"},
        }

        self.repository.get_user_current_status.return_value = ("Meeting", "#FFFFFF")
        self.repository.get_custom_statuses.return_value = custom_statuses_data

        result = await self.service.get_user_availability_status(user_id, partner_id)

        assert result.current_status_icon == "#FFFFFF"
        # The shared catalog entry (what other users would see) is unaffected.
        assert result.custom_statuses["custom_1"].status_icon == "#000000"

    @pytest.mark.asyncio
    async def test_get_user_availability_status_custom_status_falls_back_to_default_icon(self):
        """Without a personal override, the partner-wide default icon is shown."""
        user_id = 1
        partner_id = 100
        custom_statuses_data = {
            "uuid1": {"display_id": "custom_1", "name": "Meeting", "status_icon": "#000000"},
        }

        self.repository.get_user_current_status.return_value = ("Meeting", None)
        self.repository.get_custom_statuses.return_value = custom_statuses_data

        result = await self.service.get_user_availability_status(user_id, partner_id)

        assert result.current_status_icon == "#000000"

    @pytest.mark.asyncio
    async def test_get_user_availability_status_user_not_found(self):
        """Test when user is not found"""
        # Arrange
        user_id = 999
        partner_id = 100

        self.repository.get_user_current_status.side_effect = UserTrackerNotFoundError(user_id)

        # Act & Assert
        with pytest.raises(UserTrackerNotFoundError):
            await self.service.get_user_availability_status(user_id, partner_id)

        self.logger.info.assert_called_once()
        self.logger.error.assert_not_called()

    @pytest.mark.asyncio
    async def test_get_user_availability_status_generic_error(self):
        """Test generic error handling"""
        # Arrange
        user_id = 1
        partner_id = 100

        self.repository.get_user_current_status.side_effect = Exception("Unexpected error")

        # Act & Assert
        with pytest.raises(Exception) as exc_info:
            await self.service.get_user_availability_status(user_id, partner_id)

        assert str(exc_info.value) == "Unexpected error"
        self.logger.error.assert_called_once()
        assert "Error in get_user_availability_status" in self.logger.error.call_args[0][0]

    # ── update_user_status tests ────────────────────────────────────────

    @pytest.mark.asyncio
    async def test_update_user_status_success_fixed_status(self):
        """Test successfully updating to a fixed status"""
        # Arrange
        user_id = 1
        partner_id = 100
        new_status = "On Break"
        previous_status = "Active"
        custom_statuses_data = {
            "uuid1": {"display_id": "custom_1", "name": "Meeting"},
        }
        active_map = {"custom_1": "Meeting"}

        self.repository.get_custom_statuses.return_value = custom_statuses_data
        self.repository.update_user_current_status.return_value = previous_status

        with patch.object(self.service, '_UserTrackerService__get_active_display_map', return_value=active_map):
            # Act
            result = await self.service.update_user_status(user_id, partner_id, new_status)

        # Assert
        assert isinstance(result, UpdateUserStatusResponse)
        assert result.previous_status == previous_status
        assert result.updated_status == new_status
        assert result.status_icon == StandardStatuses.default_icon("On Break")
        self.repository.get_custom_statuses.assert_awaited_once_with(partner_id)
        self.repository.update_user_current_status.assert_awaited_once_with(
            user_id, new_status, None
        )

    @pytest.mark.asyncio
    async def test_update_user_status_success_custom_status(self):
        """Test successfully updating to a custom status"""
        # Arrange
        user_id = 1
        partner_id = 100
        new_status = "Meeting"  # Custom status
        previous_status = "Active"
        custom_statuses_data = {
            "uuid1": {"display_id": "custom_1", "name": "Meeting"},
        }
        active_map = {"custom_1": "Meeting"}

        self.repository.get_custom_statuses.return_value = custom_statuses_data
        self.repository.update_user_current_status.return_value = previous_status

        with patch.object(self.service, '_UserTrackerService__get_active_display_map', return_value=active_map):
            # Act
            result = await self.service.update_user_status(user_id, partner_id, new_status)

        # Assert
        assert result.updated_status == new_status
        assert result.previous_status == previous_status
        assert result.status_icon is None

    @pytest.mark.asyncio
    async def test_update_user_status_ignores_status_icon_for_standard_status(self):
        """
        Standard statuses' icons are fixed — a status_icon provided while setting a
        standard status must be ignored, and the response must always carry the
        fixed default icon instead.
        """
        # Arrange
        user_id = 1
        partner_id = 100
        new_status = "Active"
        previous_status = "Away"
        custom_statuses_data = {}
        active_map = {}

        self.repository.get_custom_statuses.return_value = custom_statuses_data
        self.repository.update_user_current_status.return_value = previous_status

        with patch.object(self.service, '_UserTrackerService__get_active_display_map', return_value=active_map):
            # Act — caller tries to override the icon for a standard status
            result = await self.service.update_user_status(
                user_id, partner_id, new_status, status_icon="🟢"
            )

        # Assert — provided icon is ignored; fixed default is used instead
        assert result.status_icon == StandardStatuses.default_icon("Active")
        assert result.status_icon != "🟢"
        self.repository.upsert_custom_statuses.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_update_user_status_sets_custom_status_icon(self):
        """
        Providing status_icon for a custom status is a per-user override —
        it's persisted on this user's own row (via update_user_current_status)
        and must NOT mutate the shared partner-wide custom status catalog.
        """
        # Arrange
        user_id = 1
        partner_id = 100
        new_status = "Meeting"
        previous_status = "Active"
        custom_statuses_data = {
            "uuid1": {"display_id": "custom_1", "name": "Meeting", "status_icon": "#000000"},
        }
        active_map = {"custom_1": "Meeting"}

        self.repository.get_custom_statuses.return_value = custom_statuses_data
        self.repository.update_user_current_status.return_value = previous_status

        with patch.object(self.service, '_UserTrackerService__get_active_display_map', return_value=active_map):
            # Act
            result = await self.service.update_user_status(
                user_id, partner_id, new_status, status_icon="📅"
            )

        # Assert
        assert result.status_icon == "📅"
        # The shared catalog entry (the Admin-set default) is untouched.
        assert custom_statuses_data["uuid1"]["status_icon"] == "#000000"
        self.repository.upsert_custom_statuses.assert_not_awaited()
        self.repository.update_user_current_status.assert_awaited_once_with(
            user_id, new_status, "📅"
        )

    @pytest.mark.asyncio
    async def test_update_user_status_custom_status_without_icon_uses_default(self):
        """Without an explicit status_icon, the response carries the partner-wide
        default icon, and no per-user override is persisted."""
        # Arrange
        user_id = 1
        partner_id = 100
        new_status = "Meeting"
        previous_status = "Active"
        custom_statuses_data = {
            "uuid1": {"display_id": "custom_1", "name": "Meeting", "status_icon": "#000000"},
        }
        active_map = {"custom_1": "Meeting"}

        self.repository.get_custom_statuses.return_value = custom_statuses_data
        self.repository.update_user_current_status.return_value = previous_status

        with patch.object(self.service, '_UserTrackerService__get_active_display_map', return_value=active_map):
            # Act
            result = await self.service.update_user_status(user_id, partner_id, new_status)

        # Assert
        assert result.status_icon == "#000000"
        self.repository.upsert_custom_statuses.assert_not_awaited()
        self.repository.update_user_current_status.assert_awaited_once_with(
            user_id, new_status, None
        )

    @pytest.mark.asyncio
    async def test_update_user_status_with_whitespace(self):
        """Test updating with status containing whitespace"""
        # Arrange
        user_id = 1
        partner_id = 100
        new_status = "  On Break  "  # With whitespace
        cleaned_status = "On Break"
        previous_status = "Active"
        custom_statuses_data = {}
        active_map = {}

        self.repository.get_custom_statuses.return_value = custom_statuses_data
        self.repository.update_user_current_status.return_value = previous_status

        with patch.object(self.service, '_UserTrackerService__get_active_display_map', return_value=active_map):
            # Act
            result = await self.service.update_user_status(user_id, partner_id, new_status)

        # Assert
        assert result.updated_status == cleaned_status
        self.repository.update_user_current_status.assert_awaited_once_with(
            user_id, cleaned_status, None
        )

    @pytest.mark.asyncio
    async def test_update_user_status_validation_error_empty(self):
        """Test validation error with empty status"""
        # Arrange
        user_id = 1
        partner_id = 100
        invalid_status = ""

        # Act & Assert
        with pytest.raises(CustomStatusValidationError):
            await self.service.update_user_status(user_id, partner_id, invalid_status)

        self.repository.get_custom_statuses.assert_not_awaited()
        self.repository.update_user_current_status.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_update_user_status_validation_error_too_short(self):
        """Test validation error with status too short"""
        # Arrange
        user_id = 1
        partner_id = 100
        invalid_status = "A"  # Too short

        # Act & Assert
        with pytest.raises(CustomStatusValidationError):
            await self.service.update_user_status(user_id, partner_id, invalid_status)

    @pytest.mark.asyncio
    async def test_update_user_status_validation_error_too_long(self):
        """Test validation error with status too long"""
        # Arrange
        user_id = 1
        partner_id = 100
        invalid_status = "A" * (UserTrackerValidation.STATUS_MAX_LENGTH + 1)

        # Act & Assert
        with pytest.raises(CustomStatusValidationError):
            await self.service.update_user_status(user_id, partner_id, invalid_status)

    @pytest.mark.asyncio
    async def test_update_user_status_invalid_status_not_in_lists(self):
        """Test when status is not in allowed list"""
        # Arrange
        user_id = 1
        partner_id = 100
        new_status = "Invalid Status"
        custom_statuses_data = {}  # No custom statuses
        active_map = {}

        self.repository.get_custom_statuses.return_value = custom_statuses_data

        with patch.object(self.service, '_UserTrackerService__get_active_display_map', return_value=active_map):
            # Act & Assert
            with pytest.raises(InvalidStatusError) as exc_info:
                await self.service.update_user_status(user_id, partner_id, new_status)

        # The error message contains the status
        assert new_status in str(exc_info.value)
        self.repository.get_custom_statuses.assert_awaited_once()
        self.repository.update_user_current_status.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_update_user_status_user_not_found(self):
        """Test when user is not found during update"""
        # Arrange
        user_id = 999
        partner_id = 100
        new_status = "Active"
        custom_statuses_data = {}
        active_map = {}

        self.repository.get_custom_statuses.return_value = custom_statuses_data
        self.repository.update_user_current_status.side_effect = UserTrackerNotFoundError(user_id)

        with patch.object(self.service, '_UserTrackerService__get_active_display_map', return_value=active_map):
            # Act & Assert
            with pytest.raises(UserTrackerNotFoundError):
                await self.service.update_user_status(user_id, partner_id, new_status)

    @pytest.mark.asyncio
    async def test_update_user_status_generic_error(self):
        """Test generic error during update"""
        # Arrange
        user_id = 1
        partner_id = 100
        new_status = "Active"
        custom_statuses_data = {}
        active_map = {}

        self.repository.get_custom_statuses.return_value = custom_statuses_data
        self.repository.update_user_current_status.side_effect = Exception("Update failed")

        with patch.object(self.service, '_UserTrackerService__get_active_display_map', return_value=active_map):
            # Act & Assert
            with pytest.raises(Exception) as exc_info:
                await self.service.update_user_status(user_id, partner_id, new_status)

        assert str(exc_info.value) == "Update failed"
        self.logger.error.assert_called_once()
        assert "Error in update_user_status" in self.logger.error.call_args[0][0]

    # ── update_custom_statuses tests ────────────────────────────────────

    @pytest.mark.asyncio
    async def test_update_custom_statuses_forbidden_for_non_admin(self):
        """Test that a user below Admin cannot manage custom statuses"""
        non_admin_user = {
            CurrentUserMap.USER_ID: 2,
            CurrentUserMap.ROLE_HIERARCHY_LEVEL: CurrentUserMap.MAINTAINER_ROLE_HIERARCHY_LEVEL,
        }

        with pytest.raises(UnauthorizedCustomStatusAccessError):
            await self.service.update_custom_statuses(
                non_admin_user, 100, 2, {}, [CustomStatusAddItem(name="New Status")]
            )

        self.repository.get_custom_statuses.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_update_custom_statuses_forbidden_for_super_admin(self):
        """Test that Super Admin (excluded from Admin-only access) cannot manage custom statuses"""
        super_admin_user = {
            CurrentUserMap.USER_ID: 3,
            CurrentUserMap.ROLE_HIERARCHY_LEVEL: CurrentUserMap.SUPER_ADMIN_ROLE_HIERARCHY_LEVEL,
        }

        with pytest.raises(UnauthorizedCustomStatusAccessError):
            await self.service.update_custom_statuses(
                super_admin_user, 100, 3, {}, [CustomStatusAddItem(name="New Status")]
            )

        self.repository.get_custom_statuses.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_update_custom_statuses_edit_only(self):
        """Test editing existing custom statuses"""
        # Arrange
        partner_id = 100
        updated_by = 1
        edit_statuses = {"custom_1": CustomStatusEditItem(name="Updated Meeting")}
        add_statuses = []

        existing_data = {
            "uuid1": {"display_id": "custom_1", "name": "Meeting"},
            "uuid2": {"display_id": "custom_2", "name": "Remote"},
        }
        saved_data = {
            "uuid1": {"display_id": "custom_1", "name": "Updated Meeting"},
            "uuid2": {"display_id": "custom_2", "name": "Remote"},
        }

        self.repository.get_custom_statuses.return_value = existing_data
        self.repository.upsert_custom_statuses.return_value = saved_data

        # Act
        result = await self.service.update_custom_statuses(
            self.admin_user, partner_id, updated_by, edit_statuses, add_statuses
        )

        # Assert
        assert isinstance(result, UpdateCustomStatusesResponse)
        assert result.message == UserTrackerResponseMsg.CUSTOM_STATUSES_UPDATED
        assert result.custom_statuses == {
            "custom_1": CustomStatusItem(name="Updated Meeting"),
            "custom_2": CustomStatusItem(name="Remote"),
        }
        self.repository.upsert_custom_statuses.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_update_custom_statuses_edit_icon_only(self):
        """Test updating only the status_icon of an existing custom status (name untouched)"""
        # Arrange
        partner_id = 100
        updated_by = 1
        edit_statuses = {"custom_1": CustomStatusEditItem(status_icon="🎯")}
        add_statuses = []

        existing_data = {
            "uuid1": {"display_id": "custom_1", "name": "Meeting"},
        }
        saved_data = {
            "uuid1": {"display_id": "custom_1", "name": "Meeting", "status_icon": "🎯"},
        }

        self.repository.get_custom_statuses.return_value = existing_data
        self.repository.upsert_custom_statuses.return_value = saved_data

        # Act
        result = await self.service.update_custom_statuses(
            self.admin_user, partner_id, updated_by, edit_statuses, add_statuses
        )

        # Assert
        assert existing_data["uuid1"]["name"] == "Meeting"  # untouched
        assert existing_data["uuid1"]["status_icon"] == "🎯"
        assert result.custom_statuses["custom_1"] == CustomStatusItem(
            name="Meeting", status_icon="🎯"
        )

    @pytest.mark.asyncio
    async def test_update_custom_statuses_soft_delete(self):
        """Test soft deleting a custom status"""
        # Arrange
        partner_id = 100
        updated_by = 1
        edit_statuses = {"custom_1": CustomStatusEditItem(name="")}  # Empty name means soft delete
        add_statuses = []

        existing_data = {
            "uuid1": {"display_id": "custom_1", "name": "Meeting"},
            "uuid2": {"display_id": "custom_2", "name": "Remote"},
        }
        saved_data = {
            "uuid1": {"display_id": "custom_1", "name": ""},  # Soft deleted
            "uuid2": {"display_id": "custom_2", "name": "Remote"},
        }

        self.repository.get_custom_statuses.return_value = existing_data
        self.repository.upsert_custom_statuses.return_value = saved_data

        # Act
        result = await self.service.update_custom_statuses(
            self.admin_user, partner_id, updated_by, edit_statuses, add_statuses
        )

        # Assert - Active map should not include soft-deleted status
        assert result.custom_statuses == {"custom_2": CustomStatusItem(name="Remote")}

    @pytest.mark.asyncio
    async def test_update_custom_statuses_add_only(self):
        """Test adding new custom statuses"""
        # Arrange
        partner_id = 100
        updated_by = 1
        edit_statuses = {}
        add_statuses = [
            CustomStatusAddItem(name="New Status", status_icon="🆕"),
            CustomStatusAddItem(name="Another Status"),
        ]

        existing_data = {
            "uuid1": {"display_id": "custom_1", "name": "Meeting"},
        }

        saved_data = {
            "uuid1": {"display_id": "custom_1", "name": "Meeting"},
            "uuid2": {"display_id": "custom_2", "name": "New Status", "status_icon": "🆕"},
            "uuid3": {"display_id": "custom_3", "name": "Another Status", "status_icon": None},
        }

        self.repository.get_custom_statuses.return_value = existing_data
        self.repository.upsert_custom_statuses.return_value = saved_data

        with patch.object(self.service, '_UserTrackerService__get_next_display_id') as mock_get_next:
            mock_get_next.side_effect = ["custom_2", "custom_3"]
            # Act
            result = await self.service.update_custom_statuses(
                self.admin_user, partner_id, updated_by, edit_statuses, add_statuses
            )

        # Assert
        assert len(result.custom_statuses) == 3
        assert result.custom_statuses["custom_2"] == CustomStatusItem(
            name="New Status", status_icon="🆕"
        )
        assert result.custom_statuses["custom_3"] == CustomStatusItem(name="Another Status")

    @pytest.mark.asyncio
    async def test_update_custom_statuses_edit_and_add(self):
        """Test both editing and adding custom statuses"""
        # Arrange
        partner_id = 100
        updated_by = 1
        edit_statuses = {"custom_1": CustomStatusEditItem(name="Updated Meeting")}
        add_statuses = [CustomStatusAddItem(name="Brand New")]

        existing_data = {
            "uuid1": {"display_id": "custom_1", "name": "Meeting"},
        }

        self.repository.get_custom_statuses.return_value = existing_data

        saved_data = {
            "uuid1": {"display_id": "custom_1", "name": "Updated Meeting"},
            "uuid2": {"display_id": "custom_2", "name": "Brand New"},
        }

        self.repository.upsert_custom_statuses.return_value = saved_data

        with patch.object(self.service, '_UserTrackerService__get_next_display_id', return_value="custom_2"):
            # Act
            result = await self.service.update_custom_statuses(
                self.admin_user, partner_id, updated_by, edit_statuses, add_statuses
            )

        # Assert
        assert len(result.custom_statuses) == 2
        assert result.custom_statuses["custom_1"] == CustomStatusItem(name="Updated Meeting")
        assert result.custom_statuses["custom_2"] == CustomStatusItem(name="Brand New")

    @pytest.mark.asyncio
    async def test_update_custom_statuses_display_id_not_found(self):
        """Test editing a non-existent display_id"""
        # Arrange
        partner_id = 100
        updated_by = 1
        edit_statuses = {"custom_999": CustomStatusEditItem(name="New Name")}  # Doesn't exist
        add_statuses = []

        existing_data = {
            "uuid1": {"display_id": "custom_1", "name": "Meeting"},
        }

        self.repository.get_custom_statuses.return_value = existing_data

        # Act & Assert
        with pytest.raises(CustomStatusValidationError) as exc_info:
            await self.service.update_custom_statuses(
                self.admin_user, partner_id, updated_by, edit_statuses, add_statuses
            )

        assert "not found" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_update_custom_statuses_fixed_status_conflict_edit(self):
        """Test trying to rename a custom status to a fixed status name"""
        # Arrange
        partner_id = 100
        updated_by = 1
        edit_statuses = {"custom_1": CustomStatusEditItem(name="Active")}  # Active is a fixed status
        add_statuses = []

        existing_data = {
            "uuid1": {"display_id": "custom_1", "name": "Meeting"},
        }

        self.repository.get_custom_statuses.return_value = existing_data

        # Act & Assert
        with pytest.raises(CustomStatusValidationError) as exc_info:
            await self.service.update_custom_statuses(
                self.admin_user, partner_id, updated_by, edit_statuses, add_statuses
            )

        assert str(exc_info.value) == UserTrackerResponseMsg.FIXED_STATUS_CONFLICT

    @pytest.mark.asyncio
    async def test_update_custom_statuses_fixed_status_conflict_add(self):
        """Test trying to add a custom status with fixed status name"""
        # Arrange
        partner_id = 100
        updated_by = 1
        edit_statuses = {}
        add_statuses = [CustomStatusAddItem(name="Busy")]  # Busy is a fixed status

        existing_data = {}

        self.repository.get_custom_statuses.return_value = existing_data

        # Act & Assert
        with pytest.raises(CustomStatusValidationError) as exc_info:
            await self.service.update_custom_statuses(
                self.admin_user, partner_id, updated_by, edit_statuses, add_statuses
            )

        assert str(exc_info.value) == UserTrackerResponseMsg.FIXED_STATUS_CONFLICT

    @pytest.mark.asyncio
    async def test_update_custom_statuses_duplicate_in_add(self):
        """Test adding duplicate statuses in same request"""
        # Arrange
        partner_id = 100
        updated_by = 1
        edit_statuses = {}
        add_statuses = [
            CustomStatusAddItem(name="Meeting"),
            CustomStatusAddItem(name="Meeting"),
        ]  # Duplicate in add list

        existing_data = {}

        self.repository.get_custom_statuses.return_value = existing_data

        # Act & Assert
        with pytest.raises(CustomStatusAlreadyExistsError):
            await self.service.update_custom_statuses(
                self.admin_user, partner_id, updated_by, edit_statuses, add_statuses
            )

    @pytest.mark.asyncio
    async def test_update_custom_statuses_duplicate_with_existing(self):
        """Test adding a status that already exists"""
        # Arrange
        partner_id = 100
        updated_by = 1
        edit_statuses = {}
        add_statuses = [CustomStatusAddItem(name="Meeting")]  # Already exists

        existing_data = {
            "uuid1": {"display_id": "custom_1", "name": "Meeting"},
        }

        self.repository.get_custom_statuses.return_value = existing_data

        # Act & Assert
        with pytest.raises(CustomStatusAlreadyExistsError) as exc_info:
            await self.service.update_custom_statuses(
                self.admin_user, partner_id, updated_by, edit_statuses, add_statuses
            )

        assert "Meeting" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_update_custom_statuses_duplicate_case_insensitive(self):
        """Test adding a status that already exists with different case"""
        # Arrange
        partner_id = 100
        updated_by = 1
        edit_statuses = {}
        add_statuses = [CustomStatusAddItem(name="MEETING")]  # Already exists but different case

        existing_data = {
            "uuid1": {"display_id": "custom_1", "name": "Meeting"},
        }

        self.repository.get_custom_statuses.return_value = existing_data

        # Act & Assert
        with pytest.raises(CustomStatusAlreadyExistsError) as exc_info:
            await self.service.update_custom_statuses(
                self.admin_user, partner_id, updated_by, edit_statuses, add_statuses
            )

        assert "MEETING" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_update_custom_statuses_validation_error_on_add(self):
        """Test validation error when adding invalid status"""
        # Arrange
        partner_id = 100
        updated_by = 1
        edit_statuses = {}
        add_statuses = [CustomStatusAddItem(name="A")]  # Too short

        existing_data = {}

        self.repository.get_custom_statuses.return_value = existing_data

        # Act & Assert
        with pytest.raises(CustomStatusValidationError) as exc_info:
            await self.service.update_custom_statuses(
                self.admin_user, partner_id, updated_by, edit_statuses, add_statuses
            )

        assert str(exc_info.value) == UserTrackerResponseMsg.STATUS_TOO_SHORT

    @pytest.mark.asyncio
    async def test_update_custom_statuses_validation_error_on_edit(self):
        """Test validation error when editing to invalid status"""
        # Arrange
        partner_id = 100
        updated_by = 1
        edit_statuses = {"custom_1": CustomStatusEditItem(name="A")}  # Too short
        add_statuses = []

        existing_data = {
            "uuid1": {"display_id": "custom_1", "name": "Meeting"},
        }

        self.repository.get_custom_statuses.return_value = existing_data

        # Act & Assert
        with pytest.raises(CustomStatusValidationError) as exc_info:
            await self.service.update_custom_statuses(
                self.admin_user, partner_id, updated_by, edit_statuses, add_statuses
            )

        assert str(exc_info.value) == UserTrackerResponseMsg.STATUS_TOO_SHORT

    @pytest.mark.asyncio
    async def test_update_custom_statuses_generic_error(self):
        """Test generic error during custom status update"""
        # Arrange
        partner_id = 100
        updated_by = 1
        edit_statuses = {}
        add_statuses = [CustomStatusAddItem(name="New Status")]

        self.repository.get_custom_statuses.side_effect = Exception("Fetch failed")

        # Act & Assert
        with pytest.raises(Exception) as exc_info:
            await self.service.update_custom_statuses(
                self.admin_user, partner_id, updated_by, edit_statuses, add_statuses
            )

        assert str(exc_info.value) == "Fetch failed"
        self.logger.error.assert_called_once()
        assert "Error in update_custom_statuses" in self.logger.error.call_args[0][0]

    @pytest.mark.asyncio
    async def test_update_custom_statuses_rename_same_name_allowed(self):
        """Test renaming to the same name (case-insensitive) is allowed"""
        # Arrange
        partner_id = 100
        updated_by = 1
        edit_statuses = {"custom_1": CustomStatusEditItem(name="Meeting")}  # Same name
        add_statuses = []

        existing_data = {
            "uuid1": {"display_id": "custom_1", "name": "Meeting"},
        }
        saved_data = {
            "uuid1": {"display_id": "custom_1", "name": "Meeting"},
        }

        self.repository.get_custom_statuses.return_value = existing_data
        self.repository.upsert_custom_statuses.return_value = saved_data

        # Act - Should not raise duplicate error
        result = await self.service.update_custom_statuses(
            self.admin_user, partner_id, updated_by, edit_statuses, add_statuses
        )

        # Assert
        assert result.custom_statuses["custom_1"] == CustomStatusItem(name="Meeting")

    @pytest.mark.asyncio
    async def test_update_custom_statuses_rename_different_case_same_name(self):
        """Test renaming with different case but same text is allowed"""
        # Arrange
        partner_id = 100
        updated_by = 1
        edit_statuses = {"custom_1": CustomStatusEditItem(name="MEETING")}  # Different case
        add_statuses = []

        existing_data = {
            "uuid1": {"display_id": "custom_1", "name": "Meeting"},
        }
        saved_data = {
            "uuid1": {"display_id": "custom_1", "name": "MEETING"},
        }

        self.repository.get_custom_statuses.return_value = existing_data
        self.repository.upsert_custom_statuses.return_value = saved_data

        # Act - Should not raise duplicate error
        result = await self.service.update_custom_statuses(
            self.admin_user, partner_id, updated_by, edit_statuses, add_statuses
        )

        # Assert
        assert result.custom_statuses["custom_1"] == CustomStatusItem(name="MEETING")

    @pytest.mark.asyncio
    async def test_update_custom_statuses_empty_edit_and_add(self):
        """Test with empty edit and add lists"""
        # Arrange
        partner_id = 100
        updated_by = 1
        edit_statuses = {}
        add_statuses = []

        existing_data = {
            "uuid1": {"display_id": "custom_1", "name": "Meeting"},
        }
        saved_data = existing_data

        self.repository.get_custom_statuses.return_value = existing_data
        self.repository.upsert_custom_statuses.return_value = saved_data

        # Act
        result = await self.service.update_custom_statuses(
            self.admin_user, partner_id, updated_by, edit_statuses, add_statuses
        )

        # Assert
        assert result.custom_statuses == {"custom_1": CustomStatusItem(name="Meeting")}

    @pytest.mark.asyncio
    async def test_update_custom_statuses_with_whitespace_in_names(self):
        """Test handling whitespace in status names"""
        # Arrange
        partner_id = 100
        updated_by = 1
        edit_statuses = {"custom_1": CustomStatusEditItem(name="  Updated Meeting  ")}  # With whitespace
        add_statuses = [CustomStatusAddItem(name="  New Status  ")]  # With whitespace

        existing_data = {
            "uuid1": {"display_id": "custom_1", "name": "Meeting"},
        }

        self.repository.get_custom_statuses.return_value = existing_data

        saved_data = {
            "uuid1": {"display_id": "custom_1", "name": "Updated Meeting"},
            "uuid2": {"display_id": "custom_2", "name": "New Status"},
        }

        self.repository.upsert_custom_statuses.return_value = saved_data

        with patch.object(self.service, '_UserTrackerService__get_next_display_id', return_value="custom_2"):
            # Act
            result = await self.service.update_custom_statuses(
                self.admin_user, partner_id, updated_by, edit_statuses, add_statuses
            )

        # Assert
        assert result.custom_statuses["custom_1"] == CustomStatusItem(name="Updated Meeting")
        assert result.custom_statuses["custom_2"] == CustomStatusItem(name="New Status")
