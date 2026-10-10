import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from sqlalchemy.exc import IntegrityError

from src.components.session_mangement.repositories import UserSessionRepository
from src.components.session_mangement.models import UserSession
from src.components.user.models import User
from src.components.user_config.models import UserConfig
from src.components.auth.constant import TokenKeys


@pytest.mark.asyncio
class TestUserSessionRepository:

    @pytest.fixture(autouse=True)
    def setup(self, mock_session_factory):
        self.repo = UserSessionRepository(session_factory=mock_session_factory)
        self.session = mock_session_factory.return_value.__aenter__.return_value

    # ---------------------------
    # create_user_session
    # ---------------------------
    async def test_create_user_session_success(self):
        data = {"user_id": 1, "session_id": "abc", "is_active": True}

        user_session_mock = MagicMock()
        with patch("src.components.session_mangement.repositories.UserSession", return_value=user_session_mock):
            self.session.add = MagicMock()
            self.session.commit = AsyncMock()
            self.session.refresh = AsyncMock()

            result = await self.repo.create_user_session(**data)

            self.session.add.assert_called_once_with(user_session_mock)
            self.session.commit.assert_awaited_once()
            self.session.refresh.assert_awaited_once_with(user_session_mock)
            assert result == user_session_mock

    # ---------------------------
    # get_user_session
    # ---------------------------
    async def test_get_user_session_success(self):
        session_id = "test_session"

        fake_result = MagicMock()
        fake_result.scalar_one_or_none.return_value = "session_obj"
        self.session.execute = AsyncMock(return_value=fake_result)

        result = await self.repo.get_user_session(session_id)

        self.session.execute.assert_awaited_once()
        assert result == "session_obj"

    async def test_get_user_session_not_found(self):
        session_id = "not_exist"

        fake_result = MagicMock()
        fake_result.scalar_one_or_none.return_value = None
        self.session.execute = AsyncMock(return_value=fake_result)

        result = await self.repo.get_user_session(session_id)
        assert result is None

    # ---------------------------
    # update_user_session
    # ---------------------------
    async def test_update_user_session_success(self):
        session_id = "abc"
        update_data = {"is_active": False}

        # UPDATE query result
        update_result = MagicMock()
        update_result.scalar_one_or_none.return_value = "updated_session"

        # REFRESH select result
        refresh_result = MagicMock()

        self.session.execute = AsyncMock(side_effect=[update_result, refresh_result])
        self.session.commit = AsyncMock()

        result = await self.repo.update_user_session(session_id, update_data)

        assert result == "updated_session"
        assert self.session.execute.await_count == 2
        self.session.commit.assert_awaited_once()

    # ---------------------------
    # deactivate_all_sessions_by_user_id
    # ---------------------------
    async def test_deactivate_all_sessions_by_user_id_single_user(self):
        self.session.execute = AsyncMock(return_value=MagicMock(rowcount=5))
        self.session.commit = AsyncMock()

        result = await self.repo.deactivate_all_sessions_by_user_id(1)

        assert result == 5
        self.session.execute.assert_awaited_once()
        self.session.commit.assert_awaited_once()

    async def test_deactivate_all_sessions_by_user_id_multiple_users(self):
        self.session.execute = AsyncMock(return_value=MagicMock(rowcount=3))
        self.session.commit = AsyncMock()

        result = await self.repo.deactivate_all_sessions_by_user_id([1, 2, 3])

        assert result == 3
        self.session.execute.assert_awaited_once()
        self.session.commit.assert_awaited_once()

    async def test_deactivate_all_sessions_by_user_id_with_service_name(self):
        self.session.execute = AsyncMock(return_value=MagicMock(rowcount=2))
        self.session.commit = AsyncMock()

        result = await self.repo.deactivate_all_sessions_by_user_id(1, service_name="MAGLO")

        assert result == 2

    # ---------------------------
    # deactivate_all_sessions_by_partner_id
    # ---------------------------
    async def test_deactivate_all_sessions_by_partner_id_success(self):
        partner_id = 5

        # Step 1: fetch user IDs
        user_result = MagicMock()
        user_result.fetchall.return_value = [(11,), (12,)]
        self.session.execute = AsyncMock(side_effect=[user_result, MagicMock(rowcount=4)])
        self.session.commit = AsyncMock()

        count, user_ids = await self.repo.deactivate_all_sessions_by_partner_id(partner_id)

        assert count == 4
        assert user_ids == [11, 12]
        assert self.session.execute.await_count == 2

    async def test_deactivate_all_sessions_by_partner_id_no_users(self):
        user_result = MagicMock()
        user_result.fetchall.return_value = []
        self.session.execute = AsyncMock(return_value=user_result)

        count, user_ids = await self.repo.deactivate_all_sessions_by_partner_id(99)

        assert count == 0
        assert user_ids == []

    async def test_deactivate_all_sessions_by_partner_id_with_service_name(self):
        partner_id = 10

        user_result = MagicMock()
        user_result.fetchall.return_value = [(1,), (2,)]

        deactivate_result = MagicMock(rowcount=3)

        self.session.execute = AsyncMock(side_effect=[user_result, deactivate_result])
        self.session.commit = AsyncMock()

        count, user_ids = await self.repo.deactivate_all_sessions_by_partner_id(partner_id, service_name="MAGLO")

        assert count == 3
        assert user_ids == [1, 2]

    # ---------------------------
    # deactivate_or_create_user_configs_by_user_ids
    # ---------------------------
    async def test_deactivate_or_create_user_configs_all_exist(self):
        user_ids = [1, 2]
        config_value = False

        # Pretend both users already have configs
        existing_configs = MagicMock()
        existing_configs.scalars.return_value.all.return_value = [1, 2]

        update_result = MagicMock(rowcount=2)

        self.session.execute = AsyncMock(side_effect=[existing_configs, update_result])
        self.session.commit = AsyncMock()

        result = await self.repo.deactivate_or_create_user_configs_by_user_ids(user_ids, config_value)

        assert result == 2  # updated only
        self.session.commit.assert_awaited_once()

    async def test_deactivate_or_create_user_configs_some_missing(self):
        user_ids = [1, 2, 3]
        config_value = False

        # Only user 1 exists
        existing_configs = MagicMock()
        existing_configs.scalars.return_value.all.return_value = [1]

        update_result = MagicMock(rowcount=1)  # updated only 1 user

        self.session.execute = AsyncMock(side_effect=[existing_configs, update_result])
        self.session.add_all = MagicMock()
        self.session.commit = AsyncMock()

        result = await self.repo.deactivate_or_create_user_configs_by_user_ids(user_ids, config_value)

        # updated:1 , new configs for:2,3 → total = 3
        assert result == 3
        self.session.add_all.assert_called_once()
        self.session.commit.assert_awaited_once()

    async def test_deactivate_or_create_user_configs_no_user_ids(self):
        result = await self.repo.deactivate_or_create_user_configs_by_user_ids([], False)
        assert result == 0


    async def test_deactivate_all_sessions_by_service_name_success(self):
        service_name = "MAGLO"

        execute_result = MagicMock(rowcount=6)
        self.session.execute = AsyncMock(return_value=execute_result)
        self.session.commit = AsyncMock()

        result = await self.repo.deactivate_all_sessions_by_service_name(service_name)

        assert result == 6
        self.session.execute.assert_awaited_once()
        self.session.commit.assert_awaited_once()

    async def test_deactivate_all_sessions_by_service_name_no_sessions(self):
        service_name = "BABBLER"

        execute_result = MagicMock(rowcount=0)
        self.session.execute = AsyncMock(return_value=execute_result)
        self.session.commit = AsyncMock()

        result = await self.repo.deactivate_all_sessions_by_service_name(service_name)

        assert result == 0
        self.session.execute.assert_awaited_once()
        self.session.commit.assert_awaited_once()
