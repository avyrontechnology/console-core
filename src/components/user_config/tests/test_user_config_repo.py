import pytest
from unittest.mock import AsyncMock, MagicMock, patch, Mock
from sqlalchemy.exc import IntegrityError

from src.components.user_config.repositories import UserConfigRepository
from src.components.user_config.schemas import UserConfigBase, UserConfigData
from src.components.user_config.models import UserConfig
from src.exceptions import PartnerConfigException


@pytest.mark.asyncio
class TestUserConfigRepository:

    @pytest.fixture(autouse=True)
    def setup(self, mock_session_factory, mock_logger):
        self.repo = UserConfigRepository(
            session_factory=mock_session_factory,
            console_service_logger=mock_logger
        )
        self.session_context_manager = AsyncMock()
        self.session = mock_session_factory.return_value.__aenter__.return_value
        self.logger = mock_logger
        self.logger.reset_mock()

    async def test_create_user_config_success(self):
        user_config_data = UserConfigBase(user_id=1, key="theme", value="dark")

        self.session.add = MagicMock()
        self.session.commit = AsyncMock()
        self.session.refresh = AsyncMock()

        result = await self.repo.create_user_config(user_config_data)

        assert isinstance(result, UserConfig)
        assert result.key == "theme"
        assert result.value == "dark"
        self.session.add.assert_called_once()
        self.session.commit.assert_awaited_once()
        self.session.refresh.assert_awaited_once()

    async def test_create_user_config_integrity_error(self):
        user_config_data = UserConfigBase(user_id = 1, key="theme", value="dark")
        
        with patch("src.components.user_config.repositories.UserConfigRepository", MagicMock()):
            self.session.add = MagicMock(side_effect=IntegrityError("Integrity error", None, None))
            self.session.commit = AsyncMock()
            self.session.refresh = AsyncMock()

            with pytest.raises(IntegrityError):
                await self.repo.create_user_config(user_config_data)

            assert any(
                "Integrity error occured:" in str(call.args[0]) and "Integrity error" in str(call.args[0])
                for call in self.logger.error.call_args_list
            )

    async def test_create_user_config_generic_exception(self):
        user_config_data = UserConfigBase(user_id = 2, key="lang", value="en")

        with patch("src.components.user_config.repositories.UserConfigRepository", MagicMock()):
            self.session.add = MagicMock(side_effect=Exception("Some Error"))

            with pytest.raises(Exception):
                await self.repo.create_user_config(user_config_data)

            self.logger.error.assert_any_call(
                "Unexpected error occured while creating user config: Some Error"
            )

    async def test_get_user_config_by_key_found(self):
        user_id = 3
        key = "theme"
        expected_config = MagicMock()

        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = expected_config
        self.session.execute = AsyncMock(return_value=result_mock)

        result = await self.repo.get_user_config_by_key(user_id, key)

        assert result == expected_config
        self.session.execute.assert_awaited_once()
        self.logger.info.assert_any_call(f"getting user config for user id: {user_id}")

    async def test_get_user_config_by_key_exception(self):
        user_id = 3
        key = "theme"
        self.session.execute = AsyncMock(side_effect=Exception("DB error"))

        with pytest.raises(Exception):
            await self.repo.get_user_config_by_key(user_id, key)

        self.logger.error.assert_any_call("Unexpected error occured while getting user config: DB error")

    

    async def test_get_user_configs_by_user_id_success(self):
        user_id = 7
        config_mock = MagicMock()
        scalars_mock = MagicMock()
        scalars_mock.all.return_value = [config_mock]
        execute_mock = AsyncMock()
        execute_mock.scalars = MagicMock(return_value=scalars_mock)
        self.session.execute = AsyncMock(return_value=execute_mock)

        result = await self.repo.get_user_configs_by_user_id(user_id)

        assert result == [config_mock]
        self.session.execute.assert_awaited_once()
        self.logger.info.assert_any_call(f"getting all user configs for user id: {user_id}")

    async def test_get_user_configs_by_user_id_exception(self):
        user_id = 7
        self.session.execute = AsyncMock(side_effect=Exception("DB Error"))

        with pytest.raises(Exception):
            await self.repo.get_user_configs_by_user_id(user_id)

        self.logger.error.assert_any_call(
            "Unexpected error occured while getting all user configs: DB Error"
        )

    async def test_update_user_config_exception(self):
        user_id = 50
        current_user_id = 5
        data = UserConfigData(theme="dark")

        self.session.execute = AsyncMock(side_effect=Exception("Update error"))

        with pytest.raises(Exception):
            await self.repo.update_user_config(user_id, data, current_user_id)
