from uuid import UUID
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.components.audit_log.schema import AuditLogSchema
from src.components.common.constants import CurrentUserMap
from src.components.default_role_permission.models import DefaultRolePermission
from src.components.default_role_permission.schemas import (
    DefaultRolePermissionData,
    DefaultRolePermissionResponse,
)
from src.components.default_role_permission.services import DefaultRolePermissionService
from src.exceptions import PartnerRolePermissionException


@pytest.mark.asyncio
class TestDefaultRolePermissionService:

    @pytest.fixture(autouse=True)
    def setup(self, mock_logger):
        """Set up the service with mocked dependencies."""
        self.audit_service_mock = AsyncMock()
        self.logger_mock = mock_logger
        self.default_role_permission_repository_mock = AsyncMock()
        self.partner_config_service_mock = AsyncMock()

        self.partner_role_perm_service_mock = DefaultRolePermissionService(
            audit_service=self.audit_service_mock,
            console_service_logger=self.logger_mock,
            default_role_permission_repository=self.default_role_permission_repository_mock,
            partner_config_service=self.partner_config_service_mock,
        )

    async def test_add_default_role_permission_success(self): 
        add_data = DefaultRolePermissionData(role_id= UUID("11111111-1111-1111-1111-111111111111"), permission_id= UUID("22222222-2222-2222-2222-222222222222"))
        current_user = {CurrentUserMap.USER_ID: UUID("12312312-3123-1231-2312-312312312312")}
        mock_result = MagicMock(spec=DefaultRolePermission)
        mock_result.id = 10
        self.default_role_permission_repository_mock.add_default_role_permission.return_value = (
            mock_result
        )
        auth_service_mock = AsyncMock()
        auth_service_mock.get_role_by_id.return_value = MagicMock(is_internal=True)
        auth_service_mock.get_permission_by_id.return_value = MagicMock(is_internal=False)

        result = await self.partner_role_perm_service_mock.add_default_role_permission(
            add_data, current_user, auth_service=auth_service_mock
        )

        self.logger_mock.info.assert_any_call(
            "Inserting new entry in Default Role Permission table for role id: {} and permission id: {}".format(
                add_data.role_id, add_data.permission_id
            )
        )
        self.logger_mock.info.assert_any_call(
            "Successfully inserted mapping in db for role id: {} and permission id: {}".format(
                add_data.role_id, add_data.permission_id
            )
        )
        self.audit_service_mock.log_action.assert_awaited_once()
        assert result == mock_result

    async def test_add_default_role_permission_partner_exception(self):
        add_data = DefaultRolePermissionData(role_id= UUID("11111111-1111-1111-1111-111111111111"), permission_id= UUID("22222222-2222-2222-2222-222222222222"))
        current_user = {CurrentUserMap.USER_ID: UUID("12312312-3123-1231-2312-312312312312")}
        self.default_role_permission_repository_mock.add_default_role_permission.side_effect = PartnerRolePermissionException(
            "error"
        )
        auth_service_mock = AsyncMock()
        auth_service_mock.get_role_by_id.return_value = MagicMock(is_internal=True)
        auth_service_mock.get_permission_by_id.return_value = MagicMock(is_internal=False)

        with pytest.raises(PartnerRolePermissionException):
            await self.partner_role_perm_service_mock.add_default_role_permission(
                add_data, current_user, auth_service=auth_service_mock
            )
        self.logger_mock.error.assert_called()

    async def test_add_default_role_permission_general_exception(self):
        add_data = DefaultRolePermissionData(role_id= UUID("11111111-1111-1111-1111-111111111111"), permission_id= UUID("22222222-2222-2222-2222-222222222222"))
        current_user = {CurrentUserMap.USER_ID: UUID("12312312-3123-1231-2312-312312312312")}
        self.default_role_permission_repository_mock.add_default_role_permission.side_effect = Exception(
            "db error"
        )

        with pytest.raises(Exception):   #NOSONAR
            await self.partner_role_perm_service_mock.add_default_role_permission(
                add_data, current_user
            )
        self.logger_mock.error.assert_called()

    async def test_get_default_role_permissions_success(self):
        current_user = {CurrentUserMap.PARTNER_ID: 1}
        mock_db_result = [MagicMock(), MagicMock()]
        self.default_role_permission_repository_mock.get_default_role_permissions.return_value = (
            mock_db_result
        )
        self.partner_config_service_mock.get_partner_config_by_key.return_value = None

        # Patch DefaultRolePermissionResponse.model_validate to just return the input for simplicity
        with pytest.MonkeyPatch.context() as m:
            m.setattr(
                DefaultRolePermissionResponse,
                "model_validate",
                staticmethod(lambda x: x),
            )
            result = (
                await self.partner_role_perm_service_mock.get_default_role_permissons(
                    current_user
                )
            )
            assert result == mock_db_result
            self.logger_mock.info.assert_called_with(
                "Fetching default role permissions..."
            )

    async def test_get_default_role_permissions_error(self):
        current_user = {CurrentUserMap.PARTNER_ID: 1}
        self.partner_config_service_mock.get_partner_config_by_key.return_value = None
        self.default_role_permission_repository_mock.get_default_role_permissions.side_effect = Exception(
            "db error"
        )
        with pytest.raises(Exception):    #NOSONAR
            await self.partner_role_perm_service_mock.get_default_role_permissons(
                current_user
            )
        self.logger_mock.error.assert_called()

    async def test_get_default_role_permissions_by_role_id_success(self):
        mock_db_result = [MagicMock(), MagicMock()]
        self.default_role_permission_repository_mock.get_default_role_permissions_by_role_id.return_value = (
            mock_db_result
        )

        with pytest.MonkeyPatch.context() as m:
            m.setattr(
                DefaultRolePermissionResponse,
                "model_validate",
                staticmethod(lambda x: x),
            )
            result = await self.partner_role_perm_service_mock.get_default_role_permissons_by_role_id(
                1
            )
            assert result == mock_db_result
            self.logger_mock.info.assert_called_with(
                "Fetching default role permissions by role id: {}".format(1)
            )

    async def test_get_default_role_permissions_by_role_id_error(self):
        self.default_role_permission_repository_mock.get_default_role_permissions_by_role_id.side_effect = Exception(
            "db error"
        )
        with pytest.raises(Exception):    #NOSONAR
            await self.partner_role_perm_service_mock.get_default_role_permissons_by_role_id(
                1
            )
        self.logger_mock.error.assert_called()
