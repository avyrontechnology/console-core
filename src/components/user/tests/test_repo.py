from uuid import UUID
from collections import namedtuple
from unittest.mock import AsyncMock, MagicMock, PropertyMock, patch
import json
import pytest
from sqlalchemy.exc import SQLAlchemyError, IntegrityError
from src.components.user.constants import UserRoles
from src.components.common.errors import NotFoundError


from src.components.user.errors import UserNotFoundError
from src.components.user.repositories import UserRepository
from src.exceptions import UserException


@pytest.mark.asyncio
class TestUserRepository:

    @pytest.fixture(
        autouse=True,
    )
    def setup_class(self, mock_session_factory, mock_logger):
        """Set up the auth repository using fixtures for mock session and logger."""
        self.user_repository = UserRepository(
            session_factory=mock_session_factory, console_service_logger=mock_logger
        )

        self.session = mock_session_factory.return_value.__aenter__.return_value
        self.mock_logger = mock_logger

    async def test_get_user_details(self):

        user_id= UUID("11111111-1111-1111-1111-111111111111")
        mock_user = AsyncMock(
            user_id=user_id,
            name="test user",
            email="test@example.com",
            partner_id= UUID("11111111-1111-1111-1111-111111111111"),
            role_hierarchy_level=1,
        )

        # Mock the database execution and response
        mock_scalars = MagicMock()
        mock_scalars.first.return_value = mock_user
        mock_execute = MagicMock()
        mock_execute.mappings.return_value = mock_scalars
        self.session.execute = AsyncMock(return_value=mock_execute)

        result = await self.user_repository.get_user_details(user_id)

        assert result == mock_user

    async def test_get_user_details_generic_exception(self):
        user_id= UUID("11111111-1111-1111-1111-111111111111")
        self.session.execute = AsyncMock(side_effect=Exception("Unexpected Error"))

        with pytest.raises(Exception) as exc_info:
            await self.user_repository.get_user_details(user_id)

        assert str(exc_info.value) == "Unexpected Error"

    async def test_get_service_board_users_details_success(self):
        user_ids = [UUID("11111111-1111-1111-1111-111111111111"), UUID("22222222-2222-2222-2222-222222222222")]

        # Mock User data
        mock_user1 = {
            "user_id": 1,
            "email": "user1@example.com",
            "is_active": True,
            "is_suspended": False,
            "name": "User One",
        }
        mock_user2 = {
            "user_id": 2,
            "email": "user2@example.com",
            "is_active": True,
            "is_suspended": False,
            "name": "User Two",
        }
        mock_users = [mock_user1, mock_user2]

        # Mock database execution and response
        mock_result = MagicMock()
        mock_result.mappings.return_value.all.return_value = mock_users
        self.session.execute = AsyncMock(return_value=mock_result)

        result = await self.user_repository.get_service_board_users_details(user_ids)

        assert isinstance(result, list)
        assert len(result) == 2
        assert result[0]["user_id"] == 1
        assert result[0]["email"] == "user1@example.com"
        assert result[1]["user_id"] == 2
        assert result[1]["email"] == "user2@example.com"

    async def test_get_service_board_users_details_generic_exception(self):
        user_ids = [UUID("11111111-1111-1111-1111-111111111111"), UUID("22222222-2222-2222-2222-222222222222")]

        # Mock the execute method to raise an exception
        self.session.execute = AsyncMock(side_effect=Exception("Database Error"))

        with pytest.raises(Exception) as exc_info:
            await self.user_repository.get_service_board_users_details(user_ids)

        assert str(exc_info.value) == "Database Error"

    async def test_get_users_availability_status_success(self):
        user_ids = [UUID("11111111-1111-1111-1111-111111111111"), UUID("22222222-2222-2222-2222-222222222222")]

        mock_users_status = [
            {"user_id": 1, "current_status": "Active"},
            {"user_id": 2, "current_status": "Offline"},
        ]

        mock_result = MagicMock()
        mock_result.mappings.return_value.all.return_value = mock_users_status
        self.session.execute = AsyncMock(return_value=mock_result)

        result = await self.user_repository.get_users_availability_status(user_ids)

        assert isinstance(result, list)
        assert len(result) == 2
        assert result[0]["user_id"] == 1
        assert result[0]["current_status"] == "Active"
        assert result[1]["user_id"] == 2
        assert result[1]["current_status"] == "Offline"

    async def test_get_users_availability_status_generic_exception(self):
        user_ids = [UUID("11111111-1111-1111-1111-111111111111"), UUID("22222222-2222-2222-2222-222222222222")]

        self.session.execute = AsyncMock(side_effect=Exception("Database Error"))

        with pytest.raises(Exception) as exc_info:
            await self.user_repository.get_users_availability_status(user_ids)

        assert str(exc_info.value) == "Database Error"

    async def test_get_all_success(self):
        """Test successful retrieval of paginated users in a user's hierarchy."""
        current_user_id= UUID("11111111-1111-1111-1111-111111111111")
        limit = 10
        offset = 0

        # Mock User objects
        mock_user1 = MagicMock()
        mock_user1.id = UUID("11111111-1111-1111-1111-111111111111")
        mock_user1.name = "User One"
        mock_user1.email = "user1@example.com"
        mock_user1.is_active = True
        mock_user1.is_deleted = False
        mock_user1.country = MagicMock(name="USA")
        mock_user1.country.name = "USA"
        mock_user1.parent = None
        mock_user1.role_id= UUID("11111111-1111-1111-1111-111111111111")
        mock_user1.partner_id= UUID("11111111-1111-1111-1111-111111111111")

        mock_user2 = MagicMock()
        mock_user2.id = UUID("22222222-2222-2222-2222-222222222222")
        mock_user2.name = "User Two"
        mock_user2.email = "user2@example.com"
        mock_user2.is_active = True
        mock_user2.is_deleted = False
        mock_user2.country = MagicMock(name="Canada")
        mock_user2.country.name = "Canada"
        mock_user2.parent = mock_user1
        mock_user2.role_id= UUID("22222222-2222-2222-2222-222222222222")
        mock_user2.partner_id= UUID("11111111-1111-1111-1111-111111111111")

        mock_users = [mock_user1, mock_user2]

        # Mock auth_repository and get_role_by_id
        mock_auth_repository = MagicMock()
        mock_role = MagicMock()
        mock_role.slug = "USER"  # Non-MAINTAINER role to avoid admin logic
        mock_auth_repository.get_role_by_id = AsyncMock(return_value=mock_role)

        # Mock database execution and response
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = mock_users
        mock_count_result = MagicMock()
        mock_count_result.scalar.return_value = 2  # Mock total count

        # Mock current user query
        mock_current_user_result = MagicMock()
        mock_current_user_result.scalars.return_value.one_or_none.return_value = (
            mock_user1
        )

        self.session.execute = AsyncMock(
            side_effect=[mock_current_user_result, mock_count_result, mock_result]
        )

        # Call the repository method with mocked auth_repository
        users, total_count = await self.user_repository.get_all(
            current_user_id, limit, offset, auth_repository=mock_auth_repository
        )

        # Assertions
        assert isinstance(users, list)
        assert len(users) == 2
        assert users[0].id == UUID("11111111-1111-1111-1111-111111111111")
        assert users[0].name == "User One"
        assert users[0].email == "user1@example.com"
        assert users[0].country.name == "USA"
        assert users[0].parent is None
        assert users[1].id == UUID("22222222-2222-2222-2222-222222222222")
        assert users[1].name == "User Two"
        assert users[1].email == "user2@example.com"
        assert users[1].country.name == "Canada"
        assert users[1].parent == mock_user1
        assert total_count == 2

        # Verify logger calls
        self.mock_logger.info.assert_any_call(
            f"Getting all users under the hierarchy of user_id={current_user_id} from the database..."
        )
        self.mock_logger.info.assert_any_call(
            f"Fetched users in the user id: {current_user_id} hierarchy successfully, total count: {total_count}"
        )
        assert (
            self.session.execute.call_count == 3
        )  # Current user query + count + main query

    async def test_get_all_exception(self):
        """Test handling of SQLAlchemyError in get_all method."""
        current_user_id= UUID("11111111-1111-1111-1111-111111111111")
        limit = 10
        offset = 0

        # Mock auth_repository to avoid Depends issue
        mock_auth_repository = MagicMock()
        mock_role = MagicMock()
        mock_role.slug = "USER"
        mock_auth_repository.get_role_by_id = AsyncMock(return_value=mock_role)

        # Mock current user query to return a user
        mock_user = MagicMock()
        mock_user.id = 1
        mock_user.role_id= UUID("11111111-1111-1111-1111-111111111111")
        mock_user.partner_id= UUID("11111111-1111-1111-1111-111111111111")
        mock_current_user_result = MagicMock()
        mock_current_user_result.scalars.return_value.one_or_none.return_value = (
            mock_user
        )

        # Mock the execute method to raise an SQLAlchemyError
        self.session.execute = AsyncMock(
            side_effect=[
                mock_current_user_result,
                SQLAlchemyError("Database connection failed"),
            ]
        )

        # Reset logger mock
        self.mock_logger.reset_mock()

        # Expect the exception to be raised
        with pytest.raises(SQLAlchemyError) as exc_info:
            await self.user_repository.get_all(
                current_user_id, limit, offset, auth_repository=mock_auth_repository
            )

        # Assertions
        assert str(exc_info.value) == "Database connection failed"
        self.mock_logger.info.assert_called_once_with(
            f"Getting all users under the hierarchy of user_id={current_user_id} from the database..."
        )
        self.mock_logger.error.assert_called_once_with(
            "Database error: Database connection failed"
        )
        assert (
            self.session.execute.call_count == 2
        )  # Current user query + count query (fails)

    async def test_get_all_with_filter_criteria_on_user_field_applies_filter(self):
        """A filter on a plain User column (no role join) should still build and count correctly."""
        from src.components.filters.criteria import BaseFilterCriteria

        current_user_id= UUID("11111111-1111-1111-1111-111111111111")
        limit = 10
        offset = 0

        filter_criteria = BaseFilterCriteria()
        filter_criteria.add_filter("email", "=", "john@example.com")

        mock_user = MagicMock()
        mock_user.id = 1
        mock_user.role_id= UUID("11111111-1111-1111-1111-111111111111")
        mock_user.partner_id= UUID("11111111-1111-1111-1111-111111111111")
        mock_user.country = None
        mock_user.parent = None

        mock_auth_repository = MagicMock()
        mock_role = MagicMock()
        mock_role.slug = "USER"  # Non-MAINTAINER, so no admin exclusion logic
        mock_auth_repository.get_role_by_id = AsyncMock(return_value=mock_role)

        mock_current_user_result = MagicMock()
        mock_current_user_result.scalars.return_value.one_or_none.return_value = (
            mock_user
        )

        mock_count_result = MagicMock()
        mock_count_result.scalar.return_value = 1

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [mock_user]

        self.session.execute = AsyncMock(
            side_effect=[mock_current_user_result, mock_count_result, mock_result]
        )

        users, total_count = await self.user_repository.get_all(
            current_user_id,
            limit,
            offset,
            auth_repository=mock_auth_repository,
            filter_criteria=filter_criteria,
        )

        assert users == [mock_user]
        assert total_count == 1
        # Current user query + filtered count query + filtered main query
        assert self.session.execute.call_count == 3

    async def test_get_all_with_filter_criteria_on_role_field_joins_role(self):
        """A filter on a role_* alias must trigger the Role join before building/counting."""
        from src.components.filters.criteria import BaseFilterCriteria

        current_user_id= UUID("11111111-1111-1111-1111-111111111111")
        limit = 10
        offset = 0

        filter_criteria = BaseFilterCriteria()
        filter_criteria.add_filter("role_name", "=", "Admin")

        mock_user = MagicMock()
        mock_user.id = 1
        mock_user.role_id= UUID("11111111-1111-1111-1111-111111111111")
        mock_user.partner_id= UUID("11111111-1111-1111-1111-111111111111")
        mock_user.country = None
        mock_user.parent = None

        mock_auth_repository = MagicMock()
        mock_role = MagicMock()
        mock_role.slug = "USER"
        mock_auth_repository.get_role_by_id = AsyncMock(return_value=mock_role)

        mock_current_user_result = MagicMock()
        mock_current_user_result.scalars.return_value.one_or_none.return_value = (
            mock_user
        )

        mock_count_result = MagicMock()
        mock_count_result.scalar.return_value = 1

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [mock_user]

        self.session.execute = AsyncMock(
            side_effect=[mock_current_user_result, mock_count_result, mock_result]
        )

        with patch(
            "src.components.user.repositories.UserRoleFilterBuilder.requires_role_join",
            return_value=True,
        ) as mock_requires_join:
            users, total_count = await self.user_repository.get_all(
                current_user_id,
                limit,
                offset,
                auth_repository=mock_auth_repository,
                filter_criteria=filter_criteria,
            )

        mock_requires_join.assert_called_once_with(["role_name"])
        assert users == [mock_user]
        assert total_count == 1
        assert self.session.execute.call_count == 3

    async def test_get_all_without_filter_criteria_skips_filter_builder(self):
        """Passing no filter_criteria keeps the original, unfiltered hierarchy query."""
        current_user_id= UUID("11111111-1111-1111-1111-111111111111")
        limit = 10
        offset = 0

        mock_user = MagicMock()
        mock_user.id = 1
        mock_user.role_id= UUID("11111111-1111-1111-1111-111111111111")
        mock_user.partner_id= UUID("11111111-1111-1111-1111-111111111111")
        mock_user.country = None
        mock_user.parent = None

        mock_auth_repository = MagicMock()
        mock_role = MagicMock()
        mock_role.slug = "USER"
        mock_auth_repository.get_role_by_id = AsyncMock(return_value=mock_role)

        mock_current_user_result = MagicMock()
        mock_current_user_result.scalars.return_value.one_or_none.return_value = (
            mock_user
        )

        mock_count_result = MagicMock()
        mock_count_result.scalar.return_value = 1

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [mock_user]

        self.session.execute = AsyncMock(
            side_effect=[mock_current_user_result, mock_count_result, mock_result]
        )

        with patch(
            "src.components.user.repositories.UserRoleFilterBuilder"
        ) as MockBuilder:
            users, total_count = await self.user_repository.get_all(
                current_user_id, limit, offset, auth_repository=mock_auth_repository
            )

        # filter_criteria defaults to None, so the builder must never be touched
        MockBuilder.assert_not_called()
        MockBuilder.requires_role_join.assert_not_called()
        assert users == [mock_user]
        assert total_count == 1

    async def test_update_user_success(self):
        """Test successful update of a user."""
        # Arrange
        user_id= UUID("11111111-1111-1111-1111-111111111111")
        current_user_id= UUID("33333333-3333-3333-3333-333333333333")
        update_fields = {"name": "Updated Name", "email": "updated@example.com"}
        mock_user = MagicMock(
            id=user_id, name="Old Name", email="old@example.com", is_active=True, is_deleted=False,
        )
        self.session.execute = AsyncMock(
            return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=mock_user))
        )
        self.session.add = MagicMock()
        self.session.commit = AsyncMock()
        self.session.refresh = AsyncMock()

        # Act
        result = await self.user_repository.update_user(
            user_id, current_user_id, **update_fields
        )

        # Assert
        self.session.execute.assert_called_once()
        self.session.add.assert_called_once_with(mock_user)
        self.session.commit.assert_called_once()
        self.session.refresh.assert_called_once_with(mock_user)
        assert result == mock_user
        assert mock_user.name == "Updated Name"
        assert mock_user.email == "updated@example.com"

    async def test_update_user_sqlalchemy_error(self):
        """Test handling of SQLAlchemyError during user update."""
        # Arrange
        user_id= UUID("11111111-1111-1111-1111-111111111111")
        current_user_id= UUID("33333333-3333-3333-3333-333333333333")
        update_fields = {"name": "Updated Name"}
        self.session.execute = AsyncMock(side_effect=SQLAlchemyError("Database error"))

        # Act & Assert
        with pytest.raises(SQLAlchemyError, match="Database error"):
            await self.user_repository.update_user(
                user_id, current_user_id, **update_fields
            )

        self.session.execute.assert_called_once()
        self.mock_logger.error.assert_called_with("Database error: Database error")

    async def test_get_admin_credentials_by_hierarchy_success(self):
        """Test successful retrieval of admin credentials by hierarchy."""
        user_hierarchy = 1
        partner_id= UUID("12312312-3123-1231-2312-312312312312")

        # Mock admin credentials
        mock_admin_credentials = {
            "email": "admin@example.com",
            "phone_number": "1234567890",
        }

        # Mock database execution and response
        mock_result = MagicMock()
        mock_result.mappings.return_value.all.return_value = [mock_admin_credentials]
        self.session.execute = AsyncMock(return_value=mock_result)

        # Call the repository method
        result = await self.user_repository.get_admin_credentials_by_hierarchy(
            user_hierarchy, partner_id
        )

        # Assertions
        assert result == [mock_admin_credentials]
        assert result[0]["email"] == "admin@example.com"
        assert result[0]["phone_number"] == "1234567890"

    async def test_get_admin_credentials_by_hierarchy_not_found(self):
        """Test case where no admin credentials are found."""
        user_hierarchy = 1
        partner_id= UUID("12312312-3123-1231-2312-312312312312")

        # Mock database execution and response
        mock_result = MagicMock()
        mock_result.mappings.return_value.all.return_value = None
        self.session.execute = AsyncMock(return_value=mock_result)

        # Call the repository method
        result = await self.user_repository.get_admin_credentials_by_hierarchy(
            user_hierarchy, partner_id
        )

        # Assertions
        assert result is None

    async def test_get_admin_credentials_by_hierarchy_exception(self):
        """Test handling of unexpected exceptions."""
        user_hierarchy = 1
        partner_id= UUID("12312312-3123-1231-2312-312312312312")

        # Mock the execute method to raise an exception
        self.session.execute = AsyncMock(side_effect=Exception("Unexpected Error"))

        # Expect the exception to be raised
        with pytest.raises(Exception) as exc_info:
            await self.user_repository.get_admin_credentials_by_hierarchy(
                user_hierarchy, partner_id
            )

        # Assertions
        assert str(exc_info.value) == "Unexpected Error"

    async def test_check_admin_exists_exception(self):
        """Test handling of unexpected exceptions."""
        role_id= UUID("11111111-1111-1111-1111-111111111111")
        partner_id= UUID("12312312-3123-1231-2312-312312312312")

        # Simulate an exception during execution
        self.session.execute = AsyncMock(side_effect=Exception("Unexpected DB error"))

        with pytest.raises(Exception) as exc_info:
            await self.user_repository.is_admin_exists(role_id, partner_id)

        assert str(exc_info.value) == "Unexpected DB error"

    async def test_check_admin_not_found(self):
        """Test case where no admin credentials are found."""
        role_id= UUID("11111111-1111-1111-1111-111111111111")
        partner_id= UUID("12312312-3123-1231-2312-312312312312")

        # Mock database execution and response
        mock_result = MagicMock()
        mock_result.mappings.return_value.first.return_value = None
        self.session.execute = AsyncMock(return_value=mock_result)

        # Call the repository method
        result = await self.user_repository.is_admin_exists(role_id, partner_id)

        # Assertions
        assert result is False

    async def test_check_admin_success(self):
        """Test successful check if admin exists for given role and partner."""
        role_id= UUID("11111111-1111-1111-1111-111111111111")
        partner_id= UUID("12312312-3123-1231-2312-312312312312")

        # Mock user to be returned by scalars().all()
        mock_user = MagicMock()

        # Mock scalars().all() to return non-empty list
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = [mock_user]

        # Mock the result of session.execute()
        mock_result = MagicMock()
        mock_result.scalars.return_value = mock_scalars

        self.session.execute = AsyncMock(return_value=mock_result)

        result = await self.user_repository.is_admin_exists(
            partner_id=partner_id, role_id=role_id
        )

        assert result is True
        self.session.execute.assert_called_once()
        self.mock_logger.info.assert_called()

    async def test_get_user_by_user_id_success(self):
        user_id= UUID("11111111-1111-1111-1111-111111111111")
        partner_id= UUID("10101010-1010-1010-1010-101010101010")
        user_mock = MagicMock()
        result_mock = MagicMock()
        result_mock.scalars.return_value.first.return_value = user_mock
        self.session.execute = AsyncMock(return_value=result_mock)

        result = await self.user_repository.get_user_by_user_id(user_id, partner_id)

        assert result == user_mock
        self.mock_logger.info.assert_any_call(f"Fetching user by user_id: {user_id}")
        self.mock_logger.info.assert_any_call(f"user_fetched_successfully: {user_mock}")

    async def test_get_user_by_user_id_not_found(self):
        user_id= UUID("22222222-2222-2222-2222-222222222222")
        partner_id= UUID("20202020-2020-2020-2020-202020202020")
        result_mock = MagicMock()
        result_mock.scalars.return_value.first.return_value = None
        self.session.execute = AsyncMock(return_value=result_mock)

        with pytest.raises(UserNotFoundError):
            await self.user_repository.get_user_by_user_id(user_id, partner_id)
        self.mock_logger.error.assert_any_call(f"User with id: {user_id} is not found.")

    async def test_get_user_by_user_id_unexpected_exception(self):
        user_id= UUID("33333333-3333-3333-3333-333333333333")
        partner_id= UUID("30303030-3030-3030-3030-303030303030")
        self.session.execute = AsyncMock(side_effect=Exception("DB error"))

        with pytest.raises(Exception, match="DB error"):
            await self.user_repository.get_user_by_user_id(user_id, partner_id)
        self.mock_logger.error.assert_any_call(
            "An error occured while fetching the user: DB error"
        )

    async def test_get_admin_details_by_partner_id_success(self):
        partner_id= UUID("12312312-3123-1231-2312-312312312312")
        mock_admin_role = MagicMock()
        mock_admin_role.id = 1
        mock_admin_role.slug = "ADMIN"
        mock_admin_role.is_active = True

        mock_admin_user = MagicMock()
        mock_admin_user.partner_id = partner_id
        mock_admin_user.role_id = mock_admin_role.id
        mock_admin_user.is_active = True

        # Mock admin role query result
        mock_admin_role_result = MagicMock()
        mock_admin_role_result.scalars.return_value.first.return_value = mock_admin_role

        # Mock admin user query result
        mock_admin_user_result = MagicMock()
        mock_admin_user_result.scalars.return_value.first.return_value = mock_admin_user

        self.session.execute = AsyncMock(
            side_effect=[mock_admin_role_result, mock_admin_user_result]
        )

        await self.user_repository.get_admin_details_by_partner_id(partner_id)

    async def test_get_admin_details_by_partner_id_role_not_found(self):
        partner_id= UUID("12312312-3123-1231-2312-312312312312")
        # Mock admin role query returns None
        mock_admin_role_result = MagicMock()
        mock_admin_role_result.scalars.return_value.first.return_value = None
        self.session.execute = AsyncMock(return_value=mock_admin_role_result)

        with pytest.raises(UserException, match="Role not found"):
            await self.user_repository.get_admin_details_by_partner_id(partner_id)
        self.mock_logger.error.assert_any_call("Admin role not found in the database.")

    async def test_get_admin_details_by_partner_id_unexpected_exception(self):
        partner_id= UUID("12312312-3123-1231-2312-312312312312")
        self.session.execute = AsyncMock(side_effect=Exception("DB error"))
        with pytest.raises(Exception, match="DB error"):
            await self.user_repository.get_admin_details_by_partner_id(partner_id)
        self.mock_logger.error.assert_any_call(
            f"Unexpected error while fetching admin details for partner_id {partner_id}: DB error"
        )

    async def test_get_admin_details_by_partner_id_prefers_partner_owned_admin_role(self):
        """If the partner has its own materialized "admin"-slugged role, it must
        be preferred over the shared default — the two can have different ids,
        and the partner's users are repointed to the partner-owned copy on
        materialization, so matching the wrong one silently finds no admin."""
        partner_id= UUID("12312312-3123-1231-2312-312312312312")
        partner_admin_role = MagicMock()
        partner_admin_role.id = 105

        mock_admin_user = MagicMock()
        mock_admin_user.partner_id = partner_id
        mock_admin_user.role_id = partner_admin_role.id

        partner_role_result = MagicMock()
        partner_role_result.scalars.return_value.first.return_value = partner_admin_role

        mock_admin_user_result = MagicMock()
        mock_admin_user_result.scalars.return_value.first.return_value = mock_admin_user

        self.session.execute = AsyncMock(
            side_effect=[partner_role_result, mock_admin_user_result]
        )

        result = await self.user_repository.get_admin_details_by_partner_id(partner_id)

        assert result == mock_admin_user
        # Only two queries: the partner-scoped role lookup and the user
        # lookup — the global-default fallback must not have been attempted.
        assert self.session.execute.await_count == 2
        user_query = self.session.execute.call_args.args[0]
        assert "console_users.role_id = " in str(user_query)

    async def test_get_admin_details_by_partner_id_falls_back_to_default_admin_role(self):
        """If the partner has never materialized its own "admin" role, fall
        back to the shared default one (today's behavior for un-customized
        partners)."""
        partner_id= UUID("12312312-3123-1231-2312-312312312312")
        default_admin_role = MagicMock()
        default_admin_role.id = 22

        mock_admin_user = MagicMock()
        mock_admin_user.partner_id = partner_id
        mock_admin_user.role_id = default_admin_role.id

        no_partner_role_result = MagicMock()
        no_partner_role_result.scalars.return_value.first.return_value = None

        default_role_result = MagicMock()
        default_role_result.scalars.return_value.first.return_value = default_admin_role

        mock_admin_user_result = MagicMock()
        mock_admin_user_result.scalars.return_value.first.return_value = mock_admin_user

        self.session.execute = AsyncMock(
            side_effect=[no_partner_role_result, default_role_result, mock_admin_user_result]
        )

        result = await self.user_repository.get_admin_details_by_partner_id(partner_id)

        assert result == mock_admin_user
        assert self.session.execute.await_count == 3

    async def test_get_users_by_partner_id_success(self):
        partner_id= UUID("10110110-1101-1011-0110-110110110110")

        # Define a named tuple to simulate result row
        MockRow = namedtuple(
            "MockRow",
            [
                "id",
                "name",
                "email",
                "phone_number",
                "role_name",
                "role_hierarchy",
                "role_data_scope",
            ],
        )
        mock_rows = [
            MockRow(
                1,
                "Alice",
                "alice@example.com",
                "+911234567890",
                "Admin",
                1,
                "ALL",
            ),
            MockRow(
                2,
                "Bob",
                "bob@example.com",
                "+919876543210",
                "Manager",
                2,
                "SUBTREE",
            ),
        ]

        mock_result = MagicMock()
        mock_result.all.return_value = mock_rows
        self.session.execute = AsyncMock(return_value=mock_result)

        users = await self.user_repository.get_users_by_partner_id(partner_id)

        assert isinstance(users, list)
        assert len(users) == 2
        assert users[0]["name"] == "Alice"
        assert users[0]["role"] == "Admin"
        assert users[0]["role_data_scope"] == "ALL"
        assert users[1]["email"] == "bob@example.com"
        assert users[1]["role_hierarchy"] == 2
        assert users[1]["role_data_scope"] == "SUBTREE"

        self.mock_logger.info.assert_called_with(
            f"Attempting to get list of user by partner_id: {partner_id}"
        )

    async def test_get_users_by_partner_id_unexpected_exception(self):
        partner_id= UUID("20220220-2202-2022-0220-220220220220")
        self.session.execute = AsyncMock(side_effect=Exception("DB failure"))

        with pytest.raises(Exception) as exc_info:
            await self.user_repository.get_users_by_partner_id(partner_id)

        assert str(exc_info.value) == "DB failure"

        self.mock_logger.error.assert_called_with(
            "Unexpected error during get users by partner_id: {}, error: {}".format(
                partner_id, "DB failure"
            )
        )

    async def test_execure_user_filter_query_success(self):
        query = MagicMock()
        mock_result = MagicMock()
        mock_result.fetchall.return_value = [("row1",), ("row2",)]
        self.session.execute = AsyncMock(return_value=mock_result)

        result = await self.user_repository.execure_user_filter_query(query)
        assert result == [("row1",), ("row2",)]
        self.session.execute.assert_awaited_once_with(query)

    async def test_execure_user_filter_query_sqlalchemy_error(self):
        query = MagicMock()
        self.session.execute = AsyncMock(side_effect=SQLAlchemyError("DB error"))

        with pytest.raises(SQLAlchemyError):
            await self.user_repository.execure_user_filter_query(query)
        self.mock_logger.error.assert_called_with(
            "Database error while executing query: DB error"
        )

    async def test_execute_user_filter_scalar_query_success(self):
        query = MagicMock()
        mock_result = MagicMock()
        mock_result.scalar.return_value = 42
        self.session.execute = AsyncMock(return_value=mock_result)

        result = await self.user_repository.execute_user_filter_scalar_query(query)
        assert result == 42
        self.session.execute.assert_awaited_once_with(query)

    async def test_execute_user_filter_scalar_query_sqlalchemy_error(self):
        query = MagicMock()
        self.session.execute = AsyncMock(side_effect=SQLAlchemyError("Scalar DB error"))

        with pytest.raises(SQLAlchemyError):
            await self.user_repository.execute_user_filter_scalar_query(query)
        self.mock_logger.error.assert_called_with(
            "Database error while executing scalar query: Scalar DB error"
        )

    async def test_get_service_board_users_details_inactive_user(self):
        user_ids = [UUID("33333333-3333-3333-3333-333333333333")]

        # Mock inactive user data
        mock_user_inactive = {
            "user_id": 3,
            "email": "inactive_user@example.com",
            "is_active": False,
            "is_suspended": False,
            "name": "User Inactive",
        }
        mock_users = [mock_user_inactive]

        # Mock database execution and response
        mock_result = MagicMock()
        mock_result.mappings.return_value.all.return_value = mock_users
        self.session.execute = AsyncMock(return_value=mock_result)

        # Call the repository method
        result = await self.user_repository.get_service_board_users_details(user_ids)

        # Validate result
        assert isinstance(result, list)
        assert len(result) == 1
        assert result[0]["user_id"] == 3
        assert result[0]["email"] == "inactive_user@example.com"

        name = (
            f"{result[0]['name']} (Inactive)"
            if not result[0]["is_active"]
            else result[0]["name"]
        )
        assert "Inactive" in name

    async def test_get_system_admin_user_success(self):
        self.mock_logger.reset_mock()
        mock_user = MagicMock()
        mock_user.id = 10
        mock_user.role_id= UUID("11111111-1111-1111-1111-111111111111")

        mock_scalars = MagicMock()
        mock_scalars.first = MagicMock(return_value=mock_user)
        mock_result = MagicMock()
        mock_result.scalars = MagicMock(return_value=mock_scalars)

        self.session.execute = AsyncMock(return_value=mock_result)

        result = await self.user_repository.get_system_admin_user()

        assert result == mock_user
        self.mock_logger.info.assert_called_once_with("Fetching system admin user")

    async def test_get_system_admin_user_not_found(self):
        self.mock_logger.reset_mock()

        mock_scalars = MagicMock()
        mock_scalars.first = MagicMock(return_value=None)
        mock_result = MagicMock()
        mock_result.scalars = MagicMock(return_value=mock_scalars)

        self.session.execute = AsyncMock(return_value=mock_result)

        result = await self.user_repository.get_system_admin_user()

        assert result is None
        self.mock_logger.info.assert_called_once_with("Fetching system admin user")

    async def test_get_system_admin_user_exception(self):
        self.mock_logger.reset_mock()
        self.session.execute = AsyncMock(side_effect=Exception("DB error"))

        with pytest.raises(Exception) as exc:
            await self.user_repository.get_system_admin_user()

        assert str(exc.value) == "DB error"

        # Ensure logger captured the error
        self.mock_logger.error.assert_called_once_with(
            "Unexpected error while getting system admnin user: DB error"
        )

    async def test_toggle_walkthrough_key_activation_success(self):
        user_id= UUID("11111111-1111-1111-1111-111111111111")
        mock_user = MagicMock()
        mock_user.id = user_id
        mock_user.is_active = True
        mock_user.is_walkthrough_completed = False

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_user
        self.session.execute = AsyncMock(return_value=mock_result)

        self.session.add = MagicMock()
        self.session.commit = AsyncMock()
        self.session.refresh = AsyncMock()

        result = await self.user_repository.toggle_walkthrough_key_activation(
            user_id, is_walkthrough_completed=True
        )

        assert result == mock_user
        assert mock_user.is_walkthrough_completed is True
        self.session.add.assert_called_once_with(mock_user)
        self.session.commit.assert_called_once()
        self.session.refresh.assert_called_once_with(mock_user)
        self.mock_logger.info.assert_called()

    async def test_toggle_walkthrough_key_activation_user_not_found_raises(self):
        user_id= UUID("22222222-2222-2222-2222-222222222222")

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        self.session.execute = AsyncMock(return_value=mock_result)

        from src.components.common.errors import NotFoundError

        with pytest.raises(NotFoundError) as exc:
            await self.user_repository.toggle_walkthrough_key_activation(
                user_id, is_walkthrough_completed=True
            )

        assert str(exc.value) == f"User not found, id: {user_id}"
        self.mock_logger.error.assert_any_call(f"User with ID {user_id} not found")

    async def test_toggle_walkthrough_key_activation_inactive_user_raises(self):
        user_id= UUID("33333333-3333-3333-3333-333333333333")
        mock_user = MagicMock()
        mock_user.is_active = False

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_user
        self.session.execute = AsyncMock(return_value=mock_result)

        from src.components.common.errors import NotFoundError

        with pytest.raises(NotFoundError):
            await self.user_repository.toggle_walkthrough_key_activation(
                user_id, is_walkthrough_completed=False
            )

        self.mock_logger.error.assert_any_call(f"User with ID {user_id} not found")

    async def test_toggle_walkthrough_key_activation_unexpected_exception(self):
        user_id= UUID("44444444-4444-4444-4444-444444444444")
        self.session.execute = AsyncMock(side_effect=Exception("DB error"))

        with pytest.raises(Exception, match="DB error"):
            await self.user_repository.toggle_walkthrough_key_activation(
                user_id, is_walkthrough_completed=True
            )

        self.mock_logger.error.assert_called()

    async def test_get_by_id_masks_password(self):
        """Test that password/hashed_password is masked in logs when fetching user by ID."""
        # Arrange
        user_id= UUID("11111111-1111-1111-1111-111111111111")
        mock_user = MagicMock()
        mock_user.id = user_id
        mock_user.name = "Test User"
        mock_user.email = "test@example.com"
        mock_user.hashed_password = "secret_hash_value_123"
        mock_user.is_active = True

        # Mock session.get to return the user
        self.session.get = AsyncMock(return_value=mock_user)

        # Clear any existing log calls
        self.mock_logger.info.reset_mock()

        # Act
        user = await self.user_repository.get_by_id(user_id)

        # Assert - user should be returned correctly
        assert user == mock_user

        # Verify that info was called and doesn't contain the password
        log_calls = self.mock_logger.info.call_args_list
        assert len(log_calls) >= 1, "No log calls found"

        # Convert all log calls to string and check
        all_logs = " ".join([str(call) for call in log_calls])
        assert "secret_hash_value_123" not in all_logs
        # The log should contain the user ID or name to confirm logging happened
        assert str(user_id) in all_logs or "Test User" in all_logs

    async def test_add_user_masks_password_in_logs(self):
        """Test that password is masked in logs when adding a new user."""
        # Arrange
        from src.components.auth.schema import UserData

        # Use a valid password that meets validation requirements
        user_data = UserData(
            name="New User",
            email="new@example.com",
            password="Test@123456",
            phone_number="+1234567890",
            role_id= UUID("11111111-1111-1111-1111-111111111111"),
            partner_id= UUID("11111111-1111-1111-1111-111111111111"),
            parent_id=None,
            country_id= UUID("11111111-1111-1111-1111-111111111111"),
            is_active=True
        )

        # Clear logs
        self.mock_logger.info.reset_mock()

        # Mock session operations
        self.session.add = MagicMock()
        self.session.flush = AsyncMock()
        self.session.commit = AsyncMock()
        self.session.refresh = AsyncMock()

        # Mock execute for user_config insert
        mock_execute_result = MagicMock()
        self.session.execute = AsyncMock(return_value=mock_execute_result)

        # Act
        user = await self.user_repository.add_user(user_data)

        # Assert
        # Check that logs don't contain plain password
        log_calls = self.mock_logger.info.call_args_list
        log_messages = [str(call) for call in log_calls]
        all_logs = " ".join(log_messages)

        assert "Test@123456" not in all_logs
        # Should have called info with masked dict
        assert any("******" in msg for msg in log_messages)

    async def test_update_user_masks_password_in_logs(self):
        """Test that password is masked in logs when updating user."""
        # Arrange
        user_id= UUID("11111111-1111-1111-1111-111111111111")
        current_user_id= UUID("33333333-3333-3333-3333-333333333333")
        update_fields = {"name": "Updated Name", "password": "new_secret_password"}

        mock_user = MagicMock()
        mock_user.id = user_id
        mock_user.name = "Old Name"
        mock_user.email = "old@example.com"
        mock_user.is_active = True
        mock_user.is_deleted = False
        mock_user.hashed_password = "old_secret_hash"

        # Mock the query execution - use MagicMock for scalar_one_or_none
        mock_result = MagicMock()
        mock_result.scalar_one_or_none = MagicMock(return_value=mock_user)
        self.session.execute = AsyncMock(return_value=mock_result)
        self.session.add = MagicMock()
        self.session.commit = AsyncMock()
        self.session.refresh = AsyncMock()

        # Clear logs
        self.mock_logger.info.reset_mock()

        # Act
        result = await self.user_repository.update_user(
            user_id, current_user_id, **update_fields
        )

        # Assert
        assert result == mock_user

        # Verify password is masked in logs
        log_calls = self.mock_logger.info.call_args_list
        log_messages = [str(call) for call in log_calls]
        all_logs = " ".join(log_messages)

        # Check that plain passwords are not in logs
        assert "new_secret_password" not in all_logs
        assert "old_secret_hash" not in all_logs
        # Check that ****** appears in logs or at least update was logged
        assert "******" in all_logs or "Updating user" in all_logs

    async def test_delete_by_id_masks_password_in_logs(self):
        """Test that password is masked in logs when deleting user."""
        # Arrange
        user_id= UUID("11111111-1111-1111-1111-111111111111")
        mock_user = MagicMock()
        mock_user.id = user_id
        mock_user.name = "User To Delete"
        mock_user.email = "delete@example.com"
        mock_user.hashed_password = "secret_hash_to_delete"
        mock_user.phone_number = "+1234567890"
        mock_user.is_active = True
        mock_user.is_deleted = False

        # Mock session.get to return the user
        self.session.get = AsyncMock(return_value=mock_user)
        self.session.add = MagicMock()
        self.session.commit = AsyncMock()
        self.session.refresh = AsyncMock()

        # Clear logs
        self.mock_logger.info.reset_mock()

        # Act
        result = await self.user_repository.delete_by_id(user_id)

        # Assert
        assert result == mock_user

        # Verify password is masked in logs
        log_calls = self.mock_logger.info.call_args_list
        log_messages = [str(call) for call in log_calls]
        all_logs = " ".join(log_messages)

        # Check that actual hash is not in logs
        assert "secret_hash_to_delete" not in all_logs
        # Check that ****** appears in logs or at least deletion was logged
        assert "******" in all_logs or "User deleted successfully" in all_logs


    async def test_update_popup_last_closed_success_new_key(self):
        """User has no existing popup_last_closed — creates it fresh."""
        self.mock_logger.reset_mock()
        user_id= UUID("11111111-1111-1111-1111-111111111111")
        service_name = "console"

        mock_user = MagicMock()
        mock_user.additional_info = {}

        mock_result = MagicMock()
        mock_result.scalars.return_value.first.return_value = mock_user
        self.session.execute = AsyncMock(return_value=mock_result)
        self.session.commit = AsyncMock()

        await self.user_repository.update_popup_last_closed(
            user_id=user_id, service_name=service_name
        )

        assert "popup_last_closed" in mock_user.additional_info
        assert service_name in mock_user.additional_info["popup_last_closed"]
        assert isinstance(
            mock_user.additional_info["popup_last_closed"][service_name], int
        )
        self.session.commit.assert_called_once()
        self.mock_logger.info.assert_called_once()

    async def test_update_popup_last_closed_success_existing_keys_preserved(self):
        """Other keys in additional_info and popup_last_closed are not overwritten."""
        user_id= UUID("11111111-1111-1111-1111-111111111111")
        service_name = "talko"

        mock_user = MagicMock()
        mock_user.additional_info = {
            "some_other_key": "some_value",
            "popup_last_closed": {"console": 1000000},
        }

        mock_result = MagicMock()
        mock_result.scalars.return_value.first.return_value = mock_user
        self.session.execute = AsyncMock(return_value=mock_result)
        self.session.commit = AsyncMock()

        await self.user_repository.update_popup_last_closed(
            user_id=user_id, service_name=service_name
        )

        assert mock_user.additional_info["some_other_key"] == "some_value"
        assert mock_user.additional_info["popup_last_closed"]["console"] == 1000000
        assert service_name in mock_user.additional_info["popup_last_closed"]
        self.session.commit.assert_called_once()

    async def test_update_popup_last_closed_success_additional_info_none(self):
        """User.additional_info is None — treated as empty dict."""
        user_id= UUID("11111111-1111-1111-1111-111111111111")
        service_name = "talko"

        mock_user = MagicMock()
        mock_user.additional_info = None

        mock_result = MagicMock()
        mock_result.scalars.return_value.first.return_value = mock_user
        self.session.execute = AsyncMock(return_value=mock_result)
        self.session.commit = AsyncMock()

        await self.user_repository.update_popup_last_closed(
            user_id=user_id, service_name=service_name
        )

        assert mock_user.additional_info["popup_last_closed"][service_name] is not None
        self.session.commit.assert_called_once()

    async def test_update_popup_last_closed_overwrites_existing_service_timestamp(self):
        """Calling again for same service updates the timestamp."""
        user_id= UUID("11111111-1111-1111-1111-111111111111")
        service_name = "console"
        old_ts = 1000000

        mock_user = MagicMock()
        mock_user.additional_info = {"popup_last_closed": {service_name: old_ts}}

        mock_result = MagicMock()
        mock_result.scalars.return_value.first.return_value = mock_user
        self.session.execute = AsyncMock(return_value=mock_result)
        self.session.commit = AsyncMock()

        await self.user_repository.update_popup_last_closed(
            user_id=user_id, service_name=service_name
        )

        new_ts = mock_user.additional_info["popup_last_closed"][service_name]
        assert new_ts != old_ts
        assert new_ts > old_ts
        self.session.commit.assert_called_once()

    async def test_update_popup_last_closed_db_exception_rolls_back(self):
        """DB error triggers rollback and re-raises."""
        self.mock_logger.reset_mock()
        user_id= UUID("11111111-1111-1111-1111-111111111111")
        service_name = "console"

        self.session.execute = AsyncMock(side_effect=Exception("DB write failed"))
        self.session.rollback = AsyncMock()

        with pytest.raises(Exception) as exc_info:
            await self.user_repository.update_popup_last_closed(
                user_id=user_id, service_name=service_name
            )

        assert str(exc_info.value) == "DB write failed"
        self.session.rollback.assert_called_once()
        self.mock_logger.error.assert_called_once()

    """
Additional coverage for src/components/user/repositories.py.

Your existing test_repositories.py (TestUserRepository) already covers a
good chunk of UserRepository, but the following were still at 0% or
missing key branches:

  * get_by_id                         -> 0% (no tests)
  * get_user_by_field                 -> 0% (no tests)
  * get_user_with_role                -> 0% (no tests)
  * partner_user_limit                -> 0% (no tests)
  * get_users_by_user_ids             -> 0% (no tests)
  * has_child_users                   -> 0% (no tests)
  * get_users_by_emails               -> 0% (no tests)
  * get_users_by_phones               -> 0% (no tests)
  * get_users_id_hierarchy_by_emails  -> 0% (no tests)
  * get_all                           -> MAINTAINER branch + filter_criteria
                                          branch untested
  * add_user                          -> generic SQLAlchemyError branch,
                                          explicit `services` param branch
                                          untested
  * delete_by_id                      -> not-found / exception branches
                                          untested
  * update_user                       -> not-found branch, email/phone
                                          re-verification reset, generic
                                          Exception branch untested

This file reuses the same `mock_session_factory` / `mock_logger` fixtures
your existing suite relies on (defined in your conftest.py) and follows
the same class-based, `setup_class` autouse-fixture pattern as
test_repositories.py so it drops in next to it unchanged.

Run together with your existing suite:
    pytest test_repositories.py test_repositories_missing_coverage.py \
        --cov=src.components.user.repositories --cov-report=term-missing -v
"""
@pytest.mark.asyncio
class TestUserRepositoryMissingCoverage:

    @pytest.fixture(autouse=True)
    def setup_class(self, mock_session_factory, mock_logger):
        self.user_repository = UserRepository(
            session_factory=mock_session_factory, console_service_logger=mock_logger
        )
        self.session = mock_session_factory.return_value.__aenter__.return_value
        self.mock_logger = mock_logger

    # =====================================================================
    # get_by_id
    # =====================================================================

    async def test_get_by_id_success(self):
        user_id= UUID("11111111-1111-1111-1111-111111111111")
        mock_user = MagicMock(id=user_id, is_active=True)
        self.session.get = AsyncMock(return_value=mock_user)

        result = await self.user_repository.get_by_id(user_id)

        assert result == mock_user
        self.session.get.assert_awaited_once()
        assert self.session.get.call_args.args[1] == user_id

    async def test_get_by_id_not_found_raises(self):
        self.session.get = AsyncMock(return_value=None)

        with pytest.raises(UserNotFoundError):
            await self.user_repository.get_by_id(99)

    async def test_get_by_id_inactive_raises(self):
        mock_user = MagicMock(id= UUID("11111111-1111-1111-1111-111111111111"), is_active=False)
        self.session.get = AsyncMock(return_value=mock_user)

        with pytest.raises(UserNotFoundError):
            await self.user_repository.get_by_id(1)

    async def test_get_by_id_sqlalchemy_error(self):
        self.session.get = AsyncMock(side_effect=SQLAlchemyError("db down"))

        with pytest.raises(SQLAlchemyError):
            await self.user_repository.get_by_id(1)
        self.mock_logger.error.assert_called()

    # =====================================================================
    # get_user_by_field
    # =====================================================================

    async def test_get_user_by_field_invalid_field_raises(self):
        with pytest.raises(ValueError, match="no attribute 'not_a_real_field'"):
            await self.user_repository.get_user_by_field("not_a_real_field", "x")

    async def test_get_user_by_field_found(self):
        mock_user = MagicMock(id= UUID("11111111-1111-1111-1111-111111111111"), email="a@x.com")
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_user
        self.session.execute = AsyncMock(return_value=mock_result)

        result = await self.user_repository.get_user_by_field("email", "a@x.com")

        assert result == mock_user

    async def test_get_user_by_field_not_found_returns_none(self):
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        self.session.execute = AsyncMock(return_value=mock_result)

        result = await self.user_repository.get_user_by_field("email", "ghost@x.com")

        assert result is None

    async def test_get_user_by_field_exception(self):
        self.session.execute = AsyncMock(side_effect=SQLAlchemyError("boom"))

        with pytest.raises(SQLAlchemyError):
            await self.user_repository.get_user_by_field("email", "a@x.com")
        self.mock_logger.error.assert_called()

    # =====================================================================
    # get_user_with_role
    # =====================================================================

    async def test_get_user_with_role_success(self):
        mock_user = MagicMock()
        mock_role = MagicMock(name="Admin")
        mock_result = MagicMock()
        mock_result.one_or_none.return_value = (mock_user, mock_role)
        self.session.execute = AsyncMock(return_value=mock_result)

        result = await self.user_repository.get_user_with_role(1)

        assert result == mock_role

    async def test_get_user_with_role_not_found_raises(self):
        mock_result = MagicMock()
        mock_result.one_or_none.return_value = None
        self.session.execute = AsyncMock(return_value=mock_result)

        with pytest.raises(UserNotFoundError):
            await self.user_repository.get_user_with_role(999)

    async def test_get_user_with_role_generic_exception(self):
        self.session.execute = AsyncMock(side_effect=Exception("db error"))

        with pytest.raises(Exception, match="db error"):
            await self.user_repository.get_user_with_role(1)
        self.mock_logger.error.assert_called()

    # =====================================================================
    # partner_user_limit
    # =====================================================================

    async def test_partner_user_limit_success(self):
        partner_id= UUID("11111111-1111-1111-1111-111111111111")
        mock_partner = MagicMock(active_license=50)
        self.session.get = AsyncMock(return_value=mock_partner)
        self.session.scalar = AsyncMock(return_value=12)

        result = await self.user_repository.partner_user_limit(partner_id)

        assert result == 12

    async def test_partner_user_limit_partner_not_found_raises(self):
        self.session.get = AsyncMock(return_value=None)

        with pytest.raises(UserException, match="not found"):
            await self.user_repository.partner_user_limit(999)

    async def test_partner_user_limit_sqlalchemy_error(self):
        self.session.get = AsyncMock(side_effect=SQLAlchemyError("db error"))

        with pytest.raises(SQLAlchemyError):
            await self.user_repository.partner_user_limit(1)
        self.mock_logger.error.assert_called()

    async def test_partner_user_limit_generic_exception(self):
        self.session.get = AsyncMock(side_effect=Exception("weird error"))

        with pytest.raises(Exception, match="weird error"):
            await self.user_repository.partner_user_limit(1)
        self.mock_logger.error.assert_called()

    # =====================================================================
    # get_users_by_user_ids
    # =====================================================================

    async def test_get_users_by_user_ids_success(self):
        mock_users = [MagicMock(id= UUID("11111111-1111-1111-1111-111111111111")), MagicMock(id= UUID("22222222-2222-2222-2222-222222222222"))]
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = mock_users
        self.session.execute = AsyncMock(return_value=mock_result)

        result = await self.user_repository.get_users_by_user_ids(1, [UUID("11111111-1111-1111-1111-111111111111"), UUID("22222222-2222-2222-2222-222222222222")])

        assert result == mock_users

    async def test_get_users_by_user_ids_exception(self):
        self.session.execute = AsyncMock(side_effect=Exception("db failure"))

        with pytest.raises(Exception, match="db failure"):
            await self.user_repository.get_users_by_user_ids(1, [UUID("11111111-1111-1111-1111-111111111111"), UUID("22222222-2222-2222-2222-222222222222")])
        self.mock_logger.error.assert_called()

    # =====================================================================
    # has_child_users
    # =====================================================================

    async def test_has_child_users_true(self):
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = 5
        self.session.execute = AsyncMock(return_value=mock_result)

        result = await self.user_repository.has_child_users(1)

        assert result is True

    async def test_has_child_users_false(self):
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        self.session.execute = AsyncMock(return_value=mock_result)

        result = await self.user_repository.has_child_users(1)

        assert result is False

    async def test_has_child_users_exception(self):
        self.session.execute = AsyncMock(side_effect=Exception("db error"))

        with pytest.raises(Exception, match="db error"):
            await self.user_repository.has_child_users(1)
        self.mock_logger.error.assert_called()

    # =====================================================================
    # get_users_by_emails
    # =====================================================================

    async def test_get_users_by_emails_empty_input_short_circuits(self):
        result = await self.user_repository.get_users_by_emails([])
        assert result == []

    async def test_get_users_by_emails_returns_existing(self):
        mock_result = MagicMock()
        mock_result.all.return_value = [("a@x.com",), ("b@x.com",)]
        self.session.execute = AsyncMock(return_value=mock_result)

        result = await self.user_repository.get_users_by_emails(["a@x.com", "b@x.com", "c@x.com"])

        assert result == ["a@x.com", "b@x.com"]

    async def test_get_users_by_emails_exception(self):
        self.session.execute = AsyncMock(side_effect=Exception("db down"))

        with pytest.raises(Exception, match="db down"):
            await self.user_repository.get_users_by_emails(["a@x.com"])

    # =====================================================================
    # get_users_by_phones
    # =====================================================================

    async def test_get_users_by_phones_empty_input_short_circuits(self):
        result = await self.user_repository.get_users_by_phones([])
        assert result == []

    async def test_get_users_by_phones_dedupes_primary_and_alternate(self):
        primary_result = MagicMock()
        primary_result.all.return_value = [("+911111111111",)]
        alt_result = MagicMock()
        alt_result.all.return_value = [("+911111111111",), ("+912222222222",)]

        self.session.execute = AsyncMock(side_effect=[primary_result, alt_result])

        result = await self.user_repository.get_users_by_phones(
            ["+911111111111", "+912222222222"]
        )

        assert sorted(result) == ["+911111111111", "+912222222222"]

    async def test_get_users_by_phones_exception(self):
        self.session.execute = AsyncMock(side_effect=Exception("db error"))

        with pytest.raises(Exception, match="db error"):
            await self.user_repository.get_users_by_phones(["+911111111111"])

    # =====================================================================
    # get_users_id_hierarchy_by_emails
    # =====================================================================

    async def test_get_users_id_hierarchy_by_emails_empty_input(self):
        result = await self.user_repository.get_users_id_hierarchy_by_emails([])
        assert result == {}

    async def test_get_users_id_hierarchy_by_emails_success(self):
        Row = type("Row", (), {})
        row1 = Row()
        row1.email, row1.id, row1.role_hierarchy = "a@x.com", 1, 2
        mock_result = MagicMock()
        mock_result.all.return_value = [row1]
        self.session.execute = AsyncMock(return_value=mock_result)

        result = await self.user_repository.get_users_id_hierarchy_by_emails(["a@x.com"])

        assert result == {"a@x.com": {"id": 1, "role_hierarchy": 2}}

    async def test_get_users_id_hierarchy_by_emails_exception(self):
        self.session.execute = AsyncMock(side_effect=Exception("db error"))

        with pytest.raises(Exception, match="db error"):
            await self.user_repository.get_users_id_hierarchy_by_emails(["a@x.com"])

    # =====================================================================
    # get_all — MAINTAINER branch & filter_criteria branch
    # =====================================================================

    async def test_get_all_maintainer_with_admin_found_excludes_both(self):
        current_user_id= UUID("55555555-5555-5555-5555-555555555555")
        mock_current_user = MagicMock(id=current_user_id, role_id= UUID("11111111-1111-1111-1111-111111111111"), partner_id= UUID("10101010-1010-1010-1010-101010101010"))
        current_user_result = MagicMock()
        current_user_result.scalars.return_value.one_or_none.return_value = mock_current_user

        mock_auth_repository = MagicMock()
        maintainer_role = MagicMock(slug=UserRoles.MAINTAINER)
        mock_auth_repository.get_role_by_id = AsyncMock(return_value=maintainer_role)

        admin_role = MagicMock(id= UUID("77777777-7777-7777-7777-777777777777"))
        admin_role_result = MagicMock()
        admin_role_result.scalars.return_value.first.return_value = admin_role

        admin_user = MagicMock(id= UUID("88888888-8888-8888-8888-888888888888"))
        admin_user_result = MagicMock()
        admin_user_result.scalars.return_value.first.return_value = admin_user

        count_result = MagicMock()
        count_result.scalar.return_value = 3

        final_result = MagicMock()
        final_result.scalars.return_value.all.return_value = []

        self.session.execute = AsyncMock(
            side_effect=[
                current_user_result,
                admin_role_result,
                admin_user_result,
                count_result,
                final_result,
            ]
        )

        users, total = await self.user_repository.get_all(
            current_user_id, 10, 1, auth_repository=mock_auth_repository
        )

        assert users == []
        assert total == 3

    async def test_get_all_maintainer_admin_role_missing_raises(self):
        current_user_id= UUID("55555555-5555-5555-5555-555555555555")
        mock_current_user = MagicMock(id=current_user_id, role_id= UUID("11111111-1111-1111-1111-111111111111"), partner_id= UUID("10101010-1010-1010-1010-101010101010"))
        current_user_result = MagicMock()
        current_user_result.scalars.return_value.one_or_none.return_value = mock_current_user

        mock_auth_repository = MagicMock()
        maintainer_role = MagicMock(slug=UserRoles.MAINTAINER)
        mock_auth_repository.get_role_by_id = AsyncMock(return_value=maintainer_role)

        admin_role_result = MagicMock()
        admin_role_result.scalars.return_value.first.return_value = None

        self.session.execute = AsyncMock(
            side_effect=[current_user_result, admin_role_result]
        )

        with pytest.raises(UserException, match="Admin role not found"):
            await self.user_repository.get_all(
                current_user_id, 10, 1, auth_repository=mock_auth_repository
            )

    async def test_get_all_maintainer_no_admin_user_found_uses_self_as_root(self):
        current_user_id= UUID("55555555-5555-5555-5555-555555555555")
        mock_current_user = MagicMock(id=current_user_id, role_id= UUID("11111111-1111-1111-1111-111111111111"), partner_id= UUID("10101010-1010-1010-1010-101010101010"))
        current_user_result = MagicMock()
        current_user_result.scalars.return_value.one_or_none.return_value = mock_current_user

        mock_auth_repository = MagicMock()
        maintainer_role = MagicMock(slug=UserRoles.MAINTAINER)
        mock_auth_repository.get_role_by_id = AsyncMock(return_value=maintainer_role)

        admin_role = MagicMock(id= UUID("77777777-7777-7777-7777-777777777777"))
        admin_role_result = MagicMock()
        admin_role_result.scalars.return_value.first.return_value = admin_role

        admin_user_result = MagicMock()
        admin_user_result.scalars.return_value.first.return_value = None  # no admin user

        count_result = MagicMock()
        count_result.scalar.return_value = 0

        final_result = MagicMock()
        final_result.scalars.return_value.all.return_value = []

        self.session.execute = AsyncMock(
            side_effect=[
                current_user_result,
                admin_role_result,
                admin_user_result,
                count_result,
                final_result,
            ]
        )

        users, total = await self.user_repository.get_all(
            current_user_id, 10, 1, auth_repository=mock_auth_repository
        )
        assert users == []
        assert total == 0

    async def test_get_all_with_filter_criteria_applies_filters(self):
        current_user_id= UUID("11111111-1111-1111-1111-111111111111")
        mock_current_user = MagicMock(id=current_user_id, role_id= UUID("11111111-1111-1111-1111-111111111111"), partner_id= UUID("10101010-1010-1010-1010-101010101010"))
        current_user_result = MagicMock()
        current_user_result.scalars.return_value.one_or_none.return_value = mock_current_user

        mock_auth_repository = MagicMock()
        non_maintainer_role = MagicMock(slug="USER")
        mock_auth_repository.get_role_by_id = AsyncMock(return_value=non_maintainer_role)

        from sqlalchemy import select
        from src.components.user.models import User

        filtered_query = select(User)

        filter_criteria = MagicMock()
        filter_criteria.filters = [{"field": "role_name"}]

        count_result = MagicMock()
        count_result.scalar.return_value = 1
        final_result = MagicMock()
        final_result.scalars.return_value.all.return_value = []

        self.session.execute = AsyncMock(
            side_effect=[current_user_result, count_result, final_result]
        )

        with patch(
            "src.components.user.repositories.UserRoleFilterBuilder"
        ) as mock_builder_cls:
            mock_builder_cls.requires_role_join.return_value = True
            mock_builder_instance = MagicMock()
            mock_builder_instance.build_query = AsyncMock(return_value=filtered_query)
            mock_builder_cls.return_value = mock_builder_instance

            users, total = await self.user_repository.get_all(
                current_user_id,
                10,
                1,
                auth_repository=mock_auth_repository,
                filter_criteria=filter_criteria,
            )

        assert users == []
        assert total == 1
        mock_builder_instance.build_query.assert_awaited_once()

    # =====================================================================
    # add_user — untested branches
    # =====================================================================

    async def test_add_user_generic_sqlalchemy_error(self):
        from src.components.auth.schema import UserData

        user_data = UserData(
            name="New User", email="new@example.com", password="Test@123456",
            phone_number="+1234567890", role_id= UUID("11111111-1111-1111-1111-111111111111"), partner_id= UUID("11111111-1111-1111-1111-111111111111"),
            parent_id=None, country_id= UUID("11111111-1111-1111-1111-111111111111"), is_active=True,
        )

        self.session.add = MagicMock()
        self.session.flush = AsyncMock(side_effect=SQLAlchemyError("generic db error"))

        with pytest.raises(SQLAlchemyError, match="generic db error"):
            await self.user_repository.add_user(user_data)

    async def test_add_user_with_explicit_services_param(self):
        from src.components.auth.schema import UserData
        from src.components.auth.constant import SignupConfigKeys

        user_data = UserData(
            name="New User", email="new@example.com", password="Test@123456",
            phone_number="+1234567890", role_id= UUID("11111111-1111-1111-1111-111111111111"), partner_id= UUID("11111111-1111-1111-1111-111111111111"),
            parent_id=None, country_id= UUID("11111111-1111-1111-1111-111111111111"), is_active=True,
        )

        self.session.add = MagicMock()
        self.session.flush = AsyncMock()
        self.session.commit = AsyncMock()
        self.session.refresh = AsyncMock()
        self.session.execute = AsyncMock(return_value=MagicMock())

        result = await self.user_repository.add_user(
            user_data, services=SignupConfigKeys.TALKO
        )

        # Explicit `services` -> exactly one config-flag insert (vs. three
        # for the default/no-services branch already covered elsewhere).
        self.session.execute.assert_awaited_once()
        assert result is not None

    # =====================================================================
    # delete_by_id — untested branches
    # =====================================================================

    async def test_delete_by_id_not_found_raises(self):
        self.session.get = AsyncMock(return_value=None)

        with pytest.raises(UserNotFoundError):
            await self.user_repository.delete_by_id(1)

    async def test_delete_by_id_inactive_raises(self):
        mock_user = MagicMock(is_active=False)
        self.session.get = AsyncMock(return_value=mock_user)

        with pytest.raises(UserNotFoundError):
            await self.user_repository.delete_by_id(1)

    async def test_delete_by_id_sqlalchemy_error(self):
        self.session.get = AsyncMock(side_effect=SQLAlchemyError("db error"))

        with pytest.raises(SQLAlchemyError):
            await self.user_repository.delete_by_id(1)
        self.mock_logger.error.assert_called()

    async def test_update_user_email_change_resets_verification(self):
        mock_user = MagicMock(
            id= UUID("11111111-1111-1111-1111-111111111111"), is_active=True, is_deleted=False, email="old@example.com", phone_number="+911111111111",
        )
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_user
        self.session.execute = AsyncMock(return_value=mock_result)
        self.session.add = MagicMock()
        self.session.commit = AsyncMock()
        self.session.refresh = AsyncMock()

        await self.user_repository.update_user(UUID("11111111-1111-1111-1111-111111111111"), UUID("33333333-3333-3333-3333-333333333333"), email="new@example.com")

        assert mock_user.is_email_verified is False

    async def test_update_user_phone_change_resets_verification(self):
        mock_user = MagicMock(
            id= UUID("11111111-1111-1111-1111-111111111111"), is_active=True, is_deleted=False, email="a@example.com", phone_number="+911111111111",
        )
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_user
        self.session.execute = AsyncMock(return_value=mock_result)
        self.session.add = MagicMock()
        self.session.commit = AsyncMock()
        self.session.refresh = AsyncMock()

        await self.user_repository.update_user(UUID("11111111-1111-1111-1111-111111111111"), UUID("33333333-3333-3333-3333-333333333333"), phone_number="+922222222222")

        assert mock_user.is_phone_number_verified is False

    async def test_update_user_unchanged_email_does_not_reset_verification(self):
        mock_user = MagicMock(
            id= UUID("11111111-1111-1111-1111-111111111111"), is_active=True, is_deleted=False, email="same@example.com", phone_number="+911111111111",
        )
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_user
        self.session.execute = AsyncMock(return_value=mock_result)
        self.session.add = MagicMock()
        self.session.commit = AsyncMock()
        self.session.refresh = AsyncMock()

        # Explicitly set to a sentinel first so we can detect "untouched".
        mock_user.is_email_verified = "untouched"

        await self.user_repository.update_user(UUID("11111111-1111-1111-1111-111111111111"), UUID("33333333-3333-3333-3333-333333333333"), email="same@example.com")

        assert mock_user.is_email_verified == "untouched"

    async def test_update_user_generic_exception(self):
        self.session.execute = AsyncMock(side_effect=Exception("weird failure"))

        with pytest.raises(Exception, match="weird failure"):
            await self.user_repository.update_user(UUID("11111111-1111-1111-1111-111111111111"), UUID("33333333-3333-3333-3333-333333333333"), name="X")
        self.mock_logger.error.assert_called()

    # ---- get_by_id with show_inactive_users=True ----
    async def test_get_by_id_show_inactive_returns_active_user(self):
        mock_user = MagicMock(id= UUID("11111111-1111-1111-1111-111111111111"), is_active=True, is_deleted=False)
        self.session.get = AsyncMock(return_value=mock_user)

        result = await self.user_repository.get_by_id(1, show_inactive_users=True)

        assert result == mock_user

    async def test_get_by_id_show_inactive_returns_inactive_user(self):
        mock_user = MagicMock(id= UUID("11111111-1111-1111-1111-111111111111"), is_active=False, is_deleted=False)
        self.session.get = AsyncMock(return_value=mock_user)

        result = await self.user_repository.get_by_id(1, show_inactive_users=True)

        assert result == mock_user

    async def test_get_by_id_show_inactive_deleted_raises(self):
        self.session.get = AsyncMock(
            return_value=MagicMock(id= UUID("11111111-1111-1111-1111-111111111111"), is_active=False, is_deleted=True)
        )

        with pytest.raises(UserNotFoundError):
            await self.user_repository.get_by_id(1, show_inactive_users=True)

    async def test_get_by_id_show_inactive_not_found_raises(self):
        self.session.get = AsyncMock(return_value=None)

        with pytest.raises(UserNotFoundError):
            await self.user_repository.get_by_id(99, show_inactive_users=True)

    async def test_get_by_id_show_inactive_sqlalchemy_error(self):
        self.session.get = AsyncMock(side_effect=SQLAlchemyError("db down"))

        with pytest.raises(SQLAlchemyError):
            await self.user_repository.get_by_id(1, show_inactive_users=True)
        self.mock_logger.error.assert_called()

    # ---- update_user activation guards ----
    def _stub_update_session(self, user):
        result = MagicMock()
        result.scalar_one_or_none.return_value = user
        self.session.execute = AsyncMock(return_value=result)
        self.session.add = MagicMock()
        self.session.commit = AsyncMock()
        self.session.refresh = AsyncMock()

    async def test_update_user_missing_user_raises(self):
        self._stub_update_session(None)
        with pytest.raises(NotFoundError):
            await self.user_repository.update_user(UUID("11111111-1111-1111-1111-111111111111"), UUID("33333333-3333-3333-3333-333333333333"), name="X")

    async def test_update_user_deleted_user_raises_even_when_reactivating(self):
        self._stub_update_session(MagicMock(id= UUID("11111111-1111-1111-1111-111111111111"), is_active=False, is_deleted=True))
        with pytest.raises(NotFoundError):
            await self.user_repository.update_user(UUID("11111111-1111-1111-1111-111111111111"), UUID("33333333-3333-3333-3333-333333333333"), is_active=True)
        self.session.commit.assert_not_awaited()

    async def test_update_user_inactive_user_non_reactivating_raises(self):
        self._stub_update_session(MagicMock(id= UUID("11111111-1111-1111-1111-111111111111"), is_active=False, is_deleted=False))
        with pytest.raises(NotFoundError):
            await self.user_repository.update_user(UUID("11111111-1111-1111-1111-111111111111"), UUID("33333333-3333-3333-3333-333333333333"), name="X")
        self.session.commit.assert_not_awaited()

    async def test_update_user_inactive_user_with_is_active_false_raises(self):
        self._stub_update_session(MagicMock(id= UUID("11111111-1111-1111-1111-111111111111"), is_active=False, is_deleted=False))
        with pytest.raises(NotFoundError):
            await self.user_repository.update_user(UUID("11111111-1111-1111-1111-111111111111"), UUID("33333333-3333-3333-3333-333333333333"), is_active=False)

    async def test_update_user_reactivates_inactive_user(self):
        mock_user = MagicMock(id= UUID("11111111-1111-1111-1111-111111111111"), is_active=False, is_deleted=False)
        self._stub_update_session(mock_user)
        result = await self.user_repository.update_user(UUID("11111111-1111-1111-1111-111111111111"), UUID("33333333-3333-3333-3333-333333333333"), is_active=True)
        assert result.is_active is True
        assert mock_user.updated_by== UUID("33333333-3333-3333-3333-333333333333")
        self.session.commit.assert_awaited_once()

    async def test_update_user_deactivates_active_user(self):
        mock_user = MagicMock(id= UUID("11111111-1111-1111-1111-111111111111"), is_active=True, is_deleted=False)
        self._stub_update_session(mock_user)
        result = await self.user_repository.update_user(UUID("11111111-1111-1111-1111-111111111111"), UUID("33333333-3333-3333-3333-333333333333"), is_active=False)
        assert result.is_active is False
        self.session.commit.assert_awaited_once()

    # ---- get_user_by_user_id: inactive user handling ----
    async def test_get_user_by_user_id_inactive_user_raises(self):
        result_mock = MagicMock()
        result_mock.scalars.return_value.first.return_value = None
        self.session.execute = AsyncMock(return_value=result_mock)

        with pytest.raises(UserNotFoundError):
            await self.user_repository.get_user_by_user_id(5, 10)

        query = self.session.execute.call_args.args[0]
        assert "console_users.is_active IS" in str(query)

    async def test_get_user_by_user_id_show_inactive_skips_active_filter(self):
        result_mock = MagicMock()
        result_mock.scalars.return_value.first.return_value = MagicMock(is_active=False)
        self.session.execute = AsyncMock(return_value=result_mock)

        await self.user_repository.get_user_by_user_id(5, 10, show_inactive_users=True)

        query = self.session.execute.call_args.args[0]
        assert "console_users.is_active IS" not in str(query)