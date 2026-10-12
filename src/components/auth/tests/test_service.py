from uuid import UUID
from unittest.mock import AsyncMock, MagicMock, PropertyMock, patch

import pytest
from fastapi import Request
from pydantic import ValidationError

from src.components.auth.constant import AuthExceptionMsg, AuthSuccessMsg, ServiceNames, SvcFlagMap, TokenKeys
from src.components.auth.error import PermissionNotFoundError, RoleNotFoundError
from src.components.auth.permission_mapper import PermissionCategories
from src.components.auth.schema import (
    LoginData,
    PermissionData,
    PermissionResponse,
    ResetPasswordRequest,
    RoleData,
    RoleResponse,
    UpdatePermissionResponse,
    UpdatePermissionRquest,
    UserData,
    UserDataResponse,
    UserBase
)
from src.components.auth.service import AuthService
from src.components.common.constants import CurrentUserMap
from src.components.partner.error import PartnerNotFoundError
from src.components.partner_config.constants import PartnerConfigEnum
from src.components.partner_config.schemas import PartnerConfigResponse
from src.components.user.errors import UserNotFoundError
from src.components.user.schema import Contrasts
from src.exceptions import AuthException, PartnerException
from src.components.auth.dto import ServiceAccessDTO
from src.components.common.datetime import DateTimeUtil
from datetime import timedelta

@pytest.mark.asyncio
class TestAuthService:

    @pytest.fixture(autouse=True)
    def setup_class(self, mock_logger, redis_mock):

        self.auth_repository_mock = AsyncMock()
        self.mock_logger = mock_logger
        self.redis_mock = redis_mock
        self.user_repository_mock = AsyncMock()
        self.partner_repository_mock = AsyncMock()
        self.audit_log_mock = AsyncMock()
        self.user_session_service = AsyncMock()
        self.auth_utility_mock = MagicMock()
        self.auth_utility_mock.verify_password = AsyncMock()
        self.auth_utility_mock.get_password_hash = AsyncMock()
        self.auth_utility_mock.create_access_token = AsyncMock()
        self.auth_utility_mock.get_current_user = AsyncMock()

        self.auth_service = AuthService(
            auth_repository=self.auth_repository_mock,
            auth_service_logger=self.mock_logger,
            auth_service_cache=self.redis_mock,
            auth_service_utility=self.auth_utility_mock,
            user_session_service=self.user_session_service,
            audit_service=self.audit_log_mock,
        )

        # Test data
        self.role_list_mock = [MagicMock(title="admin"), MagicMock(title="user")]

        self.role_mock = RoleData(
            name="admin",
            slug="admin",
            hierarchy=1,
            description="admin can have all access",
        )

        self.permission_mock = PermissionData(
            title="edit", slug="talko_admin_view", description="admin can edit"
        )

        self.current_user_mock = {"user_id": UUID("11111111-1111-1111-1111-111111111111")}

        self.login_data = LoginData(
            credential="mockuser@gmail.com", password="password"
        )

        self.user_data = UserData(
            username="newuser@example.com",
            email="newuser@example.com",
            password="Password@1234",
            phone_number="+911234567890",
            name="New User",
            designation="Developer",
            partner_id= UUID("11111111-1111-1111-1111-111111111111"),
            role_id= UUID("11111111-1111-1111-1111-111111111111"),
            parent_id=None,
        )

        self.permission_response = PermissionResponse(
            id= UUID("11111111-1111-1111-1111-111111111111"),
            title="edit",
            slug="talko_admin_view",
            description="admin can edit",
            is_active=True,
            is_deleted=False,
        )

        self.role_response = RoleResponse(
            id= UUID("11111111-1111-1111-1111-111111111111"),
            name="Admin",
            slug="admin",
            hierarchy=1,
            description="Administrator role with all permissions",
            is_active=True,
            is_deleted=False,
            created_by= UUID("10011001-1001-1001-1001-100110011001"),
            updated_by= UUID("10021002-1002-1002-1002-100210021002"),
            deleted_by=None,
        )

        self.user_response = UserDataResponse(
            id= UUID("11111111-1111-1111-1111-111111111111"),
            email="newuser@example.com",
            password="password",
            phone_number="+911234567890",
            name="New User",
            designation="Developer",
            partner_id= UUID("11111111-1111-1111-1111-111111111111"),
            role_id= UUID("11111111-1111-1111-1111-111111111111"),
            parent_id=None,
        )

    def _prepare_get_token_mocks(self, partner_config_service):
        """Shared scaffolding for get_token() happy-path tests."""
        user_mock = AsyncMock()
        user_mock.id = UUID("11111111-1111-1111-1111-111111111111")
        user_mock.name = "testuser"
        user_mock.partner_id= UUID("11111111-1111-1111-1111-111111111111")
        user_mock.is_internal = False

        user_config_service = AsyncMock()
        user_config_service.get_user_configs_by_user_id.return_value = [
            {"key": "is_talko_enabled", "value": False},
            {"key": "is_obotaai_enabled", "value": False},
            {"key": "is_talko_enabled", "value": False},
        ]

        user_session_mock = AsyncMock()
        user_session_mock.is_active = True
        self.user_session_service.create_user_session.return_value = user_session_mock

        self.auth_utility_mock.create_access_token.return_value = "mocked_access_token"
        self.auth_service._AuthService__auth_service_cache.set_cache = AsyncMock(
            return_value=True
        )
        self.auth_service.resolve_user_walkthrough_key = AsyncMock(return_value=None)

        request_mock = AsyncMock(spec=Request)
        request_mock.headers = {"User-Agent": "test-agent"}
        request_mock.client = MagicMock()
        request_mock.client.host = "127.0.0.1"
        partner_service = AsyncMock()
        partner_service.get_partner_by_id.return_value = {"is_active": True}

        # Mock `_get_user` to return user_mock explicitly to prevent real service call raising
        self.auth_service._get_user = AsyncMock(return_value=user_mock)
        
        partner_config_service.get_partner_configs_by_partner_id.return_value = [
            PartnerConfigResponse(
                key=PartnerConfigEnum.IS_OTP_ENABLED.value,
                value=False,
                partner_id= UUID("11111111-1111-1111-1111-111111111111"),
            ),
            PartnerConfigResponse(
                key=PartnerConfigEnum.IS_TALKO_ENABLED.value,
                value=False,
                partner_id= UUID("11111111-1111-1111-1111-111111111111"),
            ),
            PartnerConfigResponse(
                key=PartnerConfigEnum.IS_OBOTAAI_ENABLED.value,
                value=True,
                partner_id= UUID("11111111-1111-1111-1111-111111111111"),
            ),
        ]

        
        return dict(
            request=request_mock,
            login_data=self.login_data,
            user_config_service=user_config_service,
            partner_config_service=partner_config_service,
            partner_service=partner_service,
        )

    @pytest.mark.asyncio
    async def test_get_token_success(self):
        partner_config_service = AsyncMock()
        partner_config_service.get_partner_config_by_key.return_value = (
            PartnerConfigResponse(
                key=PartnerConfigEnum.IS_OTP_ENABLED.value, value=False, partner_id= UUID("11111111-1111-1111-1111-111111111111")
            )
        )

        response = await self.auth_service.get_token(
            **self._prepare_get_token_mocks(partner_config_service)
        )

        assert response["token_type"] == "bearer"
        assert response["access_token"] == "mocked_access_token"

    @pytest.mark.asyncio
    async def test_get_token_does_not_bake_add_number_flag_into_token(self):
        """is_add_number_enabled must be resolved live via gRPC, never embedded
        in the JWT — is_obotaai_enabled is unaffected and stays in the token."""

        def config_by_key(partner_id, key):
            if key == PartnerConfigEnum.IS_OBOTAAI_ENABLED.value:
                return PartnerConfigResponse(key=key, value=True, partner_id=partner_id)
            return PartnerConfigResponse(key=key, value=False, partner_id=partner_id)

        partner_config_service = AsyncMock()
        # partner_config_service._get_partner_config_map
        partner_config_service.get_partner_config_by_key.side_effect = config_by_key

        await self.auth_service.get_token(
            **self._prepare_get_token_mocks(partner_config_service)
        )

        # token_data is the first positional arg passed to create_access_token
        token_data = self.auth_utility_mock.create_access_token.call_args.args[0]

        assert not hasattr(TokenKeys, "IS_ADD_NUMBER_ENABLED")
        assert "is_add_number_enabled" not in token_data
        assert token_data[TokenKeys.IS_OBOTAAI_ENABLED] is True

  
    async def test_sign_up_user_creation_success(self):
        partner_mock = MagicMock(active_license=10)
        self.partner_repository_mock.get_by_id.return_value = partner_mock

        self.auth_service.validate_location_hierarchy = AsyncMock(return_value=True)

        user_role_mock = MagicMock(hierarchy=1)
        self.auth_repository_mock.get_role_by_id.return_value = user_role_mock

        self.user_repository_mock.partner_user_limit.return_value = 5
        self.auth_utility_mock.get_password_hash.return_value = "hashed_password"
        self.user_repository_mock.add_user.return_value = self.user_response
        self.user_repository_mock.is_admin_exists.return_value = False

        # Mock partner_config_service to prevent DB hit
        self.partner_config_service_mock = AsyncMock()
        self.partner_config_service_mock.get_partner_config_by_key.return_value = None

        created_user = await self.auth_service.sing_up(
            self.user_data,
            services="is_talko_enabled",
            user_repository=self.user_repository_mock,
            partner_repository=self.partner_repository_mock,
            partner_config_service=self.partner_config_service_mock,  # <-- important
        )

        self.mock_logger.info.assert_called_with(
            "User created successfully: {}".format(created_user)
        )

    async def test_sign_up_partner_limit_exceeded(self):

        # Mock partner with active license and role hierarchy
        self.partner_repository_mock.get_by_id.return_value = MagicMock(
            active_license=5
        )
        self.auth_repository_mock.get_role_by_id.return_value = MagicMock(hierarchy=1)

        # Set partner limit to match the active license to trigger limit exception
        self.user_repository_mock.partner_user_limit.return_value = 5
        self.user_repository_mock.is_admin_exists.return_value = False
        services = "is_talko_enabled"
        partner_config_service_mock = AsyncMock()
        partner_config_service_mock.get_partner_config_by_key.return_value = None
        # Check for AuthException due to partner limit
        with pytest.raises(AuthException) as exc:
            await self.auth_service.sing_up(
                self.user_data,
                services=services,
                user_repository=self.user_repository_mock,
                partner_repository=self.partner_repository_mock,
                partner_config_service=partner_config_service_mock,
            )
        assert str(exc.value) == AuthExceptionMsg.PARTNER_LIMIT.format(5)

    async def test_sign_up_admin_exist(self):

        # Mock partner with active license and role hierarchy
        self.partner_repository_mock.get_by_id.return_value = MagicMock(
            active_license=5
        )
        self.auth_repository_mock.get_role_by_id.return_value = MagicMock(hierarchy=1)

        self.user_repository_mock.partner_user_limit.return_value = 5
        self.user_repository_mock.is_admin_exists.return_value = True
        services = "is_talko_enabled"
        partner_config_service_mock = AsyncMock()
        partner_config_service_mock.get_partner_config_by_key.return_value = None
        with pytest.raises(AuthException) as exc:
            await self.auth_service.sing_up(
                self.user_data,
                services=services,
                user_repository=self.user_repository_mock,
                partner_repository=self.partner_repository_mock,
                partner_config_service=partner_config_service_mock,
            )
        assert str(exc.value) == AuthExceptionMsg.ADMIN_EXIST

    def _prepare_signup_common_mocks(self) -> None:
        self.partner_repository_mock.get_by_id.return_value = MagicMock(
            active_license=10, is_internal=False
        )
        self.auth_repository_mock.get_role_by_id.return_value = MagicMock(hierarchy=1)
        self.user_repository_mock.partner_user_limit.return_value = 0
        self.user_repository_mock.is_admin_exists.return_value = False
        self.user_repository_mock.add_user.return_value = self.user_response
        self.auth_utility_mock.get_password_hash.return_value = "hashed_password"

    async def test_sign_up_team_role_id_requires_team_id(self) -> None:
        self._prepare_signup_common_mocks()
        user_data = self.user_data.model_copy(update={"team_role_id": UUID("55555555-5555-5555-5555-555555555555")})
        team_repository_mock = AsyncMock()

        with pytest.raises(AuthException, match="team_role_id requires team_id"):
            await self.auth_service.sing_up(
                user_data,
                services="is_talko_enabled",
                user_repository=self.user_repository_mock,
                partner_repository=self.partner_repository_mock,
                partner_config_service=AsyncMock(),
                team_repository=team_repository_mock,
            )
        team_repository_mock.get_team_by_id.assert_not_called()

    @staticmethod
    def _teams_enabled_config_by_key(partner_id, key):
        return MagicMock(value=key == PartnerConfigEnum.IS_TEAMS_ENABLED.value)

    async def test_sign_up_team_role_id_not_in_catalog_rejected(self) -> None:
        self._prepare_signup_common_mocks()
        user_data = self.user_data.model_copy(
            update={"team_id": UUID("77777777-7777-7777-7777-777777777777"), "team_role_id": UUID("99999999-9999-9999-9999-999999999999")}
        )

        partner_config_service_mock = AsyncMock()
        partner_config_service_mock.get_partner_config_by_key.side_effect = (
            self._teams_enabled_config_by_key
        )
        team_repository_mock = AsyncMock()
        team_repository_mock.get_team_by_id.return_value = MagicMock(id= UUID("77777777-7777-7777-7777-777777777777"))
        team_repository_mock.is_role_in_partner_catalog.return_value = False

        with pytest.raises(AuthException, match="not part of this partner's role catalog"):
            await self.auth_service.sing_up(
                user_data,
                services="is_talko_enabled",
                user_repository=self.user_repository_mock,
                partner_repository=self.partner_repository_mock,
                partner_config_service=partner_config_service_mock,
                team_repository=team_repository_mock,
            )
        team_repository_mock.add_member.assert_not_called()

    async def test_sign_up_creates_team_member_with_team_role_id(self) -> None:
        self._prepare_signup_common_mocks()
        user_data = self.user_data.model_copy(
            update={"team_id": UUID("77777777-7777-7777-7777-777777777777"), "team_role_id": UUID("44444444-4444-4444-4444-444444444444")}
        )

        partner_config_service_mock = AsyncMock()
        partner_config_service_mock.get_partner_config_by_key.side_effect = (
            self._teams_enabled_config_by_key
        )
        team_repository_mock = AsyncMock()
        team_repository_mock.get_team_by_id.return_value = MagicMock(id= UUID("77777777-7777-7777-7777-777777777777"))
        team_repository_mock.is_role_in_partner_catalog.return_value = True

        await self.auth_service.sing_up(
            user_data,
            services="is_talko_enabled",
            user_repository=self.user_repository_mock,
            partner_repository=self.partner_repository_mock,
            partner_config_service=partner_config_service_mock,
            team_repository=team_repository_mock,
        )

        team_repository_mock.add_member.assert_awaited_once()
        call_kwargs = team_repository_mock.add_member.call_args.kwargs
        assert call_kwargs["team_id"] == UUID("77777777-7777-7777-7777-777777777777")
        assert call_kwargs["role_id"] == UUID("44444444-4444-4444-4444-444444444444")

    async def test_add_role_success(self):
        """Test successful role addition."""
        self.auth_repository_mock.add_role.return_value = self.role_response
        created_role = await self.auth_service.add_role(
            self.role_mock, self.current_user_mock
        )

        assert created_role.name == "Admin"
        self.mock_logger.info.assert_called_with("Attempting to create new role")

    async def test_get_role_by_id(self):
        """Test retrieving a role by ID."""
        self.auth_repository_mock.get_role_by_id.return_value = self.role_mock
        role = await self.auth_service.get_role_by_id(id= UUID("11111111-1111-1111-1111-111111111111"))

        assert role == self.role_mock
        self.mock_logger.info.assert_called_with("Attempting to get role11111111-1111-1111-1111-111111111111")

    async def test_get_all_roles(self):
        """Test retrieving all roles."""
        self.auth_repository_mock.get_all_role.return_value = self.role_list_mock
        partner_service_mock = AsyncMock()
        partner_service_mock.get_partner_by_id.return_value = MagicMock(
            is_internal=True
        )
        partner_config_service_mock = AsyncMock()
        partner_config_service_mock.get_partner_config_by_key.return_value = None
        roles = await self.auth_service.get_all_role(
            12,
            partner_service=partner_service_mock,
            partner_config_service=partner_config_service_mock,
        )

        assert len(roles) == 2
        assert roles[0].title == "admin"
        assert roles[1].title == "user"
        self.mock_logger.info.assert_called_with("Attempting to getting all roles")

    async def test_get_all_roles_filters_by_partner_when_custom_roles_enabled(self):
        """When custom roles are enabled for the partner, roles are scoped to it."""
        self.auth_repository_mock.get_all_role.return_value = self.role_list_mock
        partner_service_mock = AsyncMock()
        partner_service_mock.get_partner_by_id.return_value = MagicMock(
            is_internal=True
        )
        partner_config_service_mock = AsyncMock()
        partner_config_service_mock.get_partner_config_by_key.return_value = MagicMock(
            value=True
        )
        await self.auth_service.get_all_role(
            12,
            partner_service=partner_service_mock,
            partner_config_service=partner_config_service_mock,
        )

        self.auth_repository_mock.get_all_role.assert_awaited_with(True, 12)

    async def test_get_all_roles_uses_default_catalog_when_custom_roles_disabled(self):
        """When custom roles are disabled, roles fall back to the shared defaults."""
        self.auth_repository_mock.get_all_role.return_value = self.role_list_mock
        partner_service_mock = AsyncMock()
        partner_service_mock.get_partner_by_id.return_value = MagicMock(
            is_internal=True
        )
        partner_config_service_mock = AsyncMock()
        partner_config_service_mock.get_partner_config_by_key.return_value = MagicMock(
            value=False
        )
        await self.auth_service.get_all_role(
            12,
            partner_service=partner_service_mock,
            partner_config_service=partner_config_service_mock,
        )

        self.auth_repository_mock.get_all_role.assert_awaited_with(True, None)

    @pytest.mark.asyncio
    async def test_get_token_user_not_found(self):
        request = AsyncMock()

        # Mock _get_user to raise AuthException (imitating user not found in service)
        self.auth_service._get_user = AsyncMock(
            side_effect=AuthException("User not found")
        )

        with pytest.raises(AuthException) as exc:
            await self.auth_service.get_token(
                request=request, login_data=self.login_data
            )

        assert "User not found" in str(exc.value)

    async def test_delete_role(self):
        """Test delete role"""
        self.auth_repository_mock.delete_role.return_value = True

        result = await self.auth_service.delete_role(1, self.current_user_mock)

        assert result == True

    async def test_add_permission_success(self):

        self.auth_repository_mock.add_permission.return_value = self.permission_response

        created_permission = await self.auth_service.create_permission(
            user_permission=self.permission_mock, current_user=self.current_user_mock
        )

        assert created_permission == self.permission_response

    async def test_sign_up_partner_not_found(self):

        # Mock partner retrieval to raise PartnerNotFoundError
        self.partner_repository_mock.get_by_id.side_effect = PartnerNotFoundError(UUID("11111111-1111-1111-1111-111111111111"))
        services = "is_talko_enabled"
        with pytest.raises(AuthException) as exc:
            await self.auth_service.sing_up(
                self.user_data,
                services=services,
                user_repository=self.user_repository_mock,
                partner_repository=self.partner_repository_mock,
            )

        assert str(exc.value) == "Partner not found, id: 11111111-1111-1111-1111-111111111111"
        self.mock_logger.error.assert_called_with(
            "Partner not find while create user: Partner not found, id: 11111111-1111-1111-1111-111111111111"
        )

    async def test_sign_up_parent_not_found(self):

        user_data = UserData(
            username="newuser@example.com",
            password="Correctpassword@1234",
            email="testuser@example.com",
            phone_number="+911234567890",
            name="Test User",
            designation="Developer",
            partner_id= UUID("12121212-1212-1212-1212-121212121212"),
            role_id= UUID("11111111-1111-1111-1111-111111111111"),
            parent_id= UUID("11111111-1111-1111-1111-111111111111"),
        )

        self.user_repository_mock.get_user_with_role.side_effect = UserNotFoundError(UUID("11111111-1111-1111-1111-111111111111"))
        self.partner_repository_mock.get_by_id.return_value = MagicMock(
            active_license=5
        )
        self.auth_repository_mock.get_role_by_id.return_value = MagicMock(hierarchy=1)

        self.user_repository_mock.partner_user_limit.return_value = 1
        self.user_repository_mock.is_admin_exists.return_value = False
        services = "is_talko_enabled"
        partner_config_service_mock = AsyncMock()
        partner_config_service_mock.get_partner_config_by_key.return_value = None
        # Act & Assert
        with pytest.raises(AuthException) as exc:
            await self.auth_service.sing_up(
                user_data,
                services=services,
                user_repository=self.user_repository_mock,
                partner_repository=self.partner_repository_mock,
                partner_config_service=partner_config_service_mock,
            )

        assert str(exc.value) == "Parent not found"
        self.mock_logger.error.assert_called_with(
            "Parent not find while create user: User not found, id: 11111111-1111-1111-1111-111111111111"
        )

    async def test_get_all_permission(self):

        self.auth_repository_mock.get_all_permission.return_value = [
            self.permission_mock
        ]

        permission = await self.auth_service.get_all_permission()
        assert len(permission) == 1

    async def test_get_permission_by_id(self):

        self.auth_repository_mock.get_permission_by_id.return_value = (
            self.permission_mock
        )

        permission = await self.auth_service.get_permission_by_id(id= UUID("11111111-1111-1111-1111-111111111111"))

        assert permission == self.permission_mock

    async def test_delete_permission(self):
        permission_id= UUID("11111111-1111-1111-1111-111111111111")

        self.auth_repository_mock.delete_permission.return_value = True

        result = await self.auth_service.delete_permission(
            permission_id, self.current_user_mock
        )

        assert result == True

    async def test_sign_up_parent_role_hierarchy_validation(self):
        # Setup user data with parent ID for role hierarchy check
        user_data = UserData(
            username="newuser@example.com",
            email="newuser@example.com",
            password="Password@1234",
            phone_number="+911234567890",
            name="New User",
            designation="Developer",
            partner_id= UUID("11111111-1111-1111-1111-111111111111"),
            role_id= UUID("11111111-1111-1111-1111-111111111111"),
            parent_id= UUID("22222222-2222-2222-2222-222222222222"),
        )

        # Mock partner and role hierarchy
        self.partner_repository_mock.get_by_id.return_value = MagicMock(
            active_license=10, is_internal=False
        )

        user_role_mock = MagicMock(hierarchy=2)
        self.auth_repository_mock.get_role_by_id.return_value = user_role_mock

        self.user_repository_mock.partner_user_limit.return_value = 5

        # Mock parent's role hierarchy
        parent_user_role_mock = MagicMock(hierarchy=3)
        self.user_repository_mock.get_user_with_role.return_value = (
            parent_user_role_mock
        )
        services = "is_talko_enabled"
        partner_config_service_mock = AsyncMock()
        partner_config_service_mock.get_partner_config_by_key.return_value = None

        # Check for AuthException due to parent role hierarchy violation
        with pytest.raises(AuthException) as exc:
            await self.auth_service.sing_up(
                user_data,
                services=services,
                user_repository=self.user_repository_mock,
                partner_repository=self.partner_repository_mock,
                partner_config_service=partner_config_service_mock,
            )
        assert str(exc.value) == AuthExceptionMsg.PARENT_VALIDATION

    async def test_sign_up_user_creation_general_exception(self):

        self.auth_repository_mock.sing_up.side_effect = Exception(
            "Some unexpected error"
        )
        services = "is_talko_enabled"
        with pytest.raises(Exception):
            await self.auth_service.sing_up(
                self.user_data,
                services,
                self.user_repository_mock,
                self.partner_repository_mock,
            )

    async def test_get_role_by_id_general_exception(self):

        self.auth_repository_mock.get_role_by_id.side_effect = Exception(
            "Some unexpected error"
        )

        with pytest.raises(Exception):
            await self.auth_service.get_role_by_id(1)

    async def test_get_permission_by_id_general_exception(self):

        self.auth_repository_mock.get_permission_by_id.side_effect = Exception(
            "Some unexpected error"
        )

        with pytest.raises(Exception):
            await self.auth_service.get_permission_by_id(1)

    async def test_get_all_role_general_exception(self):

        self.auth_repository_mock.get_all_role.side_effect = Exception(
            "Some unexpected error"
        )

        with pytest.raises(Exception):
            await self.auth_service.get_all_role()

    async def test_delete_role_general_exception(self):

        self.auth_repository_mock.delete_role.side_effect = Exception(
            "Some unexpected error"
        )

        with pytest.raises(Exception):
            await self.auth_service.delete_role(1, self.current_user_mock)

    async def test_get_all_permission_general_exception(self):

        self.auth_repository_mock.get_all_permission.side_effect = Exception(
            "Some unexpected error"
        )

        with pytest.raises(Exception):
            await self.auth_service.get_all_permission()

    async def test_delete_permission_general_exception(self):

        self.auth_repository_mock.delete_permission.side_effect = Exception(
            "Some unexpected error"
        )

        with pytest.raises(Exception):
            await self.auth_service.delete_permission(1, self.current_user_mock)

    async def test_sign_up_role_not_found(self):

        # Mock partner with active license and set partner limit
        partner_mock = MagicMock(active_license=10)
        self.partner_repository_mock.get_by_id.return_value = partner_mock

        self.auth_repository_mock.get_role_by_id.side_effect = RoleNotFoundError(UUID("11111111-1111-1111-1111-111111111111"))
        services = "is_talko_enabled"
        partner_config_service_mock = AsyncMock()
        partner_config_service_mock.get_partner_config_by_key.return_value = None
        # Act & Assert
        with pytest.raises(AuthException) as exc:
            await self.auth_service.sing_up(
                self.user_data,
                services=services,
                user_repository=self.user_repository_mock,
                partner_repository=self.partner_repository_mock,
                partner_config_service=partner_config_service_mock,
            )

        assert str(exc.value) == "Role not found, id: 11111111-1111-1111-1111-111111111111"
        self.mock_logger.error.assert_called_with(
            "Role not find while create user: Role not found, id: 11111111-1111-1111-1111-111111111111"
        )

    async def test_add_role_general_exception(self):

        self.auth_repository_mock.add_role.side_effect = Exception(
            "Some unexpected error"
        )

        with pytest.raises(Exception):
            await self.auth_service.add_role(self.role_mock, self.current_user_mock)

    async def test_add_role_auth_exception(self):

        self.auth_repository_mock.add_role.side_effect = AuthException(
            "Some unexpected error"
        )

        with pytest.raises(AuthException):
            await self.auth_service.add_role(self.role_mock, self.current_user_mock)
        self.mock_logger.error.assert_called_with(
            "Integrity error during role creation: "
        )

    async def test_delete_permission_permission_not_found_exception(self):

        self.auth_repository_mock.delete_permission.side_effect = (
            PermissionNotFoundError(UUID("11111111-1111-1111-1111-111111111111"))
        )

        with pytest.raises(AuthException):
            await self.auth_service.delete_permission(
                id= UUID("11111111-1111-1111-1111-111111111111"), current_user=self.current_user_mock
            )

    async def test_get_permission_by_id_permission_not_found_exception(self):

        self.auth_repository_mock.get_permission_by_id.side_effect = (
            PermissionNotFoundError(UUID("11111111-1111-1111-1111-111111111111"))
        )

        with pytest.raises(AuthException):
            await self.auth_service.get_permission_by_id(id= UUID("11111111-1111-1111-1111-111111111111"))

    async def test_create_permission_auth_exception(self):

        self.auth_repository_mock.add_permission.side_effect = AuthException(
            "Some unexpected error"
        )

        with pytest.raises(AuthException):
            await self.auth_service.create_permission(
                user_permission=self.permission_mock,
                current_user=self.current_user_mock,
            )

    async def test_create_permission_general_exception(self):

        self.auth_repository_mock.add_permission.side_effect = Exception(
            "Some unexpected error"
        )

        with pytest.raises(Exception):
            await self.auth_service.create_permission(
                user_permission=self.permission_mock,
                current_user=self.current_user_mock,
            )

    async def test_delete_role_not_found_exception(self):

        self.auth_repository_mock.delete_role.side_effect = RoleNotFoundError(UUID("11111111-1111-1111-1111-111111111111"))

        with pytest.raises(AuthException):
            await self.auth_service.delete_role(
                id= UUID("11111111-1111-1111-1111-111111111111"), current_user=self.current_user_mock
            )

    async def test_get_role_by_id_not_found_exception(self):

        self.auth_repository_mock.get_role_by_id.side_effect = RoleNotFoundError(UUID("11111111-1111-1111-1111-111111111111"))

        with pytest.raises(AuthException):
            await self.auth_service.get_role_by_id(id= UUID("11111111-1111-1111-1111-111111111111"))

    async def test_get_token_general_exception(self):

        self.auth_repository_mock.get_token.side_effect = Exception(
            "Some unexpected error"
        )

        with pytest.raises(Exception):
            await self.auth_service.get_token(self.login_data)

    async def test_reset_password_success(self):
        reset_password_request = ResetPasswordRequest(
            email="user@example.com",
            current_password="OldPass@123",
            new_password="NewPass@123",
        )

        user_mock = AsyncMock()
        user_session_service = AsyncMock()
        user_mock.email = "user@example.com"
        user_mock.is_active = True
        user_mock.hashed_password = "hashed_old_password"
        user_mock.partner_id= UUID("11111111-1111-1111-1111-111111111111")

        self.user_repository_mock.get_user_by_field.return_value = user_mock
        self.user_repository_mock.get_user_details.return_value = {
            "partner_id": UUID("11111111-1111-1111-1111-111111111111"),
            "role_hierarchy_level": CurrentUserMap.ADMIN_ROLE_HIERARCHY_LEVEL,
            "email": "admin@example.com",
        }

        # Mock verify_password to return True for current password and False for new password
        self.auth_utility_mock.verify_password.side_effect = (
            lambda plain_password, hashed_password: (
                plain_password == "OldPass@123"  # True for current password
            )
        )

        self.auth_utility_mock.get_password_hash.return_value = "hashed_new_password"
        self.auth_repository_mock.reset_password.return_value = None
        user_session_service.deactivate_user_sessions.return_value = None

        response = await self.auth_service.reset_password(
            current_user={"user_id": 1},
            reset_password_request=reset_password_request,
            user_service=self.user_repository_mock,
            user_session_service=user_session_service,
        )

        assert response == AuthSuccessMsg.PASSWORD_RESET_SUCCESSFULLY
        self.mock_logger.info.assert_called_with(
            "Attempting to reset password for user: user@example.com"
        )
        self.auth_repository_mock.reset_password.assert_called_with(
            "hashed_new_password", user_mock
        )

    @pytest.mark.asyncio
    async def test_reset_password_user_not_found(self):
        reset_password_request = ResetPasswordRequest(
            email="nonexistent@example.com",
            current_password="OldPass@123d",
            new_password="NewPass@123",
        )

        self.user_repository_mock.get_user_by_field.return_value = None

        with pytest.raises(AuthException) as exc_info:
            await self.auth_service.reset_password(
                current_user={"user_id": 1},
                reset_password_request=reset_password_request,
                user_service=self.user_repository_mock,
            )

        assert str(exc_info.value) == AuthExceptionMsg.USER_NOT_FOUND
        self.mock_logger.warning.assert_called_with(
            "User not found nonexistent@example.com"
        )

    @pytest.mark.asyncio
    async def test_reset_password_incorrect_current_password(self):
        reset_password_request = ResetPasswordRequest(
            email="user@example.com",
            current_password="wrongpassword",
            new_password="NewPass@123",
        )

        user_mock = AsyncMock()
        user_mock.email = "user@example.com"
        user_mock.is_active = True
        user_mock.hashed_password = "hashed_old_password"
        user_mock.partner_id= UUID("11111111-1111-1111-1111-111111111111")

        user_session_mock = AsyncMock()
        # Mocking repository calls
        self.user_repository_mock.get_user_by_field.return_value = user_mock
        self.user_repository_mock.get_user_details.return_value = {
            "partner_id": UUID("11111111-1111-1111-1111-111111111111"),
            "role_hierarchy_level": 8,
            "email": "user@example.com",
        }

        # current password is incorrect, new password is not same as current (False, False)
        self.auth_utility_mock.verify_password.side_effect = [False, False]

        with pytest.raises(AuthException) as exc_info:
            await self.auth_service.reset_password(
                current_user={"user_id": 1},
                reset_password_request=reset_password_request,
                user_service=self.user_repository_mock,
                user_session_service=user_session_mock,
            )

        assert str(exc_info.value) == AuthExceptionMsg.INCORRECT_PWD
        self.mock_logger.error.assert_called_with(
            "Unexpected error occurred while reset password: {}".format(
                AuthExceptionMsg.INCORRECT_PWD
            )
        )

    async def test_get_parents_by_role_id_success(self):
        """Test successful retrieval of parents by role ID."""
        role_id= UUID("11111111-1111-1111-1111-111111111111")
        partner_id= UUID("10010010-0100-1001-0010-010010010010")
        mock_parents = [
            {
                "id": UUID("11111111-1111-1111-1111-111111111111"),
                "name": "Parent One",
                "designation": "Admin",
                "email": "parent1@example.com",
            },
            {
                "id": UUID("22222222-2222-2222-2222-222222222222"),
                "name": "Parent Two",
                "designation": "Manager",
                "email": "parent2@example.com",
            },
        ]

        self.auth_repository_mock.get_parent_users_by_role_id.return_value = (
            mock_parents
        )

        result = await self.auth_service.get_parent_users_by_role_id(
            role_id, partner_id
        )

        self.auth_repository_mock.get_parent_users_by_role_id.assert_called_once_with(
            role_id, partner_id
        )
        assert len(result) == len(mock_parents)
        assert all(isinstance(res, Contrasts.ParentUserResponse) for res in result)

    async def test_get_parents_by_role_id_role_not_found(self):
        """Test case when the specified role ID does not exist."""
        role_id= UUID("99999999-9999-9999-9999-999999999999")  # Non-existent role ID
        partner_id= UUID("10010010-0100-1001-0010-010010010010")

        self.auth_repository_mock.get_parent_users_by_role_id.side_effect = (
            RoleNotFoundError("Role not found")
        )

        with pytest.raises(RoleNotFoundError) as exc_info:
            await self.auth_service.get_parent_users_by_role_id(role_id, partner_id)

        self.auth_repository_mock.get_parent_users_by_role_id.assert_called_once_with(
            role_id, partner_id
        )
        assert str(exc_info.value) == "Role not found, id: Role not found"
        self.mock_logger.error.assert_called_with(
            "Role not found: Role not found, id: Role not found"
        )

    async def test_get_parents_by_role_id_unexpected_error(self):
        """Test case when an unexpected error occurs."""
        role_id= UUID("11111111-1111-1111-1111-111111111111")
        partner_id= UUID("10010010-0100-1001-0010-010010010010")

        self.auth_repository_mock.get_parent_users_by_role_id.side_effect = Exception(
            "Unexpected database error"
        )

        with pytest.raises(Exception) as exc_info:
            await self.auth_service.get_parent_users_by_role_id(role_id, partner_id)

        self.auth_repository_mock.get_parent_users_by_role_id.assert_called_once_with(
            role_id, partner_id
        )
        assert str(exc_info.value) == "Unexpected database error"
        self.mock_logger.error.assert_called_with(
            "An unexpected error: Unexpected database error"
        )

    # @pytest.mark.asyncio
    # async def test_sign_up_with_city_state_country_success(self):
    #     """Test successful user sign-up with city_id, state_id, and country_id."""
    #     # Arrange
    #     user_data = UserData(
    #         username="testuser",
    #         email="testuser@example.com",
    #         password="Password@1234",
    #         phone_number="+911234567890",
    #         name="Test User",
    #         designation="Developer",
    #         partner_id= UUID("11111111-1111-1111-1111-111111111111"),
    #         role_id= UUID("11111111-1111-1111-1111-111111111111"),
    #         parent_id=None,
    #         city_id= UUID("10110110-1101-1011-0110-110110110110"),
    #         state_id= UUID("20220220-2202-2022-0220-220220220220"),
    #         country_id= UUID("30330330-3303-3033-0330-330330330330"),
    #     )

    #     partner_config_service_mock = AsyncMock()
    #     partner_config_service_mock.get_partner_config_by_key.return_value = MagicMock(
    #         value=True
    #     )

    #     # Mock partner with active license and set partner limit
    #     partner_mock = MagicMock(active_license=10)
    #     self.partner_repository_mock.get_by_id.return_value = partner_mock

    #     # Mock role with a hierarchy level
    #     user_role_mock = MagicMock(hierarchy=1)
    #     self.auth_repository_mock.get_role_by_id.return_value = user_role_mock

    #     # Set partner limit check to a valid number within active license limit
    #     self.user_repository_mock.partner_user_limit.return_value = 5

    #     # Hash password mock
    #     self.auth_utility_mock.get_password_hash.return_value = "hashed_password"

    #     # Mock user creation
    #     self.user_repository_mock.add.return_value = self.user_response

    #     # Properly mock LocationService instance instead of patching at the module level
    #     location_service_mock = AsyncMock()
    #     location_service_mock.validate_location_hierarchy.return_value = True
    #     self.user_repository_mock.is_admin_exists.return_value = False
    #     services = "is_talko_enabled"
    #     # Act
    #     created_user = await self.auth_service.sing_up(
    #         user_data,
    #         services=services,
    #         user_repository=self.user_repository_mock,
    #         partner_repository=self.partner_repository_mock,
    #         location_service=location_service_mock,  # Pass the mocked instance
    #         partner_config_service=partner_config_service_mock,
    #     )

    #     # Assert
    #     location_service_mock.validate_location_hierarchy.assert_called_once_with(
    #         user_data.country_id, user_data.state_id, user_data.city_id
    #     )
    #     self.mock_logger.info.assert_called_with(
    #         "User credentials sent successfully: {}".format(created_user)
    #     )

    async def test_reset_password_with_existing_password(self):
        reset_password_request = ResetPasswordRequest(
            email="user@example.com",
            current_password="OldPass@123",
            new_password="OldPass@123",  # New password is the same as the old password
        )

        user_mock = AsyncMock()
        user_mock.email = "user@example.com"
        user_mock.is_active = True
        user_mock.hashed_password = "hashed_old_password"
        user_mock.partner_id= UUID("11111111-1111-1111-1111-111111111111")

        self.user_repository_mock.get_user_by_field.return_value = user_mock
        self.user_repository_mock.get_user_details.return_value = {
            "partner_id": UUID("11111111-1111-1111-1111-111111111111"),
            "role_hierarchy_level": CurrentUserMap.ADMIN_ROLE_HIERARCHY_LEVEL,
            "email": "admin@example.com",
        }

        # Mock verify_password to return True for both current and new password
        self.auth_utility_mock.verify_password.side_effect = (
            lambda plain_password, hashed_password: (
                plain_password
                == "OldPass@123"  # True for both current and new password
            )
        )

        with pytest.raises(AuthException) as exc_info:
            await self.auth_service.reset_password(
                current_user={"user_id": 1},
                reset_password_request=reset_password_request,
                user_service=self.user_repository_mock,
                user_session_service=AsyncMock(),
            )

        assert str(exc_info.value) == AuthExceptionMsg.EXISTING_PASSWORD_WARNING
        self.mock_logger.warning.assert_called_with(
            "New password cannot be the same as the existing password"
        )

    async def test_get_role_permissions_matrix_success(self):
        user_id= UUID("12312312-3123-1231-2312-312312312312")
        # Mock roles
        role1 = MagicMock(id= UUID("11111111-1111-1111-1111-111111111111"))
        role2 = MagicMock(id= UUID("22222222-2222-2222-2222-222222222222"))
        roles = [role1, role2]
        self.auth_service.get_all_role = AsyncMock(return_value=roles)

        # Mock permissions
        perm1 = MagicMock(category="cat1", slug="perm1")
        perm2 = MagicMock(category="cat2", slug="perm2")
        perm3 = MagicMock(category=None, slug="perm3")

        user_service_mock = AsyncMock()
        user_service_mock.get_user_by_id.return_value = AsyncMock(
            id=user_id, email="user@example.com"
        )
        self.auth_repository_mock.get_default_role_permissions_by_role_id.side_effect = [
            [perm1],
            [perm2],
        ]
        self.auth_repository_mock.get_partner_role_permissions_by_partner_and_role.side_effect = [
            [perm3],
            [],
        ]

        # Mock _build_permissions_response
        default_permissions_response = {"role1": "default"}
        partner_permissions_response = {"role1": "partner"}
        self.auth_service._build_permissions_response = AsyncMock(
            side_effect=[default_permissions_response, partner_permissions_response]
        )

        # Act
        await self.auth_service.get_role_permissions_matrix(
            user_id, True, user_service=user_service_mock
        )

    async def test_assume_user_success(self):
        mock_token = {"access_token": "mock_token", "token_type": "bearer"}

        self.auth_service.get_token = AsyncMock(return_value=mock_token)

        request_mock = AsyncMock(spec=Request)
        request_mock.headers = {"User-Agent": "test-agent"}
        request_mock.client = MagicMock()
        request_mock.client.host = "127.0.0.1"
        request_mock.state = MagicMock()
        request_mock.state.user = {"user_id": UUID("10010010-0100-1001-0010-010010010010")}

         # mock console service
        console_service_mock = AsyncMock()
        console_service_mock.get_user_by_id.return_value = MagicMock(
            id= UUID("20220220-2202-2022-0220-220220220220"), partner_id= UUID("11111111-1111-1111-1111-111111111111")
        )

        #  mock partner config
        partner_config_service_mock = AsyncMock()
        partner_config_service_mock.get_partner_configs_by_partner_id.return_value = [
            MagicMock(key="is_console_enabled", value=True)
        ]

        # mock user config
        user_config_service_mock = AsyncMock()
        user_config_service_mock.get_user_configs_by_user_id.return_value = [
            MagicMock(key="is_console_enabled", value=True)
        ]

        result = await self.auth_service.assume_user(
            request_mock,
            UUID("20220220-2202-2022-0220-220220220220"),
            console_service=console_service_mock,
            partner_config_service=partner_config_service_mock,
            user_config_service=user_config_service_mock,
        )

        self.auth_service.get_token.assert_awaited_once_with(
            request=request_mock,
            is_assume_user=True,
            user_id= UUID("20220220-2202-2022-0220-220220220220"),
            svc_name="console",
        )

        assert result == mock_token
        
    async def test_assume_user_user_not_found_exception(self):
        request_mock = AsyncMock(spec=Request)
        request_mock.headers = {"User-Agent": "test-agent"}
        request_mock.client = MagicMock()
        request_mock.client.host = "127.0.0.1"
        request_mock.state = MagicMock()
        request_mock.state.user = {"user_id": UUID("10010010-0100-1001-0010-010010010010")}

        # mock console service to raise error
        console_service_mock = AsyncMock()
        console_service_mock.get_user_by_id.side_effect = UserNotFoundError(UUID("20220220-2202-2022-0220-220220220220"))

        with pytest.raises(UserNotFoundError):
            await self.auth_service.assume_user(
                request_mock,
                UUID("20220220-2202-2022-0220-220220220220"),
                console_service=console_service_mock,
            )
        async def test__get_user_user_not_found(self):
            user_service = AsyncMock()
            user_service.get_user_by_field.return_value = None

            login_data = LoginData(credential="unknown@example.com", password="Wrong@123")

            with pytest.raises(AuthException) as exc_info:
                await self.auth_service._get_user(
                    login_data=login_data,
                    is_assume_user=False,
                    user_id=None,
                    user_service=user_service,
                )

            assert str(exc_info.value) == AuthExceptionMsg.USER_NOT_FOUND
            self.mock_logger.warning.assert_called_with(
                "User not found: unknown@example.com"
            )

        async def test_logout_success(self):
            token = "valid_token"
            payload = {"user_session_id": 123}

            self.auth_utility_mock.decode_access_token.return_value = payload
            self.auth_utility_mock.decode_access_token_without_exp.return_value = None

            self.redis_mock.delete_cache.return_value = True

            user_session_mock = MagicMock()
            user_session_mock.is_active = True
            self.user_session_service.get_user_session.return_value = user_session_mock

            updated_session_mock = MagicMock(is_active=False)
            self.user_session_service.update_user_session.return_value = (
                updated_session_mock
            )

            result = await self.auth_service.logout(token)

            assert result is False

    async def test_logout_unexpected_exception(self):
        token = "valid_token"
        payload = {"user_session_id": 123}

        self.auth_utility_mock.decode_access_token.return_value = payload
        self.redis_mock.delete_cache.return_value = True

        self.user_session_service.get_user_session.side_effect = Exception(
            "Unexpected error"
        )

        with pytest.raises(Exception) as exc:
            await self.auth_service.logout(token)

        assert "Unexpected error" in str(exc.value)

    async def test_get_user_incorrect_password(self):
        # Arrange
        login_data = self.login_data
        user_mock = MagicMock()
        user_mock.is_active = True
        user_mock.hashed_password = "hashed_password"

        user_service = AsyncMock()
        user_service.get_user_by_field.return_value = user_mock

        self.auth_utility_mock.verify_password.return_value = False

        # Act & Assert
        with pytest.raises(AuthException) as exc:
            await self.auth_service._get_user(
                login_data=login_data,
                is_assume_user=False,
                user_id=None,
                user_service=user_service,
            )

        assert str(exc.value) == AuthExceptionMsg.INCORRECT_PWD
        self.mock_logger.warning.assert_called_with("Incorrect password")

    async def test_get_user_assume_user_success(self):
        # Arrange
        user_id= UUID("42424242-4242-4242-4242-424242424242")
        user_mock = MagicMock()
        user_mock.is_internal = False

        user_service = AsyncMock()
        user_service.get_user_by_id.return_value = user_mock

        # Act
        user = await self.auth_service._get_user(
            login_data=None,
            is_assume_user=True,
            user_id=user_id,
            user_service=user_service,
        )

        # Assert
        assert user == user_mock
        self.mock_logger.info.assert_called_with(f"Assuming user by ID: {user_id}")

    async def test_get_user_assume_internal_user(self):
        # Arrange
        user_id= UUID("42424242-4242-4242-4242-424242424242")
        user_mock = MagicMock()
        user_mock.is_internal = True

        user_service = AsyncMock()
        user_service.get_user_by_id.return_value = user_mock

        # Act & Assert
        with pytest.raises(UserNotFoundError) as exc:
            await self.auth_service._get_user(
                login_data=None,
                is_assume_user=True,
                user_id=user_id,
                user_service=user_service,
            )

        assert exc.value.args[0] == f"User not found, id: {user_id}"
        self.mock_logger.warning.assert_called_with("Cannot assume internal user")

    async def test_update_permission_success(self):
        permission_id= UUID("11111111-1111-1111-1111-111111111111")
        request_data = UpdatePermissionRquest(
            name="edit_user", description="Edit user permission"
        )
        updated_data = {
            "id": UUID("11111111-1111-1111-1111-111111111111"),
            "name": "edit_user",
            "description": "Edit user permission",
        }

        self.auth_repository_mock.update_permission.return_value = updated_data

        result = await self.auth_service.update_permission(permission_id, request_data)

        self.auth_repository_mock.update_permission.assert_awaited_once_with(
            permission_id, request_data
        )
        self.mock_logger.info.assert_any_call(
            f"Attempting to update permission with id: {permission_id}"
        )
        self.mock_logger.info.assert_any_call(
            f"Permission with id: {permission_id} updated successfully"
        )
        assert isinstance(result, UpdatePermissionResponse)
        assert result.id == updated_data["id"]

    async def test_update_permission_permission_not_found(self):
        permission_id= UUID("99999999-9999-9999-9999-999999999999")
        request_data = UpdatePermissionRquest(
            name="invalid", description="Invalid permission"
        )
        self.auth_repository_mock.update_permission.side_effect = (
            PermissionNotFoundError("Permission not found")
        )

        with pytest.raises(PermissionNotFoundError):
            await self.auth_service.update_permission(permission_id, request_data)

    async def test_update_permission_auth_exception(self):
        permission_id= UUID("11111111-1111-1111-1111-111111111111")
        request_data = UpdatePermissionRquest(
            name="auth_error", description="Auth fails"
        )
        self.auth_repository_mock.update_permission.side_effect = AuthException(
            "Auth failed"
        )

        with pytest.raises(AuthException):
            await self.auth_service.update_permission(permission_id, request_data)

        self.mock_logger.error.assert_called_with(
            "Auth error during updating permission: AuthException('Auth failed')"
        )

    async def test_update_permission_unexpected_exception(self):
        permission_id= UUID("11111111-1111-1111-1111-111111111111")
        request_data = UpdatePermissionRquest(
            name="unknown", description="unknown error"
        )
        self.auth_repository_mock.update_permission.side_effect = Exception(
            "Something went wrong"
        )

        with pytest.raises(Exception):
            await self.auth_service.update_permission(permission_id, request_data)

        self.mock_logger.error.assert_called_with(
            "Unexpected error during updating permission: Exception('Something went wrong')"
        )

    def test_get_categories_success(self):
        # Arrange: setup dummy permissions

        PermissionCategories.CONSOLE_PERMISSIONS = {
            "DB Constants": [("get_constants", True)]
        }

        PermissionCategories.TALKO_PERMISSIONS = {"Vendor": [("create_vendor", True)]}

        # Act
        result = self.auth_service.get_categories()

        # Assert
        assert result == {
            "console": ["DB Constants"],
            "talko": ["Vendor"],
        }
        self.mock_logger.info.assert_any_call("getting categories name...")
        self.mock_logger.info.assert_any_call("Fetched all the categories ")

    def test_get_permission_title_by_category_name_success(self):

        PermissionCategories.CONSOLE_PERMISSIONS = {
            "Dashboard": [("view_dashboard", True), ("edit_dashboard", False)]
        }

        # Act
        result = self.auth_service.get_permission_title_by_category_name(
            "Dashboard", "console"
        )

        # Assert
        assert result == ["view_dashboard", "edit_dashboard"]
        self.mock_logger.info.assert_any_call(
            "Attempting to get permission titles by category name: dashboard"
        )
        self.mock_logger.info.assert_any_call(
            "Fetched permission titles for category {}: {}".format(
                "dashboard", ["view_dashboard", "edit_dashboard"]
            )
        )

    def test_get_categories_generic_exception(self):
        # Patch the attribute to raise an exception when accessed
        def raise_exception(*args, **kwargs):
            raise Exception("Unexpected error")

        with patch.object(
            PermissionCategories, "CONSOLE_PERMISSIONS", new_callable=PropertyMock
        ) as mock_console_permissions:
            mock_console_permissions.side_effect = raise_exception

            with pytest.raises(Exception) as exc:
                self.auth_service.get_categories()

            assert str(exc.value) == "Unexpected error"

    async def test_get_permission_titles_generic_exception(self):
        with patch.object(
            PermissionCategories, "CONSOLE_PERMISSIONS", new_callable=PropertyMock
        ) as mock_console_permissions:
            mock_console_permissions.side_effect = Exception("Unexpected error")
            with pytest.raises(Exception) as exc:
                await self.auth_service.get_permission_title_by_category_name(
                    "db constants", "console"
                )
            self.mock_logger.error.assert_any_call(
                "Error fetching permission titles for {}: {}".format(
                    "db constants", exc.value
                )
            )

    async def test_update_role_success(self):
        role_id= UUID("11111111-1111-1111-1111-111111111111")
        request_data = MagicMock()
        request_data.model_dump.return_value = {
            "name": "Updated Admin",
            "slug": "updated_admin",
        }
        updated_role = MagicMock()
        self.auth_repository_mock.update_role.return_value = updated_role

        with patch(
            "src.components.auth.schema.RoleResponse.model_validate",
            return_value=MagicMock(id=role_id),
        ) as mock_validate:
            result = await self.auth_service.update_role(role_id, request_data)

        self.mock_logger.info.assert_any_call(
            f"Attempting to update the role with id: {role_id}"
        )
        self.auth_repository_mock.update_role.assert_awaited_once_with(
            role_id, name="Updated Admin", slug="updated_admin"
        )
        mock_validate.assert_called_once_with(updated_role)
        assert result.id == role_id

    async def test_update_role_role_not_found(self):
        role_id= UUID("99999999-9999-9999-9999-999999999999")
        request_data = MagicMock()
        request_data.model_dump.return_value = {"name": "Not Found"}
        self.auth_repository_mock.update_role.side_effect = RoleNotFoundError(
            "Role not found"
        )

        with pytest.raises(RoleNotFoundError):
            await self.auth_service.update_role(role_id, request_data)

        self.mock_logger.error.assert_called_with(
            "Role not found during updating role: RoleNotFoundError('Role not found, id: Role not found')"
        )

    async def test_update_role_auth_exception(self):
        role_id= UUID("11111111-1111-1111-1111-111111111111")
        request_data = MagicMock()
        request_data.model_dump.return_value = {"name": "Auth Error"}
        self.auth_repository_mock.update_role.side_effect = AuthException("Auth failed")

        with pytest.raises(AuthException):
            await self.auth_service.update_role(role_id, request_data)

        self.mock_logger.error.assert_called_with(
            "Auth error during updating role: AuthException('Auth failed')"
        )

    async def test_update_role_unexpected_exception(self):
        role_id= UUID("11111111-1111-1111-1111-111111111111")
        request_data = MagicMock()
        request_data.model_dump.return_value = {"name": "Unexpected"}
        self.auth_repository_mock.update_role.side_effect = Exception(
            "Unexpected error"
        )

        with pytest.raises(Exception):
            await self.auth_service.update_role(role_id, request_data)

        self.mock_logger.error.assert_called_with(
            "Unexpected error during updating role: Exception('Unexpected error')"
        )

    async def test_get_role_by_hierarchy_success(self):
        """Should return role when repository returns a role."""
        mock_role = {"id": 1, "name": "Admin"}
        self.auth_repository_mock.get_role_by_hierarchy.return_value = mock_role

        result = await self.auth_service.get_role_by_hierarchy(1)

        assert result == mock_role
        self.auth_repository_mock.get_role_by_hierarchy.assert_awaited_once_with(1)
        self.mock_logger.info.assert_called_with(
            "Attempting to get role details by hierarchy number: {}".format(1)
        )

    async def test_get_role_by_hierarchy_exception(self):
        """Should log error and raise exception when repository fails."""
        self.auth_repository_mock.get_role_by_hierarchy.side_effect = Exception(
            "DB error"
        )

        with pytest.raises(Exception) as exc_info:
            await self.auth_service.get_role_by_hierarchy(2)

        assert str(exc_info.value) == "DB error"
        self.auth_repository_mock.get_role_by_hierarchy.assert_awaited_once_with(2)
        self.mock_logger.error.assert_called()

    @pytest.mark.asyncio
    async def test_resolve_user_walkthrough_key_success(self):
        user_id= UUID("10101010-1010-1010-1010-101010101010")
        partner_id= UUID("20202020-2020-2020-2020-202020202020")

        user_service = AsyncMock()
        user_service.resolve_user_walkthrough_key = AsyncMock(return_value=None)

        await self.auth_service.resolve_user_walkthrough_key(
            user_id=user_id,
            partner_id=partner_id,
            user_service=user_service,
        )

        user_service.resolve_user_walkthrough_key.assert_awaited_once_with(
            user_id, partner_id
        )

    @pytest.mark.asyncio
    async def test_resolve_user_walkthrough_key_exception(self):
        user_id= UUID("10101010-1010-1010-1010-101010101010")
        partner_id= UUID("20202020-2020-2020-2020-202020202020")

        user_service = AsyncMock()
        user_service.resolve_user_walkthrough_key = AsyncMock(
            side_effect=Exception("boom")
        )

        with pytest.raises(Exception, match="boom"):
            await self.auth_service.resolve_user_walkthrough_key(
                user_id=user_id,
                partner_id=partner_id,
                user_service=user_service,
            )

        user_service.resolve_user_walkthrough_key.assert_awaited_once_with(
            user_id, partner_id
        )


    @pytest.mark.asyncio
    async def test_service_not_enabled(self):
        dto = ServiceAccessDTO(
            user=MagicMock(partner_id= UUID("11111111-1111-1111-1111-111111111111"), id= UUID("99999999-9999-9999-9999-999999999999")),
            svc_name=ServiceNames.TALKO,
            config_map={SvcFlagMap.get(ServiceNames.TALKO): False},
            partner_config_map={SvcFlagMap.get(ServiceNames.TALKO): True},
            is_assume_user=False,
            trial_expiry=None,
        )

        partner_config_service = AsyncMock()
        partner_meta_data_service = AsyncMock()

        with pytest.raises(AuthException) as exc:
            await self.auth_service.validate_service_access(
                dto,
                partner_config_service,
                partner_meta_data_service,
            )

        assert AuthExceptionMsg.SVC_NOT_ENABLED.split("{")[0] in str(exc.value)

    @pytest.mark.asyncio
    async def test_partner_service_not_enabled(self):
        dto = ServiceAccessDTO(
            user=MagicMock(partner_id= UUID("11111111-1111-1111-1111-111111111111"), id= UUID("99999999-9999-9999-9999-999999999999")),
            svc_name=ServiceNames.TALKO,
            config_map={SvcFlagMap.get(ServiceNames.TALKO): True},
            partner_config_map={SvcFlagMap.get(ServiceNames.TALKO): False},
            is_assume_user=False,
            trial_expiry=None,
        )

        partner_config_service = AsyncMock()
        partner_meta_data_service = AsyncMock()

        with pytest.raises(AuthException) as exc:
            await self.auth_service.validate_service_access(
                dto,
                partner_config_service,
                partner_meta_data_service,
            )

        assert AuthExceptionMsg.PARTNER_SERVICE_NOT_ENABLED.split("{")[0] in str(exc.value)



    @pytest.mark.asyncio
    async def test_console_service_bypass(self):
        dto = ServiceAccessDTO(
            user=MagicMock(partner_id= UUID("11111111-1111-1111-1111-111111111111"), id= UUID("10101010-1010-1010-1010-101010101010")),
            svc_name=ServiceNames.CONSOLE,
            config_map={},
            is_assume_user=False,
            trial_expiry=None,
        )

        partner_config_service = AsyncMock()
        partner_meta_data_service = AsyncMock()

        await self.auth_service.validate_service_access(
            dto,
            partner_config_service,
            partner_meta_data_service,
        )

    async def test_assume_user_partner_deactivated(self):
        request_mock = AsyncMock(spec=Request)
        request_mock.headers = {"User-Agent": "test-agent"}
        request_mock.client = MagicMock()
        request_mock.client.host = "127.0.0.1"
        request_mock.state = MagicMock()
        request_mock.state.user = {"user_id": UUID("10010010-0100-1001-0010-010010010010")}

        # mock console service
        console_service_mock = AsyncMock()
        console_service_mock.get_user_by_id.return_value = MagicMock(
            id= UUID("20220220-2202-2022-0220-220220220220"), partner_id= UUID("11111111-1111-1111-1111-111111111111")
        )

        # mock partner config
        partner_config_service_mock = AsyncMock()
        partner_config_service_mock.get_partner_configs_by_partner_id.return_value = [
            MagicMock(key="is_console_enabled", value=True)
        ]

        # mock user config
        user_config_service_mock = AsyncMock()
        user_config_service_mock.get_user_configs_by_user_id.return_value = [
            MagicMock(key="is_console_enabled", value=True)
        ]

        # simulate partner deactivated at token stage
        self.auth_service.get_token = AsyncMock(
            side_effect=PartnerException("Partner is deactivated")
        )

        with pytest.raises(AuthException) as exc:
            await self.auth_service.assume_user(
                request_mock,
                UUID("20220220-2202-2022-0220-220220220220"),
                console_service=console_service_mock,
                partner_config_service=partner_config_service_mock,
                user_config_service=user_config_service_mock,
            )

        assert str(exc.value) == AuthExceptionMsg.RESTRICT_LOGIN
        self.mock_logger.error.assert_called_with(
            "Can't log in as the partner is deactivated."
        )