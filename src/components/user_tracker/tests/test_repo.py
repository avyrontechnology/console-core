from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy.exc import SQLAlchemyError

from src.components.user_tracker.repositories import UserTrackerRepository
from src.components.user_tracker.constants import StandardStatuses, UserTrackerPartnerConfigKey
from src.components.user_tracker.errors import UserTrackerNotFoundError
from src.components.user.models import User
from src.components.partner_config.models import PartnerConfig


@pytest.mark.asyncio
class TestUserTrackerRepository:

    @pytest.fixture(autouse=True)
    def setup(self):
        # Create a mock session
        self.mock_session = AsyncMock()

        # Create a mock context manager that returns the mock session
        mock_context = AsyncMock()
        mock_context.__aenter__.return_value = self.mock_session
        mock_context.__aexit__.return_value = None

        # Create a mock session factory that returns the context manager
        self.mock_session_factory = MagicMock(return_value=mock_context)
        self.mock_logger = MagicMock()

        # Create repository instance
        self.repo = UserTrackerRepository(
            session_factory=self.mock_session_factory,
            console_service_logger=self.mock_logger
        )

    # ── get_user_current_status tests ─────────────────────────────────────

    async def test_get_user_current_status_success_with_value(self):
        """Test successfully getting user current status when user has a value"""
        # Arrange
        user_id = 1
        expected_status = "On Break"
        expected_icon = "#123456"

        # Create a mock user
        user_mock = MagicMock(spec=User)
        user_mock.current_status = expected_status
        user_mock.current_status_icon = expected_icon

        # Create a mock result that returns the user
        result_mock = MagicMock()
        result_mock.scalar_one_or_none = MagicMock(return_value=user_mock)
        self.mock_session.execute = AsyncMock(return_value=result_mock)

        # Act
        result = await self.repo.get_user_current_status(user_id)

        # Assert
        assert result == (expected_status, expected_icon)
        self.mock_session.execute.assert_awaited_once()
        self.mock_logger.info.assert_called_with(
            f"[UserTrackerRepository] Fetching current_status for user_id: {user_id}"
        )

    async def test_get_user_current_status_success_with_null(self):
        """Test getting user current status when DB value is NULL (falls back to AWAY)"""
        # Arrange
        user_id = 1

        # Create a mock user with null status
        user_mock = MagicMock(spec=User)
        user_mock.current_status = None
        user_mock.current_status_icon = None

        # Create a mock result that returns the user
        result_mock = MagicMock()
        result_mock.scalar_one_or_none = MagicMock(return_value=user_mock)
        self.mock_session.execute = AsyncMock(return_value=result_mock)

        # Act
        result = await self.repo.get_user_current_status(user_id)

        # Assert
        assert result == (StandardStatuses.AWAY, None)

    async def test_get_user_current_status_user_not_found(self):
        """Test when user does not exist"""
        # Arrange
        user_id = 999

        # Create a mock result that returns None
        result_mock = MagicMock()
        result_mock.scalar_one_or_none = MagicMock(return_value=None)
        self.mock_session.execute = AsyncMock(return_value=result_mock)

        # Act & Assert
        with pytest.raises(UserTrackerNotFoundError) as exc_info:
            await self.repo.get_user_current_status(user_id)

        assert str(user_id) in str(exc_info.value)

    async def test_get_user_current_status_db_error(self):
        """Test database error during fetch"""
        # Arrange
        user_id = 1

        self.mock_session.execute = AsyncMock(side_effect=SQLAlchemyError("DB connection error"))

        # Act & Assert
        with pytest.raises(SQLAlchemyError):
            await self.repo.get_user_current_status(user_id)

        self.mock_logger.error.assert_called_once()
        assert "DB error fetching current_status" in self.mock_logger.error.call_args[0][0]

    # ── update_user_current_status tests ─────────────────────────────────

    async def test_update_user_current_status_success(self):
        """Test successfully updating user status"""
        # Arrange
        user_id = 1
        new_status = "Offline"
        previous_status = "Active"
        new_icon = "#654321"

        # Create a mock user
        user_mock = MagicMock(spec=User)
        user_mock.current_status = previous_status

        # Create a mock result that returns the user
        result_mock = MagicMock()
        result_mock.scalar_one_or_none = MagicMock(return_value=user_mock)
        self.mock_session.execute = AsyncMock(return_value=result_mock)
        self.mock_session.commit = AsyncMock()
        self.mock_session.add = MagicMock()

        # Act
        result = await self.repo.update_user_current_status(user_id, new_status, new_icon)

        # Assert
        assert result == previous_status
        assert user_mock.current_status == new_status
        assert user_mock.current_status_icon == new_icon
        self.mock_session.add.assert_called_once_with(user_mock)
        self.mock_session.commit.assert_awaited_once()

    async def test_update_user_current_status_with_null_previous(self):
        """Test updating status when previous was NULL"""
        # Arrange
        user_id = 1
        new_status = "On Break"

        # Create a mock user with null status
        user_mock = MagicMock(spec=User)
        user_mock.current_status = None

        # Create a mock result that returns the user
        result_mock = MagicMock()
        result_mock.scalar_one_or_none = MagicMock(return_value=user_mock)
        self.mock_session.execute = AsyncMock(return_value=result_mock)
        self.mock_session.commit = AsyncMock()

        # Act
        result = await self.repo.update_user_current_status(user_id, new_status)

        # Assert
        assert result == StandardStatuses.AWAY  # Falls back to AWAY
        assert user_mock.current_status == new_status

    async def test_update_user_current_status_user_not_found(self):
        """Test updating status for non-existent user"""
        # Arrange
        user_id = 999
        new_status = "Active"

        # Create a mock result that returns None
        result_mock = MagicMock()
        result_mock.scalar_one_or_none = MagicMock(return_value=None)
        self.mock_session.execute = AsyncMock(return_value=result_mock)

        # Act & Assert
        with pytest.raises(UserTrackerNotFoundError):
            await self.repo.update_user_current_status(user_id, new_status)

        self.mock_session.commit.assert_not_awaited()

    async def test_update_user_current_status_db_error(self):
        """Test database error during update"""
        # Arrange
        user_id = 1
        new_status = "Active"

        # Create a mock user
        user_mock = MagicMock(spec=User)

        # Create a mock result that returns the user
        result_mock = MagicMock()
        result_mock.scalar_one_or_none = MagicMock(return_value=user_mock)
        self.mock_session.execute = AsyncMock(return_value=result_mock)
        self.mock_session.commit = AsyncMock(side_effect=SQLAlchemyError("Commit failed"))

        # Act & Assert
        with pytest.raises(SQLAlchemyError):
            await self.repo.update_user_current_status(user_id, new_status)

        self.mock_logger.error.assert_called_once()

    # ── get_custom_statuses tests ───────────────────────────────────────

    async def test_get_custom_statuses_success_new_format(self):
        """Test getting custom statuses with new format data"""
        # Arrange
        partner_id = 100
        expected_data = {
            "uuid1": {"display_id": "custom_1", "name": "In Meeting"},
            "uuid2": {"display_id": "custom_2", "name": "Remote"}
        }

        # Create a mock config
        config_mock = MagicMock(spec=PartnerConfig)
        config_mock.value = expected_data

        # Create mock scalars result
        scalars_mock = MagicMock()
        scalars_mock.first = MagicMock(return_value=config_mock)

        result_mock = MagicMock()
        result_mock.scalars = MagicMock(return_value=scalars_mock)
        self.mock_session.execute = AsyncMock(return_value=result_mock)

        # Act
        result = await self.repo.get_custom_statuses(partner_id)

        # Assert
        assert result == expected_data

    async def test_get_custom_statuses_success_old_format_migration(self):
        """Test getting custom statuses with old format (string values) and migrating"""
        # Arrange
        partner_id = 100
        old_format_data = {
            "key1": "In Meeting",
            "key2": "Remote"
        }

        # Create a mock config
        config_mock = MagicMock(spec=PartnerConfig)
        config_mock.value = old_format_data

        # Create mock scalars result
        scalars_mock = MagicMock()
        scalars_mock.first = MagicMock(return_value=config_mock)

        result_mock = MagicMock()
        result_mock.scalars = MagicMock(return_value=scalars_mock)
        self.mock_session.execute = AsyncMock(return_value=result_mock)

        # Act
        result = await self.repo.get_custom_statuses(partner_id)

        # Assert
        assert isinstance(result, dict)
        assert len(result) == 2
        for uid, value in result.items():
            assert "display_id" in value
            assert "name" in value
            assert value["name"] in ["In Meeting", "Remote"]

    async def test_get_custom_statuses_no_config(self):
        """Test when no config exists for partner"""
        # Arrange
        partner_id = 100

        # Create mock scalars result that returns None
        scalars_mock = MagicMock()
        scalars_mock.first = MagicMock(return_value=None)

        result_mock = MagicMock()
        result_mock.scalars = MagicMock(return_value=scalars_mock)
        self.mock_session.execute = AsyncMock(return_value=result_mock)

        # Act
        result = await self.repo.get_custom_statuses(partner_id)

        # Assert
        assert result == {}

    async def test_get_custom_statuses_db_error(self):
        """Test database error during fetch"""
        # Arrange
        partner_id = 100

        self.mock_session.execute = AsyncMock(side_effect=SQLAlchemyError("DB error"))

        # Act & Assert
        with pytest.raises(SQLAlchemyError):
            await self.repo.get_custom_statuses(partner_id)

        self.mock_logger.error.assert_called_once()

    async def test_get_custom_statuses_migration_with_existing_display_ids(self):
        """Test migration when some entries already have display_ids"""
        # Arrange
        partner_id = 100
        mixed_data = {
            "uuid1": {"display_id": "custom_5", "name": "Meeting"},
            "key2": "Remote"  # old format
        }

        # Create a mock config
        config_mock = MagicMock(spec=PartnerConfig)
        config_mock.value = mixed_data

        # Create mock scalars result
        scalars_mock = MagicMock()
        scalars_mock.first = MagicMock(return_value=config_mock)

        result_mock = MagicMock()
        result_mock.scalars = MagicMock(return_value=scalars_mock)
        self.mock_session.execute = AsyncMock(return_value=result_mock)

        # Act
        result = await self.repo.get_custom_statuses(partner_id)

        # Assert
        assert len(result) == 2
        # Check that the migrated entry got the next display_id
        migrated_entry = [v for v in result.values() if v["name"] == "Remote"][0]
        assert migrated_entry["display_id"] == "custom_6"  # Should be next after 5

    async def test_get_custom_statuses_migration_with_malformed_display_ids(self):
        """Test migration when display_ids are malformed"""
        # Arrange
        partner_id = 100
        mixed_data = {
            "uuid1": {"display_id": "custom_abc", "name": "Meeting"},
            "key2": "Remote"  # old format
        }

        # Create a mock config
        config_mock = MagicMock(spec=PartnerConfig)
        config_mock.value = mixed_data

        # Create mock scalars result
        scalars_mock = MagicMock()
        scalars_mock.first = MagicMock(return_value=config_mock)

        result_mock = MagicMock()
        result_mock.scalars = MagicMock(return_value=scalars_mock)
        self.mock_session.execute = AsyncMock(return_value=result_mock)

        # Act
        result = await self.repo.get_custom_statuses(partner_id)

        # Assert
        assert len(result) == 2
        # Should still migrate the old format entry
        migrated_entry = [v for v in result.values() if v["name"] == "Remote"][0]
        assert migrated_entry["display_id"] == "custom_1"

    # ── upsert_custom_statuses tests ────────────────────────────────────

    async def test_upsert_custom_statuses_update_existing(self):
        """Test updating existing custom statuses config"""
        # Arrange
        partner_id = 100
        updated_by = 1
        custom_statuses = {
            "uuid1": {"display_id": "custom_1", "name": "Updated Name"}
        }

        # Create a mock config
        config_mock = MagicMock(spec=PartnerConfig)
        config_mock.value = {"old": "data"}
        config_mock.update_history = MagicMock()

        # Create mock scalars result
        scalars_mock = MagicMock()
        scalars_mock.first = MagicMock(return_value=config_mock)

        result_mock = MagicMock()
        result_mock.scalars = MagicMock(return_value=scalars_mock)
        self.mock_session.execute = AsyncMock(return_value=result_mock)
        self.mock_session.commit = AsyncMock()
        self.mock_session.refresh = AsyncMock()

        # Act
        result = await self.repo.upsert_custom_statuses(partner_id, custom_statuses, updated_by)

        # Assert
        assert result == custom_statuses
        assert config_mock.value == custom_statuses
        assert config_mock.updated_by == updated_by
        config_mock.update_history.assert_called_once_with({"old": "data"}, custom_statuses)

    async def test_upsert_custom_statuses_create_new(self):
        """Test creating new custom statuses config"""
        # Arrange
        partner_id = 100
        updated_by = 1
        custom_statuses = {
            "uuid1": {"display_id": "custom_1", "name": "New Status"}
        }

        # Create mock scalars result that returns None (no existing config)
        scalars_mock = MagicMock()
        scalars_mock.first = MagicMock(return_value=None)

        result_mock = MagicMock()
        result_mock.scalars = MagicMock(return_value=scalars_mock)
        self.mock_session.execute = AsyncMock(return_value=result_mock)
        self.mock_session.commit = AsyncMock()
        self.mock_session.refresh = AsyncMock()
        self.mock_session.add = MagicMock()

        # We don't need to mock the PartnerConfig constructor with a return_value
        # Instead, we'll let it create a real object and capture it
        added_config = None

        def verify_add(config):
            nonlocal added_config
            added_config = config
            # Verify the config has the right properties
            assert config.partner_id == partner_id
            assert config.key == UserTrackerPartnerConfigKey.USER_TRACKER_STATUSES
            assert config.value == custom_statuses
            assert config.is_active is True

        self.mock_session.add.side_effect = verify_add

        # Mock the PartnerConfig constructor to return a real object with our properties
        def create_config(*args, **kwargs):
            config = MagicMock(spec=PartnerConfig)
            config.partner_id = kwargs.get('partner_id')
            config.key = kwargs.get('key')
            config.value = kwargs.get('value')
            config.is_active = kwargs.get('is_active', True)
            return config

        with patch('src.components.partner_config.models.PartnerConfig', side_effect=create_config):
            # Act
            result = await self.repo.upsert_custom_statuses(partner_id, custom_statuses, updated_by)

        # Assert
        assert result == custom_statuses

        # Verify add was called once
        assert self.mock_session.add.call_count == 1

        # Verify the added config had the right properties
        assert added_config is not None
        assert added_config.partner_id == partner_id
        assert added_config.key == UserTrackerPartnerConfigKey.USER_TRACKER_STATUSES
        assert added_config.value == custom_statuses
        assert added_config.is_active is True

        # Verify commit was called
        self.mock_session.commit.assert_awaited_once()

        # Verify refresh was called once (without checking the exact argument)
        assert self.mock_session.refresh.await_count == 1

    async def test_upsert_custom_statuses_db_error(self):
        """Test database error during upsert"""
        # Arrange
        partner_id = 100
        updated_by = 1
        custom_statuses = {"uuid1": {"display_id": "custom_1", "name": "Test"}}

        self.mock_session.execute = AsyncMock(side_effect=SQLAlchemyError("Upsert failed"))

        # Act & Assert
        with pytest.raises(SQLAlchemyError):
            await self.repo.upsert_custom_statuses(partner_id, custom_statuses, updated_by)

        self.mock_logger.error.assert_called_once()
