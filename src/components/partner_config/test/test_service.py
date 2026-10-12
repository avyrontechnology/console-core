from uuid import UUID
import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch, MagicMock

import pytest
from sqlalchemy.exc import IntegrityError

from src.components.cache.helper import CacheHelper
from src.components.common.constants import CurrentUserMap
from src.components.partner.models import Partner
from src.components.partner_config.errors import (
    PartnerConfigKeyError,
    PartnerConfigValidationError,
)
from src.components.partner_config.schemas import (
    PartnerConfigData,
    PartnerConfigRequest,
    PartnerConfigUpdateRequest,
)
from src.components.partner_config.services import PartnerConfigService
from src.components.user_config.models import UserConfig
from src.exceptions import AuthException, PartnerConfigException


def _perm(slug: str) -> SimpleNamespace:
    return SimpleNamespace(slug=slug)


@pytest.mark.asyncio
class TestPartnerConfigService:
    @pytest.fixture(autouse=True)
    def setup_class(self, mock_logger):
        self.partner_config_repository = AsyncMock()
        self.mock_logger = mock_logger
        self.mock_cache = AsyncMock(spec=CacheHelper)
        self.partner_config_service = PartnerConfigService(
            partner_config_repository=self.partner_config_repository,
            console_service_logger=self.mock_logger,
            console_service_cache=self.mock_cache,
        )

    async def test_create_partner_config_success(self):
        partner_id= UUID("11111111-1111-1111-1111-111111111111")
        partner_config_data = PartnerConfigRequest(key="some_key", value="val")
        repo_response = SimpleNamespace(
            key="some_key", value="val", created_at=987654321245
        )

        self.partner_config_repository.create_partner_config.return_value = (
            repo_response
        )
        self.mock_cache.clear_pattern.return_value = None

        result = await self.partner_config_service.create_partner_config(
            partner_config_data, partner_id
        )

        assert result.key == "some_key"
        assert result.value == "val"
        assert result.created_at == 987654321245
        self.mock_logger.info.assert_any_call(
            f"Trying to create partner config for partner id: {partner_id}"
        )
        self.mock_logger.info.assert_any_call(
            f"Configuration  created successfully for partner with id: {partner_id}"  # Fixed extra space
        )
        self.mock_cache.clear_pattern.assert_awaited()

    async def test_create_partner_config_integrity_error(self):
        partner_id= UUID("11111111-1111-1111-1111-111111111111")
        partner_config_data = PartnerConfigRequest(key="some_key", value="val")

        self.partner_config_repository.create_partner_config.side_effect = (
            IntegrityError("Integrity error", None, None)
        )

        with pytest.raises(IntegrityError):
            await self.partner_config_service.create_partner_config(
                partner_config_data, partner_id
            )

        self.mock_logger.error.assert_called_with(
            "An integrity error occured: (builtins.NoneType) None\n[SQL: Integrity error]\n(Background on this error at: https://sqlalche.me/e/20/gkpj)"
        )

    async def test_create_partner_config_general_exception(self):
        partner_id= UUID("11111111-1111-1111-1111-111111111111")
        partner_config_data = PartnerConfigRequest(key="some_key", value="val")

        self.partner_config_repository.create_partner_config.side_effect = Exception(
            "Some error"
        )

        with pytest.raises(Exception):
            await self.partner_config_service.create_partner_config(
                partner_config_data, partner_id
            )

        self.mock_logger.error.assert_called_with(
            "An unexpected error occured while creating partner config: Some error"
        )

    @pytest.mark.asyncio
    async def test_get_partner_config_by_key_success(self):
        partner_id= UUID("11111111-1111-1111-1111-111111111111")
        key = "is_custom_role_permission_enabled"

        repo_config = SimpleNamespace(
            id= UUID("11111111-1111-1111-1111-111111111111"),
            partner_id=partner_id,
            key=key,
            value="val",
            created_at=76543754332,
            history=None,
        )

        # Cache miss
        self.mock_cache.get_cache.return_value = None

        # Repo now returns a LIST, not a single object
        self.partner_config_repository.get_partner_config_by_key.return_value = [
            repo_config
        ]

        self.mock_cache.set_cache.return_value = None

        result = await self.partner_config_service.get_partner_config_by_key(
            partner_id, key
        )

        # Updated log assertion to match new log
        self.mock_logger.info.assert_any_call(
            "Trying to get partner config for partner id(s): {}".format([partner_id])
        )

        # Updated repository call assertion
        self.partner_config_repository.get_partner_config_by_key.assert_awaited_once_with(
            [partner_id], key
        )

        # Cache must be set
        self.mock_cache.set_cache.assert_awaited()

        # Output validation
        assert result.key == key
        assert result.value == "val"
        assert result.created_at == 76543754332

    @pytest.mark.asyncio
    async def test_get_partner_config_by_key_cache_hit(self):
        partner_id= UUID("11111111-1111-1111-1111-111111111111")
        key = "is_custom_role_permission_enabled"

        cached_data = {
            "id": UUID("11111111-1111-1111-1111-111111111111"),
            "partner_id": partner_id,
            "key": key,
            "value": "val",
            "created_at": 76543754332,
            "history": None,
        }

        # Simulate cache hit
        self.mock_cache.get_cache.return_value = cached_data

        result = await self.partner_config_service.get_partner_config_by_key(
            partner_id, key
        )

        # Updated log assertions to match new service logs
        self.mock_logger.info.assert_any_call(
            "Trying to get partner config for partner id(s): {}".format([partner_id])
        )

        self.mock_logger.info.assert_any_call(
            "Returning cached config for partner_id: {}".format(partner_id)
        )

        # Repo must NOT be called
        self.partner_config_repository.get_partner_config_by_key.assert_not_awaited()

        # Validate returned response
        assert result.key == key
        assert result.value == "val"
        assert result.created_at == 76543754332

    @pytest.mark.asyncio
    async def test_get_partner_config_by_key_none(self):
        partner_id= UUID("11111111-1111-1111-1111-111111111111")
        key = "is_custom_role_permission_enabled"

        # Cache miss
        self.mock_cache.get_cache.return_value = None

        # Repo returns empty list when nothing found
        self.partner_config_repository.get_partner_config_by_key.return_value = []

        result = await self.partner_config_service.get_partner_config_by_key(
            partner_id, key
        )

        # Updated log to match new service
        self.mock_logger.info.assert_any_call(
            "Trying to get partner config for partner id(s): {}".format([partner_id])
        )

        # Repository now receives a LIST of IDs
        self.partner_config_repository.get_partner_config_by_key.assert_awaited_once_with(
            [partner_id], key
        )

        # No config found
        assert result is None

    @pytest.mark.asyncio
    async def test_get_partner_config_partner_config_exception(self):
        partner_id= UUID("11111111-1111-1111-1111-111111111111")
        key = "is_custom_role_permission_enabled"

        # Cache miss
        self.mock_cache.get_cache.return_value = None

        # Raise domain-specific exception
        self.partner_config_repository.get_partner_config_by_key.side_effect = (
            PartnerConfigException("Not found")
        )

        with pytest.raises(PartnerConfigException):
            await self.partner_config_service.get_partner_config_by_key(partner_id, key)

        # Updated log assertion
        self.mock_logger.error.assert_called_with(
            "No partner config found for partner id(s): {}".format(partner_id)
        )

        # Repo called with list
        self.partner_config_repository.get_partner_config_by_key.assert_awaited_once_with(
            [partner_id], key
        )

    @pytest.mark.asyncio
    async def test_get_partner_config_general_exception(self):
        partner_id= UUID("11111111-1111-1111-1111-111111111111")
        key = "is_custom_role_permission_enabled"

        self.mock_cache.get_cache.return_value = None

        self.partner_config_repository.get_partner_config_by_key.side_effect = (
            Exception("Some error")
        )

        with pytest.raises(Exception):
            await self.partner_config_service.get_partner_config_by_key(partner_id, key)

        # Updated log assertion
        self.mock_logger.error.assert_called_with(
            "Unexpected error occurred while getting partner config: Some error"
        )

        # Repo called with list
        self.partner_config_repository.get_partner_config_by_key.assert_awaited_once_with(
            [partner_id], key
        )

    async def test_update_partner_config_success(self):
        partner_id= UUID("11111111-1111-1111-1111-111111111111")
        current_user = {
            CurrentUserMap.USER_ID: UUID("42424242-4242-4242-4242-424242424242"),
            CurrentUserMap.PARTNER_ID: partner_id,  # auth pass
        }
        update_partner_config_data = PartnerConfigData(is_talko_enabled=True)

        repo_response = [
            SimpleNamespace(
                id= UUID("11111111-1111-1111-1111-111111111111"),
                partner_id=partner_id,
                key="some_key",
                value="new_val",
                created_at=98765434567,
                updated_at=98765434568,
                updated_by= UUID("42424242-4242-4242-4242-424242424242"),
                history=None,
            )
        ]

        # Mock repository, cache, and user service
        self.partner_config_repository.update_partner_config.return_value = (
            repo_response
        )
        self.mock_cache.clear_pattern.return_value = None

        mock_user_service = AsyncMock()
        mock_user_service.is_user_internal.return_value = False

        # Mock user session service to avoid DB calls
        mock_user_session_service = AsyncMock()
        mock_user_session_service.deactivate_all_sessions_by_partner_id.return_value = 1

        # Call service
        result = await self.partner_config_service.update_partner_config(
            partner_id,
            update_partner_config_data,
            current_user,
            user_service=mock_user_service,
            user_session_service=mock_user_session_service,  # inject mock
        )

        # Logs check
        self.mock_logger.info.assert_any_call(
            f"Fetching partner sources mapped to current user partner id: {partner_id}"
        )
        self.mock_logger.info.assert_any_call(
            f"Trying to update partner config for partner id: {partner_id}"
        )
        self.mock_logger.info.assert_any_call(
            f"Configuration setting update successfully for service board with id: {partner_id}"
        )

        # Calls check
        self.partner_config_repository.update_partner_config.assert_awaited_once()
        self.mock_cache.clear_pattern.assert_awaited()
        mock_user_session_service.deactivate_all_sessions_by_partner_id.assert_awaited_once_with(
            partner_id, None
        )

        # Result check
        assert isinstance(result, list)
        assert result[0].key == "some_key"
        assert result[0].value == "new_val"

    async def test_update_partner_config_partner_config_exception(self):
        partner_id= UUID("11111111-1111-1111-1111-111111111111")
        current_user = {
            CurrentUserMap.USER_ID: UUID("42424242-4242-4242-4242-424242424242"),
            CurrentUserMap.PARTNER_ID: partner_id,  # required for auth pass
        }
        update_partner_config_data = PartnerConfigData(
            is_talko_enabled=None
        )


        # simulate repo raising PartnerConfigException
        self.partner_config_repository.update_partner_config.side_effect = (
            PartnerConfigException("Not found")
        )

        mock_user_service = AsyncMock()
        mock_user_service.is_user_internal.return_value = False

        with pytest.raises(PartnerConfigException):
            await self.partner_config_service.update_partner_config(
                partner_id,
                update_partner_config_data,
                current_user,
                user_service=mock_user_service,
            )

        self.mock_logger.error.assert_called_with(
            f"No partner config found for partner id: {partner_id}"
        )

    async def test_update_partner_config_general_exception(self):
        partner_id= UUID("11111111-1111-1111-1111-111111111111")
        current_user = {
            CurrentUserMap.USER_ID: UUID("42424242-4242-4242-4242-424242424242"),
            CurrentUserMap.PARTNER_ID: partner_id,  # required for auth pass
        }
        update_partner_config_data = PartnerConfigData(
            is_talko_enabled=None
        )

        # simulate repo raising generic Exception
        self.partner_config_repository.update_partner_config.side_effect = Exception(
            "Some error"
        )

        mock_user_service = AsyncMock()
        mock_user_service.is_user_internal.return_value = False

        with pytest.raises(Exception):
            await self.partner_config_service.update_partner_config(
                partner_id,
                update_partner_config_data,
                current_user,
                user_service=mock_user_service,
            )

        self.mock_logger.error.assert_called_with(
            "An unexpected error occured while updating partner config: Some error"
        )

    async def test_get_partner_configs_by_partner_id_success(self):
        partner_id= UUID("11111111-1111-1111-1111-111111111111")
        mock_response = [
            SimpleNamespace(
                id= UUID("11111111-1111-1111-1111-111111111111"),
                partner_id=partner_id,
                key="key1",
                value="val1",
                history=["h1", "h2", "h3", "h4", "h5", "h6"],
                created_at=1234567890,
                created_by= UUID("42424242-4242-4242-4242-424242424242"),
            ),
            SimpleNamespace(
                id= UUID("22222222-2222-2222-2222-222222222222"),
                partner_id=partner_id,
                key="key2",
                value="val2",
                history=None,
                created_at=1234567891,
                created_by= UUID("43434343-4343-4343-4343-434343434343"),
            ),
        ]
        self.mock_cache.get_cache.return_value = None
        self.partner_config_repository.get_partner_configs_by_partner_id.return_value = (
            mock_response
        )
        self.mock_cache.set_cache.return_value = None

        result = await self.partner_config_service.get_partner_configs_by_partner_id(
            partner_id
        )

        self.mock_logger.info.assert_any_call(
            f"Trying to get all partner configs for partner id: {partner_id}"
        )
        self.mock_logger.info.assert_any_call(
            f"Configuration settings fetched successfully for service board with id: {partner_id}"
        )
        self.partner_config_repository.get_partner_configs_by_partner_id.assert_awaited_once_with(
            partner_id
        )
        self.mock_cache.set_cache.assert_awaited()
        assert isinstance(result, list)
        assert result[0].key == "is_custom_role_permission_enabled"
        assert result[0].history == None
        assert result[1].history is None

    async def test_get_partner_configs_by_partner_id_general_exception(self):
        partner_id= UUID("11111111-1111-1111-1111-111111111111")
        self.mock_cache.get_cache.return_value = None
        self.partner_config_repository.get_partner_configs_by_partner_id.side_effect = (
            Exception("Some error")
        )

        with pytest.raises(Exception):
            await self.partner_config_service.get_partner_configs_by_partner_id(
                partner_id
            )

        self.mock_logger.error.assert_called_with(
            "An unexpected error occured while getting all partner configs: Some error"
        )

    async def test_custom_role_permission_check_enabled(self):
        user_id= UUID("42424242-4242-4242-4242-424242424242")
        partner_id= UUID("11111111-1111-1111-1111-111111111111")

        # Mocks
        mock_auth_repo = AsyncMock()
        mock_user_service = AsyncMock()
        mock_user_config_repo = AsyncMock()
        mock_user_repo = AsyncMock()

        # Mock User
        mock_user = SimpleNamespace(partner_id=partner_id, is_internal=True)
        mock_user_service.get_user_by_id.return_value = mock_user

        # Mock system admin user (not the current user)
        mock_sys_admin = SimpleNamespace(id= UUID("11111111-1111-1111-1111-111111111111"))
        mock_user_repo.get_system_admin_user.return_value = mock_sys_admin

        # Mock PartnerConfig: custom role permission enabled
        mock_partner_config = SimpleNamespace(
            id= UUID("11111111-1111-1111-1111-111111111111"),
            partner_id=partner_id,
            key="is_custom_role_enabled",
            value=True,
            created_at=1234567890,
            history=None,
        )
        self.partner_config_repository.get_partner_config_by_key.return_value = (
            mock_partner_config
        )

        # Mock UserConfig: not a super admin
        mock_user_config = UserConfig(
            id= UUID("11111111-1111-1111-1111-111111111111"),
            user_id=user_id,
            key="is_super_admin",
            value=False,
            created_at=1234567890,
            history=None,
        )
        mock_user_config_repo.get_user_config_by_key.return_value = mock_user_config

        # Permissions
        mock_auth_repo.get_user_permission.return_value = ["perm1", "perm2"]
        mock_auth_repo.get_default_role_permission_for_user.return_value = [
            "perm2",
            "perm3",
        ]

        # Execute
        result = await self.partner_config_service.custom_role_permission_check(
            user_id,
            auth_repo=mock_auth_repo,
            user_service=mock_user_service,
            user_config_repo=mock_user_config_repo,
            user_repo=mock_user_repo,
        )

        # Assertions
        self.mock_logger.info.assert_any_call(
            "Getting user object to get partner id..."
        )
        self.mock_logger.info.assert_any_call(
            f"checking the custom role permission value for partner id: {partner_id}"
        )
        assert set(result) == {"perm1", "perm2", "perm3"}

    async def test_custom_role_permission_check_disabled(self):
        user_id= UUID("42424242-4242-4242-4242-424242424242")
        partner_id= UUID("11111111-1111-1111-1111-111111111111")

        # Mocks
        mock_auth_repo = AsyncMock()
        mock_user_service = AsyncMock()
        mock_user_config_repo = AsyncMock()
        mock_user_repo = AsyncMock()

        # Mock User
        mock_user = SimpleNamespace(partner_id=partner_id, is_internal=False)
        mock_user_service.get_user_by_id.return_value = mock_user

        # Mock system admin user (not the current user)
        mock_sys_admin = SimpleNamespace(id= UUID("11111111-1111-1111-1111-111111111111"))
        mock_user_repo.get_system_admin_user.return_value = mock_sys_admin

        # Mock PartnerConfig: custom role permission disabled
        mock_partner_config = SimpleNamespace(
            id= UUID("11111111-1111-1111-1111-111111111111"),
            partner_id=partner_id,
            key="is_custom_role_enabled",
            value=False,
            created_at=1234567890,
            history=None,
        )
        self.partner_config_repository.get_partner_config_by_key.return_value = (
            mock_partner_config
        )

        # Mock UserConfig: not a super admin
        mock_user_config = UserConfig(
            id= UUID("11111111-1111-1111-1111-111111111111"),
            user_id=user_id,
            key="is_super_admin",
            value=False,
            created_at=1234567890,
            history=None,
        )
        mock_user_config_repo.get_user_config_by_key.return_value = mock_user_config

        # Permissions
        mock_auth_repo.get_default_role_permission_for_user.return_value = [
            "permA",
            "permB",
        ]

        # Execute
        result = await self.partner_config_service.custom_role_permission_check(
            user_id,
            auth_repo=mock_auth_repo,
            user_service=mock_user_service,
            user_config_repo=mock_user_config_repo,
            user_repo=mock_user_repo,
        )

        # Assertions
        self.mock_logger.info.assert_any_call(
            "Getting user object to get partner id..."
        )
        self.mock_logger.info.assert_any_call(
            f"checking the custom role permission value for partner id: {partner_id}"
        )
        assert result == ["permA", "permB"]

    async def test_custom_role_permission_check_exception(self):
        user_id= UUID("42424242-4242-4242-4242-424242424242")
        mock_auth_repo = AsyncMock()
        mock_user_service = AsyncMock()
        mock_user_config_repo = AsyncMock()
        mock_user_repo = AsyncMock()

        # Mock system admin user (not the current user)
        mock_sys_admin = SimpleNamespace(id= UUID("11111111-1111-1111-1111-111111111111"))
        mock_user_repo.get_system_admin_user.return_value = mock_sys_admin

        mock_user_service.get_user_by_id.side_effect = Exception("Some error")
        mock_user_config = UserConfig(
            id= UUID("11111111-1111-1111-1111-111111111111"),
            user_id=user_id,
            key="is_super_admin",
            value=False,
            created_at=1234567890,
            history=None,
        )
        mock_user_config_repo.get_user_config_by_key.return_value = mock_user_config

        with pytest.raises(Exception):
            await self.partner_config_service.custom_role_permission_check(
                user_id,
                auth_repo=mock_auth_repo,
                user_service=mock_user_service,
                user_config_repo=mock_user_config_repo,
                user_repo=mock_user_repo,
            )

        self.mock_logger.error.assert_called_with(
            "An unexpected error occured while custom role permission check: Some error"
        )

    async def test_update_partner_config_auth_exception(self):
        partner_id= UUID("99999999-9999-9999-9999-999999999999")  # different from current_user partner_id
        current_user = {
            CurrentUserMap.USER_ID: UUID("42424242-4242-4242-4242-424242424242"),
            CurrentUserMap.PARTNER_ID: 1,  # mismatch to trigger auth check
        }
        update_partner_config_data = PartnerConfigData(
            is_talko_enabled=True
        )

        mock_user_service = AsyncMock()
        mock_user_service.is_user_internal.return_value = (
            False  # user is not internal → should raise
        )

        with pytest.raises(AuthException):
            await self.partner_config_service.update_partner_config(
                partner_id,
                update_partner_config_data,
                current_user,
                user_service=mock_user_service,
            )

        self.mock_logger.error.assert_called_with(
            f"Unauthorized access attempt by user id: {current_user.get(CurrentUserMap.USER_ID)} "
            f"for partner id: {partner_id}"
        )



@pytest.mark.asyncio
class TestRolePermissionCheck:
    """role_permission_check: configured permissions granted to a role (no user)."""

    @pytest.fixture(autouse=True)
    def setup(self, mock_logger):
        self.partner_config_repository = AsyncMock()
        self.service = PartnerConfigService(
            partner_config_repository=self.partner_config_repository,
            console_service_logger=mock_logger,
            console_service_cache=AsyncMock(spec=CacheHelper),
        )
        self.auth_repo = AsyncMock()

    async def _call(self, role_id):
        return await self.service.role_permission_check(
            role_id, auth_repo=self.auth_repo
        )

    async def test_system_default_role_returns_default_perms(self):
        # partner_id None -> system default role -> default permissions only.
        self.auth_repo.get_role_by_id.return_value = SimpleNamespace(
            partner_id=None, is_internal=True
        )
        self.auth_repo.get_default_role_permissions_by_role_id.return_value = [
            _perm("d1"),
            _perm("d2"),
        ]
        result = await self._call(10)
        assert set(result) == {"d1", "d2"}
        self.auth_repo.get_partner_role_permissions_by_partner_and_role.assert_not_awaited()

    async def test_partner_role_custom_disabled_returns_defaults(self):
        self.auth_repo.get_role_by_id.return_value = SimpleNamespace(
            partner_id= UUID("55555555-5555-5555-5555-555555555555"), is_internal=False
        )
        self.auth_repo.get_default_role_permissions_by_role_id.return_value = [
            _perm("d1")
        ]
        self.partner_config_repository.get_partner_config_by_key.return_value = (
            SimpleNamespace(value=False)
        )
        result = await self._call(10)
        assert set(result) == {"d1"}
        self.auth_repo.get_partner_role_permissions_by_partner_and_role.assert_not_awaited()

    async def test_partner_role_custom_enabled_unions_partner_perms(self):
        self.auth_repo.get_role_by_id.return_value = SimpleNamespace(
            partner_id= UUID("55555555-5555-5555-5555-555555555555"), is_internal=False
        )
        self.auth_repo.get_default_role_permissions_by_role_id.return_value = [
            _perm("d1")
        ]
        self.partner_config_repository.get_partner_config_by_key.return_value = (
            SimpleNamespace(value=True)
        )
        self.auth_repo.get_partner_role_permissions_by_partner_and_role.return_value = [
            _perm("p1")
        ]
        result = await self._call(10)
        assert set(result) == {"d1", "p1"}
        self.auth_repo.get_partner_role_permissions_by_partner_and_role.assert_awaited_once_with(
            UUID("55555555-5555-5555-5555-555555555555"), 10
        )

    