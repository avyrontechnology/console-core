from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy.exc import IntegrityError

from src.components.common.constants import CurrentUserMap
from src.components.partner_config.constants import PartnerConfigEnum
from src.components.partner_config.repositories import PartnerConfigRepository
from src.components.partner_config.schemas import PartnerConfigBase, PartnerConfigData


@pytest.mark.asyncio
class TestPartnerConfigRepository:

    @pytest.fixture(autouse=True)
    def setup(self, mock_session_factory, mock_logger):
        self.repo = PartnerConfigRepository(
            session_factory=mock_session_factory, console_service_logger=mock_logger
        )
        self.session = mock_session_factory.return_value.__aenter__.return_value
        self.logger = mock_logger
        self.logger.reset_mock()

    async def test_create_partner_config_success(self):
        partner_config_data = PartnerConfigBase(key="test_key", value="test_value")
        partner_id = 10
        partner_config_mock = MagicMock()

        with patch(
            "src.components.partner_config.repositories.PartnerConfig",
            return_value=partner_config_mock,
        ):
            self.session.add = MagicMock()
            self.session.commit = AsyncMock()
            self.session.refresh = AsyncMock()

            result = await self.repo.create_partner_config(
                partner_config_data, partner_id
            )

            self.session.add.assert_called_once_with(partner_config_mock)
            self.session.commit.assert_awaited_once()
            self.session.refresh.assert_awaited_once_with(partner_config_mock)
            assert result == partner_config_mock
            self.logger.info.assert_any_call(
                f"Creating partner config with current user partner id: {partner_id} and key {partner_config_data.key}"
            )

    async def test_create_partner_config_integrity_error(self):
        partner_config_data = PartnerConfigBase(key="key", value="val")
        partner_id = 1

        with patch(
            "src.components.partner_config.repositories.PartnerConfig", MagicMock()
        ):
            self.session.add = MagicMock(
                side_effect=IntegrityError("Integrity error", None, None)
            )
            self.session.commit = AsyncMock()
            self.session.refresh = AsyncMock()

            with pytest.raises(IntegrityError):
                await self.repo.create_partner_config(partner_config_data, partner_id)

            assert any(
                "Integrity error occured:" in str(call.args[0])
                and "Integrity error" in str(call.args[0])
                for call in self.logger.error.call_args_list
            )

    async def test_create_partner_config_general_exception(self):
        partner_config_data = PartnerConfigBase(key="key", value="val")
        partner_id = 1

        with patch(
            "src.components.partner_config.repositories.PartnerConfig", MagicMock()
        ):
            self.session.add = MagicMock(side_effect=Exception("Some Error"))
            with pytest.raises(Exception):
                await self.repo.create_partner_config(partner_config_data, partner_id)
            self.logger.error.assert_any_call(
                "Unexpected error occured while creating partner config: Some Error"
            )

    @pytest.mark.asyncio
    async def test_get_partner_config_by_key_success(self):
        partner_id = 1
        key = "test_key"

        fake_result = MagicMock()
        fake_result.scalars.return_value.all.return_value = ["cfg"]

        # Mock session.execute() → returns result having .scalars().all()
        self.session.execute = AsyncMock(return_value=fake_result)

        result = await self.repo.get_partner_config_by_key(partner_id, key)

        # Should return list
        assert result == ["cfg"]

        # execute must be awaited
        self.session.execute.assert_awaited_once()

        # Updated log expectation (matches your repo)
        self.logger.info.assert_any_call(
            "getting partner config for partner id: {}".format([partner_id])
        )

    async def test_get_partner_config_by_key_exception(self):
        partner_id = 1
        key = "error_key"
        self.session.execute = AsyncMock(side_effect=Exception("DB error"))

        with pytest.raises(Exception):
            await self.repo.get_partner_config_by_key(partner_id, key)
        self.logger.error.assert_any_call(
            "Unexpected error occured while getting partner config: DB error"
        )

    async def test_update_partner_config_update_existing(self):
        partner_id = 1
        user_id = 2
        update_data = PartnerConfigData(is_custom_role_permission_enabled=True)

        existing_config = MagicMock(
            key="is_custom_role_permission_enabled", value=False
        )
        existing_config.update_history = MagicMock()
        execute_mock = AsyncMock()
        scalars_mock = MagicMock()
        scalars_mock.all.return_value = [existing_config]
        execute_mock.scalars = MagicMock(return_value=scalars_mock)
        self.session.execute = AsyncMock(return_value=execute_mock)

        self.session.commit = AsyncMock()
        self.session.refresh = AsyncMock()

        result = await self.repo.update_partner_config(partner_id, update_data, user_id)

        assert result == [existing_config]
        existing_config.update_history.assert_called_once_with(False, True)
        self.session.commit.assert_awaited_once()
        self.session.refresh.assert_awaited_once_with(existing_config)

    @pytest.mark.asyncio
    async def test_update_partner_config_add_new(self):
        partner_id = 1
        user_id = 2
        update_data = PartnerConfigData(is_custom_role_permission_enabled=True)

        # Simulate no existing configs in DB
        scalars_mock = MagicMock()
        scalars_mock.all.return_value = []  # No config exists
        execute_mock = AsyncMock()
        execute_mock.scalars = MagicMock(return_value=scalars_mock)
        self.session.execute = AsyncMock(return_value=execute_mock)

        self.session.add = MagicMock()
        self.session.commit = AsyncMock()
        self.session.refresh = AsyncMock()

        result = await self.repo.update_partner_config(partner_id, update_data, user_id)

        assert len(result) == 1
        self.session.add.assert_called_once()
        self.session.refresh.assert_awaited_once()

    async def test_update_partner_config_exception(self):
        partner_id = 1
        user_id = 2
        update_data = PartnerConfigData(is_custom_role_permission_enabled=True)
        self.session.execute = AsyncMock(side_effect=Exception("Update error"))

        with pytest.raises(Exception):
            await self.repo.update_partner_config(partner_id, update_data, user_id)
        self.logger.error.assert_any_call(
            "Unexpected error occured while updating partner config: Update error"
        )

    async def test_get_partner_configs_by_partner_id_success(self):
        partner_id = 1
        config_mock = MagicMock()
        execute_mock = AsyncMock()
        scalars_mock = MagicMock()
        scalars_mock.all.return_value = [config_mock]
        execute_mock.scalars = MagicMock(return_value=scalars_mock)
        self.session.execute = AsyncMock(return_value=execute_mock)

        result = await self.repo.get_partner_configs_by_partner_id(partner_id)
        assert result == [config_mock]
        self.session.execute.assert_awaited_once()
        self.logger.info.assert_any_call(
            f"getting all partner configs for partner id: {partner_id}"
        )

    async def test_get_partner_configs_by_partner_id_exception(self):
        partner_id = 1
        self.session.execute = AsyncMock(side_effect=Exception("DB Error"))

        with pytest.raises(Exception):
            await self.repo.get_partner_configs_by_partner_id(partner_id)
        self.logger.error.assert_any_call(
            "Unexpected error occured while getting all partner configs: DB Error"
        )

    async def test_create_partner_config_commit_failure(self):
        partner_config_data = PartnerConfigBase(key="k1", value="v1")
        partner_id = 5

        with patch("src.components.partner_config.repositories.PartnerConfig"):
            self.session.add = MagicMock()
            self.session.commit = AsyncMock(side_effect=Exception("Commit Failed"))

            with pytest.raises(Exception):
                await self.repo.create_partner_config(partner_config_data, partner_id)

            self.logger.error.assert_any_call(
                "Unexpected error occured while creating partner config: Commit Failed"
            )

    async def test_get_partner_config_by_key_with_list_partner_ids(self):
        partner_ids = [2, 3]
        key = "abc"

        fake_result = MagicMock()
        fake_result.scalars.return_value.all.return_value = ["cfg1", "cfg2"]

        self.session.execute = AsyncMock(return_value=fake_result)

        result = await self.repo.get_partner_config_by_key(partner_ids, key)

        assert result == ["cfg1", "cfg2"]
        self.logger.info.assert_any_call(
            f"getting partner config for partner id: {partner_ids}"
        )

    async def test_get_partner_config_by_key_returns_empty(self):
        self.session.execute = AsyncMock(
            return_value=MagicMock(scalars=lambda: MagicMock(all=lambda: []))
        )

        result = await self.repo.get_partner_config_by_key(1, "missing")
        assert result == []

    async def test_update_partner_config_none_value_ignored(self):
        partner_id = 1
        user_id = 2
        update_data = PartnerConfigData(is_custom_role_permission_enabled=None)

        scalars_mock = MagicMock()
        scalars_mock.all.return_value = []
        self.session.execute = AsyncMock(
            return_value=MagicMock(scalars=lambda: scalars_mock)
        )

        self.session.add = MagicMock()  # should never be called
        self.session.commit = AsyncMock()

        result = await self.repo.update_partner_config(partner_id, update_data, user_id)

        assert result == []
        self.session.add.assert_not_called()
        self.session.commit.assert_awaited_once()

    async def test_update_partner_config_multiple_keys(self):
        partner_id = 1
        user_id = 99
        update_data = PartnerConfigData(
            is_custom_role_permission_enabled=True,
            is_talko_enabled=False,  # <-- use a real field instead
        )

        existing1 = MagicMock(key="is_custom_role_permission_enabled", value=False)
        existing1.update_history = MagicMock()

        existing2 = MagicMock(key="is_talko_enabled", value=True)
        existing2.update_history = MagicMock()

        scalars_mock = MagicMock()
        scalars_mock.all.return_value = [existing1, existing2]
        self.session.execute = AsyncMock(
            return_value=MagicMock(scalars=lambda: scalars_mock)
        )
        self.session.commit = AsyncMock()
        self.session.refresh = AsyncMock()

        result = await self.repo.update_partner_config(partner_id, update_data, user_id)

        assert len(result) == 2
        existing1.update_history.assert_called_once()
        existing2.update_history.assert_called_once()

    async def test_update_partner_config_commit_failure(self):
        partner_id = 1
        update_data = PartnerConfigData(is_custom_role_permission_enabled=True)

        scalars_mock = MagicMock()
        scalars_mock.all.return_value = []
        self.session.execute = AsyncMock(
            return_value=MagicMock(scalars=lambda: scalars_mock)
        )
        self.session.commit = AsyncMock(side_effect=Exception("CommitError"))

        with pytest.raises(Exception):
            await self.repo.update_partner_config(partner_id, update_data, 2)

        self.logger.error.assert_any_call(
            "Unexpected error occured while updating partner config: CommitError"
        )

    async def test_get_partner_configs_by_partner_id_empty_returns_enum_keys(self):
        scalars_mock = MagicMock()
        scalars_mock.all.return_value = []
        self.session.execute = AsyncMock(
            return_value=MagicMock(scalars=lambda: scalars_mock)
        )

        result = await self.repo.get_partner_configs_by_partner_id(1)

        enum_values = [item.value for item in PartnerConfigEnum]
        assert result == enum_values

    async def test_upsert_partner_config_updates_existing(self):
        current_user = {CurrentUserMap.PARTNER_ID: 10}
        key, value = "x", "y"

        existing = MagicMock()
        existing.value = "old"
        existing.updated_by = None

        scalars_mock = MagicMock()
        scalars_mock.first.return_value = existing

        self.session.execute = AsyncMock(
            return_value=MagicMock(scalars=lambda: scalars_mock)
        )
        self.session.commit = AsyncMock()

        result = await self.repo.upsert_partner_config(current_user, key, value)

        assert result is True
        assert existing.value == value
        assert existing.updated_by == 10

    async def test_upsert_partner_config_creates_new(self):
        current_user = {CurrentUserMap.PARTNER_ID: 5}
        key, value = "newkey", "newval"

        scalars_mock = MagicMock()
        scalars_mock.first.return_value = None

        self.session.execute = AsyncMock(
            return_value=MagicMock(scalars=lambda: scalars_mock)
        )
        self.session.add = MagicMock()
        self.session.commit = AsyncMock()

        result = await self.repo.upsert_partner_config(current_user, key, value)

        assert result is True
        self.session.add.assert_called_once()

    async def test_upsert_partner_config_commit_failure(self):
        current_user = {CurrentUserMap.PARTNER_ID: 10}
        key, value = "a", "b"

        scalars_mock = MagicMock()
        scalars_mock.first.return_value = None
        self.session.execute = AsyncMock(
            return_value=MagicMock(scalars=lambda: scalars_mock)
        )

        self.session.add = MagicMock()
        self.session.commit = AsyncMock(side_effect=Exception("CommitFail"))

        with pytest.raises(Exception):
            await self.repo.upsert_partner_config(current_user, key, value)

        self.logger.error.assert_any_call(
            "Error during upsert_partner_config: CommitFail"
        )

    async def test_upsert_partner_config_missing_partner_id(self):
        current_user = {}  # empty dict
        key, value = "k", "v"

        scalars_mock = MagicMock()
        scalars_mock.first.return_value = None
        self.session.execute = AsyncMock(
            return_value=MagicMock(scalars=lambda: scalars_mock)
        )

        self.session.add = MagicMock()
        self.session.commit = AsyncMock()

        result = await self.repo.upsert_partner_config(current_user, key, value)

        assert result is True
        self.session.add.assert_called_once()

    async def test_update_partner_config_existing_no_change(self):
        partner_id = 1
        user_id = 2
        update_data = PartnerConfigData(is_custom_role_permission_enabled=True)

        existing = MagicMock(key="is_custom_role_permission_enabled", value=True)
        existing.update_history = MagicMock()

        scalars_mock = MagicMock()
        scalars_mock.all.return_value = [existing]

        self.session.execute = AsyncMock(
            return_value=MagicMock(scalars=lambda: scalars_mock)
        )

        self.session.commit = AsyncMock()
        self.session.refresh = AsyncMock()

        result = await self.repo.update_partner_config(partner_id, update_data, user_id)

        assert result == [existing]
        existing.update_history.assert_called_once()  # or assert_not_called() if designed so
