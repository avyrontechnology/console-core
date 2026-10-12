from uuid import UUID
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import pytest
from sqlalchemy.exc import IntegrityError
from pydantic import ValidationError

from src.components.auth.error import RoleNotFoundError
from src.components.auth.schema import (
    AllUsersDataResponse,
    PaginatedAllUsersDataResponse,
)
from src.components.cache import Keys as CacheKeys
from src.components.location.errors import (
    CityNotFoundError,
    CountryNotFoundError,
    StateNotFoundError,
)
from src.components.partner.error import PartnerNotFoundError
from src.components.user.errors import UserNotFoundError
from src.components.user.models import User
from src.components.user.schema import UserRoleFilterRequest, Contrasts
from src.components.user.services import ApiKeyNotFoundError, UserService
from src.components.user_tracker.constants import StandardStatuses
from src.components.user_tracker.errors import InvalidStatusError
from src.core.redis import RedisCache
from src.exceptions import UserException
from src.components.user.constants import UserResponseMsg


@pytest.mark.asyncio
class TestUserService:

    @pytest.fixture
    def user_service(self):
        return UserService(
            user_repository=AsyncMock(),
            audit_service=AsyncMock(),
            console_service_logger=MagicMock(),
            console_service_cache=AsyncMock(),
            auth_service_utility=AsyncMock(),
            session_factory=MagicMock(),
        )

    @pytest.fixture(autouse=True)
    def setup_class(self, mock_logger, redis_mock):

        self.user_repository_mock = AsyncMock()
        self.mock_logger = mock_logger
        self.redis_mock = redis_mock
        self.auth_utility_mock = AsyncMock()
        self.partner_repository_mock = AsyncMock()
        self.audit_log_mock = AsyncMock()
        self.user_session_service = AsyncMock()

        self.user_service = UserService(
            user_repository=self.user_repository_mock,
            audit_service=self.audit_log_mock,
            console_service_logger=self.mock_logger,
            console_service_cache=self.redis_mock,
            auth_service_utility=self.auth_utility_mock,
            session_factory=MagicMock(),
        )

    async def test_get_user_by_email_success(self):
        user_mock = AsyncMock()
        self.user_repository_mock.get_user_by_field.return_value = user_mock
        result = await self.user_service.get_user_by_field("email", "test@example.com")
        assert result == user_mock

    async def test_get_user_details_success(self):
        user_mock = AsyncMock()
        self.user_repository_mock.get_user_details.return_value = user_mock
        result = await self.user_service.get_user_details(1)
        assert result == user_mock

    async def test_get_service_board_users_details_success(self):
        """Test successful retrieval of service board users details."""
        user_ids = [UUID("11111111-1111-1111-1111-111111111111"), UUID("22222222-2222-2222-2222-222222222222")]

        mock_users = [
            {
                "user_id": UUID("11111111-1111-1111-1111-111111111111"),
                "email": "user1@example.com",
                "is_active": True,
                "is_suspended": False,
                "name": "User One",
            },
            {
                "user_id": UUID("22222222-2222-2222-2222-222222222222"),
                "email": "user2@example.com",
                "is_active": True,
                "is_suspended": False,
                "name": "User Two",
            },
        ]

        self.user_repository_mock.get_service_board_users_details.return_value = (
            mock_users
        )

        result = await self.user_service.get_service_board_users_details(user_ids)

        assert isinstance(result, list)
        assert len(result) == 2
        assert result[0]["user_id"] == UUID("11111111-1111-1111-1111-111111111111")
        assert result[0]["email"] == "user1@example.com"
        assert result[1]["user_id"] == UUID("22222222-2222-2222-2222-222222222222")
        assert result[1]["email"] == "user2@example.com"

    async def test_get_service_board_users_details_generic_exception(self):
        """Test handling of unexpected exceptions in get_service_board_users_details."""
        user_ids = [UUID("11111111-1111-1111-1111-111111111111"), UUID("22222222-2222-2222-2222-222222222222")]

        self.user_repository_mock.get_service_board_users_details.side_effect = (
            Exception("Database Error")
        )

        with pytest.raises(Exception) as exc_info:
            await self.user_service.get_service_board_users_details(user_ids)

        assert str(exc_info.value) == "Database Error"

    async def test_get_users_success(self):
        """Test successful retrieval of paginated users under a user's hierarchy."""
        current_user_id= UUID("11111111-1111-1111-1111-111111111111")
        limit = 10
        offset = 0

        # Mock User object
        user_mock = AsyncMock(spec=User)
        user_mock.id = UUID("11111111-1111-1111-1111-111111111111")
        user_mock.name = "John Doe"  # String
        user_mock.email = "john@example.com"
        user_mock.designation = "Manager"
        user_mock.phone_number = "+1-202-555-0123"  # E.164 format
        user_mock.parent_id = None
        user_mock.partner_id = None
        user_mock.role_id= UUID("11111111-1111-1111-1111-111111111111")
        user_mock.country_id= UUID("11111111-1111-1111-1111-111111111111")
        user_mock.country = Mock()
        user_mock.country.name = "USA"  # String
        user_mock.state_id = None
        user_mock.city_id = None
        user_mock.parent = None
        user_mock.cloud_agent_number = "09876"
        user_mock.current_status = "Active"

        # Mock repository response
        self.user_repository_mock.get_all.return_value = (
            [user_mock],
            1,
        )  # Return tuple (users, total_count)

        # Mock auth service response
        role_mock = Mock()
        role_mock.name = "Counsellor"  # String
        self.auth_utility_mock.get_role_by_id.return_value = role_mock

        # Call the service method
        result = await self.user_service.get_users(
            current_user_id, limit, offset, auth_service=self.auth_utility_mock
        )

        # Assertions
        assert isinstance(result, PaginatedAllUsersDataResponse)
        assert result.total_count == 1
        assert result.limit == limit
        assert result.offset == offset
        assert len(result.users_data) == 1
        assert isinstance(result.users_data[0], AllUsersDataResponse)
        assert result.users_data[0].id == UUID("11111111-1111-1111-1111-111111111111")
        assert result.users_data[0].name == "John Doe"
        assert result.users_data[0].email == "john@example.com"
        assert result.users_data[0].role_name == "Counsellor"
        assert result.users_data[0].country_name == "USA"
        assert result.users_data[0].parent_name is None
        assert result.users_data[0].phone_number == "+1-202-555-0123"
        assert result.users_data[0].cloud_agent_number == "09876"
        assert result.users_data[0].current_status == "Active"
        # No team_repository/partner_config_service wired -> team_count omitted.
        assert result.users_data[0].team_count is None

        # Verify mocks
        self.user_repository_mock.get_all.assert_called_once_with(
            current_user_id, limit, offset, filter_criteria=None
        )
        self.auth_utility_mock.get_role_by_id.assert_called_once_with(UUID("11111111-1111-1111-1111-111111111111"))
        self.mock_logger.info.assert_any_call("getting all users")

    async def test_get_users_current_status_null_falls_back_to_away(self):
        """A user with no current_status set in the DB (NULL, e.g. a pre-existing
        row created before the column/default existed) reports "Away" here too,
        matching the fallback used by GET /user-tracker/status and the
        GetUsersAvailabilityStatus gRPC — never a bare null."""
        current_user_id, limit, offset = 1, 10, 0

        user_mock = AsyncMock(spec=User)
        user_mock.id = UUID("11111111-1111-1111-1111-111111111111")
        user_mock.name = "John Doe"
        user_mock.email = "john@example.com"
        user_mock.designation = "Manager"
        user_mock.phone_number = "+1-202-555-0123"
        user_mock.parent_id = None
        user_mock.partner_id = None
        user_mock.role_id = None
        user_mock.country_id = None
        user_mock.country = None
        user_mock.state_id = None
        user_mock.city_id = None
        user_mock.parent = None
        user_mock.is_active = True
        user_mock.cloud_agent_number = None
        user_mock.current_status = None

        self.user_repository_mock.get_all.return_value = ([user_mock], 1)

        result = await self.user_service.get_users(
            current_user_id, limit, offset, auth_service=self.auth_utility_mock
        )

        assert result.users_data[0].current_status == StandardStatuses.AWAY

    async def test_get_users_team_count_populated_when_teams_enabled(self):
        """team_count is populated per-user when teams are enabled for the partner."""
        current_user_id, limit, offset = 1, 10, 0

        user_mock = AsyncMock(spec=User)
        user_mock.id = UUID("11111111-1111-1111-1111-111111111111")
        user_mock.name = "John Doe"
        user_mock.email = "john@example.com"
        user_mock.designation = "Manager"
        user_mock.phone_number = "+1-202-555-0123"
        user_mock.parent_id = None
        user_mock.partner_id= UUID("10101010-1010-1010-1010-101010101010")
        user_mock.role_id= UUID("11111111-1111-1111-1111-111111111111")
        user_mock.country_id = None
        user_mock.country = None
        user_mock.state_id = None
        user_mock.city_id = None
        user_mock.parent = None
        user_mock.is_active = True
        user_mock.cloud_agent_number = None
        user_mock.current_status = "Active"

        self.user_repository_mock.get_all.return_value = ([user_mock], 1)
        self.auth_utility_mock.get_role_by_id.return_value = None

        team_repository_mock = AsyncMock()
        team_repository_mock.get_member_counts_for_users.return_value = {UUID("11111111-1111-1111-1111-111111111111"): 4}
        partner_config_service_mock = AsyncMock()
        partner_config_service_mock.get_partner_config_by_key.return_value = Mock(
            value=True
        )

        service_with_teams = UserService(
            user_repository=self.user_repository_mock,
            audit_service=self.audit_log_mock,
            console_service_logger=self.mock_logger,
            console_service_cache=self.redis_mock,
            auth_service_utility=self.auth_utility_mock,
            session_factory=MagicMock(),
            team_repository=team_repository_mock,
        )

        result = await service_with_teams.get_users(
            current_user_id,
            limit,
            offset,
            auth_service=self.auth_utility_mock,
            partner_config_service=partner_config_service_mock,
        )

        assert result.users_data[0].team_count == 4
        team_repository_mock.get_member_counts_for_users.assert_awaited_once_with([UUID("11111111-1111-1111-1111-111111111111")])

    async def test_get_users_team_count_none_when_teams_disabled(self):
        """team_count stays None when teams aren't enabled for the partner."""
        current_user_id, limit, offset = 1, 10, 0

        user_mock = AsyncMock(spec=User)
        user_mock.id = UUID("11111111-1111-1111-1111-111111111111")
        user_mock.name = "John Doe"
        user_mock.email = "john@example.com"
        user_mock.designation = "Manager"
        user_mock.phone_number = "+1-202-555-0123"
        user_mock.parent_id = None
        user_mock.partner_id= UUID("10101010-1010-1010-1010-101010101010")
        user_mock.role_id= UUID("11111111-1111-1111-1111-111111111111")
        user_mock.country_id = None
        user_mock.country = None
        user_mock.state_id = None
        user_mock.city_id = None
        user_mock.parent = None
        user_mock.is_active = True
        user_mock.cloud_agent_number = None
        user_mock.current_status = "Active"

        self.user_repository_mock.get_all.return_value = ([user_mock], 1)
        self.auth_utility_mock.get_role_by_id.return_value = None

        team_repository_mock = AsyncMock()
        partner_config_service_mock = AsyncMock()
        partner_config_service_mock.get_partner_config_by_key.return_value = Mock(
            value=False
        )

        service_with_teams = UserService(
            user_repository=self.user_repository_mock,
            audit_service=self.audit_log_mock,
            console_service_logger=self.mock_logger,
            console_service_cache=self.redis_mock,
            auth_service_utility=self.auth_utility_mock,
            session_factory=MagicMock(),
            team_repository=team_repository_mock,
        )

        result = await service_with_teams.get_users(
            current_user_id,
            limit,
            offset,
            auth_service=self.auth_utility_mock,
            partner_config_service=partner_config_service_mock,
        )

        assert result.users_data[0].team_count is None
        team_repository_mock.get_member_counts_for_users.assert_not_called()

    async def test_get_users_exception(self):
        """Test handling of exceptions in get_users method."""
        current_user_id= UUID("11111111-1111-1111-1111-111111111111")
        limit = 10
        offset = 0

        # Mock repository to raise an exception
        self.user_repository_mock.get_all.side_effect = Exception(
            "Database connection failed"
        )

        # Reset mock logger to ensure no interference from other tests
        self.mock_logger.reset_mock()

        # Expect the exception to be raised
        with pytest.raises(Exception) as exc_info:
            await self.user_service.get_users(
                current_user_id, limit, offset, auth_service=self.auth_utility_mock
            )

        # Assertions
        assert str(exc_info.value) == "Database connection failed"
        self.mock_logger.error.assert_called_once_with(
            "Error retriving users.Database connection failed"
        )
        self.mock_logger.info.assert_called_once_with("getting all users")
        self.user_repository_mock.get_all.assert_called_once_with(
            current_user_id, limit, offset, filter_criteria=None
        )

    async def test_update_user_success(self):
        """Test successful user update."""

        # Arrange
        user_id= UUID("11111111-1111-1111-1111-111111111111")
        current_user = {"user_id": UUID("33333333-3333-3333-3333-333333333333"), "partner_id": UUID("12121212-1212-1212-1212-121212121212")}

        user_data = MagicMock(
            country_id= UUID("11111111-1111-1111-1111-111111111111"),
            state_id= UUID("22222222-2222-2222-2222-222222222222"),
            city_id= UUID("33333333-3333-3333-3333-333333333333"),
            password="new_password",
            role_id= UUID("11111111-1111-1111-1111-111111111111"),
            partner_id=current_user.get("partner_id"),
            parent_id=None,
        )

        user_data.model_dump.return_value = {
            "country_id": UUID("11111111-1111-1111-1111-111111111111"),
            "state_id": UUID("22222222-2222-2222-2222-222222222222"),
            "city_id": UUID("33333333-3333-3333-3333-333333333333"),
            "password": "new_password",
            "role_id": UUID("11111111-1111-1111-1111-111111111111"),
            "partner_id": current_user.get("partner_id"),
            "parent_id": None,
        }

        existing_user = MagicMock(id=user_id, name="Old Name")

        updated_user = MagicMock(
            id=user_id,
            name="Updated Name",
            partner_id=current_user.get("partner_id"),
        )

        user_role = MagicMock(hierarchy="USER")

        repository_mock = AsyncMock()
        repository_mock.get_by_id.return_value = existing_user
        repository_mock.update_user.return_value = updated_user
        repository_mock.is_admin_exists.return_value = False

        location_service_mock = AsyncMock()

        auth_service_utility_mock = AsyncMock()
        auth_service_utility_mock.get_password_hash.return_value = (
            "hashed_password"
        )

        auth_repository_mock = AsyncMock()
        auth_repository_mock.get_role_by_id.return_value = user_role

        partner_service_mock = AsyncMock()
        partner_service_mock.get_partner_by_id.return_value = MagicMock(
            is_internal=True
        )

        user_session_service_mock = AsyncMock()
        user_session_service_mock.deactivate_user_sessions.return_value = (
            MagicMock()
        )

        audit_service_mock = AsyncMock()

        logger_mock = MagicMock()

        cache_mock = AsyncMock()
        cache_mock.clear_pattern.return_value = True

        user_service = UserService(
            user_repository=repository_mock,
            audit_service=audit_service_mock,
            console_service_logger=logger_mock,
            console_service_cache=cache_mock,
            auth_service_utility=auth_service_utility_mock,
            session_factory=MagicMock(),
        )

        # Act
        result = await user_service.update_user(
            user_id,
            current_user,
            user_data,
            location_service=location_service_mock,
            auth_repository=auth_repository_mock,
            partner_service=partner_service_mock,
            user_session_service=user_session_service_mock,
        )

        # Assert
        repository_mock.get_by_id.assert_called_once_with(
            user_id, show_inactive_users=True
        )

        location_service_mock.validate_location_hierarchy.assert_called_once_with(
            user_data.country_id,
            user_data.state_id,
            user_data.city_id,
        )

        auth_repository_mock.get_role_by_id.assert_called_once_with(
            user_data.role_id
        )

        auth_service_utility_mock.get_password_hash.assert_called_once_with(
            "new_password"
        )

        cache_mock.clear_pattern.assert_any_call(
            prefix=RedisCache.KeysPrefix.CONSOLE,
            pattern=CacheKeys.TOKEN.format(
                updated_user.partner_id,
                "",
            ),
        )

        user_session_service_mock.deactivate_user_sessions.assert_called_once_with(
            user_id
        )

        audit_service_mock.log_action.assert_called_once()

        assert result == updated_user

        logger_mock.info.assert_any_call(
            f"user updated successfully: {updated_user}"
        )

    async def test_update_user_current_status_success(self):
        """A valid current_status (standard or active custom) is accepted."""
        # Arrange
        user_id= UUID("11111111-1111-1111-1111-111111111111")
        current_user = {"user_id": UUID("33333333-3333-3333-3333-333333333333"), "partner_id": UUID("12121212-1212-1212-1212-121212121212")}

        user_data = MagicMock(
            country_id=None,
            state_id=None,
            city_id=None,
            parent_id=None,
        )
        user_data.model_dump.return_value = {"current_status": "Meeting"}

        existing_user = MagicMock(id=user_id, partner_id= UUID("12121212-1212-1212-1212-121212121212"))
        updated_user = MagicMock(id=user_id, partner_id= UUID("12121212-1212-1212-1212-121212121212"))

        repository_mock = AsyncMock()
        repository_mock.get_by_id.return_value = existing_user
        repository_mock.update_user.return_value = updated_user

        partner_service_mock = AsyncMock()
        partner_service_mock.get_partner_by_id.return_value = MagicMock(is_internal=True)

        user_tracker_service_mock = AsyncMock()
        user_tracker_service_mock.is_valid_status.return_value = True

        user_session_service_mock = AsyncMock()
        audit_service_mock = AsyncMock()
        cache_mock = AsyncMock()
        logger_mock = MagicMock()

        user_service = UserService(
            user_repository=repository_mock,
            audit_service=audit_service_mock,
            console_service_logger=logger_mock,
            console_service_cache=cache_mock,
            auth_service_utility=AsyncMock(),
            session_factory=MagicMock(),
        )

        # Act
        result = await user_service.update_user(
            user_id,
            current_user,
            user_data,
            partner_service=partner_service_mock,
            user_tracker_service=user_tracker_service_mock,
            user_session_service=user_session_service_mock,
            auth_repository=AsyncMock(),
        )

        # Assert
        user_tracker_service_mock.is_valid_status.assert_awaited_once_with(
            existing_user.partner_id, "Meeting"
        )
        repository_mock.update_user.assert_awaited_once_with(
            user_id=user_id,
            current_user_id= UUID("33333333-3333-3333-3333-333333333333"),
            current_status="Meeting",
            current_status_icon=None,
        )
        assert result == updated_user

    async def test_update_user_current_status_invalid(self):
        """An unknown current_status (not standard, not an active custom status) is rejected."""
        # Arrange
        user_id= UUID("11111111-1111-1111-1111-111111111111")
        current_user = {"user_id": UUID("33333333-3333-3333-3333-333333333333"), "partner_id": UUID("12121212-1212-1212-1212-121212121212")}

        user_data = MagicMock(country_id=None, state_id=None, city_id=None)
        user_data.model_dump.return_value = {"current_status": "Not A Real Status"}

        existing_user = MagicMock(id=user_id, partner_id= UUID("12121212-1212-1212-1212-121212121212"))

        repository_mock = AsyncMock()
        repository_mock.get_by_id.return_value = existing_user

        partner_service_mock = AsyncMock()
        partner_service_mock.get_partner_by_id.return_value = MagicMock(is_internal=True)

        user_tracker_service_mock = AsyncMock()
        user_tracker_service_mock.is_valid_status.return_value = False

        logger_mock = MagicMock()

        user_service = UserService(
            user_repository=repository_mock,
            audit_service=AsyncMock(),
            console_service_logger=logger_mock,
            console_service_cache=AsyncMock(),
            auth_service_utility=AsyncMock(),
            session_factory=MagicMock(),
        )

        # Act & Assert
        with pytest.raises(InvalidStatusError):
            await user_service.update_user(
                user_id,
                current_user,
                user_data,
                partner_service=partner_service_mock,
                user_tracker_service=user_tracker_service_mock,
            )

        repository_mock.update_user.assert_not_awaited()

    async def test_update_user_country_not_found(self):
        """Test update user with invalid country."""
        # Arrange
        user_id= UUID("11111111-1111-1111-1111-111111111111")
        user_data = MagicMock(country_id= UUID("99999999-9999-9999-9999-999999999999"))
        existing_user = MagicMock(id=user_id)
        current_user = {"user_id": UUID("33333333-3333-3333-3333-333333333333"), "partner_id": UUID("12121212-1212-1212-1212-121212121212")}

        repository_mock = AsyncMock()
        repository_mock.get_by_id.return_value = existing_user

        location_service_mock = AsyncMock()
        location_service_mock.validate_location_hierarchy.side_effect = (
            CountryNotFoundError("Country not found")
        )

        partner_service_mock = AsyncMock()
        partner_service_mock.get_partner_by_id.return_value = MagicMock(
            is_internal=True
        )

        logger_mock = MagicMock()

        user_service = UserService(
            user_repository=repository_mock,
            audit_service=None,
            console_service_logger=logger_mock,
            console_service_cache=None,
            auth_service_utility=None,
            session_factory=MagicMock(),
        )

        # Act & Assert
        with pytest.raises(CountryNotFoundError, match="Country not found"):
            await user_service.update_user(
                user_id,
                current_user,
                user_data,
                location_service=location_service_mock,
                partner_service=partner_service_mock,
            )

        repository_mock.get_by_id.assert_called_once_with(
            user_id, show_inactive_users=True
        )
        logger_mock.error.assert_called_with(
            "Country not find while create user: Country not found, id: Country not found"
        )

    async def test_update_user_not_found(self):
        """Test update user when user is not found."""
        # Arrange
        user_id= UUID("11111111-1111-1111-1111-111111111111")
        user_data = MagicMock()

        repository_mock = AsyncMock()
        repository_mock.get_by_id.side_effect = UserNotFoundError(
            "User not found, id: User not found"
        )

        logger_mock = MagicMock()
        partner_service_mock = AsyncMock()
        partner_service_mock.get_partner_by_id.return_value = MagicMock(
            is_internal=True
        )

        user_service = UserService(
            user_repository=repository_mock,
            audit_service=None,
            console_service_logger=logger_mock,
            console_service_cache=None,
            auth_service_utility=None,
            session_factory=MagicMock(),
        )

        # Act & Assert
        with pytest.raises(
            UserNotFoundError,
            match="User not found, id: User not found, id: User not found",
        ):
            await user_service.update_user(
                user_id, 12, user_data, partner_service=partner_service_mock
            )

        repository_mock.get_by_id.assert_called_once_with(
            user_id, show_inactive_users=True
        )
        logger_mock.error.assert_called_with(
            "User not found, id: User not found, id: User not found"
        )

    async def test_update_user_unexpected_error(self):
        """Test update user with an unexpected error."""
        # Arrange
        user_id= UUID("11111111-1111-1111-1111-111111111111")
        user_data = MagicMock()

        repository_mock = AsyncMock()
        repository_mock.get_by_id.side_effect = Exception(
            "Unexpected error"
        )

        logger_mock = MagicMock()
        partner_service_mock = AsyncMock()
        partner_service_mock.get_partner_by_id.return_value = MagicMock(
            is_internal=True
        )

        user_service = UserService(
            user_repository=repository_mock,
            audit_service=None,
            console_service_logger=logger_mock,
            console_service_cache=None,
            auth_service_utility=None,
            session_factory=MagicMock(),
        )

        # Act & Assert
        with pytest.raises(Exception, match="Unexpected error"):
            await user_service.update_user(
                user_id, 12, user_data, partner_service=partner_service_mock
            )

        repository_mock.get_by_id.assert_called_once_with(
            user_id, show_inactive_users=True
        )
        logger_mock.error.assert_called_with("error updating partner Unexpected error")

    async def test_update_user_city_not_found(self):
        """Test update user with invalid city."""
        # Arrange
        user_id= UUID("11111111-1111-1111-1111-111111111111")
        user_data = MagicMock(city_id= UUID("99999999-9999-9999-9999-999999999999"))
        existing_user = MagicMock(id=user_id)
        current_user = {"user_id": UUID("33333333-3333-3333-3333-333333333333"), "partner_id": UUID("12121212-1212-1212-1212-121212121212")}

        repository_mock = AsyncMock()
        repository_mock.get_by_id.return_value = existing_user

        partner_service_mock = AsyncMock()
        partner_service_mock.get_partner_by_id.return_value = MagicMock(
            is_internal=True
        )

        location_service_mock = AsyncMock()
        location_service_mock.validate_location_hierarchy.side_effect = (
            CityNotFoundError("City not found")
        )

        logger_mock = MagicMock()

        user_service = UserService(
            user_repository=repository_mock,
            audit_service=None,
            console_service_logger=logger_mock,
            console_service_cache=None,
            auth_service_utility=None,
            session_factory=MagicMock(),
        )

        # Act & Assert
        with pytest.raises(CityNotFoundError, match="City not found"):
            await user_service.update_user(
                user_id,
                current_user,
                user_data,
                location_service=location_service_mock,
                partner_service=partner_service_mock,
            )

        repository_mock.get_by_id.assert_called_once_with(
            user_id, show_inactive_users=True
        )
        logger_mock.error.assert_called_with(
            "City not find while create user: City not found, id: City not found"
        )

    async def test_update_user_state_not_found(self):
        """Test update user with invalid state."""
        # Arrange
        user_id= UUID("11111111-1111-1111-1111-111111111111")
        user_data = MagicMock(state_id= UUID("99999999-9999-9999-9999-999999999999"))
        existing_user = MagicMock(id=user_id)
        current_user = {"user_id": UUID("33333333-3333-3333-3333-333333333333"), "partner_id": UUID("12121212-1212-1212-1212-121212121212")}

        repository_mock = AsyncMock()
        repository_mock.get_by_id.return_value = existing_user

        location_service_mock = AsyncMock()
        location_service_mock.validate_location_hierarchy.side_effect = (
            StateNotFoundError("State not found")
        )
        partner_service_mock = AsyncMock()
        partner_service_mock.get_partner_by_id.return_value = MagicMock(
            is_internal=True
        )

        logger_mock = MagicMock()

        user_service = UserService(
            user_repository=repository_mock,
            audit_service=None,
            console_service_logger=logger_mock,
            console_service_cache=None,
            auth_service_utility=None,
            session_factory=MagicMock(),
        )

        # Act & Assert
        with pytest.raises(StateNotFoundError, match="State not found"):
            await user_service.update_user(
                user_id,
                current_user,
                user_data,
                location_service=location_service_mock,
                partner_service=partner_service_mock,
            )

        repository_mock.get_by_id.assert_called_once_with(
            user_id, show_inactive_users=True
        )
        logger_mock.error.assert_called_with(
            "State not find while create user: State not found, id: State not found"
        )

    async def test_update_user_reactivates_inactive_user(self):
        """An inactive user can be reactivated; audit action is ACTIVATE."""
        user_id= UUID("11111111-1111-1111-1111-111111111111")
        current_user = {"user_id": UUID("33333333-3333-3333-3333-333333333333"), "partner_id": UUID("12121212-1212-1212-1212-121212121212")}

        user_data = MagicMock(
            country_id=None,
            state_id=None,
            city_id=None,
            parent_id=None,
        )
        user_data.model_dump.return_value = {"is_active": True}

        existing_user = MagicMock(id=user_id, partner_id= UUID("12121212-1212-1212-1212-121212121212"), is_active=False)
        updated_user = MagicMock(id=user_id, partner_id= UUID("12121212-1212-1212-1212-121212121212"))

        repository_mock = AsyncMock()
        repository_mock.get_by_id.return_value = existing_user
        repository_mock.update_user.return_value = updated_user

        partner_service_mock = AsyncMock()
        partner_service_mock.get_partner_by_id.return_value = MagicMock(
            is_internal=True
        )
        audit_service_mock = AsyncMock()

        user_service = UserService(
            user_repository=repository_mock,
            audit_service=audit_service_mock,
            console_service_logger=MagicMock(),
            console_service_cache=AsyncMock(),
            auth_service_utility=AsyncMock(),
            session_factory=MagicMock(),
        )

        result = await user_service.update_user(
            user_id,
            current_user,
            user_data,
            location_service=AsyncMock(),
            auth_repository=AsyncMock(),
            partner_service=partner_service_mock,
            user_session_service=AsyncMock(),
            user_tracker_service=AsyncMock(),
        )

        repository_mock.get_by_id.assert_called_once_with(
            user_id, show_inactive_users=True
        )
        repository_mock.update_user.assert_awaited_once_with(
            user_id=user_id, current_user_id= UUID("33333333-3333-3333-3333-333333333333"), is_active=True
        )
        assert audit_service_mock.log_action.call_args.args[0].action == "ACTIVATE"
        assert result == updated_user

    async def test_update_user_deactivates_active_user(self):
        """An active user can be deactivated; sessions are killed and audit action is DEACTIVATE."""
        user_id= UUID("11111111-1111-1111-1111-111111111111")
        current_user = {"user_id": UUID("33333333-3333-3333-3333-333333333333"), "partner_id": UUID("12121212-1212-1212-1212-121212121212")}

        user_data = MagicMock(
            country_id=None,
            state_id=None,
            city_id=None,
            parent_id=None,
        )
        user_data.model_dump.return_value = {"is_active": False}

        repository_mock = AsyncMock()
        repository_mock.get_by_id.return_value = MagicMock(
            id=user_id, partner_id= UUID("12121212-1212-1212-1212-121212121212"), is_active=True
        )
        repository_mock.update_user.return_value = MagicMock(id=user_id, partner_id= UUID("12121212-1212-1212-1212-121212121212"))

        partner_service_mock = AsyncMock()
        partner_service_mock.get_partner_by_id.return_value = MagicMock(
            is_internal=True
        )
        audit_service_mock = AsyncMock()
        user_session_service_mock = AsyncMock()

        user_service = UserService(
            user_repository=repository_mock,
            audit_service=audit_service_mock,
            console_service_logger=MagicMock(),
            console_service_cache=AsyncMock(),
            auth_service_utility=AsyncMock(),
            session_factory=MagicMock(),
        )

        await user_service.update_user(
            user_id,
            current_user,
            user_data,
            location_service=AsyncMock(),
            auth_repository=AsyncMock(),
            partner_service=partner_service_mock,
            user_session_service=user_session_service_mock,
            user_tracker_service=AsyncMock(),
        )

        assert audit_service_mock.log_action.call_args.args[0].action == "DEACTIVATE"
        user_session_service_mock.deactivate_user_sessions.assert_awaited_once_with(
            user_id
        )

    async def test_update_user_same_status_raises(self):
        """Sending the status the user already has is rejected before any write."""
        user_data = MagicMock()
        user_data.model_dump.return_value = {"is_active": True}

        repository_mock = AsyncMock()
        repository_mock.get_by_id.return_value = MagicMock(
            id= UUID("11111111-1111-1111-1111-111111111111"), is_active=True
        )
        partner_service_mock = AsyncMock()
        partner_service_mock.get_partner_by_id.return_value = MagicMock(
            is_internal=True
        )

        user_service = UserService(
            user_repository=repository_mock,
            audit_service=AsyncMock(),
            console_service_logger=MagicMock(),
            console_service_cache=AsyncMock(),
            auth_service_utility=AsyncMock(),
            session_factory=MagicMock(),
        )

        with pytest.raises(UserException, match="already active"):
            await user_service.update_user(
                1,
                {"user_id": UUID("33333333-3333-3333-3333-333333333333"), "partner_id": UUID("12121212-1212-1212-1212-121212121212")},
                user_data,
                partner_service=partner_service_mock,
            )

        repository_mock.update_user.assert_not_awaited()

    @pytest.mark.parametrize(
        "constraint_name,expected_exception,field",
        [
            ("console_users_partner_id_fkey", PartnerNotFoundError, "partner_id"),
            ("console_users_parent_id_fkey", UserNotFoundError, "parent_id"),
            ("console_users_role_id_fkey", RoleNotFoundError, "role_id"),
            ("console_users_country_id_fkey", CountryNotFoundError, "country_id"),
            ("console_users_state_id_fkey", StateNotFoundError, "state_id"),
            ("console_users_city_id_fkey", CityNotFoundError, "city_id"),
            ("console_users_email_key", UserException, "Provided email already exists"),
        ],
    )
    async def test_update_user_sqlalchemy_error(
        self, constraint_name, expected_exception, field
    ):
        # Arrange
        user_id= UUID("11111111-1111-1111-1111-111111111111")
        user_data = MagicMock()
        setattr(user_data, field, 999)
        user_role = MagicMock(hierarchy="USER")  # Mock role object
        current_user = {"user_id": UUID("33333333-3333-3333-3333-333333333333"), "partner_id": UUID("12121212-1212-1212-1212-121212121212")}

        self.user_repository_mock.get_by_id.return_value = (
            MagicMock()
        )

        # Build a realistic error message (matches our regex: r'constraint\s+"([^"]+)"')
        error_message = (
            f'duplicate key value violates unique constraint "{constraint_name}"'
        )
        orig = Exception(error_message)
        mock_exception = IntegrityError(statement=None, params=None, orig=orig)

        self.user_repository_mock.update_user.side_effect = mock_exception

        auth_repository_mock = AsyncMock()  # Mock auth_repository
        auth_repository_mock.get_role_by_id.return_value = user_role
        partner_service_mock = AsyncMock()
        partner_service_mock.get_partner_by_id.return_value = MagicMock(
            is_internal=True
        )

        # Act & Assert
        with pytest.raises(expected_exception):
            await self.user_service.update_user(
                user_id,
                current_user,
                user_data,
                location_service=AsyncMock(),
                auth_repository=auth_repository_mock,
                partner_service=partner_service_mock,
            )

        self.mock_logger.error.assert_called()

    async def test_get_admin_credentials_by_hierarchy_success(self):
        """Test successful retrieval of admin credentials by hierarchy."""

        # Mock repository's method
        mock_admin_credentials = {
            "email": "admin@example.com",
            "phone_number": "9876543210",
        }
        self.user_repository_mock.get_admin_credentials_by_hierarchy.return_value = (
            mock_admin_credentials
        )

        # Call the service method
        user_hierarchy = 1
        partner_id= UUID("10101010-1010-1010-1010-101010101010")
        result = await self.user_service.get_admin_credentials_by_hierarchy(
            user_hierarchy, partner_id
        )

        # Assertions
        assert result == mock_admin_credentials
        self.user_repository_mock.get_admin_credentials_by_hierarchy.assert_awaited_once_with(
            user_hierarchy, partner_id
        )
        self.mock_logger.info.assert_any_call(
            f"Trying to get the admin creds by hierarchy: {user_hierarchy}"
        )
        self.mock_logger.info.assert_any_call(
            f"Admin creds fetched successfully: {mock_admin_credentials}"
        )

    async def test_get_admin_credentials_by_hierarchy_unexpected_error(self):
        """Test unexpected error while retrieving admin credentials by hierarchy."""

        # Mock repository's method to raise an exception
        self.user_repository_mock.get_admin_credentials_by_hierarchy.side_effect = (
            Exception("Database error")
        )

        user_hierarchy = 1
        partner_id= UUID("10101010-1010-1010-1010-101010101010")

        # Call the service method and expect an exception
        with pytest.raises(Exception) as exc_info:
            await self.user_service.get_admin_credentials_by_hierarchy(
                user_hierarchy, partner_id
            )

        # Assertions
        assert str(exc_info.value) == "Database error"
        self.user_repository_mock.get_admin_credentials_by_hierarchy.assert_awaited_once_with(
            user_hierarchy, partner_id
        )
        self.mock_logger.info.assert_any_call(
            f"Trying to get the admin creds by hierarchy: {user_hierarchy}"
        )
        self.mock_logger.error.assert_called()

    async def test_get_users_availability_status_success(self):
        """Test successful retrieval of users status."""
        user_ids = [UUID("11111111-1111-1111-1111-111111111111"), UUID("22222222-2222-2222-2222-222222222222")]

        mock_users_status = [
            {"user_id": 1, "current_status": "Active"},
            {"user_id": 2, "current_status": "Offline"},
        ]
        self.user_repository_mock.get_users_availability_status.return_value = mock_users_status

        result = await self.user_service.get_users_availability_status(user_ids)

        assert result == mock_users_status
        self.user_repository_mock.get_users_availability_status.assert_awaited_once_with(user_ids)
        self.mock_logger.info.assert_any_call(
            f"Trying to get the users status by user_ids: {user_ids}"
        )
        self.mock_logger.info.assert_any_call(
            f"Users status fetched successfully: {mock_users_status}"
        )

    async def test_get_users_availability_status_unexpected_error(self):
        """Test unexpected error while retrieving users status."""
        user_ids = [UUID("11111111-1111-1111-1111-111111111111"), UUID("22222222-2222-2222-2222-222222222222")]

        self.user_repository_mock.get_users_availability_status.side_effect = Exception(
            "Database error"
        )

        with pytest.raises(Exception) as exc_info:
            await self.user_service.get_users_availability_status(user_ids)

        assert str(exc_info.value) == "Database error"
        self.user_repository_mock.get_users_availability_status.assert_awaited_once_with(user_ids)
        self.mock_logger.error.assert_called()

    async def test_get_admin_details_by_partner_id_success(self):
        partner_id= UUID("12312312-3123-1231-2312-312312312312")
        user_mock = MagicMock()
        response_mock = MagicMock()

        self.user_repository_mock.get_admin_details_by_partner_id.return_value = (
            user_mock
        )

        with patch(
            "src.components.user.services.Contrasts.GetUserDetailResponse.model_validate",
            return_value=response_mock,
        ) as mock_validate:
            result = await self.user_service.get_admin_details_by_partner_id(partner_id)
            assert result == response_mock
            self.user_repository_mock.get_admin_details_by_partner_id.assert_awaited_once_with(
                partner_id
            )
            mock_validate.assert_called_once_with(user_mock)
            self.mock_logger.info.assert_any_call(
                f"Fetching admin user by partner id: {partner_id}"
            )

    async def test_get_admin_details_by_partner_id_user_exception(self):
        partner_id= UUID("12312312-3123-1231-2312-312312312312")
        self.user_repository_mock.get_admin_details_by_partner_id.side_effect = (
            UserException("User not found")
        )

        with pytest.raises(UserException, match="User not found"):
            await self.user_service.get_admin_details_by_partner_id(partner_id)
        self.user_repository_mock.get_admin_details_by_partner_id.assert_awaited_once_with(
            partner_id
        )
        self.mock_logger.error.assert_any_call(
            f"User not found for the partner id: {partner_id}"
        )

    async def test_get_admin_details_by_partner_id_unexpected_exception(self):
        partner_id= UUID("12312312-3123-1231-2312-312312312312")
        self.user_repository_mock.get_admin_details_by_partner_id.side_effect = (
            Exception("Unexpected error")
        )

        with pytest.raises(Exception, match="Unexpected error"):
            await self.user_service.get_admin_details_by_partner_id(partner_id)
        self.user_repository_mock.get_admin_details_by_partner_id.assert_awaited_once_with(
            partner_id
        )
        self.mock_logger.error.assert_any_call(
            "An error occured while fetching the user: Unexpected error"
        )

    def test_clean_user_data_active_user_no_id_prefix_suffix(self):
        """Test _clean_user_data with active user having no ID prefix/suffix in email and phone_number."""
        user_mock = AsyncMock()
        user_mock.email = "shalini.rani@affinityeducation.in"
        user_mock.phone_number = "+91-7634-567-890"
        user_mock.id = 48

        result = self.user_service._clean_user_data(user_mock)

        assert result == ("shalini.rani@affinityeducation.in", "+91-7634-567-890")

    def test_clean_user_data_with_id_prefix_in_email(self):
        """Test _clean_user_data with email having ID prefix."""
        user_mock = AsyncMock()
        user_mock.email = "48_shalini.rani@affinityeducation.in"
        user_mock.phone_number = "+91-7634-567-890"
        user_mock.id = 48

        result = self.user_service._clean_user_data(user_mock)

        assert result == ("shalini.rani@affinityeducation.in", "+91-7634-567-890")

    def test_clean_user_data_with_id_suffix_in_email(self):
        """Test _clean_user_data with email having ID suffix."""
        user_mock = AsyncMock()
        user_mock.email = "shalini.rani_48@affinityeducation.in"
        user_mock.phone_number = "+91-7634-567-890"
        user_mock.id = 48

        result = self.user_service._clean_user_data(user_mock)

        assert result == ("shalini.rani@affinityeducation.in", "+91-7634-567-890")

    def test_clean_user_data_with_id_suffix_in_phone_number(self):
        """Test _clean_user_data with phone_number having ID suffix."""
        user_mock = AsyncMock()
        user_mock.email = "shalini.rani@affinityeducation.in"
        user_mock.phone_number = "+91-7634-567-890_48"
        user_mock.id = 48

        result = self.user_service._clean_user_data(user_mock)

        assert result == ("shalini.rani@affinityeducation.in", "+91-7634-567-890")

    def test_clean_user_data_with_id_in_both_email_and_phone_number(self):
        """Test _clean_user_data with ID in both email prefix and phone_number suffix."""
        user_mock = AsyncMock()
        user_mock.email = "48_shalini.rani@affinityeducation.in"
        user_mock.phone_number = "+91-7634-567-890_48"
        user_mock.id = 48

        result = self.user_service._clean_user_data(user_mock)

        assert result == ("shalini.rani@affinityeducation.in", "+91-7634-567-890")

    async def test_get_users_inactive_user_cleaned_data(self):
        """Test get_users calls _clean_user_data for inactive user."""
        current_user_id= UUID("11111111-1111-1111-1111-111111111111")
        limit = 10
        offset = 0

        # Mock User object for inactive user
        user_mock = AsyncMock(spec=User)
        user_mock.id = UUID("11111111-1111-1111-1111-111111111111")
        user_mock.name = "John Doe"
        user_mock.email = "11111111-1111-1111-1111-111111111111_john.doe@example.com"
        user_mock.designation = "Manager"
        user_mock.phone_number = "+1-202-555-0123_11111111-1111-1111-1111-111111111111"
        user_mock.parent_id = None
        user_mock.partner_id = None
        user_mock.role_id= UUID("11111111-1111-1111-1111-111111111111")
        user_mock.country_id= UUID("11111111-1111-1111-1111-111111111111")
        user_mock.country = Mock()
        user_mock.country.name = "USA"
        user_mock.state_id = None
        user_mock.city_id = None
        user_mock.parent = None
        user_mock.is_active = False
        user_mock.cloud_agent_number = "09876"
        user_mock.current_status = "Active"

        # Mock repository response
        self.user_repository_mock.get_all.return_value = ([user_mock], 1)

        # Mock auth service response
        role_mock = Mock()
        role_mock.name = "Counsellor"
        self.auth_utility_mock.get_role_by_id.return_value = role_mock

        # Call the service method
        result = await self.user_service.get_users(
            current_user_id, limit, offset, auth_service=self.auth_utility_mock
        )

        # Assertions
        assert isinstance(result, PaginatedAllUsersDataResponse)
        assert result.total_count == 1
        assert result.limit == limit
        assert result.offset == offset
        assert len(result.users_data) == 1
        assert isinstance(result.users_data[0], AllUsersDataResponse)
        assert result.users_data[0].id == UUID("11111111-1111-1111-1111-111111111111")
        assert result.users_data[0].email == "john.doe@example.com"  # Cleaned email
        assert (
            result.users_data[0].phone_number == "+1-202-555-0123"
        )  # Cleaned phone number
        assert result.users_data[0].is_active is False

    async def test_get_user_by_id_user_not_found(self, user_service):
        user_service._UserService__repository.get_by_id.side_effect = UserNotFoundError(
            "User not found"
        )
        with pytest.raises(UserNotFoundError):
            await user_service.get_user_by_id(999)

    @pytest.mark.asyncio
    async def test_delete_user_by_id_clears_cache(self):
        # --- Arrange ---
        mock_user = User(id= UUID("11111111-1111-1111-1111-111111111111"), is_active=False, partner_id= UUID("12312312-3123-1231-2312-312312312312"))
        self.user_repository_mock.delete_by_id.return_value = mock_user
        self.user_repository_mock.get_by_id.return_value = mock_user
        self.user_repository_mock.has_child_users.return_value = False

        # Mock request with Authorization header
        mock_request = MagicMock()
        mock_request.headers = {"Authorization": "Bearer test-token"}

        # Mock session service
        user_session_service = AsyncMock()

        # --- Act ---
        await self.user_service.delete_user_by_id(
            request=mock_request,
            user_id= UUID("11111111-1111-1111-1111-111111111111"),
            user_session_service=user_session_service,
        )

        # --- Assert ---
        self.user_repository_mock.delete_by_id.assert_called_once_with(UUID("11111111-1111-1111-1111-111111111111"))
        self.redis_mock.clear_pattern.assert_called()
        user_session_service.deactivate_user_sessions.assert_called_once_with(UUID("11111111-1111-1111-1111-111111111111"))

    async def test_get_user_by_user_id_not_found(self, user_service):
        user_service._UserService__repository.get_user_by_user_id.side_effect = (
            UserNotFoundError("Not found")
        )
        with pytest.raises(UserNotFoundError):
            await user_service.get_user_by_user_id(1, 2)

    async def test_clean_user_data(self, user_service):
        user = User(
            id= UUID("48484848-4848-4848-4848-484848484848"),
            email="48484848-4848-4848-4848-484848484848_shalini.rani@affinityeducation.in",
            phone_number="+91-7634-567-890_48484848-4848-4848-4848-484848484848",
        )
        email, phone = user_service._clean_user_data(user)
        assert email == "shalini.rani@affinityeducation.in"
        assert phone == "+91-7634-567-890"

    async def test_is_user_internal_false(self, user_service):
        mock_user = User(id= UUID("11111111-1111-1111-1111-111111111111"), is_internal=False)
        user_service.get_user_by_id = AsyncMock(return_value=mock_user)
        assert not await user_service.is_user_internal(1)

    async def test_is_user_internal_true(self, user_service):
        mock_user = User(id= UUID("11111111-1111-1111-1111-111111111111"), is_internal=True)
        user_service.get_user_by_id = AsyncMock(return_value=mock_user)
        assert await user_service.is_user_internal(1)

    async def test_get_users_user_exception(self):
        """Test handling of UserException in get_users method."""
        current_user_id= UUID("11111111-1111-1111-1111-111111111111")
        limit = 10
        offset = 0

        # Mock repository to raise UserException
        self.user_repository_mock.get_all.side_effect = UserException(
            "User role not found"
        )

        # Reset mock logger to avoid interference
        self.mock_logger.reset_mock()

        # Expect UserException to be raised
        with pytest.raises(UserException) as exc_info:
            await self.user_service.get_users(
                current_user_id, limit, offset, auth_service=self.auth_utility_mock
            )

        # Assertions
        assert str(exc_info.value) == "User role not found"
        self.mock_logger.error.assert_called_once_with(
            "User role not found while getting all users: User role not found"
        )
        self.mock_logger.info.assert_called_once_with("getting all users")
        self.user_repository_mock.get_all.assert_called_once_with(
            current_user_id, limit, offset, filter_criteria=None
        )

    async def test_get_user_by_id_success(self):
        """Test successful retrieval of a user by ID."""
        user_id= UUID("11111111-1111-1111-1111-111111111111")
        user_mock = AsyncMock(spec=User)
        user_mock.id = user_id
        user_mock.name = "Jane Doe"

        # Mock repository response
        self.user_repository_mock.get_by_id.return_value = user_mock

        # Call the service method
        result = await self.user_service.get_user_by_id(user_id)

        # Assertions
        assert result == user_mock
        assert result.id == user_id
        assert result.name == "Jane Doe"
        self.user_repository_mock.get_by_id.assert_called_once_with(user_id)
        self.mock_logger.info.assert_any_call(f"Getting the user by id :{user_id} ")
        self.mock_logger.info.assert_any_call(
            f"User fetched sucsessfully : {user_mock} "
        )

    async def test_get_user_by_id_generic_exception(self):
        """Test handling of generic exception in get_user_by_id method."""
        user_id= UUID("11111111-1111-1111-1111-111111111111")

        # Mock repository to raise generic exception
        self.user_repository_mock.get_by_id.side_effect = Exception("Database error")

        # Reset mock logger
        self.mock_logger.reset_mock()

        # Expect generic exception to be raised
        with pytest.raises(Exception) as exc_info:
            await self.user_service.get_user_by_id(user_id)

        # Assertions
        assert str(exc_info.value) == "Database error"
        self.mock_logger.error.assert_called_once_with(
            "error getting user Database error"
        )
        self.mock_logger.info.assert_called_once_with(
            f"Getting the user by id :{user_id} "
        )
        self.user_repository_mock.get_by_id.assert_called_once_with(user_id)

    async def test_get_user_by_id_not_found(self):
        """Test handling of UserNotFoundError in get_user_by_id method."""
        user_id= UUID("11111111-1111-1111-1111-111111111111")

        # Mock repository to raise UserNotFoundError
        self.user_repository_mock.get_by_id.side_effect = UserNotFoundError(user_id)

        # Reset mock logger
        self.mock_logger.reset_mock()

        # Expect UserNotFoundError to be raised
        with pytest.raises(UserNotFoundError) as exc_info:
            await self.user_service.get_user_by_id(user_id)

        # Assertions
        assert str(exc_info.value) == f"User not found, id: {user_id}"
        self.mock_logger.error.assert_called_once_with(str(exc_info.value))
        self.mock_logger.info.assert_called_once_with(
            f"Getting the user by id :{user_id} "
        )
        self.user_repository_mock.get_by_id.assert_called_once_with(user_id)

    async def test_delete_user_by_id_not_found(self):
        """Test handling of UserNotFoundError when user not found in get_user_by_id."""
        user_id= UUID("11111111-1111-1111-1111-111111111111")

        # Simulate user not found
        self.user_service.get_user_by_id = AsyncMock(
            side_effect=UserNotFoundError(user_id)
        )
        # Mock request and session
        mock_request = MagicMock()
        mock_request.headers = {"Authorization": "Bearer test-token"}
        user_session_service = AsyncMock()

        # Reset mocks
        self.mock_logger.reset_mock()
        self.user_repository_mock.delete_by_id.reset_mock()
        self.redis_mock.clear_pattern.reset_mock()
        self.audit_log_mock.log_action.reset_mock()

        # --- Act & Assert ---
        with pytest.raises(UserNotFoundError) as exc_info:
            await self.user_service.delete_user_by_id(
                request=mock_request,
                user_id=user_id,
                user_session_service=user_session_service,
            )

    async def test_delete_user_by_id_generic_exception(self):
        """Test handling of generic exception in delete_user_by_id method."""
        user_id= UUID("11111111-1111-1111-1111-111111111111")

        # --- Arrange ---
        # Mock get_user_by_id to succeed (so we reach delete_by_id)
        self.user_service.get_user_by_id = AsyncMock(return_value=AsyncMock())

        # Mock repository delete_by_id to raise generic Exception
        self.user_repository_mock.delete_by_id.side_effect = Exception("Database error")

        # Mock request with Authorization header
        mock_request = MagicMock()
        mock_request.headers = {"Authorization": "Bearer test-token"}

        # Reset mocks
        self.mock_logger.reset_mock()
        self.redis_mock.clear_pattern.reset_mock()
        self.audit_log_mock.log_action.reset_mock()
        self.user_session_service.deactivate_user_sessions.reset_mock()

        # --- Act & Assert ---
        with pytest.raises(Exception) as exc_info:
            await self.user_service.delete_user_by_id(
                request=mock_request,
                user_id=user_id,
                user_session_service=self.user_session_service,
            )

    async def test_enlist_users_by_partner_id_success(self):
        filter_request = UserRoleFilterRequest(partner_id= UUID("12312312-3123-1231-2312-312312312312"))
        partner_repository = AsyncMock()
        filter_service = AsyncMock()
        partner_repository.get_by_id.return_value = MagicMock()
        filter_service.get_user_data.return_value = [{"user_id": 1, "role_id": 2}]

        result = await self.user_service.enlist_users_dynamically(
            {"user_id": 10},
            filter_request,
            partner_repository=partner_repository,
            filter_service=filter_service,
        )

        assert result == [{"user_id": 1, "role_id": 2}]
        partner_repository.get_by_id.assert_awaited_once_with(UUID("12312312-3123-1231-2312-312312312312"))
        filter_service.get_user_data.assert_awaited_once_with(
            filter_request=filter_request
        )
        self.mock_logger.info.assert_any_call(
            "Checking partner: 12312312-3123-1231-2312-312312312312 is activate or available."
        )
        self.mock_logger.info.assert_any_call(
            "Attempting to get users by partner id: 12312312-3123-1231-2312-312312312312"
        )

    async def test_enlist_users_by_partner_id_partner_not_found(self):
        filter_request = UserRoleFilterRequest(partner_id= UUID("99999999-9999-9999-9999-999999999999"))
        partner_repository = AsyncMock()
        filter_service = AsyncMock()
        partner_repository.get_by_id.return_value = None

        with pytest.raises(PartnerNotFoundError):
            await self.user_service.enlist_users_dynamically(
                {"user_id": 10},
                filter_request,
                partner_repository=partner_repository,
                filter_service=filter_service,
            )

        partner_repository.get_by_id.assert_awaited_once_with(UUID("99999999-9999-9999-9999-999999999999"))
        self.mock_logger.error.assert_called_with(
            "Partner not find while get users by partner_id: Partner not found, id: 99999999-9999-9999-9999-999999999999"
        )

    async def test_enlist_users_by_partner_id_user_exception(self):
        filter_request = UserRoleFilterRequest(partner_id= UUID("12312312-3123-1231-2312-312312312312"))
        partner_repository = AsyncMock()
        filter_service = AsyncMock()
        partner_repository.get_by_id.return_value = MagicMock()
        filter_service.get_user_data.side_effect = UserException("User error")

        with pytest.raises(UserException):
            await self.user_service.enlist_users_dynamically(
                {"user_id": 10},
                filter_request,
                partner_repository=partner_repository,
                filter_service=filter_service,
            )

        self.mock_logger.error.assert_called_with(
            "UserException occurred while getting users by partner_id: User error"
        )

    async def test_enlist_users_by_partner_id_generic_exception(self):
        filter_request = UserRoleFilterRequest(partner_id= UUID("12312312-3123-1231-2312-312312312312"))
        partner_repository = AsyncMock()
        filter_service = AsyncMock()
        partner_repository.get_by_id.side_effect = Exception("Unexpected error")

        with pytest.raises(Exception, match="Unexpected error"):
            await self.user_service.enlist_users_dynamically(
                {"user_id": 10},
                filter_request,
                partner_repository=partner_repository,
                filter_service=filter_service,
            )

        self.mock_logger.error.assert_called_with(
            "Unexpected error during get users by partner_id: Exception('Unexpected error')"
        )

    async def test_get_users_by_partner_id_not_found(self, user_service):
        partner_repo = AsyncMock()
        partner_repo.get_by_id.side_effect = PartnerNotFoundError("Not found")
        with pytest.raises(PartnerNotFoundError):
            await user_service.get_users_by_partner_id(
                1, partner_repository=partner_repo
            )

    async def test_get_users_by_partner_id_partner_not_found(self):
        # Arrange
        partner_id= UUID("10110110-1101-1011-0110-110110110110")
        self.partner_repository_mock.get_by_id.return_value = None

        # Act & Assert
        with pytest.raises(PartnerNotFoundError) as exc_info:
            await self.user_service.get_users_by_partner_id(
                partner_id=partner_id, partner_repository=self.partner_repository_mock
            )

        # Assert logs and error
        self.mock_logger.info.assert_called_with(
            f"Checking partner: {partner_id} is activate or available."
        )
        self.mock_logger.error.assert_called_with(
            f"Partner not find while get users by partner_id: Partner not found, id: {partner_id}"
        )
        assert str(exc_info.value) == f"Partner not found, id: {partner_id}"

    async def test_enlist_users_dynamically_non_internal_returns_empty(self):
        current_user = {"user_id": 10, "partner_id": 100}
        filter_request = UserRoleFilterRequest(partner_id= UUID("20020020-0200-2002-0020-020020020020"))
        partner_repository = AsyncMock()
        filter_service = AsyncMock()

        # Ensure user is non-internal
        self.user_service.is_user_internal = AsyncMock(return_value=False)

        result = await self.user_service.enlist_users_dynamically(
            current_user, filter_request, partner_repository=partner_repository, filter_service=filter_service
        )

        assert result == []
        self.user_service.is_user_internal.assert_awaited_once_with(10)
        partner_repository.get_by_id.assert_not_awaited()
        filter_service.get_user_data.assert_not_awaited()
        self.mock_logger.info.assert_any_call(
            "Checking partner: 20020020-0200-2002-0020-020020020020 is activate or available."
        )

    async def test_enlist_users_dynamically_internal_user_allows_listing(self):
        current_user = {"user_id": 11, "partner_id": 100}
        filter_request = UserRoleFilterRequest(partner_id= UUID("20020020-0200-2002-0020-020020020020"))
        partner_repository = AsyncMock()
        filter_service = AsyncMock()

        # Internal user should be allowed to fetch users for different partner_id
        self.user_service.is_user_internal = AsyncMock(return_value=True)
        partner_repository.get_by_id.return_value = MagicMock()
        filter_service.get_user_data.return_value = [{"user_id": 1, "role_id": 2}]

        result = await self.user_service.enlist_users_dynamically(
            current_user, filter_request, partner_repository=partner_repository, filter_service=filter_service
        )

        assert result == [{"user_id": 1, "role_id": 2}]
        self.user_service.is_user_internal.assert_awaited_once_with(11)
        partner_repository.get_by_id.assert_awaited_once_with(UUID("20020020-0200-2002-0020-020020020020"))
        filter_service.get_user_data.assert_awaited_once_with(filter_request=filter_request)
        self.mock_logger.info.assert_any_call(
            "Checking partner: 20020020-0200-2002-0020-020020020020 is activate or available."
        )

    async def test_toggle_walkthrough_key_activation_success(self):
        user_id= UUID("11111111-1111-1111-1111-111111111111")
        update_data = MagicMock()
        update_data.model_dump.return_value = {"is_walkthrough_completed": True}

        # repository returns an object with partner_id
        repo_result = MagicMock(partner_id= UUID("12312312-3123-1231-2312-312312312312"))
        self.user_repository_mock.toggle_walkthrough_key_activation.return_value = repo_result

        await self.user_service.toggle_walkthrough_key_activation(user_id, update_data)

        self.user_repository_mock.toggle_walkthrough_key_activation.assert_awaited_once_with(
            user_id, **{"is_walkthrough_completed": True}
        )

        self.redis_mock.clear_pattern.assert_any_call(
            prefix=RedisCache.KeysPrefix.CONSOLE,
            pattern=CacheKeys.TOKEN.format(repo_result.partner_id, ""),
        )

    async def test_toggle_walkthrough_key_activation_repository_exception(self):
        user_id= UUID("22222222-2222-2222-2222-222222222222")
        update_data = MagicMock()
        update_data.model_dump.return_value = {}

        self.user_repository_mock.toggle_walkthrough_key_activation.side_effect = Exception("db error")

        with pytest.raises(Exception, match="db error"):
            await self.user_service.toggle_walkthrough_key_activation(user_id, update_data)

        self.mock_logger.error.assert_called()

    async def test_resolve_user_walkthrough_key_calls_toggle_when_expired_and_not_completed(self):
        user_id= UUID("10101010-1010-1010-1010-101010101010")
        partner_id= UUID("20202020-2020-2020-2020-202020202020")

        user_obj = MagicMock()
        user_obj.created_at = 0
        user_obj.is_walkthrough_completed = False

        self.user_service.get_user_by_user_id = AsyncMock(return_value=user_obj)
        self.user_service.toggle_walkthrough_key_activation = AsyncMock()

        # Ensure ENV and current time produce expiry = WALKTHROUGH_TIME_PERIOD
        with patch("src.components.user.services.ENV.WALKTHROUGH_LAUNCH_DATE", "0"), \
             patch("src.components.user.services.DateTimeUtil.get_current_time", return_value=259200000):
            await self.user_service.resolve_user_walkthrough_key(user_id, partner_id)

        self.user_service.toggle_walkthrough_key_activation.assert_awaited_once()
        called_args = self.user_service.toggle_walkthrough_key_activation.call_args[0]
        assert called_args[0] == user_id
        assert called_args[1].is_walkthrough_completed is True

    async def test_resolve_user_walkthrough_key_does_not_call_toggle_when_already_completed(self):
        user_id= UUID("11111111-1111-1111-1111-111111111111")
        partner_id= UUID("21212121-2121-2121-2121-212121212121")

        user_obj = MagicMock()
        user_obj.created_at = 0
        user_obj.is_walkthrough_completed = True

        self.user_service.get_user_by_user_id = AsyncMock(return_value=user_obj)
        self.user_service.toggle_walkthrough_key_activation = AsyncMock()

        with patch("src.components.user.services.ENV.WALKTHROUGH_LAUNCH_DATE", "0"), \
             patch("src.components.user.services.DateTimeUtil.get_current_time", return_value=259200000):
            await self.user_service.resolve_user_walkthrough_key(user_id, partner_id)

        self.user_service.toggle_walkthrough_key_activation.assert_not_awaited()

    async def test_resolve_user_walkthrough_key_propagates_get_user_error(self):
        user_id= UUID("12121212-1212-1212-1212-121212121212")
        partner_id= UUID("22222222-2222-2222-2222-222222222222")

        self.user_service.get_user_by_user_id = AsyncMock(side_effect=Exception("fetch error"))

        with pytest.raises(Exception, match="fetch error"):
            await self.user_service.resolve_user_walkthrough_key(user_id, partner_id)

        self.mock_logger.error.assert_called()

    @pytest.mark.asyncio
    async def test_get_agent_details_success(self):
        partner_id= UUID("11111111-1111-1111-1111-111111111111")
        ivr_phone = "9999999999"
        api_key = "valid_key"

        self.partner_repository_mock.get_by_id.return_value = MagicMock(id=partner_id)

        mock_api_repo = AsyncMock()
        mock_api_repo.get_active_api_key.return_value = MagicMock(key="valid_key")

        mock_user = MagicMock()
        mock_user.id = 101
        mock_user.name = "John"
        mock_user.phone_number = ivr_phone
        mock_user.email = "john@test.com"
        mock_user.partner_id = partner_id

        self.user_repository_mock.get_user_by_field.return_value = mock_user

        result = await self.user_service.get_agent_details_by_IVR(
            partner_id=partner_id,
            ivr_phone=ivr_phone,
            api_key=api_key,
            apiKeyRepository=mock_api_repo,
            partner_key_repo=self.partner_repository_mock,
        )
        print(result)

        assert result == {
            "name": "John",
            "phone_number": ivr_phone,
            "id": 101,
            "email": "john@test.com",
        }

    @pytest.mark.asyncio
    async def test_invalid_api_key(self):
        partner_id= UUID("11111111-1111-1111-1111-111111111111")

        self.partner_repository_mock.get_by_id.return_value = MagicMock()

        mock_api_repo = AsyncMock()
        mock_api_repo.get_active_api_key.return_value = MagicMock(key="correct_key")

        with pytest.raises(ApiKeyNotFoundError):
            await self.user_service.get_agent_details_by_IVR(
                partner_id=partner_id,
                ivr_phone="9999999999",
                api_key="wrong_key",
                apiKeyRepository=mock_api_repo,
                partner_key_repo=self.partner_repository_mock,
            )

    @pytest.mark.asyncio
    async def test_user_not_found(self):
        partner_id= UUID("11111111-1111-1111-1111-111111111111")
        ivr_phone = "9999999999"

        self.partner_repository_mock.get_by_id.return_value = MagicMock()

        mock_api_repo = AsyncMock()
        mock_api_repo.get_active_api_key.return_value = MagicMock(key="valid_key")

        self.user_repository_mock.get_user_by_field.return_value = None

        with pytest.raises(UserNotFoundError):
            await self.user_service.get_agent_details_by_IVR(
                partner_id=partner_id,
                ivr_phone=ivr_phone,
                api_key="valid_key",
                apiKeyRepository=mock_api_repo,
                partner_key_repo=self.partner_repository_mock,
            )

    @pytest.mark.asyncio
    async def test_user_wrong_partner(self):
        partner_id= UUID("11111111-1111-1111-1111-111111111111")
        ivr_phone = "9999999999"

        self.partner_repository_mock.get_by_id.return_value = MagicMock()

        mock_api_repo = AsyncMock()
        mock_api_repo.get_active_api_key.return_value = MagicMock(key="valid_key")

        mock_user = MagicMock(partner_id= UUID("99999999-9999-9999-9999-999999999999"))  # different partner
        self.user_repository_mock.get_user_by_field.return_value = mock_user

        with pytest.raises(UserNotFoundError):
            await self.user_service.get_agent_details_by_IVR(
                partner_id=partner_id,
                ivr_phone=ivr_phone,
                api_key="valid_key",
                apiKeyRepository=mock_api_repo,
                partner_key_repo=self.partner_repository_mock,
            )
    
    async def test_update_user_unknown_constraint_reraises_original(self):
        user_data = MagicMock()
        self.user_repository_mock.get_by_id.return_value = MagicMock()
        orig = Exception(
            'duplicate key value violates unique constraint "some_unknown_constraint"'
        )
        self.user_repository_mock.update_user.side_effect = IntegrityError(
            statement=None, params=None, orig=orig
        )
        auth_repository_mock = AsyncMock()
        auth_repository_mock.get_role_by_id.return_value = MagicMock(hierarchy="USER")
        partner_service_mock = AsyncMock()
        partner_service_mock.get_partner_by_id.return_value = MagicMock(is_internal=True)

        with pytest.raises(IntegrityError):
            await self.user_service.update_user(
                1,
                {"user_id": UUID("33333333-3333-3333-3333-333333333333"), "partner_id": UUID("12121212-1212-1212-1212-121212121212")},
                user_data,
                location_service=AsyncMock(),
                auth_repository=auth_repository_mock,
                partner_service=partner_service_mock,
            )

    async def test_update_user_same_status_inactive_message(self):
        user_data = MagicMock()
        user_data.model_dump.return_value = {"is_active": False}
        repository_mock = AsyncMock()
        repository_mock.get_by_id.return_value = MagicMock(
            id= UUID("11111111-1111-1111-1111-111111111111"), is_active=False
        )
        partner_service_mock = AsyncMock()
        partner_service_mock.get_partner_by_id.return_value = MagicMock(is_internal=True)

        user_service = UserService(
            user_repository=repository_mock,
            audit_service=AsyncMock(),
            console_service_logger=MagicMock(),
            console_service_cache=AsyncMock(),
            auth_service_utility=AsyncMock(),
            session_factory=MagicMock(),
        )
        with pytest.raises(UserException, match="already inactive"):
            await user_service.update_user(
                1, {"user_id": UUID("33333333-3333-3333-3333-333333333333"), "partner_id": UUID("12121212-1212-1212-1212-121212121212")}, user_data,
                partner_service=partner_service_mock,
            )