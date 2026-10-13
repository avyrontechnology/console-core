"""Startup validation: every @permission_check slug must exist in DB.

Kills the whole class of silent grant/deny bugs from typos, renames, and
mapper/route drift. Runs at boot; raises on any missing slug (fail-closed).
"""
import glob
import os
import re

from sqlalchemy import select

from src.components.auth.models import Permission

_SLUG_PAT = re.compile(r'@permission_check\(\s*"([^"]+)"\s*\)')
_here = os.path.dirname(os.path.abspath(__file__))
_COMPONENTS_DIR = os.path.dirname(_here)  # src/components


def collect_route_slugs() -> set[str]:
    slugs: set[str] = set()
    for f in glob.glob(os.path.join(_COMPONENTS_DIR, "*", "controller*.py")) + glob.glob(
        os.path.join(_COMPONENTS_DIR, "*", "controllers.py")
    ):
        for m in _SLUG_PAT.finditer(open(f).read()):
            slugs.add(m.group(1))
    return slugs


async def validate_route_permissions(session_factory) -> set[str]:
    """Raise RuntimeError listing any route slug missing from console_permission."""
    route_slugs = collect_route_slugs()
    async with session_factory() as session:
        result = await session.execute(select(Permission.slug))
        db_slugs = set(result.scalars().all())
    missing = sorted(route_slugs - db_slugs)
    if missing:
        raise RuntimeError(
            "Permission slugs used by routes but missing in DB "
            "(seed via permissions_gen_v2): {}".format(missing)
        )
    return route_slugs
