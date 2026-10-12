from uuid import UUID
from types import SimpleNamespace
from typing import Any, Dict
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.components.team.constants import (
    TeamExceptionMsg,
    TeamStrictHierarchyMode,
)
from src.components.team.error import TeamException, TeamNotFoundError
from src.components.team.repositories import TeamRepository
from src.components.team.schema import (
    TeamCreate,
    TeamMemberCreate,
    TeamStrictHierarchyPolicy,
    TeamUpdate,
)
from src.components.team.service import TeamService


CURRENT_USER: Dict[str, Any] = {"user_id": UUID("11111111-1111-1111-1111-111111111111"), "partner_id": UUID("10101010-1010-1010-1010-101010101010")}


@pytest.mark.asyncio
class TestTeamService:
    @pytest.fixture(autouse=True)
    def setup(self) -> None:
        self.repo = AsyncMock(spec=TeamRepository)
        self.logger = MagicMock()
        self.audit = AsyncMock()
        self.partner_config = AsyncMock()
        # teams enabled by default
        self.partner_config.get_partner_config_by_key = AsyncMock(
            return_value=SimpleNamespace(value=True)
        )
        self.service = TeamService(
            team_repository=self.repo,
            console_service_logger=self.logger,
            audit_service=self.audit,
            partner_config_service=self.partner_config,
        )

    # ------------------------------ create -------------------------------- #

    async def test_create_team_success_sets_internal_from_partner(self) -> None:
        self.repo.get_partner.return_value = SimpleNamespace(is_internal=False)
        self.repo.create_team.return_value = SimpleNamespace(id= UUID("55555555-5555-5555-5555-555555555555"), slug="SMB_Sales_55555555-5555-5555-5555-555555555555")

        await self.service.create_team(
            TeamCreate(name="SMB Sales", partner_id= UUID("10101010-1010-1010-1010-101010101010")), CURRENT_USER
        )

        args = self.repo.create_team.call_args.args[0]
        assert args["partner_id"] == UUID("10101010-1010-1010-1010-101010101010")
        assert args["is_internal"] is False
        assert args["slug"] == "SMB_Sales"
        self.audit.log_action.assert_awaited()

    async def test_create_team_generates_slug_from_name_and_id(self) -> None:
        self.repo.get_partner.return_value = SimpleNamespace(is_internal=False)
        self.repo.create_team.return_value = SimpleNamespace(id= UUID("55555555-5555-5555-5555-555555555555"), slug="SMB_Sales_55555555-5555-5555-5555-555555555555")

        await self.service.create_team(
            TeamCreate(name="SMB Sales", partner_id= UUID("10101010-1010-1010-1010-101010101010")), CURRENT_USER
        )

        values, user_id, finalize_slug = self.repo.create_team.call_args.args
        assert values["slug"] == "SMB_Sales"
        assert finalize_slug(SimpleNamespace(id= UUID("55555555-5555-5555-5555-555555555555"))) == "SMB_Sales_55555555-5555-5555-5555-555555555555"

    async def test_create_team_slug_truncates_to_column_length(self) -> None:
        """name is at TeamCreate's max_length (128), same as Team.slug's column
        length, so appending "_{id}" must truncate the name portion to fit."""
        long_name = "A" * 128
        self.repo.get_partner.return_value = SimpleNamespace(is_internal=False)
        self.repo.create_team.return_value = SimpleNamespace(id= UUID("12345123-4512-3451-2345-123451234512"), slug="placeholder")

        await self.service.create_team(
            TeamCreate(name=long_name, partner_id= UUID("10101010-1010-1010-1010-101010101010")), CURRENT_USER
        )

        values, user_id, finalize_slug = self.repo.create_team.call_args.args
        assert values["slug"] == long_name

        final_slug = finalize_slug(SimpleNamespace(id= UUID("12345123-4512-3451-2345-123451234512")))
        assert len(final_slug) == 128
        assert final_slug == ("A" * 91) + "_12345123-4512-3451-2345-123451234512"

    async def test_create_team_blocked_when_teams_disabled(self) -> None:
        self.partner_config.get_partner_config_by_key = AsyncMock(
            return_value=SimpleNamespace(value=False)
        )
        with pytest.raises(TeamException, match=TeamExceptionMsg.TEAMS_NOT_ENABLED):
            await self.service.create_team(
                TeamCreate(name="X", partner_id= UUID("10101010-1010-1010-1010-101010101010")), CURRENT_USER
            )

    # --------------------------- parent cycle ----------------------------- #

    async def test_update_team_parent_cycle_rejected(self) -> None:
        self.repo.get_team_by_id.side_effect = [
            SimpleNamespace(id= UUID("22222222-2222-2222-2222-222222222222"), partner_id= UUID("10101010-1010-1010-1010-101010101010")),  # team being updated
            SimpleNamespace(id= UUID("33333333-3333-3333-3333-333333333333"), partner_id= UUID("10101010-1010-1010-1010-101010101010")),  # proposed parent
        ]
        self.repo.get_parent_chain_ids.return_value = [UUID("22222222-2222-2222-2222-222222222222")]  # team 2 is an ancestor
        with pytest.raises(TeamException, match=TeamExceptionMsg.PARENT_CYCLE):
            await self.service.update_team(
                UUID("22222222-2222-2222-2222-222222222222"), TeamUpdate(parent_team_id= UUID("33333333-3333-3333-3333-333333333333")), CURRENT_USER
            )

    # ------------------------------ members ------------------------------- #

    async def test_add_member_cross_partner_rejected(self) -> None:
        self.repo.get_team_by_id.return_value = SimpleNamespace(id= UUID("22222222-2222-2222-2222-222222222222"), partner_id= UUID("10101010-1010-1010-1010-101010101010"))
        self.repo.get_user.return_value = SimpleNamespace(partner_id= UUID("99999999-9999-9999-9999-999999999999"))
        with pytest.raises(
            TeamException, match=TeamExceptionMsg.MEMBER_DIFFERENT_PARTNER
        ):
            await self.service.add_member(
                UUID("22222222-2222-2222-2222-222222222222"), TeamMemberCreate(user_id= UUID("77777777-7777-7777-7777-777777777777")), CURRENT_USER
            )

    async def test_add_member_override_role_not_in_catalog(self) -> None:
        self.repo.get_team_by_id.return_value = SimpleNamespace(id= UUID("22222222-2222-2222-2222-222222222222"), partner_id= UUID("10101010-1010-1010-1010-101010101010"))
        self.repo.get_user.return_value = SimpleNamespace(partner_id= UUID("10101010-1010-1010-1010-101010101010"))
        self.repo.is_role_in_partner_catalog.return_value = False
        with pytest.raises(
            TeamException, match=TeamExceptionMsg.ROLE_NOT_IN_CATALOG
        ):
            await self.service.add_member(
                UUID("22222222-2222-2222-2222-222222222222"), TeamMemberCreate(user_id= UUID("77777777-7777-7777-7777-777777777777"), role_id= UUID("55555555-5555-5555-5555-555555555555")), CURRENT_USER
            )

    async def test_add_member_duplicate(self) -> None:
        self.repo.get_team_by_id.return_value = SimpleNamespace(id= UUID("22222222-2222-2222-2222-222222222222"), partner_id= UUID("10101010-1010-1010-1010-101010101010"))
        self.repo.get_user.return_value = SimpleNamespace(partner_id= UUID("10101010-1010-1010-1010-101010101010"))
        self.repo.is_role_in_partner_catalog.return_value = True
        self.repo.get_member.return_value = SimpleNamespace(id= UUID("11111111-1111-1111-1111-111111111111"))
        with pytest.raises(TeamException, match=TeamExceptionMsg.DUPLICATE_MEMBER):
            await self.service.add_member(
                UUID("22222222-2222-2222-2222-222222222222"), TeamMemberCreate(user_id= UUID("77777777-7777-7777-7777-777777777777")), CURRENT_USER
            )

    async def test_get_team_not_found(self) -> None:
        self.repo.get_team_by_id.return_value = None
        with pytest.raises(TeamNotFoundError):
            await self.service.get_team(UUID("12312312-3123-1231-2312-312312312312"), CURRENT_USER)

    # --------------------- strict-hierarchy policy ------------------------ #

    async def test_partial_mode_requires_start_role(self) -> None:
        with pytest.raises(
            TeamException, match=TeamExceptionMsg.START_ROLE_REQUIRED
        ):
            await self.service.configure_team_strict_hierarchy(
                TeamStrictHierarchyPolicy(mode=TeamStrictHierarchyMode.PARTIAL),
                CURRENT_USER,
            )

    async def test_partial_mode_invalid_start_role(self) -> None:
        self.repo.is_role_in_partner_catalog.return_value = False
        with pytest.raises(
            TeamException, match=TeamExceptionMsg.INVALID_START_ROLE
        ):
            await self.service.configure_team_strict_hierarchy(
                TeamStrictHierarchyPolicy(
                    mode=TeamStrictHierarchyMode.PARTIAL, start_role_id= UUID("44444444-4444-4444-4444-444444444444")
                ),
                CURRENT_USER,
            )

    async def test_full_mode_writes_config(self) -> None:
        result = await self.service.configure_team_strict_hierarchy(
            TeamStrictHierarchyPolicy(mode=TeamStrictHierarchyMode.FULL),
            CURRENT_USER,
        )
        assert result["mode"] == "full"
        assert result["start_role_id"] is None
        self.partner_config.update_partner_config.assert_awaited()

    # ------------------------------ list_teams ----------------------------- #

    async def test_list_teams_blocked_when_teams_disabled(self) -> None:
        self.partner_config.get_partner_config_by_key = AsyncMock(
            return_value=SimpleNamespace(value=False)
        )
        with pytest.raises(TeamException, match=TeamExceptionMsg.TEAMS_NOT_ENABLED):
            await self.service.list_teams(CURRENT_USER)

    async def test_list_teams_without_pagination_returns_all(self) -> None:
        rows = [
            {
                "id": UUID("11111111-1111-1111-1111-111111111111"), "name": "Sales", "slug": "sales", "description": None,
                "partner_id": UUID("10101010-1010-1010-1010-101010101010"), "parent_team_id": None, "is_internal": False,
                "is_active": True, "created_at": 1700000000, "updated_at": None,
                "member_count": 3,
            }
        ]
        self.repo.list_teams_paginated.return_value = (rows, 1, 1, 0)

        result = await self.service.list_teams(CURRENT_USER)

        self.repo.list_teams_paginated.assert_awaited_once_with(UUID("10101010-1010-1010-1010-101010101010"), None, None, None)
        assert result.total_count == 1
        assert result.total_active == 1
        assert result.total_inactive == 0
        assert result.limit is None
        assert result.offset is None
        assert len(result.data) == 1
        assert result.data[0].member_count == 3

    async def test_list_teams_applies_search_and_zero_based_pagination(self) -> None:
        self.repo.list_teams_paginated.return_value = ([], 0, 0, 0)

        await self.service.list_teams(CURRENT_USER, search_by="sal", limit=5, offset=1)

        self.repo.list_teams_paginated.assert_awaited_once_with(UUID("10101010-1010-1010-1010-101010101010"), "sal", 5, 1)

    # --------------------- get_user_associated_teams ----------------------- #

    async def test_get_user_associated_teams_blocked_when_teams_disabled(self) -> None:
        self.partner_config.get_partner_config_by_key = AsyncMock(
            return_value=SimpleNamespace(value=False)
        )
        with pytest.raises(TeamException, match=TeamExceptionMsg.TEAMS_NOT_ENABLED):
            await self.service.get_user_associated_teams(CURRENT_USER)
