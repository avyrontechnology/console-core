from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.components.rbac.startup_validation import (
    ensure_route_permissions,
    ensure_superadmin_grants,
)


class TestEnsureRoutePermissions:
    def test_seeds_mapper_slugs_missing_from_db(self):
        """Mapper-declared slugs (admin UI catalogue) must exist even when no
        route references them, e.g. console:add_partner."""
        meta = {
            "console:get_all_users": {
                "title": "Get All Users",
                "category": "User",
                "display_text": "x",
                "is_internal": False,
            },
            "console:add_partner": {
                "title": "Add Partner",
                "category": "Partner",
                "display_text": "y",
                "is_internal": True,
            },
        }
        session = AsyncMock()
        session.execute = AsyncMock(
            return_value=MagicMock(scalars=lambda: MagicMock(all=lambda: ["console:get_all_users"]))
        )
        session.add = MagicMock()
        session.commit = AsyncMock()

        factory = MagicMock()
        factory.return_value.__aenter__ = AsyncMock(return_value=session)
        factory.return_value.__aexit__ = AsyncMock(return_value=None)

        with patch(
            "src.components.rbac.startup_validation.collect_route_slugs",
            return_value={"console:get_all_users"},
        ), patch(
            "src.components.rbac.startup_validation._mapper_metadata",
            return_value=meta,
        ):
            report = __import__("asyncio").run(ensure_route_permissions(factory))

        assert report["seeded"] == ["console:add_partner"]
        assert session.add.call_count == 1


class TestEnsureSuperadminGrants:
    def test_grants_every_missing_permission(self):
        from uuid import uuid4

        role_id = uuid4()
        role = MagicMock(id=role_id)

        session = AsyncMock()
        # 1st execute -> Role lookup, 2nd -> permissions not yet granted
        session.execute = AsyncMock(
            side_effect=[
                MagicMock(scalars=lambda: MagicMock(first=lambda: role)),
                MagicMock(scalars=lambda: MagicMock(all=lambda: [uuid4(), uuid4()])),
            ]
        )
        session.add = MagicMock()
        session.commit = AsyncMock()

        factory = MagicMock()
        factory.return_value.__aenter__ = AsyncMock(return_value=session)
        factory.return_value.__aexit__ = AsyncMock(return_value=None)

        report = __import__("asyncio").run(ensure_superadmin_grants(factory))

        assert report == {"granted": 2, "role_id": str(role_id)}
        assert session.add.call_count == 2
        session.commit.assert_awaited_once()

    def test_noop_without_a_superadmin_role(self):
        session = AsyncMock()
        session.execute = AsyncMock(
            return_value=MagicMock(scalars=lambda: MagicMock(first=lambda: None))
        )
        session.add = MagicMock()
        session.commit = AsyncMock()

        factory = MagicMock()
        factory.return_value.__aenter__ = AsyncMock(return_value=session)
        factory.return_value.__aexit__ = AsyncMock(return_value=None)

        report = __import__("asyncio").run(ensure_superadmin_grants(factory))

        assert report == {"granted": 0, "role_id": None}
        session.commit.assert_not_awaited()


@pytest.mark.parametrize("name", ["ensure_route_permissions", "ensure_superadmin_grants"])
def test_helpers_are_coroutines(name):
    import inspect

    from src.components.rbac import startup_validation

    assert inspect.iscoroutinefunction(getattr(startup_validation, name))