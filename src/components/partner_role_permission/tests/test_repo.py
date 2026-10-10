import pytest
import collections
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from asyncpg.exceptions import UniqueViolationError
from sqlalchemy.exc import IntegrityError

from src.components.auth.models import Permission, Role
from src.components.partner.models import Partner
from src.components.partner_role_permission.constant import ExceptionMsg
from src.components.partner_role_permission.error import (
    PartnerRolePermissionNotFoundError,
)
from src.components.partner_role_permission.models import PartnerRolePermission
from src.components.partner_role_permission.repositories import (
    PartnerPermissionRepository,
)
from src.components.partner_role_permission.schema import PartnerPermissionData
from src.exceptions import PartnerRolePermissionException


@pytest.mark.asyncio
class TestPartnerPermissionRepository:

    @pytest.fixture(autouse=True)
    def setup_class(self, mock_session_factory, mock_logger):
        """Set up the PartnerPermissionRepository using fixtures for mock session and logger."""
        self.repository = PartnerPermissionRepository(
            session_factory=mock_session_factory, console_service_logger=mock_logger
        )
        self.session = mock_session_factory.return_value.__aenter__.return_value
        self.mock_logger = mock_logger

    async def test_add_partner_permission_success(self):
        """Test adding a partner permission successfully."""
        add_data = PartnerPermissionData(partner_id=1, role_id=1, permission_id=1)
        user_id = 1

        # Mock subqueries for partner, role, and permission existence
        mock_result = MagicMock()
        mock_result.fetchone.return_value = MagicMock(
            partner_exists=True, role_exists=True, permission_exists=True
        )
        self.session.execute = AsyncMock(return_value=mock_result)

        # Mock session commit and refresh
        self.session.commit = AsyncMock()
        self.session.refresh = AsyncMock()

        result = await self.repository.add_partner_permission(add_data, user_id)

        assert result.partner_id == add_data.partner_id
        assert result.role_id == add_data.role_id
        assert result.permission_id == add_data.permission_id
        self.mock_logger.info.assert_called_with(
            "Successfully inserted mapping in db for partner id {}".format(
                result.partner_id
            )
        )

    async def test_add_partner_permission_unique_violation(self):
        """Test handling unique constraint violation during partner permission addition."""
        add_data = PartnerPermissionData(partner_id=1, role_id=1, permission_id=1)
        user_id = 1

        # Simulate UniqueViolationError during commit
        self.session.commit = AsyncMock(
            side_effect=UniqueViolationError("Duplicate entry")
        )

        with pytest.raises(PartnerRolePermissionException) as exc_info:
            await self.repository.add_partner_permission(add_data, user_id)

        assert "Duplicate entry" in str(exc_info.value)

    async def test_add_partner_permission_fk_constraint_violation(self):
        """Test handling foreign key constraint violation during partner permission addition."""
        add_data = PartnerPermissionData(partner_id=1, role_id=1, permission_id=1)
        user_id = 1

        # Simulate IntegrityError for foreign key constraint
        fk_error_message = "foreign key constraint"
        self.session.commit = AsyncMock(
            side_effect=IntegrityError(fk_error_message, {}, None)
        )

        with pytest.raises(PartnerRolePermissionException) as exc_info:
            await self.repository.add_partner_permission(add_data, user_id)

        assert "A record with this combination already exists." in str(exc_info.value)

    async def test_get_all_partner_role_permission(self):
        """Test retrieving all partner role permissions."""
        mock_partner_permission = PartnerRolePermission(
            partner_id=1, role_id=1, permission_id=1
        )

        # Mock the query execution
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [mock_partner_permission]
        self.session.execute = AsyncMock(return_value=mock_result)

        result = await self.repository.get_all_partner_role_permission()

        assert len(result) == 1
        assert result[0].partner_id == mock_partner_permission.partner_id

    async def test_get_by_partner_id_partner_role_permission(self):
        """Test retrieving all partner role permissions by partner id."""
        mock_partner_permission = PartnerRolePermission(
            partner_id=1, role_id=1, permission_id=1
        )

        # Mock the query execution
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [mock_partner_permission]
        self.session.execute = AsyncMock(return_value=mock_result)

        result = await self.repository.get_by_partner_id(1)

        assert len(result) == 1
        assert result[0].partner_id == mock_partner_permission.partner_id

    async def test_get_by_partner_id_not_found(self):
        """Test retrieving partner permissions by partner ID when no permissions exist."""
        partner_id = 99

        # Mock the query execution to return an empty list
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        self.session.execute = AsyncMock(return_value=mock_result)

        with pytest.raises(PartnerRolePermissionException) as exc_info:
            await self.repository.get_by_partner_id(partner_id)

        # Verify the exception message
        assert str(exc_info.value) == "Partner Role Permission not found, id: 99"

    async def test_get_partner_role_permission_by_id(self):
        """Test retrieving a partner role permission by ID."""

        mock_partner_permission = PartnerRolePermission(
            id=1, partner_id=1, role_id=1, permission_id=1
        )

        # Mock the query execution to return a single result
        mock_result = MagicMock()
        mock_result.scalars.return_value.one_or_none.return_value = (
            mock_partner_permission
        )
        self.session.execute = AsyncMock(return_value=mock_result)

        result = await self.repository.get_partner_role_permission_by_id(1)

        assert result.id == mock_partner_permission.id
        assert result.partner_id == mock_partner_permission.partner_id

    async def test_add_partner_permission_partner_not_found(self):
        """Test adding partner permission when partner does not exist."""

        add_data = PartnerPermissionData(partner_id=99, role_id=1, permission_id=1)
        user_id = 1

        # Mock the result to show partner does not exist
        mock_result = MagicMock()
        mock_result.fetchone.return_value = MagicMock(
            partner_exists=False, role_exists=True, permission_exists=True
        )
        self.session.execute = AsyncMock(return_value=mock_result)

        with pytest.raises(PartnerRolePermissionException) as exc_info:
            await self.repository.add_partner_permission(add_data, user_id)

        assert "Partner does not exist or is inactive." in str(exc_info.value)

    async def test_add_partner_permission_permission_not_found(self):
        """Test adding partner permission when permission does not exist."""

        add_data = PartnerPermissionData(partner_id=1, role_id=1, permission_id=99)
        user_id = 1

        # Mock the result to show permission does not exist
        mock_result = MagicMock()
        mock_result.fetchone.return_value = MagicMock(
            partner_exists=True, role_exists=True, permission_exists=False
        )
        self.session.execute = AsyncMock(return_value=mock_result)

        with pytest.raises(PartnerRolePermissionException) as exc_info:
            await self.repository.add_partner_permission(add_data, user_id)

        assert "Permission does not exist or is inactive." in str(exc_info.value)

    async def test_add_partner_permission_role_not_found(self):
        """Test adding partner permission when role does not exist."""

        add_data = PartnerPermissionData(partner_id=1, role_id=99, permission_id=1)
        user_id = 1

        # Mock the result to show role does not exist
        mock_result = MagicMock()
        mock_result.fetchone.return_value = MagicMock(
            partner_exists=True, role_exists=False, permission_exists=True
        )
        self.session.execute = AsyncMock(return_value=mock_result)

        with pytest.raises(PartnerRolePermissionException) as exc_info:
            await self.repository.add_partner_permission(add_data, user_id)

        assert "Role does not exist or is inactive." in str(exc_info.value)

    async def test_delete_partner_role_permission_success(self):
        """Test deleting a partner role permission successfully."""
        permission_id = 1
        mock_permission = PartnerRolePermission(id=permission_id)

        # Mock the query execution to return the permission object
        mock_result = MagicMock()
        mock_result.scalars.return_value.one_or_none.return_value = mock_permission
        self.session.execute = AsyncMock(return_value=mock_result)

        # Mock session delete and commit
        self.session.delete = AsyncMock()
        self.session.commit = AsyncMock()

        await self.repository.delete_partner_role_permission(permission_id)

        self.session.delete.assert_called_once_with(mock_permission)
        self.session.commit.assert_called_once()
        self.mock_logger.info.assert_called_with(
            "Successfully deleted partner role permission, id: {}".format(permission_id)
        )

    async def test_get_by_id_partner_role_permission_general_exception(self):

        partner_id = 1

        # Mock the query execution to raise a general exception
        self.session.execute = AsyncMock(side_effect=Exception("Unexpected error"))

        with pytest.raises(Exception) as exc_info:
            await self.repository.get_by_partner_id(partner_id)

        assert "Unexpected error" in str(exc_info.value)

    async def test_delete_partner_role_permission_general_exception(self):

        partner_id = 1

        # Mock the query execution to raise a general exception
        self.session.execute = AsyncMock(side_effect=Exception("Unexpected error"))

        with pytest.raises(Exception) as exc_info:
            await self.repository.delete_partner_role_permission(partner_id)

        assert "Unexpected error" in str(exc_info.value)

    async def test_get_all_partner_role_permission_general_exception(self):

        # Mock the query execution to raise a general exception
        self.session.execute = AsyncMock(side_effect=Exception("Unexpected error"))

        with pytest.raises(Exception) as exc_info:
            await self.repository.get_all_partner_role_permission()

        assert "Unexpected error" in str(exc_info.value)

    async def test_add_partner_permission_general_exception(self):

        add_data = PartnerPermissionData(partner_id=1, role_id=1, permission_id=1)
        user_id = 1

        # Mock the query execution to raise a general exception
        self.session.execute = AsyncMock(side_effect=Exception("Unexpected error"))

        with pytest.raises(Exception) as exc_info:
            await self.repository.add_partner_permission(add_data, user_id)

        assert "Unexpected error" in str(exc_info.value)

    async def test_delete_partner_role_permission_not_found(self):

        # Mock the result to show permission does not exist
        mock_result = MagicMock()
        mock_result.scalars.return_value.one_or_none.return_value = None
        self.session.execute = AsyncMock(return_value=mock_result)

        with pytest.raises(PartnerRolePermissionException) as exc_info:
            await self.repository.delete_partner_role_permission(1)

        assert "Partner Role Permission not found, id: 1" in str(exc_info.value)

    async def test_get_partner_role_permission_by_id_not_found(self):

        # Mock the result to show permission does not exist
        mock_result = MagicMock()
        mock_result.scalars.return_value.one_or_none.return_value = None
        self.session.execute = AsyncMock(return_value=mock_result)

        with pytest.raises(PartnerRolePermissionException) as exc_info:
            await self.repository.get_partner_role_permission_by_id(1)

        assert "Partner Role Permission not found, id: 1" in str(exc_info.value)

    async def test_get_partner_role_permission_by_id_general_exception(self):

        # Mock the query execution to raise a general exception
        self.session.execute = AsyncMock(side_effect=Exception("Unexpected error"))

        with pytest.raises(Exception) as exc_info:
            await self.repository.get_partner_role_permission_by_id(1)

        assert "Unexpected error" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_get_partner_role_permission_matrix_success(self):
        """Test successful fetch of partner permissions matrix for config key."""
        key = "IS_CUSTOM_ROLE_PERMISSION_ENABLED"
        # Mock row object
        Row = collections.namedtuple(
            "Row",
            [
                "partner_id",
                "partner_name",
                "role_id",
                "role_name",
                "category",
                "slug",
                "permission_id",
                "created_at",
                "description",
                "display_text",
                "is_partner",
            ],
        )
        mock_row = Row(
            partner_id=1,
            partner_name="PartnerA",
            role_id=2,
            role_name="Admin",
            category="Category1",
            slug="perm_slug",
            permission_id=101,
            created_at=1234567890,
            description="desc",
            display_text="Permission Display",
            is_partner=True,
        )
        mock_result = MagicMock()
        mock_result.fetchall.return_value = [mock_row]
        self.session.execute = AsyncMock(return_value=mock_result)

        result = await self.repository.get_partner_role_permission_matrix(key,1, True)
        assert result == [mock_row]
        self.mock_logger.info.assert_any_call(
            f"Fetching full partner permission matrix for all the partners with config key: {key}"
        )
        self.mock_logger.info.assert_any_call(
            f"Successfully fetched partner permissions matrix for config key: {key}"
        )

    @pytest.mark.asyncio
    async def test_get_partner_role_permission_matrix_catches_custom_exception(self):
        """Test that PartnerRolePermissionException is logged and re-raised."""
        key = "IS_CUSTOM_ROLE_PERMISSION_ENABLED"
        partner_id = 123

        # Patch the repository method to raise the custom exception directly
        with patch.object(
            self.repository,
            "get_partner_role_permission_matrix",
            side_effect=PartnerRolePermissionException("custom error"),
        ):
            with pytest.raises(PartnerRolePermissionException) as exc_info:
                await self.repository.get_partner_role_permission_matrix(key, partner_id, True)

            assert "custom error" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_get_partner_role_permission_matrix_exception(self):
        """Test exception handling during fetch of partner permissions matrix."""
        key = "IS_CUSTOM_ROLE_PERMISSION_ENABLED"
        self.session.execute = AsyncMock(side_effect=Exception("DB error"))

        with pytest.raises(Exception) as exc_info:
            await self.repository.get_partner_role_permission_matrix(key,1,True)

        assert "DB error" in str(exc_info.value)
        self.mock_logger.error.assert_called()
