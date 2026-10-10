import pytest
from unittest.mock import AsyncMock, MagicMock
from types import SimpleNamespace
from sqlalchemy.exc import IntegrityError

from src.components.session_mangement.errors import UserSessionNotFoundError
from src.components.session_mangement.models import UserSession
from src.components.session_mangement.services import UserSessionService
from src.components.cache.helper import CacheHelper


@pytest.mark.asyncio
class TestUserSessionService:

    @pytest.fixture(autouse=True)
    def setup_service(self, mock_logger):
        self.repo = AsyncMock()
        self.cache = AsyncMock(spec=CacheHelper)
        self.logger = mock_logger

        self.service = UserSessionService(
            user_session_repository=self.repo,
            console_service_logger=self.logger,
            user_session_service_cache=self.cache
        )

    # ----------------------------------------------------------------------
    # CREATE SESSION TESTS
    # ----------------------------------------------------------------------
    async def test_create_user_session_success(self):
        session_data = {"user_id": 1, "service_name": "abc"}

        repo_response = SimpleNamespace(session_id="xyz123", user_id=1)
        self.repo.create_user_session.return_value = repo_response

        result = await self.service.create_user_session(session_data)

        assert result.session_id == "xyz123"
        self.logger.info.assert_any_call(
            f"Creating user session with data: {session_data}"
        )
        self.logger.info.assert_any_call(
            f"User session created successfully with ID: {repo_response.session_id}"
        )

    async def test_create_user_session_integrity_error(self):
        session_data = {"user_id": 1}

        self.repo.create_user_session.side_effect = IntegrityError("bad", None, None)

        result = await self.service.create_user_session(session_data)

        # Should not raise — current code only logs!
        assert result is None

    async def test_create_user_session_general_exception(self):
        session_data = {"user_id": 1}

        self.repo.create_user_session.side_effect = Exception("boom")

        with pytest.raises(Exception):
            await self.service.create_user_session(session_data)

        self.logger.error.assert_called_with(
            "Error occurred while creating user session: boom"
        )

    # ----------------------------------------------------------------------
    # GET SESSION TESTS
    # ----------------------------------------------------------------------
    async def test_get_user_session_success(self):
        session_id = "abc123"

        repo_session = SimpleNamespace(session_id=session_id)
        self.repo.get_user_session.return_value = repo_session

        result = await self.service.get_user_session(session_id)

        assert result.session_id == session_id
        self.logger.info.assert_any_call(
            f"Getting user session with ID: {session_id}"
        )

    async def test_get_user_session_not_found(self):
        session_id = "abc123"
        self.repo.get_user_session.return_value = None

        with pytest.raises(UserSessionNotFoundError):
            await self.service.get_user_session(session_id)

        self.logger.error.assert_called_with(
            f"User session not found with ID: {session_id}"
        )

    async def test_get_user_session_general_exception(self):
        session_id = "abc123"
        self.repo.get_user_session.side_effect = Exception("fail")

        with pytest.raises(Exception):
            await self.service.get_user_session(session_id)

        self.logger.error.assert_called_with(
            f"Error occurred while retrieving user session with ID: {session_id} Error: fail"
        )

    # ----------------------------------------------------------------------
    # UPDATE SESSION TESTS
    # ----------------------------------------------------------------------
    async def test_update_user_session_success(self):
        session_id = "abc123"
        update_data = {"service_name": "new"}

        repo_session = SimpleNamespace(session_id=session_id, service_name="new")
        self.repo.update_user_session.return_value = repo_session

        result = await self.service.update_user_session(session_id, update_data)

        assert result.session_id == session_id
        self.logger.info.assert_called_with(
            f"User session with ID {session_id} updated successfully."
        )

    async def test_update_user_session_not_found(self):
        session_id = "abc123"
        self.repo.update_user_session.return_value = None

        with pytest.raises(UserSessionNotFoundError):
            await self.service.update_user_session(session_id, {"x": 1})


    async def test_update_user_session_general_exception(self):
        session_id = "abc123"
        self.repo.update_user_session.side_effect = Exception("X")

        with pytest.raises(Exception):
            await self.service.update_user_session(session_id, {})

        self.logger.error.assert_called_with(
            f"Error occurred while updating user session with ID: {session_id} Error: X"
        )

    # ----------------------------------------------------------------------
    # DEACTIVATE SESSIONS TESTS
    # ----------------------------------------------------------------------
    async def test_deactivate_user_sessions_success(self):
        user_id = 1
        self.repo.deactivate_all_sessions_by_user_id.return_value = 3

        result = await self.service.deactivate_user_sessions(user_id)

        assert result == 3
        self.repo.deactivate_all_sessions_by_user_id.assert_awaited_once_with(
            user_id, None
        )

    async def test_deactivate_user_sessions_exception(self):
        user_id = 1
        self.repo.deactivate_all_sessions_by_user_id.side_effect = Exception("oops")

        with pytest.raises(Exception):
            await self.service.deactivate_user_sessions(user_id)

        self.logger.error.assert_called()

    # ----------------------------------------------------------------------
    # DEACTIVATE ALL BY PARTNER ID TESTS
    # ----------------------------------------------------------------------
    async def test_deactivate_all_sessions_by_partner_id_success(self):
        partner_id = 99
        config = True

        self.repo.deactivate_all_sessions_by_partner_id.return_value = (
            2,  # deactivated_count
            [1, 2]  # user_ids
        )
        self.repo.deactivate_or_create_user_configs_by_user_ids.return_value = 2

        result = await self.service.deactivate_all_sessions_by_partner_id(
            partner_id, config
        )

        assert result is None
        self.logger.info.assert_any_call(
            f"Deactivating all sessions for partner_id: {partner_id}"
        )
        self.repo.deactivate_all_sessions_by_partner_id.assert_awaited_once()

    async def test_deactivate_all_sessions_by_partner_id_no_users(self):
        partner_id = 99

        self.repo.deactivate_all_sessions_by_partner_id.return_value = (0, [])

        result = await self.service.deactivate_all_sessions_by_partner_id(
            partner_id, True
        )

        assert result == 0
        self.logger.info.assert_any_call(
            f"No active sessions found for partner_id: {partner_id}"
        )

    async def test_deactivate_all_sessions_by_partner_id_exception(self):
        partner_id = 99

        self.repo.deactivate_all_sessions_by_partner_id.side_effect = Exception("bad")

        with pytest.raises(Exception):
            await self.service.deactivate_all_sessions_by_partner_id(
                partner_id, True
            )

        self.logger.error.assert_called_with(
            f"Error deactivating sessions for partner_id {partner_id}: bad"
        )


    async def test_deactivate_all_sessions_by_service_name_success(self):
        service_name = "MAGLO"

        self.repo.deactivate_all_sessions_by_service_name.return_value = 4

        result = await self.service.deactivate_all_sessions_by_service_name(service_name)

        assert result == "4 sessions have been deactivated"

        self.logger.info.assert_any_call(
            f"Deactivating all sessions for service_name: {service_name}"
        )
        self.logger.info.assert_any_call(
            f"Successfully deactivated 4 sessions for service_name: {service_name}"
        )

        self.repo.deactivate_all_sessions_by_service_name.assert_awaited_once_with(
            service_name
        )

    async def test_deactivate_all_sessions_by_service_name_no_sessions(self):
        service_name = "BABBLER"

        self.repo.deactivate_all_sessions_by_service_name.return_value = 0

        result = await self.service.deactivate_all_sessions_by_service_name(service_name)

        assert result == "0 sessions have been deactivated"

        self.logger.info.assert_any_call(
            f"Successfully deactivated 0 sessions for service_name: {service_name}"
        )

    async def test_deactivate_all_sessions_by_service_name_exception(self):
        service_name = "TALKO"

        self.repo.deactivate_all_sessions_by_service_name.side_effect = Exception("DB error")

        with pytest.raises(Exception):
            await self.service.deactivate_all_sessions_by_service_name(service_name)

        self.logger.error.assert_called_with(
            f"Error deactivating sessions for service_name {service_name}: DB error"
        )
