from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from src.components.auth.constant import AuthExceptionMsg
from src.components.auth.error import PermissionNotFoundError, RoleNotFoundError
from src.components.auth.models import Permission, Role
from src.components.auth.repositories import AuthRepository
from src.components.auth.schema import PermissionData, RoleData, UpdatePermissionRquest
from src.exceptions import AuthException


@pytest.mark.asyncio
class TestAuthRepository:

    @pytest.fixture(
        autouse=True,
    )
    def setup_class(self, mock_session_factory, mock_logger):
        """Set up the auth repository using fixtures for mock session and logger."""
        self.auth_repository = AuthRepository(
            session_factory=mock_session_factory, auth_service_logger=mock_logger
        )
        self.session = mock_session_factory.return_value.__aenter__.return_value
        self.mock_logger = mock_logger

        self.mock_role = Role(id=1, name="Admin", slug="admin", is_active=True)

        self.mock_permission = Permission(
            id=1,
            title="View Users",
            slug="view_users",
            description="Permission to view users",
        )

    async def test_get_role_by_id(self):
        """Test getting a role by ID."""
        role_id = 1
        mock_role = Role(id=role_id, name="Admin", slug="admin", is_active=True)

        # Mock the database execution and response
        mock_scalars = MagicMock()
        mock_scalars.one_or_none.return_value = self.mock_role
        mock_execute = MagicMock()
        mock_execute.scalars.return_value = mock_scalars
        self.session.execute = AsyncMock(return_value=mock_execute)

        # Call the get_role_by_id method
        result = await self.auth_repository.get_role_by_id(role_id)

        # Assert the results
        assert result.id == 1
        assert result.name == "Admin"

    async def test_get_role_by_id_not_found(self):
        """Test getting a role by ID when the role is not found."""
        role_id = 2

        # Mock the behavior of session.execute().scalars().one_or_none() to return None
        mock_scalars = MagicMock()
        mock_scalars.one_or_none.return_value = None
        self.session.execute.return_value.scalars.return_value = mock_scalars

        # Check that RoleNotFoundError is raised when role is not found
        with pytest.raises(RoleNotFoundError) as excinfo:
            await self.auth_repository.get_role_by_id(role_id)

        # Assert that the exception message contains the role ID
        assert str(role_id) in str(excinfo.value)

    async def test_get_role_by_id_generic_exception(self):
        # Mock generic Exception
        self.session.execute = AsyncMock(side_effect=Exception("Unexpected Error"))

        with pytest.raises(Exception) as exc_info:
            await self.auth_repository.get_role_by_id(id=1)

        assert str(exc_info.value) == "Unexpected Error"
        self.mock_logger.error.assert_called_with(
            "Error while fetching role by id: Unexpected Error"
        )

    async def test_delete_role(self):
        """Test deleting a role."""
        role_id = 1

        mock_scalars = MagicMock()
        mock_scalars.one_or_none.return_value = self.mock_role

        mock_execute = MagicMock()
        mock_execute.scalars.return_value = mock_scalars
        self.session.execute = AsyncMock(return_value=mock_execute)

        result = await self.auth_repository.delete_role(role_id, user_id=1)

        assert result.id == role_id
        assert result.is_deleted is True

    async def test_add_role_integrity_error(self):

        self.session.commit = AsyncMock(
            side_effect=IntegrityError("Duplicate entry", {}, None)
        )
        user_role = MagicMock()
        user_id = 1

        with pytest.raises(AuthException) as exc_info:
            await self.auth_repository.add_role(user_role=user_role, user_id=user_id)

        assert str(exc_info.value) == AuthExceptionMsg.ROLE_EXISTS

    async def test_add_role_generic_exception(self):

        user_role = RoleData(
            name="Admin", slug="admin", hierarchy=1, description="Admin role"
        )
        user_id = 1

        self.session.commit = AsyncMock(side_effect=Exception("Unexpected Error"))

        with pytest.raises(Exception) as exc_info:
            await self.auth_repository.add_role(user_role, user_id)

        # Verify that the raised exception matches
        assert str(exc_info.value) == "Unexpected Error"
        self.mock_logger.error.assert_called_with(
            "Error while creating role: Unexpected Error"
        )

    async def test_delete_role_role_not_found(self):

        mock_scalars = MagicMock()
        mock_scalars.one_or_none.return_value = None
        self.session.execute.return_value.scalars.return_value = mock_scalars
        with pytest.raises(RoleNotFoundError):
            await self.auth_repository.delete_role(id=1, user_id=1)

        self.mock_logger.warning.assert_called_with("Role not found for deletion: id=1")

    async def test_get_all_role(self):
        """Test getting all roles"""

        mock_scalars = MagicMock()
        mock_scalars.all.return_value = [self.mock_role]

        mock_execute = MagicMock()
        mock_execute.scalars.return_value = mock_scalars

        self.session.execute = AsyncMock(return_value=mock_execute)

        result = await self.auth_repository.get_all_role(True)

        assert isinstance(result, list)
        assert result[0].name == "Admin"

    async def test_get_all_role_external_partner_success(self):
        """Test getting all roles"""

        mock_scalars = MagicMock()
        mock_scalars.all.return_value = [self.mock_role]

        mock_execute = MagicMock()
        mock_execute.scalars.return_value = mock_scalars

        self.session.execute = AsyncMock(return_value=mock_execute)

        result = await self.auth_repository.get_all_role(False)

        assert isinstance(result, list)
        assert result[0].name == "Admin"

    async def test_get_all_role_scoped_to_partner_when_partner_id_given(self):
        """When partner_id is supplied, roles are filtered to that partner's own catalog."""

        mock_scalars = MagicMock()
        mock_scalars.all.return_value = [self.mock_role]

        mock_execute = MagicMock()
        mock_execute.scalars.return_value = mock_scalars

        self.session.execute = AsyncMock(return_value=mock_execute)

        await self.auth_repository.get_all_role(True, partner_id=7)

        query = self.session.execute.call_args.args[0]
        assert "console_role.partner_id = " in str(query)

    async def test_get_all_role_defaults_to_shared_catalog_when_no_partner_id(self):
        """Without a partner_id, only the shared default catalog is returned."""

        mock_scalars = MagicMock()
        mock_scalars.all.return_value = [self.mock_role]

        mock_execute = MagicMock()
        mock_execute.scalars.return_value = mock_scalars

        self.session.execute = AsyncMock(return_value=mock_execute)

        await self.auth_repository.get_all_role(True)

        query = self.session.execute.call_args.args[0]
        assert "console_role.partner_id IS NULL" in str(query)

    async def test_add_permission(self):
        """Test adding a permission."""
        user_id = 1

        # Use PermissionData (Pydantic) as input
        permission_data = PermissionData(
            title="View Users",
            slug="view_users",
            description="Permission to view users",
        )

        self.session.commit = AsyncMock()
        self.session.refresh = AsyncMock()
        self.session.add = AsyncMock()

        with patch(
            "src.components.auth.repositories.Permission",
            return_value=self.mock_permission,
        ):
            result = await self.auth_repository.add_permission(permission_data, user_id)

        assert result.title == self.mock_permission.title
        assert result.slug == self.mock_permission.slug

    async def test_get_all_permissions(self):
        """Test fetching all permissions."""

        mock_scalars = MagicMock()
        mock_scalars.all.return_value = [self.mock_permission]

        mock_execute = MagicMock()
        mock_execute.scalars.return_value = mock_scalars

        self.session.execute = AsyncMock(return_value=mock_execute)

        result = await self.auth_repository.get_all_permission()
        assert len(result) == 1

    async def test_delete_permission(self):
        """Test deleting a permission."""
        permission_id = 1

        mock_scalars = MagicMock()
        mock_scalars.one_or_none.return_value = self.mock_permission

        mock_execute = MagicMock()
        mock_execute.scalars.return_value = mock_scalars
        self.session.execute = AsyncMock(return_value=mock_execute)

        result = await self.auth_repository.delete_permission(permission_id, user_id=1)

        assert result.id == permission_id
        assert result.is_deleted is True

    async def test_delete_permission_not_found(self):
        # Mock no result found
        mock_scalars = MagicMock()
        mock_scalars.one_or_none.return_value = None
        self.session.execute.return_value.scalars.return_value = mock_scalars
        with pytest.raises(PermissionNotFoundError):
            await self.auth_repository.delete_permission(id=1, user_id=1)

        self.mock_logger.warning.assert_called_with(
            "Permission not found for deletion: id=1"
        )

    async def test_add_permission_integrity_error(self):
        # Mock IntegrityError
        self.session.commit = AsyncMock(
            side_effect=IntegrityError("Duplicate entry", {}, None)
        )

        with pytest.raises(AuthException) as exc_info:
            await self.auth_repository.add_permission(
                user_permission=MagicMock(), user_id=1
            )

        assert str(exc_info.value) == AuthExceptionMsg.PERMISSIONS_EXISTS

    async def test_get_permission_by_id(self):
        """Test getting a permission by ID."""
        permission_id = 1

        # Mock the database execution and response
        mock_scalars = MagicMock()
        mock_scalars.one_or_none.return_value = self.mock_permission
        mock_execute = MagicMock()
        mock_execute.scalars.return_value = mock_scalars
        self.session.execute = AsyncMock(return_value=mock_execute)

        result = await self.auth_repository.get_permission_by_id(permission_id)

        # Assert the results
        assert result.id == 1
        assert result.title == "View Users"

    async def test_get_permission_by_id_not_found(self):
        """Test getting a permission by ID when the permission is not found."""
        permission_id = 2

        # Mock the behavior of session.execute().scalars().one_or_none() to return None
        mock_scalars = MagicMock()
        mock_scalars.one_or_none.return_value = None
        self.session.execute.return_value.scalars.return_value = mock_scalars

        # Check that RoleNotFoundError is raised when role is not found
        with pytest.raises(PermissionNotFoundError) as exc:
            await self.auth_repository.get_permission_by_id(permission_id)

        # Assert that the exception message contains the role ID
        assert str(permission_id) in str(exc.value)

    async def test_get_user_permission(self):
        """Test getting list of user permission"""

        mock_permission_list = ["Permission_1", "Permission_1"]
        user_id = 1

        mock_scalars = MagicMock()
        mock_scalars.all.return_value = mock_permission_list

        mock_execute = MagicMock()
        mock_execute.scalars.return_value = mock_scalars
        self.session.execute = AsyncMock(return_value=mock_execute)

        result = await self.auth_repository.get_user_permission(user_id=user_id)

        assert result == mock_permission_list

    async def test_get_user_permission_generic_exception(self):
        # Mock generic Exception
        self.session.execute = AsyncMock(side_effect=Exception("Unexpected Error"))

        with pytest.raises(Exception) as exc_info:
            await self.auth_repository.get_user_permission(user_id=1)

        assert str(exc_info.value) == "Unexpected Error"
        self.mock_logger.error.assert_called_with(
            "Unexpected error during list of user permission Unexpected Error"
        )

    async def test_delete_permission_generic_exception(self):
        # Mock generic Exception
        self.session.execute = AsyncMock(side_effect=Exception("Unexpected Error"))

        with pytest.raises(Exception) as exc_info:
            await self.auth_repository.delete_permission(id=1, user_id=1)

        assert str(exc_info.value) == "Unexpected Error"
        self.mock_logger.error.assert_called_with(
            "Error while deleting permission: Unexpected Error"
        )

    async def test_get_all_permission_generic_exception(self):
        # Mock generic Exception
        self.session.execute = AsyncMock(side_effect=Exception("Unexpected Error"))

        with pytest.raises(Exception) as exc_info:
            await self.auth_repository.get_all_permission()

        assert str(exc_info.value) == "Unexpected Error"
        self.mock_logger.error.assert_called_with(
            "Error while fetching all permissions: Unexpected Error"
        )

    async def test_get_permission_by_id_generic_exception(self):
        # Mock generic Exception
        self.session.execute = AsyncMock(side_effect=Exception("Unexpected Error"))

        with pytest.raises(Exception) as exc_info:
            await self.auth_repository.get_permission_by_id(id=1)

        assert str(exc_info.value) == "Unexpected Error"
        self.mock_logger.error.assert_called_with(
            "Error while fetching permission by id: Unexpected Error"
        )

    async def test_delete_role_generic_exception(self):
        # Mock generic Exception
        self.session.execute = AsyncMock(side_effect=Exception("Unexpected Error"))

        with pytest.raises(Exception) as exc_info:
            await self.auth_repository.delete_role(id=1, user_id=1)

        assert str(exc_info.value) == "Unexpected Error"
        self.mock_logger.error.assert_called_with(
            "Error while deleting role: Unexpected Error"
        )

    async def test_get_all_role_generic_exception(self):
        # Mock generic Exception
        self.session.execute = AsyncMock(side_effect=Exception("Unexpected Error"))

        with pytest.raises(Exception) as exc_info:
            await self.auth_repository.get_all_role(True)

        assert str(exc_info.value) == "Unexpected Error"
        self.mock_logger.error.assert_called_with(
            "Error while fetching all roles: Unexpected Error"
        )

    async def test_add_permission_generic_exception(self):
        user_id = 1
        # Use PermissionData (Pydantic) as input
        permission_data = PermissionData(
            title="View Users",
            slug="view_users",
            description="Permission to view users",
        )
        # Mock generic Exception
        self.session.commit = AsyncMock(side_effect=Exception("Unexpected Error"))

        with pytest.raises(Exception) as exc_info:
            await self.auth_repository.add_permission(permission_data, user_id)

        assert str(exc_info.value) == "Unexpected Error"
        self.mock_logger.error.assert_called_with(
            "Error while creating permission: Unexpected Error"
        )

    async def test_reset_password_success(self):
        """Test resetting password successfully."""
        user = AsyncMock(id=1, name="Test User", email="test@example.com")
        hashed_password = "new_hashed_password"

        self.session.execute = AsyncMock()
        self.session.commit = AsyncMock()

        await self.auth_repository.reset_password(hashed_password, user)

        self.session.execute.assert_called_once()
        self.session.commit.assert_called_once()
        self.mock_logger.info.assert_called_with("Attempting to update hash password")

    async def test_reset_password_generic_exception(self):
        """Test handling an unexpected error while resetting password."""
        user = AsyncMock(id=1, name="Test User", email="test@example.com")
        hashed_password = "new_hashed_password"

        self.session.execute = AsyncMock(side_effect=Exception("Unexpected Error"))

        with pytest.raises(Exception) as exc_info:
            await self.auth_repository.reset_password(hashed_password, user)

        assert str(exc_info.value) == "Unexpected Error"
        self.mock_logger.error.assert_called_with(
            "Error while updating password: Unexpected Error"
        )

    @pytest.mark.asyncio
    async def test_get_parents_by_role_id_success(self):
        """Test fetching parents by role ID."""
        role_id = 1
        current_user_partner_id = 1
        mock_role_hierarchy = -4
        mock_parents = ["Parent 1", "Parent 2"]

        # First mock: role hierarchy result
        role_result_mock = MagicMock()
        role_result_mock.scalar_one_or_none.return_value = mock_role_hierarchy

        # Second mock: parent user query result
        parent_query_result_mock = MagicMock() 
        parent_query_result_mock.scalars.return_value.all.return_value = mock_parents

        # Set side_effect to return mocks in order of query execution
        self.session.execute = AsyncMock(side_effect=[role_result_mock, parent_query_result_mock])

        # Call the method
        result = await self.auth_repository.get_parent_users_by_role_id(
            role_id, current_user_partner_id
        )

        assert result == mock_parents

    async def test_get_parents_by_role_id_generic_exception(self):
        """Test handling an unexpected error while fetching parents by role ID."""
        role_id = 1
        current_user_partner_id = 1

        self.session.execute = AsyncMock(side_effect=Exception("Unexpected Error"))

        with pytest.raises(Exception) as exc_info:
            await self.auth_repository.get_parent_users_by_role_id(
                role_id, current_user_partner_id
            )

        assert str(exc_info.value) == "Unexpected Error"
        self.mock_logger.error.assert_called_with(
            "Error while fetching parents by role id: Unexpected Error"
        )

    async def test_get_default_role_permission_for_user(self):
        """Test fetching default role permission slugs for a user."""
        user_id = 1
        mock_slugs = ["perm_1", "perm_2"]

        mock_scalars = MagicMock()
        mock_scalars.all.return_value = mock_slugs
        mock_execute = MagicMock()
        mock_execute.scalars.return_value = mock_scalars
        self.session.execute = AsyncMock(return_value=mock_execute)

        result = await self.auth_repository.get_default_role_permission_for_user(
            user_id
        )
        assert result == mock_slugs
        self.mock_logger.info.assert_any_call(
            f"Attempting to get default role permissions for user ID: {user_id}"
        )
        self.mock_logger.info.assert_any_call(
            f"Default role permissions fetched successfully: {mock_slugs}"
        )

    async def test_get_default_role_permission_for_user_generic_exception(self):
        user_id = 1
        self.session.execute = AsyncMock(side_effect=Exception("Unexpected Error"))
        with pytest.raises(Exception) as exc_info:
            await self.auth_repository.get_default_role_permission_for_user(user_id)
        assert str(exc_info.value) == "Unexpected Error"
        self.mock_logger.error.assert_called_with(
            "Unexpected error during fetching default role permissions for user: Unexpected Error"
        )

    async def test_get_partner_role_permissions_by_partner_and_role(self):
        """Test fetching partner role permissions."""
        partner_id = 1
        role_id = 2
        mock_permissions = [self.mock_permission]

        mock_scalars = MagicMock()
        mock_scalars.all.return_value = mock_permissions
        mock_execute = MagicMock()
        mock_execute.scalars.return_value = mock_scalars
        self.session.execute = AsyncMock(return_value=mock_execute)

        result = (
            await self.auth_repository.get_partner_role_permissions_by_partner_and_role(
                partner_id, role_id
            )
        )
        assert result == mock_permissions

    async def test_get_partner_role_permissions_by_partner_and_role_generic_exception(
        self,
    ):
        partner_id = 1
        role_id = 2
        self.session.execute = AsyncMock(side_effect=Exception("Unexpected Error"))
        with pytest.raises(Exception) as exc_info:
            await self.auth_repository.get_partner_role_permissions_by_partner_and_role(
                partner_id, role_id
            )
        assert str(exc_info.value) == "Unexpected Error"
        self.mock_logger.error.assert_called_with(
            f"Error fetching partner role permissions for partner_id={partner_id}, role_id={role_id}: Unexpected Error"
        )

    async def test_get_default_role_permissions_by_role_id(self):
        """Test fetching default role permissions by role id."""
        role_id = 2
        mock_permissions = [self.mock_permission]

        mock_scalars = MagicMock()
        mock_scalars.all.return_value = mock_permissions
        mock_execute = MagicMock()
        mock_execute.scalars.return_value = mock_scalars
        self.session.execute = AsyncMock(return_value=mock_execute)

        result = await self.auth_repository.get_default_role_permissions_by_role_id(
            role_id
        )
        assert result == mock_permissions

    async def test_get_default_role_permissions_by_role_id_generic_exception(self):
        role_id = 2
        self.session.execute = AsyncMock(side_effect=Exception("Unexpected Error"))
        with pytest.raises(Exception) as exc_info:
            await self.auth_repository.get_default_role_permissions_by_role_id(role_id)
        assert str(exc_info.value) == "Unexpected Error"
        self.mock_logger.error.assert_called_with(
            f"Error fetching default role permissions for role_id={role_id}: Unexpected Error"
        )

    async def test_update_permission_success(self):
        permission_id = 1
        update_data = UpdatePermissionRquest(title="Updated Title")

        # Set expected updated value
        self.mock_permission.title = "Updated Title"

        # Step 1: mock the .scalars().one_or_none() chain
        mock_scalars = MagicMock()
        mock_scalars.one_or_none.return_value = self.mock_permission

        mock_execute = MagicMock()
        mock_execute.scalars.return_value = mock_scalars

        self.session.execute = AsyncMock(return_value=mock_execute)
        self.session.commit = AsyncMock()
        self.session.refresh = AsyncMock()

        # Step 2: call method
        result = await self.auth_repository.update_permission(
            permission_id, update_data
        )

        # Step 3: assertions
        self.session.execute.assert_awaited_once()
        self.session.commit.assert_awaited_once()
        self.session.refresh.assert_awaited_once_with(self.mock_permission)

        assert result.title == "Updated Title"
        assert isinstance(result, Permission)

    async def test_update_permission_not_found(self):
        permission_id = 99
        update_data = UpdatePermissionRquest(title="New Title")

        mock_scalars = MagicMock()
        mock_scalars.one_or_none.return_value = None
        self.session.execute.return_value.scalars = MagicMock(return_value=mock_scalars)

        with pytest.raises(PermissionNotFoundError):
            await self.auth_repository.update_permission(permission_id, update_data)

        self.mock_logger.error.assert_any_call(
            f"Permission not found: id={permission_id}"
        )

    async def test_update_permission_integrity_error(self):
        permission_id = 1
        update_data = UpdatePermissionRquest(title="Duplicate Title")

        mock_scalars = MagicMock()
        mock_scalars.one_or_none.return_value = self.mock_permission
        self.session.execute.return_value.scalars = MagicMock(return_value=mock_scalars)

        self.session.commit = AsyncMock(
            side_effect=IntegrityError("stmt", "params", "orig")
        )

        with pytest.raises(AuthException) as exc:
            await self.auth_repository.update_permission(permission_id, update_data)

        assert str(exc.value) == AuthExceptionMsg.PERMISSIONS_EXISTS

    async def test_update_permission_unexpected_exception(self):
        permission_id = 1
        update_data = UpdatePermissionRquest(title="Something Wrong")

        mock_scalars = MagicMock()
        mock_scalars.one_or_none.return_value = self.mock_permission
        self.session.execute.return_value.scalars = MagicMock(return_value=mock_scalars)

        self.session.commit = AsyncMock(side_effect=Exception("Unexpected error"))

        with pytest.raises(Exception) as exc:
            await self.auth_repository.update_permission(permission_id, update_data)

        assert "Unexpected error" in str(exc.value)

        self.mock_logger.error.assert_any_call(
            "Error while updating permission: Unexpected error"
        )

    async def test_get_internal_permissions_success(self):
        """Test fetching internal permissions successfully."""

        mock_permissions = [("perm_1",), ("perm_2",)]
        mock_execute_result = MagicMock()
        mock_execute_result.fetchall.return_value = mock_permissions
        self.session.execute = AsyncMock(return_value=mock_execute_result)

        result = await self.auth_repository.get_internal_permissions()

        assert result == mock_permissions
        self.mock_logger.info.assert_called_with("Getting internal permissions")

    async def test_get_internal_permissions_exception(self):
        """Test exception handling in get_internal_permissions."""

        self.session.execute = AsyncMock(side_effect=Exception("Unexpected Error"))

        with pytest.raises(Exception) as exc_info:
            await self.auth_repository.get_internal_permissions()

        assert str(exc_info.value) == "Unexpected Error"
        self.mock_logger.error.assert_called_with(
            "Got the unexcpected Error: Unexpected Error"
        )

    async def test_get_default_role_permission_matrix_internal(self):
        """Test fetching permission matrix for internal permissions."""
        # Mock the response from session.execute().fetchall()
        mock_matrix = [
            {
                "role_id": 1,
                "role_name": "Admin",
                "category": "User",
                "slug": "view_users",
                "permission_id": 1,
                "created_at": "2024-01-01",
                "description": "desc",
                "display_text": "View Users",
                "is_default": True,
            }
        ]
        mock_execute_result = MagicMock()
        mock_execute_result.fetchall.return_value = mock_matrix
        self.session.execute = AsyncMock(return_value=mock_execute_result)

        result = await self.auth_repository.get_default_role_permission_matrix(
            is_internal_permission=True
        )
        assert result == mock_matrix
        self.mock_logger.info.assert_any_call(
            "fetching all default and partner role permissions"
        )
        self.mock_logger.info.assert_any_call(
            f"Permission matrix fetched successfully: {mock_matrix}"
        )

    async def test_get_default_role_permission_matrix_external(self):
        """Test fetching permission matrix for external permissions."""
        mock_matrix = [
            {
                "role_id": 2,
                "role_name": "User",
                "category": "Uncategorized",
                "slug": "edit_profile",
                "permission_id": 2,
                "created_at": "2024-01-02",
                "description": "desc2",
                "display_text": "Edit Profile",
                "is_default": False,
            }
        ]
        mock_execute_result = MagicMock()
        mock_execute_result.fetchall.return_value = mock_matrix
        self.session.execute = AsyncMock(return_value=mock_execute_result)

        result = await self.auth_repository.get_default_role_permission_matrix(
            is_internal_permission=False
        )
        assert result == mock_matrix
        self.mock_logger.info.assert_any_call(
            "fetching all default and partner role permissions"
        )
        self.mock_logger.info.assert_any_call(
            f"Permission matrix fetched successfully: {mock_matrix}"
        )

    async def test_get_default_role_permission_matrix_exception(self):
        """Test exception handling in get_default_role_permission_matrix."""
        self.session.execute = AsyncMock(side_effect=Exception("Unexpected Error"))
        with pytest.raises(Exception) as exc_info:
            await self.auth_repository.get_default_role_permission_matrix(
                is_internal_permission=True
            )
        assert str(exc_info.value) == "Unexpected Error"
        self.mock_logger.error.assert_called_with(
            "Failed to fetch permission matrix: Unexpected Error"
        )

    async def test_update_role_success(self):
        role_id = 1
        update_data = {"name": "Updated Admin", "slug": "updated_admin"}

        # Set expected updated value
        self.mock_role.name = "Updated Admin"
        self.mock_role.slug = "updated_admin"

        mock_scalars = MagicMock()
        mock_scalars.one_or_none.return_value = self.mock_role
        mock_execute = MagicMock()
        mock_execute.scalars.return_value = mock_scalars

        self.session.execute = AsyncMock(return_value=mock_execute)
        self.session.commit = AsyncMock()
        self.session.refresh = AsyncMock()

        result = await self.auth_repository.update_role(role_id, **update_data)

        self.session.execute.assert_awaited_once()
        self.session.commit.assert_awaited_once()
        self.session.refresh.assert_awaited_once_with(self.mock_role)

        assert result.name == "Updated Admin"
        assert result.slug == "updated_admin"
        assert isinstance(result, Role)

    async def test_update_role_not_found(self):
        role_id = 99
        update_data = {"name": "New Name"}

        mock_scalars = MagicMock()
        mock_scalars.one_or_none.return_value = None
        self.session.execute.return_value.scalars = MagicMock(return_value=mock_scalars)

        with pytest.raises(RoleNotFoundError):
            await self.auth_repository.update_role(role_id, **update_data)

        self.mock_logger.error.assert_any_call(f"Role not found: id={role_id}")

    async def test_update_role_integrity_error(self):
        role_id = 1
        update_data = {"name": "Duplicate Name"}

        mock_scalars = MagicMock()
        mock_scalars.one_or_none.return_value = self.mock_role
        self.session.execute.return_value.scalars = MagicMock(return_value=mock_scalars)
        self.session.commit = AsyncMock(
            side_effect=IntegrityError("stmt", "params", "orig")
        )

        with pytest.raises(AuthException) as exc:
            await self.auth_repository.update_role(role_id, **update_data)

        assert str(exc.value) == AuthExceptionMsg.ROLE_EXISTS

    async def test_update_role_unexpected_exception(self):
        role_id = 1
        update_data = {"name": "Something Wrong"}

        mock_scalars = MagicMock()
        mock_scalars.one_or_none.return_value = self.mock_role
        self.session.execute.return_value.scalars = MagicMock(return_value=mock_scalars)
        self.session.commit = AsyncMock(side_effect=Exception("Unexpected error"))

        with pytest.raises(Exception) as exc:
            await self.auth_repository.update_role(role_id, **update_data)

        assert "Unexpected error" in str(exc.value)
        self.mock_logger.error.assert_any_call(
            "Error while updating role: Unexpected error"
        )


    async def test_get_role_by_hierarchy_success(self):
        """Should return role when found by hierarchy."""
        hierarchy = 1
        mock_scalars = MagicMock()
        mock_scalars.one_or_none.return_value = self.mock_role

        mock_execute = MagicMock()
        mock_execute.scalars.return_value = mock_scalars

        self.session.execute = AsyncMock(return_value=mock_execute)

        result = await self.auth_repository.get_role_by_hierarchy(hierarchy)

        assert result == self.mock_role
        self.session.execute.assert_awaited_once()
        self.mock_logger.info.assert_called_with(
            f"Getting role details by hierarchy: {hierarchy}."
        )

    async def test_get_role_by_hierarchy_not_found(self):
        """Should return None when no role matches hierarchy."""
        hierarchy = 99
        mock_scalars = MagicMock()
        mock_scalars.one_or_none.return_value = None

        mock_execute = MagicMock()
        mock_execute.scalars.return_value = mock_scalars

        self.session.execute = AsyncMock(return_value=mock_execute)

        result = await self.auth_repository.get_role_by_hierarchy(hierarchy)

        assert result is None
        self.session.execute.assert_awaited_once()
        self.mock_logger.info.assert_called_with(
            f"Getting role details by hierarchy: {hierarchy}."
        )

    async def test_get_role_by_hierarchy_generic_exception(self):
        """Should raise exception and log error when query fails."""
        hierarchy = 2
        self.session.execute = AsyncMock(side_effect=Exception("DB failure"))

        with pytest.raises(Exception) as exc_info:
            await self.auth_repository.get_role_by_hierarchy(hierarchy)

        assert str(exc_info.value) == "DB failure"
        self.mock_logger.error.assert_called_with(
            f"Error while fetching role by hierarchy: {hierarchy}, error: DB failure"
        )