from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from asyncpg.exceptions import UniqueViolationError
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from src.components.auth.models import Permission, Role
from src.components.default_role_permission.models import DefaultRolePermission
from src.components.default_role_permission.repositories import (
    DefaultRolePermissionRepository,
)
from src.components.default_role_permission.schemas import DefaultRolePermissionData
from src.exceptions import DefaultRolePermissionException
from src.components.partner_role_permission.constant import ExceptionMsg


@pytest.mark.asyncio
class TestDefaultRolePermissionRepository:

    @pytest.fixture(autouse=True)
    def setup_class(self, mock_session_factory, mock_logger):
        """Set up the PartnerPermissionRepository using fixtures for mock session and logger."""
        self.repository = DefaultRolePermissionRepository(
            session_factory=mock_session_factory, console_service_logger=mock_logger
        )
        self.session = mock_session_factory.return_value.__aenter__.return_value
        self.mock_logger = mock_logger

        self.mock_default_role_permission = DefaultRolePermission(
            id=1,
            role_id=1,
            permission_id=2
        )

    async def test_add_default_role_permission_success(self):
        add_data = DefaultRolePermissionData(role_id=1, permission_id=2)
        user_id = 123

        # Mock permission and role existence
        mock_result = MagicMock()
        mock_result.fetchone.return_value = MagicMock(
            permission_exists=True, role_exists=True
        )
        self.session.execute = AsyncMock(return_value=mock_result)
        self.session.commit = AsyncMock()
        self.session.refresh = AsyncMock()

        result = await self.repository.add_default_role_permission(add_data, user_id)

        assert result.role_id == add_data.role_id
        assert result.permission_id == add_data.permission_id
        assert result.created_by == user_id
        self.mock_logger.info.assert_called_with(
            "Successfully inserted mapping in db for role id: {} and permission id: {}".format(
                result.role_id, result.permission_id
            )
        )

    async def test_add_default_role_permission_permission_not_found(self):
        add_data = DefaultRolePermissionData(role_id=1, permission_id=99)
        user_id = 123

        mock_result = MagicMock()
        mock_result.fetchone.return_value = MagicMock(
            permission_exists=False, role_exists=True
        )
        self.session.execute = AsyncMock(return_value=mock_result)

        with pytest.raises(DefaultRolePermissionException) as exc_info:
            await self.repository.add_default_role_permission(add_data, user_id)
        assert "Permission does not exist or is inactive." in str(exc_info.value)

    async def test_add_default_role_permission_role_not_found(self):
        add_data = DefaultRolePermissionData(role_id=99, permission_id=1)
        user_id = 123

        mock_result = MagicMock()
        mock_result.fetchone.return_value = MagicMock(
            permission_exists=True, role_exists=False
        )
        self.session.execute = AsyncMock(return_value=mock_result)

        with pytest.raises(DefaultRolePermissionException) as exc_info:
            await self.repository.add_default_role_permission(add_data, user_id)
        assert "Role does not exist or is inactive." in str(exc_info.value)

    async def test_add_default_role_permission_unique_violation(self):
        add_data = DefaultRolePermissionData(role_id=1, permission_id=2)
        user_id = 123

        # Mock permission and role existence
        mock_result = MagicMock()
        mock_result.fetchone.return_value = MagicMock(
            permission_exists=True, role_exists=True
        )
        self.session.execute = AsyncMock(return_value=mock_result)
        self.session.commit = AsyncMock(
            side_effect=UniqueViolationError("Duplicate entry")
        )

        with pytest.raises(DefaultRolePermissionException) as exc_info:
            await self.repository.add_default_role_permission(add_data, user_id)
        assert "Duplicate entry" in str(exc_info.value)

    async def test_add_default_role_permission_integrity_error(self):
        add_data = DefaultRolePermissionData(role_id=1, permission_id=2)
        user_id = 123

        # Mock permission and role existence
        mock_result = MagicMock()
        mock_result.fetchone.return_value = MagicMock(
            permission_exists=True, role_exists=True
        )
        self.session.execute = AsyncMock(return_value=mock_result)
        self.session.commit = AsyncMock(
            side_effect=IntegrityError("Integrity error", {}, None)
        )

        with pytest.raises(DefaultRolePermissionException) as exc_info:
            await self.repository.add_default_role_permission(add_data, user_id)
        assert "A record with this combination already exists." in str(exc_info.value)

    async def test_add_default_role_permission_general_exception(self):
        add_data = DefaultRolePermissionData(role_id=1, permission_id=2)
        user_id = 123

        self.session.execute = AsyncMock(side_effect=Exception("Unexpected error"))

        with pytest.raises(Exception) as exc_info:
            await self.repository.add_default_role_permission(add_data, user_id)
        assert "Unexpected error" in str(exc_info.value)

    async def test_get_default_role_permissions_success(self):
        # Arrange
        mock_result = MagicMock()
        self.session.execute = AsyncMock(return_value=mock_result)

        # Act
        result = await self.repository.get_default_role_permissions()

        # Assert
        self.session.execute.assert_awaited_once()
        self.mock_logger.info.assert_any_call(
            "getting all the default role permissions mappings..."
        )
        self.mock_logger.info.assert_any_call(
            f"The default role permissions fetched successfully: {mock_result}"
        )
        assert result == mock_result

    async def test_get_default_role_permissions_db_error(self):
        # Arrange
        self.session.execute = AsyncMock(side_effect=Exception("DB error"))

        # Act & Assert
        with pytest.raises(Exception) as exc_info:
            await self.repository.get_default_role_permissions()
        self.mock_logger.error.assert_called()
        assert "DB error" in str(exc_info.value)

    async def test_get_default_role_permissions_by_role_id_success(self):
        # Arrange
        role_id = 1
        mock_result = MagicMock()
        mock_rows = MagicMock()
        mock_result.fetchall.return_value = mock_rows
        self.session.execute = AsyncMock(return_value=mock_result)

        # Act
        result = await self.repository.get_default_role_permissions_by_role_id(role_id)

        # Assert
        self.session.execute.assert_awaited_once()
        self.mock_logger.info.assert_any_call(
            f"getting all the default role permissions mappings by role id: {role_id}"
        )
        assert result == mock_rows

    async def test_get_default_role_permissions_by_role_id_db_error(self):
        # Arrange
        role_id = 1
        self.session.execute = AsyncMock(side_effect=Exception("DB error"))

        # Act & Assert
        with pytest.raises(Exception) as exc_info:
            await self.repository.get_default_role_permissions_by_role_id(role_id)
        self.mock_logger.error.assert_called()
        assert "DB error" in str(exc_info.value)

    async def test_delete_default_role_permission_success(self):
        default_role_permission_id = 1

        # Mock .execute().scalar_one_or_none() to return the permission
        mock_scalars = MagicMock()
        mock_scalars.scalar_one_or_none.return_value = self.mock_default_role_permission
        self.session.execute = AsyncMock(return_value=mock_scalars)

        self.session.delete = AsyncMock()
        self.session.commit = AsyncMock()

        await self.repository.delete_default_role_permission(default_role_permission_id)

        self.session.execute.assert_awaited_once()
        self.session.commit.assert_awaited_once()
        self.mock_logger.info.assert_any_call(
            f"Successfully deleted default role permission with id: {default_role_permission_id}"
        )

    async def test_delete_default_role_permission_not_found(self):
        default_role_permission_id = 999

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        self.session.execute = AsyncMock(return_value=mock_result)

        with pytest.raises(DefaultRolePermissionException) as exc:
            await self.repository.delete_default_role_permission(default_role_permission_id)

        assert str(exc.value) == ExceptionMsg.DEFAULT_ROLE_PERMISSION_NOT_FOUND
        self.mock_logger.error.assert_called_with(ExceptionMsg.DEFAULT_ROLE_PERMISSION_NOT_FOUND)

    async def test_delete_default_role_permission_unexpected_error(self):
        default_role_permission_id = 1

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.side_effect = SQLAlchemyError("DB error")
        self.session.execute = AsyncMock(return_value=mock_result)

        with pytest.raises(SQLAlchemyError):
            await self.repository.delete_default_role_permission(default_role_permission_id)

        self.mock_logger.error.assert_called()
