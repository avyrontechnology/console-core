"""Tests for startup permission sync (self-seed + validate)."""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.components.rbac import startup_validation as sv


class _SessionCtx:
    def __init__(self, session):
        self._s = session

    async def __aenter__(self):
        return self._s

    async def __aexit__(self, *a):
        return None


def _factory(existing_slugs):
    session = AsyncMock()
    scalars = MagicMock()
    scalars.all.return_value = list(existing_slugs)
    execute_result = MagicMock()
    execute_result.scalars.return_value = scalars
    session.execute = AsyncMock(return_value=execute_result)
    session.add = MagicMock()
    session.commit = AsyncMock()
    factory = MagicMock(return_value=_SessionCtx(session))
    return factory, session


@pytest.mark.asyncio
async def test_ensure_seeds_missing_known_slug():
    slugs = sv.collect_route_slugs()
    assert "console:bulk_create_users" in slugs
    assert "console:generate_api_key" in slugs
    factory, session = _factory(set())
    meta = {
        "console:bulk_create_users": {
            "title": "Bulk Create Users",
            "category": "User",
            "display_text": "Bulk Create Users (User)",
            "is_internal": False,
        }
    }
    with (
        patch.object(
            sv, "collect_route_slugs", return_value={"console:bulk_create_users"}
        ),
        patch.object(sv, "_mapper_metadata", return_value=meta),
    ):
        report = await sv.ensure_route_permissions(factory)
    assert report["seeded"] == ["console:bulk_create_users"]
    assert report["unmapped_warnings"] == []
    added = session.add.call_args[0][0]
    assert added.slug == "console:bulk_create_users"
    assert added.is_internal is False  # mapper flag preserved
    session.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_ensure_unknown_slug_seeds_internal_only_with_warning():
    factory, session = _factory(set())
    with patch.object(
        sv, "collect_route_slugs", return_value={"console:typo_route_xyz"}
    ):
        report = await sv.ensure_route_permissions(factory)
    assert report["seeded"] == ["console:typo_route_xyz"]
    assert report["unmapped_warnings"] == ["console:typo_route_xyz"]
    added = session.add.call_args[0][0]
    assert added.is_internal is True  # fail-closed default


@pytest.mark.asyncio
async def test_ensure_skips_existing_slugs():
    factory, session = _factory({"console:bulk_create_users"})
    with patch.object(
        sv, "collect_route_slugs", return_value={"console:bulk_create_users"}
    ):
        report = await sv.ensure_route_permissions(factory)
    assert report["seeded"] == []
    session.add.assert_not_called()
    session.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_validate_passes_when_all_present():
    factory, _ = _factory({"console:a"})
    with patch.object(sv, "collect_route_slugs", return_value={"console:a"}):
        assert await sv.validate_route_permissions(factory) == {"console:a"}


@pytest.mark.asyncio
async def test_validate_raises_on_missing():
    factory, _ = _factory(set())
    with patch.object(sv, "collect_route_slugs", return_value={"console:zzz"}):
        with pytest.raises(RuntimeError, match="console:zzz"):
            await sv.validate_route_permissions(factory)
