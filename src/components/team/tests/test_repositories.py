from unittest.mock import AsyncMock, MagicMock

import pytest

from src.components.team.models import Team
from src.components.team.repositories import TeamRepository


@pytest.mark.asyncio
class TestTeamRepository:
    @pytest.fixture(autouse=True)
    def setup_class(self, mock_session_factory, mock_logger):
        """Set up the team repository using fixtures for mock session and logger."""
        self.team_repository = TeamRepository(
            session_factory=mock_session_factory, console_service_logger=mock_logger
        )
        self.session = mock_session_factory.return_value.__aenter__.return_value
        self.mock_logger = mock_logger

    async def test_create_team_flushes_before_finalizing_slug(self) -> None:
        """The row must be flushed (assigning its id) before finalize_slug runs,
        and the finalized slug must be applied to the object before commit."""
        added: dict = {}

        def fake_add(obj) -> None:
            added["team"] = obj

        async def fake_flush() -> None:
            # Simulate the DB assigning the autoincrement id on flush.
            added["team"].id = 42

        self.session.add = MagicMock(side_effect=fake_add)
        self.session.flush = AsyncMock(side_effect=fake_flush)
        self.session.commit = AsyncMock()
        self.session.refresh = AsyncMock()

        finalize_slug = MagicMock(return_value="final_team_slug_42")
        values = {"name": "Test Team", "slug": "placeholder", "partner_id": 1}

        result = await self.team_repository.create_team(
            values, user_id=9, finalize_slug=finalize_slug
        )

        # finalize_slug must observe the id assigned by flush.
        finalize_slug.assert_called_once()
        (called_team,) = finalize_slug.call_args.args
        assert called_team.id == 42

        assert isinstance(result, Team)
        assert result.slug == "final_team_slug_42"
        assert result.created_by == 9

        self.session.flush.assert_awaited_once()
        self.session.commit.assert_awaited_once()
        self.session.refresh.assert_awaited_once()

    async def test_create_team_db_error_logs_and_reraises(self) -> None:
        self.session.add = MagicMock()
        self.session.flush = AsyncMock(side_effect=Exception("db down"))

        with pytest.raises(Exception, match="db down"):
            await self.team_repository.create_team(
                {"name": "X", "slug": "x", "partner_id": 1},
                user_id=1,
                finalize_slug=MagicMock(),
            )
