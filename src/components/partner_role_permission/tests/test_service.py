import pytest
import collections
from src.components.auth.constant import PermissionAttributes
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.components.audit_log.schema import AuditLogSchema
from src.components.partner.models import Partner
from src.components.partner_config.constants import PartnerConfigEnum
from src.components.partner_config.schemas import PartnerConfigResponse
from src.components.partner_role_permission.models import PartnerRolePermission
from src.components.partner_role_permission.schema import PartnerPermissionData
from src.components.partner_role_permission.service import PartnerPermissionService
from src.exceptions import PartnerRolePermissionException,PartnerConfigException, PartnerException


@pytest.mark.asyncio
class TestPartnerPermissionService:

    @pytest.fixture(autouse=True)
    def setup(self, mock_logger):
        """Set up the service with mocked dependencies."""
        self.audit_service_mock = AsyncMock()
        self.logger_mock = mock_logger
        self.partner_perm_repository_mock = AsyncMock()
        self.cache_helper_mock = AsyncMock()

        self.partner_role_perm_service_mock = PartnerPermissionService(
            audit_service=self.audit_service_mock,
            console_service_logger=self.logger_mock,
            partner_perm_repository=self.partner_perm_repository_mock,
            cache_helper=self.cache_helper_mock,
        )

        self.add_data = PartnerPermissionData(partner_id=1, role_id=2, permission_id=3)

        # Mock data
        self.partner_permission_data = PartnerPermissionData(
            partner_id=1, role_id=2, permission_id=3
        )
        self.current_user = {"id": None}
        self.partner_role_permission = PartnerRolePermission(
            id=1, partner_id=1, role_id=2, permission_id=3
        )

    async def test_add_partner_permission(self):
        # Mock repository, audit service, and partner config service
        self.partner_perm_repository_mock.add_partner_permission.return_value = (
            self.partner_role_permission
        )
        self.audit_service_mock.log_action = AsyncMock()
        partner_config_service_mock = AsyncMock()

        partner_config_service_mock.get_partner_config_by_key.return_value = (
            PartnerConfigResponse(
                key=PartnerConfigEnum.IS_CUSTOM_ROLE_PERMISSION_ENABLED,
                value=True,
                created_at=17007654321,
            )
        )
        partner_service_mock = AsyncMock()
        partner_service_mock.get_partner_by_id.return_value = MagicMock(
            is_internal=False
        )
        role_service_mock = AsyncMock()
        role_service_mock.get_role_by_id.return_value = MagicMock(is_internal=False)

        # Update current_user to include required keys
        self.current_user = {"user_id": 42, "partner_id": 1}

        # Call the method
        result = await self.partner_role_perm_service_mock.add_partner_permission(
            add_data=self.partner_permission_data,
            current_user=self.current_user,
            partner_config_service=partner_config_service_mock,
            partner_service=partner_service_mock,
            role_service=role_service_mock,
        )

        # Assertions
        assert result == self.partner_role_permission
        self.partner_perm_repository_mock.add_partner_permission.assert_called_once_with(
            self.partner_permission_data, self.current_user["user_id"]
        )
        self.audit_service_mock.log_action.assert_called_once()
        self.logger_mock.info.assert_called()
        partner_config_service_mock.get_partner_config_by_key.assert_called_once_with(
            self.current_user["partner_id"],
            PartnerConfigEnum.IS_CUSTOM_ROLE_PERMISSION_ENABLED,
        )
        # Granting a permission must bust maglo's per-user RBAC cache.
        self.cache_helper_mock.invalidate_user_permissions_cache.assert_awaited_once()

    async def test_get_partner_role_permission(self):
        # Mock repository response
        self.partner_perm_repository_mock.get_all_partner_role_permission.return_value = [
            self.partner_role_permission
        ]

        # Call the method
        result = await self.partner_role_perm_service_mock.get_partner_role_permission()

        # Assertions
        assert list(result) == [self.partner_role_permission]
        self.partner_perm_repository_mock.get_all_partner_role_permission.assert_called_once()
        self.logger_mock.info.assert_called()

    async def test_get_partner_role_permission_by_id(self):
        # Mock repository response
        self.partner_perm_repository_mock.get_partner_role_permission_by_id.return_value = (
            self.partner_role_permission
        )

        # Call the method
        result = (
            await self.partner_role_perm_service_mock.get_partner_role_permission_by_id(
                1
            )
        )

        # Assertions
        assert result == self.partner_role_permission
        self.partner_perm_repository_mock.get_partner_role_permission_by_id.assert_called_once_with(
            1
        )
        self.logger_mock.info.assert_called()

    async def test_get_by_partner_id(self):
        # Mock repository response
        self.partner_perm_repository_mock.get_by_partner_id.return_value = [
            self.partner_role_permission
        ]

        # Call the method
        result = await self.partner_role_perm_service_mock.get_by_partner_id(1)

        # Assertions
        assert list(result) == [self.partner_role_permission]
        self.partner_perm_repository_mock.get_by_partner_id.assert_called_once_with(1)
        self.logger_mock.info.assert_called()

    async def test_delete_partner_role_permission(self):
        # Mock repository and audit partner_role_perm_service_mock
        self.partner_perm_repository_mock.delete_partner_role_permission = AsyncMock()
        self.audit_service_mock.log_action = AsyncMock()

        # Call the method
        await self.partner_role_perm_service_mock.delete_partner_role_permission(
            1, self.current_user
        )

        # Assertions
        self.partner_perm_repository_mock.delete_partner_role_permission.assert_called_once_with(
            1
        )
        self.audit_service_mock.log_action.assert_called_once()
        self.logger_mock.info.assert_called()

    async def test_add_partner_permission_raises_exception(self):
        # Setup mock to raise an exception
        self.partner_perm_repository_mock.add_partner_permission.side_effect = (
            PartnerRolePermissionException("Error")
        )
        partner_config_service_mock = AsyncMock()
        partner_config_service_mock.get_partner_config_by_key.return_value = (
            PartnerConfigResponse(
                key=PartnerConfigEnum.IS_CUSTOM_ROLE_PERMISSION_ENABLED,
                value=True,
                created_at=17007654321,
            )
        )
        partner_service_mock = AsyncMock()
        partner_service_mock.get_partner_by_id.return_value = MagicMock(
            is_internal=False
        )
        role_service_mock = AsyncMock()
        role_service_mock.get_role_by_id.return_value = MagicMock(is_internal=False)

        # Update current_user to include required keys
        self.current_user = {"user_id": 42, "partner_id": 1}

        # Call the method and expect an exception
        with pytest.raises(PartnerRolePermissionException):
            await self.partner_role_perm_service_mock.add_partner_permission(
                add_data=self.partner_permission_data,
                current_user=self.current_user,
                partner_config_service=partner_config_service_mock,
                partner_service=partner_service_mock,
                role_service=role_service_mock,
            )

        # Assertions
        self.partner_perm_repository_mock.add_partner_permission.assert_called_once_with(
            self.partner_permission_data, self.current_user["user_id"]
        )
        self.logger_mock.error.assert_called()

    async def test_get_partner_role_permission_by_id_raises_exception(self):
        # Setup mock to raise an exception
        self.partner_perm_repository_mock.get_partner_role_permission_by_id.side_effect = PartnerRolePermissionException(
            "Error"
        )

        # Call the method and expect an exception
        with pytest.raises(PartnerRolePermissionException):
            await self.partner_role_perm_service_mock.get_partner_role_permission_by_id(
                1
            )

        # Assertions
        self.partner_perm_repository_mock.get_partner_role_permission_by_id.assert_called_once_with(
            1
        )
        self.logger_mock.error.assert_called()

    async def test_delete_partner_role_permission_raises_exception(self):
        # Setup mock to raise an exception
        self.partner_perm_repository_mock.delete_partner_role_permission.side_effect = (
            PartnerRolePermissionException("Error")
        )

        # Call the method and expect an exception
        with pytest.raises(PartnerRolePermissionException):
            await self.partner_role_perm_service_mock.delete_partner_role_permission(
                1, current_user=1
            )

        # Assertions
        self.partner_perm_repository_mock.delete_partner_role_permission.assert_called_once_with(
            1
        )
        self.logger_mock.error.assert_called()

    async def test_add_partner_permission_general_exception(self):

        self.partner_perm_repository_mock.add_partner_permission.side_effect = (
            Exception("Some unexpected error")
        )

        with pytest.raises(Exception):
            await self.partner_role_perm_service_mock.add_partner_permission(
                add_data=self.partner_permission_data, current_user=self.current_user
            )

    async def test_get_partner_role_permission_by_id_general_exception(self):

        self.partner_perm_repository_mock.get_partner_role_permission_by_id.side_effect = Exception(
            "Some unexpected error"
        )

        with pytest.raises(Exception):
            await self.partner_role_perm_service_mock.get_partner_role_permission_by_id(
                id=1
            )

    async def test_get_by_partner_id_general_exception(self):

        self.partner_perm_repository_mock.get_by_partner_id.side_effect = Exception(
            "Some unexpected error"
        )

        with pytest.raises(Exception):
            await self.partner_role_perm_service_mock.get_by_partner_id(id=1)

    async def test_delete_partner_role_permission_general_exception(self):

        self.partner_perm_repository_mock.delete_partner_role_permission.side_effect = (
            Exception("Some unexpected error")
        )

        with pytest.raises(Exception):
            await self.partner_role_perm_service_mock.delete_partner_role_permission(
                1, self.current_user
            )

    async def test_get_all_partner_permission_general_exception(self):

        self.partner_perm_repository_mock.get_all_partner_role_permission.side_effect = Exception(
            "Some unexpected error"
        )

        with pytest.raises(Exception):
            await self.partner_role_perm_service_mock.get_partner_role_permission()

    async def test_get_by_partner_id_partner_role_perm_exception(self):

        self.partner_perm_repository_mock.get_by_partner_id.side_effect = (
            PartnerRolePermissionException("Some unexpected error")
        )

        with pytest.raises(PartnerRolePermissionException):
            await self.partner_role_perm_service_mock.get_by_partner_id(1)

    async def test_add_partner_permission_custom_permission_disabled(self):
        partner_config_service_mock = AsyncMock()
        partner_config_service_mock.get_partner_config_by_key.return_value = (
            PartnerConfigResponse(
                key=PartnerConfigEnum.IS_CUSTOM_ROLE_PERMISSION_ENABLED,
                value=False,
                created_at=17007654321,
            )
        )

        self.current_user = {"user_id": 42, "partner_id": 1}
        partner_service_mock = AsyncMock()
        partner_service_mock.get_partner_by_id.return_value = MagicMock(
            is_internal=False
        )
        role_service_mock = AsyncMock()
        role_service_mock.get_role_by_id.return_value = MagicMock(is_internal=False)

        with pytest.raises(PartnerRolePermissionException):
            await self.partner_role_perm_service_mock.add_partner_permission(
                add_data=self.partner_permission_data,
                current_user=self.current_user,
                partner_config_service=partner_config_service_mock,
                partner_service=partner_service_mock,
                role_service=role_service_mock,
            )

        partner_config_service_mock.get_partner_config_by_key.assert_called_once_with(
            self.current_user["partner_id"],
            PartnerConfigEnum.IS_CUSTOM_ROLE_PERMISSION_ENABLED,
        )
        self.logger_mock.error.assert_called()

    @pytest.mark.asyncio
    async def test_get_partner_permissions_matrix_by_config_success(self):
        # Create mock row returned by repository
        Row = collections.namedtuple(
            "Row",
            [
                "partner_name",
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
            partner_name="PartnerA",
            role_name="Admin",
            category="Category1",
            slug="perm_slug",
            permission_id=101,
            created_at=1234567890,
            description="desc",
            display_text="Permission Display",
            is_partner=True,
        )

        # Mock partner object with is_internal = True
        mock_partner = AsyncMock(spec=Partner)
        mock_partner.is_internal = True

        # Mock partner service
        mock_partner_service = AsyncMock()
        mock_partner_service.get_partner_by_id.return_value = mock_partner

        # Mock partner config service
        mock_partner_config_service = AsyncMock()
        mock_partner_config_service.get_partner_config_by_key.return_value = PartnerConfigResponse(
            key=PartnerConfigEnum.IS_CUSTOM_ROLE_PERMISSION_ENABLED,
            value=True,
            created_at=17007654321,
        )

        # Mock repository method
        self.partner_perm_repository_mock.get_partner_role_permission_matrix.return_value = [mock_row]

        # Call the method under test
        result = await self.partner_role_perm_service_mock.get_partner_permissions_matrix_by_config(
            partner_id=1,
            partner_config_service=mock_partner_config_service,
            partner_service=mock_partner_service,
        )

        # Assertions
        assert "PartnerA" in result
        assert "Admin" in result["PartnerA"]
        assert "Category1" in result["PartnerA"]["Admin"]
        assert "perm_slug" in result["PartnerA"]["Admin"]["Category1"]

        perm = result["PartnerA"]["Admin"]["Category1"]["perm_slug"]
        assert perm[PermissionAttributes.ID] == 101
        assert perm[PermissionAttributes.CREATED_AT] == 1234567890
        assert perm[PermissionAttributes.DESCRIPTION] == "desc"
        assert perm[PermissionAttributes.DISPLAY_TEXT] == "Permission Display"
        assert perm[PermissionAttributes.IS_ACTIVE] is True

        self.logger_mock.info.assert_any_call(
            "Building permission matrix for partners having custom role permissions enabled"
        )
        self.logger_mock.info.assert_any_call(f"Successfully built partner permissions matrix: {result}")

    @pytest.mark.asyncio
    async def test_get_partner_permissions_matrix_by_config_partner_config_exception(self):
        """Should raise exception when partner config is None or value is False."""

        # Mock partner object with is_internal = False or True, doesn't matter here
        mock_partner = AsyncMock(spec=Partner)
        mock_partner.is_internal = True

        # Mock partner_service
        mock_partner_service = AsyncMock()
        mock_partner_service.get_partner_by_id.return_value = mock_partner

        # CASE 1: Config is None
        partner_config_service_mock_none = AsyncMock()
        partner_config_service_mock_none.get_partner_config_by_key.return_value = None

        with pytest.raises(PartnerConfigException):
            await self.partner_role_perm_service_mock.get_partner_permissions_matrix_by_config(
                partner_id=1,
                partner_service=mock_partner_service,
                partner_config_service=partner_config_service_mock_none,
            )

        partner_config_service_mock_none.get_partner_config_by_key.assert_called_once_with(
            1, PartnerConfigEnum.IS_CUSTOM_ROLE_PERMISSION_ENABLED.value
        )
        self.logger_mock.error.assert_called()

        # CASE 2: Config.value is False
        partner_config_service_mock_false = AsyncMock()
        partner_config_service_mock_false.get_partner_config_by_key.return_value = AsyncMock(
            value=False
        )

        with pytest.raises(PartnerConfigException):
            await self.partner_role_perm_service_mock.get_partner_permissions_matrix_by_config(
                partner_id=1,
                partner_service=mock_partner_service,
                partner_config_service=partner_config_service_mock_false,
            )

        partner_config_service_mock_false.get_partner_config_by_key.assert_called_with(
            1, PartnerConfigEnum.IS_CUSTOM_ROLE_PERMISSION_ENABLED.value
        )
        self.logger_mock.error.assert_called()

    @pytest.mark.asyncio
    async def test_get_partner_permissions_matrix_by_config_partner_exception(self):
        # Mock partner_service to raise PartnerException
        mock_partner_service = AsyncMock()
        mock_partner_service.get_partner_by_id.side_effect = PartnerException("Partner not found")

        # Mock partner_config_service (won't be called)
        mock_partner_config_service = AsyncMock()

        with pytest.raises(PartnerRolePermissionException) as exc_info:
            await self.partner_role_perm_service_mock.get_partner_permissions_matrix_by_config(
                partner_id=1,
                partner_service=mock_partner_service,
                partner_config_service=mock_partner_config_service,
            )

        assert str(exc_info.value) == "Partner does not exist or is inactive."
        self.logger_mock.error.assert_called_with(
            "Error fetching partner details: Partner not found"
        )

    @pytest.mark.asyncio
    async def test_get_partner_permissions_matrix_by_config_exception(self):
        self.partner_perm_repository_mock.get_partner_role_permission_matrix.side_effect = Exception("DB error")
        mock_partner_service = AsyncMock()
        mock_partner_service.get_partner_by_id.side_effect = MagicMock(is_internal=False)
        with pytest.raises(Exception):
            await self.partner_role_perm_service_mock.get_partner_permissions_matrix_by_config(
                partner_id=1,
                is_internal_permission=True,
                partner_service=mock_partner_service,
            )
        self.logger_mock.error.assert_called()