from uuid import UUID
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, Mock

import pytest
from sqlalchemy.exc import IntegrityError

from src.components.user.errors import UserNotFoundError
from src.components.user_config.models import UserConfig
from src.components.user_config.schemas import (
    UserConfigBase,
    UserConfigData,
    UserConfigRequest,
    UserConfigResponse,
)
from src.components.user_config.services import UserConfigService
from src.components.user_config.constants import UserConfigEnum
from src.exceptions import UserConfigException


@pytest.mark.asyncio
class TestUserConfigService:

    @pytest.fixture(autouse=True)
    def setup(self):
        self.repo = AsyncMock()
        self.logger = Mock()
        self.cache = AsyncMock()

        self.service = UserConfigService(
            user_config_repository=self.repo,
            console_service_logger=self.logger,
            console_service_cache=self.cache,
        )

    async def test_create_user_config_success(self):
        user_id= UUID("11111111-1111-1111-1111-111111111111")
        partner_id= UUID("10010010-0100-1001-0010-010010010010")  # any arbitrary partner ID
        current_user = {
            "user_id": user_id,
            "partner_id": partner_id,
        }

        user_service_mock = AsyncMock()
        user_mock = MagicMock()
        user_mock.partner_id = partner_id  # important fix

        user_service_mock.get_user_by_id.return_value = user_mock

        request = UserConfigRequest(user_id=user_id, key="theme", value="dark")
        fake_config = UserConfig(
            key="theme",
            value="dark",
            user_id=user_id,
            created_at=int(datetime.now(timezone.utc).timestamp()),
        )

        self.repo.create_user_config.return_value = fake_config

        result = await self.service.create_user_config(
            request, current_user, user_service=user_service_mock
        )

        assert isinstance(result, UserConfigResponse)
        assert result.key == "theme"
        self.repo.create_user_config.assert_awaited_once_with(
            UserConfigBase(key="theme", value="dark", user_id=user_id)
        )
        self.cache.clear_pattern.assert_awaited_once()

    async def test_create_user_config_integrity_error(self):
        user_id= UUID("11111111-1111-1111-1111-111111111111")
        partner_id= UUID("10010010-0100-1001-0010-010010010010")  # any arbitrary partner ID
        current_user = {
            "user_id": user_id,
            "partner_id": partner_id,
        }

        user_service_mock = AsyncMock()
        user_mock = MagicMock()
        user_mock.partner_id = partner_id  # important fix

        user_service_mock.get_user_by_id.return_value = user_mock
        request = UserConfigRequest(user_id= UUID("11111111-1111-1111-1111-111111111111"), key="theme", value="dark")
        self.repo.create_user_config.side_effect = IntegrityError(
            "Integrity", None, None
        )

        with pytest.raises(IntegrityError):
            await self.service.create_user_config(
                request, current_user, user_service=user_service_mock
            )

        self.logger.error.assert_called_once()

    async def test_get_user_config_by_key_cached(self):
        user_id= UUID("11111111-1111-1111-1111-111111111111")
        key = "lang"
        cached_data = {
            "key": "lang",
            "value": "en",
            "user_id": user_id,
            "created_at": int(datetime.now(timezone.utc).timestamp()),
        }
        self.cache.get_cache.return_value = cached_data

        result = await self.service.get_user_config_by_key(user_id, key)

        assert isinstance(result, UserConfigResponse)
        assert result.key == "lang"
        self.repo.get_user_config_by_key.assert_not_called()

    async def test_get_user_config_by_key_db_fallback(self):
        user_id= UUID("11111111-1111-1111-1111-111111111111")
        key = "theme"
        fake_config = UserConfig(
            key="theme",
            value="light",
            user_id=user_id,
            created_at=int(datetime.now(timezone.utc).timestamp()),
        )
        self.cache.get_cache.return_value = None
        self.repo.get_user_config_by_key.return_value = fake_config

        result = await self.service.get_user_config_by_key(user_id, key)

        assert isinstance(result, UserConfigResponse)
        assert result.key == "theme"
        self.repo.get_user_config_by_key.assert_awaited_once_with(user_id, key)
        self.cache.set_cache.assert_awaited_once()

    async def test_get_user_config_by_key_not_found(self):
        user_id= UUID("11111111-1111-1111-1111-111111111111")
        key = "nonexistent"
        self.cache.get_cache.return_value = None
        self.repo.get_user_config_by_key.side_effect = UserConfigException("Not found")

        with pytest.raises(UserConfigException):
            await self.service.get_user_config_by_key(user_id, key)

        self.logger.error.assert_called_once()

    async def test_update_user_config_success(self):
        partner_id= UUID("10010010-0100-1001-0010-010010010010")
        user_ids = [UUID("11111111-1111-1111-1111-111111111111"), UUID("22222222-2222-2222-2222-222222222222")]
        current_user = {"user_id": 10, "partner_id": partner_id}
        update_data = UserConfigData(theme="dark")

        fake_updated = [
            UserConfig(
                id= UUID("11111111-1111-1111-1111-111111111111"),
                user_id= UUID("11111111-1111-1111-1111-111111111111"),
                key="theme",
                value="dark",
                created_at=int(datetime.now(timezone.utc).timestamp()),
                history=[],
            ),
            UserConfig(
                id= UUID("22222222-2222-2222-2222-222222222222"),
                user_id= UUID("22222222-2222-2222-2222-222222222222"),
                key="theme",
                value="dark",
                created_at=int(datetime.now(timezone.utc).timestamp()),
                history=[],
            ),
        ]
        self.repo.update_user_config.return_value = fake_updated

        # Mock user_service.get_users_by_user_ids to return matching users
        user_service_mock = AsyncMock()
        user_service_mock.get_users_by_user_ids.return_value = [
            MagicMock(id= UUID("11111111-1111-1111-1111-111111111111"), partner_id=partner_id),
            MagicMock(id= UUID("22222222-2222-2222-2222-222222222222"), partner_id=partner_id),
        ]
        # Patch is_user_internal to return False
        user_service_mock.is_user_internal.return_value = False

        # Patch the service to inject the mock user_service
        self.service._UserConfigService__user_service = user_service_mock

        user_session_service = AsyncMock()
        user_session_service.deactivate_user_sessions.return_value = None
        result = await self.service.update_user_config(
            partner_id, user_ids, update_data, current_user, user_service=user_service_mock, user_session_service=user_session_service
        )

        assert len(result) == 2
        assert all(isinstance(r, UserConfigResponse) for r in result)
        assert result[0].key == "theme"
        assert result[1].key == "theme"
        self.repo.update_user_config.assert_awaited_once_with(user_ids, update_data)

    async def test_update_user_config_exception(self):
        partner_id= UUID("10010010-0100-1001-0010-010010010010")
        user_ids = [UUID("11111111-1111-1111-1111-111111111111")]
        current_user = {"user_id": 10, "partner_id": partner_id}
        update_data = UserConfigData(theme="dark")
        self.repo.update_user_config.side_effect = Exception("Unexpected")

        # Mock user_service.get_users_by_user_ids to return matching users
        user_service_mock = AsyncMock()
        user_service_mock.get_users_by_user_ids.return_value = [
            MagicMock(id= UUID("11111111-1111-1111-1111-111111111111"), partner_id=partner_id)
        ]
        user_service_mock.is_user_internal.return_value = False

        self.service._UserConfigService__user_service = user_service_mock

        with pytest.raises(Exception):
            await self.service.update_user_config(
                partner_id, user_ids, update_data, current_user, user_service=user_service_mock
            )

        self.logger.error.assert_called_once()

    async def test_get_user_configs_by_user_id_db_fallback(self):
        user_id= UUID("11111111-1111-1111-1111-111111111111")
        self.cache.get_cache.return_value = None

        # Use a key that exists in REQUIRED_KEYS
        mock_config = UserConfig(
            id= UUID("11111111-1111-1111-1111-111111111111"),
            user_id=user_id,
            key=UserConfigEnum.IS_TALKO_ENABLED.value,  # "is_talko_enabled"
            value=True,
            history=[],
            created_at=int(datetime(2024, 1, 1, tzinfo=timezone.utc).timestamp()),
        )
        self.repo.get_user_configs_by_user_id.return_value = [mock_config]

        result = await self.service.get_user_configs_by_user_id(user_id)

        # Always returns all REQUIRED_KEYS entries
        assert len(result) == len(UserConfigEnum)

        # The DB row is used for is_talko_enabled
        talko = next(r for r in result if r.key == UserConfigEnum.IS_TALKO_ENABLED.value)
        assert talko.id == UUID("11111111-1111-1111-1111-111111111111")
        assert talko.value is True
        assert talko.created_at == int(datetime(2024, 1, 1, tzinfo=timezone.utc).timestamp())

        # Keys not in DB get False defaults with no created_at
        obotaai = next(r for r in result if r.key == UserConfigEnum.IS_OBOTAAI_ENABLED.value)
        assert obotaai.id is None
        assert obotaai.value is False
        assert obotaai.created_at is None

    async def test_create_user_config_raises_generic_exception(self):
        user_id= UUID("11111111-1111-1111-1111-111111111111")
        partner_id= UUID("10110110-1101-1011-0110-110110110110")
        current_user = {
            "user_id": user_id,
            "partner_id": partner_id,
        }

        request = UserConfigRequest(
            user_id=user_id, key="notifications", value="enabled"
        )

        # Create mock user with matching partner_id
        user_mock = MagicMock()
        user_mock.partner_id = partner_id

        user_service_mock = AsyncMock()
        user_service_mock.get_user_by_id.return_value = user_mock

        # Simulate unexpected exception in repository method
        self.repo.create_user_config.side_effect = Exception("Unexpected DB error")

        with pytest.raises(Exception) as exc_info:
            await self.service.create_user_config(
                request, current_user, user_service=user_service_mock
            )

        assert "Unexpected DB error" in str(exc_info.value)
        self.logger.error.assert_called_with(
            "An unexpected error occured: Unexpected DB error"
        )

    async def test_create_user_config_partner_id_mismatch(self):
        user_id= UUID("11111111-1111-1111-1111-111111111111")
        request = UserConfigRequest(user_id=user_id, key="theme", value="dark")

        current_user = {
            "user_id": user_id,
            "partner_id": 10,
        }

        user_service_mock = AsyncMock()
        user_mock = MagicMock()
        user_mock.partner_id= UUID("20202020-2020-2020-2020-202020202020")  # mismatch with current_user['partner_id']
        user_service_mock.get_user_by_id.return_value = user_mock

        with pytest.raises(UserConfigException) as exc_info:
            await self.service.create_user_config(
                request, current_user, user_service=user_service_mock
            )

        assert (
            str(exc_info.value)
            == "cant create the user config for different partner's user"
        )
        self.logger.error.assert_called_with(
            "User config exception occured: cant create the user config for different partner's user"
        )

    async def test_create_user_config_raises_user_not_found_error(self):
        user_id= UUID("11111111-1111-1111-1111-111111111111")
        partner_id= UUID("10110110-1101-1011-0110-110110110110")
        current_user = {
            "user_id": user_id,
            "partner_id": partner_id,
        }

        request = UserConfigRequest(user_id=user_id, key="language", value="en")

        user_service_mock = AsyncMock()
        user_service_mock.get_user_by_id.return_value = None  # Simulate user not found

        with pytest.raises(UserNotFoundError) as exc_info:
            await self.service.create_user_config(
                request, current_user, user_service=user_service_mock
            )

        assert str(exc_info.value) == f"User not found, id: {user_id}"
        self.logger.error.assert_called_with(
            "Not found error occured: User not found, id: 11111111-1111-1111-1111-111111111111"
        )

