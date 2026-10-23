from uuid import UUID
from types import SimpleNamespace
from typing import Any, Dict
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.components.partner_role.constants import (
    HIERARCHY_SPACING,
    MAX_PARTNER_HIERARCHY,
    MIN_PARTNER_HIERARCHY,
    PartnerRoleExceptionMsg,
    RolePlacement,
)
from src.components.partner_role.error import PartnerRoleException
from src.components.partner_role.repositories import PartnerRoleRepository
from src.components.partner_role.schema import CreatePartnerRole, UpdatePartnerRole
from src.components.partner_role.service import PartnerRoleService

CURRENT_USER: Dict[str, Any] = {"user_id": UUID("11111111-1111-1111-1111-111111111111"), "partner_id": UUID("10101010-1010-1010-1010-101010101010")}


def _role(role_id: int, hierarchy: int) -> SimpleNamespace:
    return SimpleNamespace(id=role_id, hierarchy=hierarchy)


def _full_role(
    role_id, hierarchy: int, partner_id=UUID("10101010-1010-1010-1010-101010101010"), name: str = None
) -> SimpleNamespace:
    return SimpleNamespace(
        id=role_id,
        name=name or "Role {}".format(role_id),
        slug="role_{}".format(role_id),
        hierarchy=hierarchy,
        partner_id=partner_id,
        data_scope="SUBTREE",
        is_internal=False,
        is_active=True,
        description=None,
        created_at=1700000000,
        updated_at=None,
    )


@pytest.mark.asyncio
class TestPartnerRoleService:
    @pytest.fixture(autouse=True)
    def setup(self) -> None:
        self.repo = AsyncMock(spec=PartnerRoleRepository)
        self.logger = MagicMock()
        self.audit = AsyncMock()
        self.partner_config = AsyncMock()
        self.partner_config.get_partner_config_by_key = AsyncMock(
            return_value=SimpleNamespace(value=True)
        )
        self.service = PartnerRoleService(
            partner_role_repository=self.repo,
            console_service_logger=self.logger,
            audit_service=self.audit,
            partner_config_service=self.partner_config,
        )
        # sensible defaults
        self.repo.get_partner.return_value = SimpleNamespace(is_internal=False)
        self.repo.materialize_catalog.return_value = None
        self.repo.create_role.return_value = SimpleNamespace(id= UUID("99999999-9999-9999-9999-999999999999"), slug="Regional_Lead_99")

    def _create(
        self, ref_id: int, placement: RolePlacement, base_id: int = None
    ) -> CreatePartnerRole:
        # base defaults to the reference role so happy-path tests seed from an
        # in-catalog role; pass base_id explicitly to exercise base validation.
        return CreatePartnerRole(
            name="Regional Lead",
            reference_role_id=ref_id,
            placement=placement,
            base_role_id=ref_id if base_id is None else base_id,
        )

    async def test_blocked_when_custom_roles_disabled(self) -> None:
        self.partner_config.get_partner_config_by_key = AsyncMock(
            return_value=SimpleNamespace(value=False)
        )
        with pytest.raises(
            PartnerRoleException,
            match=PartnerRoleExceptionMsg.CUSTOM_ROLES_NOT_ENABLED,
        ):
            await self.service.create_partner_role(
                self._create(UUID("11111111-1111-1111-1111-111111111111"), RolePlacement.BELOW), CURRENT_USER
            )

    async def test_internal_partner_not_supported(self) -> None:
        self.repo.get_partner.return_value = SimpleNamespace(is_internal=True)
        with pytest.raises(
            PartnerRoleException,
            match=PartnerRoleExceptionMsg.INTERNAL_NOT_SUPPORTED,
        ):
            await self.service.create_partner_role(
                self._create(UUID("11111111-1111-1111-1111-111111111111"), RolePlacement.BELOW), CURRENT_USER
            )

    async def test_bisection_below_manager_picks_midpoint(self) -> None:
        # admin=1, manager=4, team-lead=6, agent=8 ; place BELOW manager -> 5
        self.repo.get_partner_roles_ordered.return_value = [
            _role(UUID("11111111-1111-1111-1111-111111111111"), 1), _role(UUID("22222222-2222-2222-2222-222222222222"), 4), _role(UUID("33333333-3333-3333-3333-333333333333"), 6), _role(UUID("44444444-4444-4444-4444-444444444444"), 8)
        ]
        await self.service.create_partner_role(
            self._create(UUID("22222222-2222-2222-2222-222222222222"), RolePlacement.BELOW), CURRENT_USER
        )
        values = self.repo.create_role.call_args.args[0]
        assert values["hierarchy"] == 5
        assert values["data_scope"] == "SUBTREE"
        self.repo.rebalance.assert_not_called()

    async def test_bisection_below_bottom_extends_by_spacing(self) -> None:
        self.repo.get_partner_roles_ordered.return_value = [_role(UUID("22222222-2222-2222-2222-222222222222"), 4), _role(UUID("44444444-4444-4444-4444-444444444444"), 8)]
        await self.service.create_partner_role(
            self._create(UUID("44444444-4444-4444-4444-444444444444"), RolePlacement.BELOW), CURRENT_USER
        )
        values = self.repo.create_role.call_args.args[0]
        assert values["hierarchy"] == 8 + HIERARCHY_SPACING

    async def test_rebalance_triggered_when_gap_exhausted(self) -> None:
        # adjacent 4 and 5 -> no room below 4 -> rebalance then retry
        self.repo.get_partner_roles_ordered.return_value = [_role(UUID("11111111-1111-1111-1111-111111111111"), 4), _role(UUID("22222222-2222-2222-2222-222222222222"), 5)]
        self.repo.rebalance.return_value = [_role(UUID("11111111-1111-1111-1111-111111111111"), 1000), _role(UUID("22222222-2222-2222-2222-222222222222"), 2000)]
        await self.service.create_partner_role(
            self._create(UUID("11111111-1111-1111-1111-111111111111"), RolePlacement.BELOW), CURRENT_USER
        )
        self.repo.rebalance.assert_awaited_once()
        values = self.repo.create_role.call_args.args[0]
        assert values["hierarchy"] == 1500  # midpoint of 1000 and 2000

    async def test_bisection_above_picks_midpoint(self) -> None:
        # admin=1, manager=4 ; place ABOVE manager -> midpoint of 1 and 4
        self.repo.get_partner_roles_ordered.return_value = [_role(UUID("11111111-1111-1111-1111-111111111111"), 1), _role(UUID("22222222-2222-2222-2222-222222222222"), 4)]
        await self.service.create_partner_role(
            self._create(UUID("22222222-2222-2222-2222-222222222222"), RolePlacement.ABOVE), CURRENT_USER
        )
        values = self.repo.create_role.call_args.args[0]
        assert values["hierarchy"] == 2
        self.repo.rebalance.assert_not_called()

    async def test_bisection_above_top_extends_by_spacing_when_safe(self) -> None:
        # manager=200 has no lower neighbor for this partner, but
        # 200 - HIERARCHY_SPACING(100) = 100, still >= MIN_PARTNER_HIERARCHY(1)
        # -> safe, should succeed rather than raise.
        self.repo.get_partner_roles_ordered.return_value = [
            _role(UUID("11111111-1111-1111-1111-111111111111"), 200), _role(UUID("22222222-2222-2222-2222-222222222222"), 800)
        ]
        await self.service.create_partner_role(
            self._create(UUID("11111111-1111-1111-1111-111111111111"), RolePlacement.ABOVE), CURRENT_USER
        )
        values = self.repo.create_role.call_args.args[0]
        assert values["hierarchy"] == 200 - HIERARCHY_SPACING
        self.repo.rebalance.assert_not_called()

    async def test_bisection_above_top_role_at_floor_raises(self) -> None:
        # admin=1 is already the partner's most senior role -> placing ABOVE
        # it would land below MIN_PARTNER_HIERARCHY (the actual bug: this used
        # to silently return hierarchy=-99). Must raise immediately, without
        # wasting a rebalance, since rebalancing can't create room below the
        # partner's own most-senior role.
        admin = _full_role(UUID("11111111-1111-1111-1111-111111111111"), MIN_PARTNER_HIERARCHY, name="Admin")
        self.repo.get_partner_roles_ordered.return_value = [admin, _full_role(UUID("22222222-2222-2222-2222-222222222222"), 4)]
        with pytest.raises(
            PartnerRoleException,
            match="Cannot place a role above 'Admin'",
        ):
            await self.service.create_partner_role(
                self._create(UUID("11111111-1111-1111-1111-111111111111"), RolePlacement.ABOVE), CURRENT_USER
            )
        self.repo.rebalance.assert_not_called()
        self.repo.create_role.assert_not_called()

    async def test_bisection_below_ceiling_raises(self) -> None:
        # Symmetric defense-in-depth: a role already at MAX_PARTNER_HIERARCHY
        # with no lower-tier neighbor for this partner -> placing BELOW it
        # would exceed the ceiling. Must raise immediately, no rebalance.
        bottom = _full_role(UUID("11111111-1111-1111-1111-111111111111"), MAX_PARTNER_HIERARCHY, name="Bottom Tier")
        self.repo.get_partner_roles_ordered.return_value = [_full_role(UUID("22222222-2222-2222-2222-222222222222"), 4), bottom]
        with pytest.raises(
            PartnerRoleException,
            match="Cannot place a role below 'Bottom Tier'",
        ):
            await self.service.create_partner_role(
                self._create(UUID("11111111-1111-1111-1111-111111111111"), RolePlacement.BELOW), CURRENT_USER
            )
        self.repo.rebalance.assert_not_called()
        self.repo.create_role.assert_not_called()

    async def test_create_partner_role_generates_slug_from_name_and_id(self) -> None:
        self.repo.get_partner_roles_ordered.return_value = [_role(UUID("22222222-2222-2222-2222-222222222222"), 4)]
        await self.service.create_partner_role(
            self._create(UUID("22222222-2222-2222-2222-222222222222"), RolePlacement.BELOW), CURRENT_USER
        )
        values, user_id, finalize_slug = self.repo.create_role.call_args.args
        assert values["slug"] == "Regional_Lead"
        assert finalize_slug(SimpleNamespace(id=UUID("99999999-9999-9999-9999-999999999999"))) == "Regional_Lead_99999999-9999-9999-9999-999999999999"

    async def test_reference_role_not_in_catalog(self) -> None:
        self.repo.get_partner_roles_ordered.return_value = [_role(UUID("22222222-2222-2222-2222-222222222222"), 4)]
        with pytest.raises(
            PartnerRoleException,
            match=PartnerRoleExceptionMsg.REFERENCE_ROLE_NOT_FOUND,
        ):
            await self.service.create_partner_role(
                self._create(UUID("99999999-9999-9999-9999-999999999999"), RolePlacement.BELOW), CURRENT_USER
            )

    async def test_base_role_not_in_catalog(self) -> None:
        self.repo.get_partner_roles_ordered.return_value = [_role(UUID("22222222-2222-2222-2222-222222222222"), 4)]
        with pytest.raises(
            PartnerRoleException,
            match=PartnerRoleExceptionMsg.BASE_ROLE_NOT_FOUND,
        ):
            await self.service.create_partner_role(
                self._create(UUID("22222222-2222-2222-2222-222222222222"), RolePlacement.BELOW, base_id= UUID("99999999-9999-9999-9999-999999999999")), CURRENT_USER
            )
        self.repo.create_role.assert_not_called()

    async def test_base_role_id_stored_and_passed_to_create_role(self) -> None:
        # position next to role 2, but seed permissions from role 3.
        self.repo.get_partner_roles_ordered.return_value = [
            _role(UUID("11111111-1111-1111-1111-111111111111"), 1), _role(UUID("22222222-2222-2222-2222-222222222222"), 4), _role(UUID("33333333-3333-3333-3333-333333333333"), 6)
        ]
        await self.service.create_partner_role(
            self._create(UUID("22222222-2222-2222-2222-222222222222"), RolePlacement.BELOW, base_id= UUID("33333333-3333-3333-3333-333333333333")), CURRENT_USER
        )
        values = self.repo.create_role.call_args.args[0]
        assert values["base_role_id"] == UUID("33333333-3333-3333-3333-333333333333")
        # base role is forwarded so the repo copies its permissions in-txn.
        assert self.repo.create_role.call_args.kwargs["base_role_id"] == UUID("33333333-3333-3333-3333-333333333333")

    async def test_list_partner_roles_without_pagination_returns_all(self) -> None:
        self.repo.has_partner_roles.return_value = True
        roles = [_full_role(UUID("11111111-1111-1111-1111-111111111111"), 1), _full_role(UUID("22222222-2222-2222-2222-222222222222"), 4)]
        self.repo.get_partner_roles_paginated.return_value = (roles, 2, 2, 0)

        result = await self.service.list_partner_roles(CURRENT_USER)

        self.repo.get_partner_roles_paginated.assert_awaited_once_with(UUID("10101010-1010-1010-1010-101010101010"), None, None)
        assert result.total_count == 2
        assert result.total_active == 2
        assert result.total_inactive == 0
        assert result.limit is None
        assert result.offset is None
        assert len(result.data) == 2

    async def test_list_partner_roles_applies_zero_based_pagination(self) -> None:
        self.repo.has_partner_roles.return_value = True
        self.repo.get_partner_roles_paginated.return_value = ([_full_role(UUID("33333333-3333-3333-3333-333333333333"), 6)], 5, 4, 1)

        result = await self.service.list_partner_roles(CURRENT_USER, limit=2, offset=1)

        self.repo.get_partner_roles_paginated.assert_awaited_once_with(UUID("10101010-1010-1010-1010-101010101010"), 2, 1)
        assert result.total_count == 5
        assert result.total_active == 4
        assert result.total_inactive == 1
        assert result.limit == 2
        assert result.offset == 1
        assert len(result.data) == 1

    async def test_list_partner_roles_falls_back_to_defaults_when_not_customized(
        self,
    ) -> None:
        self.repo.has_partner_roles.return_value = False
        self.repo.get_default_roles_paginated.return_value = (
            [_full_role(UUID("99999999-9999-9999-9999-999999999999"), 1, None)], 1, 1, 0
        )

        result = await self.service.list_partner_roles(CURRENT_USER, limit=10, offset=0)

        self.repo.get_default_roles_paginated.assert_awaited_once_with(False, 10, 0)
        self.repo.get_partner_roles_paginated.assert_not_called()
        assert result.total_count == 1
        assert result.total_active == 1
        assert result.total_inactive == 0

    async def test_delete_blocked_when_role_in_use(self) -> None:
        self.repo.get_partner_role.return_value = SimpleNamespace(id= UUID("55555555-5555-5555-5555-555555555555"))
        self.repo.count_users_with_role.return_value = 3
        with pytest.raises(
            PartnerRoleException, match=PartnerRoleExceptionMsg.ROLE_IN_USE
        ):
            await self.service.delete_partner_role(UUID("55555555-5555-5555-5555-555555555555"), CURRENT_USER)

