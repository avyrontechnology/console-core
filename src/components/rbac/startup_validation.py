"""Startup permission sync: every @permission_check slug exists in DB.

Zero-touch deploys: missing route slugs are AUTO-SEEDED (upsert by slug)
instead of boot-failing, so new routes never need a manual seed step.
Safety preserved two ways:
  - slugs known to the mapper seed with their real title/category/flag;
  - unknown slugs (typos) seed as internal-only + loud WARNING, so they
    can never leak to external users, and CI drift-check still flags them.
Grants still come only from explicit role mappings — seeding creates the
rows, never the grants.
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


def _mapper_metadata() -> dict[str, dict]:
    """slug -> {title, category, display_text, is_internal} from the mapper."""
    from src.components.auth.permission_mapper import PermissionCategories

    meta: dict[str, dict] = {}
    for category, methods in PermissionCategories.CONSOLE_PERMISSIONS.items():
        for method_name, is_internal in methods:
            slug = f"console:{method_name}"
            title = method_name.replace("_", " ").title()
            meta[slug] = {
                "title": title,
                "category": category,
                "display_text": f"{title} ({category})",
                "is_internal": bool(is_internal),
            }
    return meta


async def ensure_route_permissions(session_factory) -> dict:
    """Upsert missing slugs.

    Seeds every mapper-declared slug, not just route-bound ones: the mapper
    is the catalogue the admin UI gates on, so a slug declared there (e.g.
    console:add_partner, whose route is intentionally public for partner
    onboarding) must still exist or the UI denies it for everyone.

    Returns {seeded: [...], unmapped_warnings: [...] }.
    """
    from src.components.common.datetime import DateTimeUtil

    route_slugs = collect_route_slugs()
    meta = _mapper_metadata()
    async with session_factory() as session:
        result = await session.execute(select(Permission.slug))
        db_slugs = set(result.scalars().all())
        # Mapper slugs exist for the UI catalogue; route slugs exist for the
        # API. Both must be present in console_permission.
        missing = sorted((route_slugs | set(meta.keys())) - db_slugs)
        seeded: list[str] = []
        warnings: list[str] = []
        for slug in missing:
            info = meta.get(slug)
            if info is None and slug in route_slugs:
                # Typo safety: internal-only so external users never get it.
                info = {
                    "title": slug,
                    "category": "Unmapped",
                    "display_text": f"{slug} (Unmapped — fix route or mapper)",
                    "is_internal": True,
                }
                warnings.append(slug)
            session.add(
                Permission(
                    title=info["title"],
                    slug=slug,
                    category=info["category"],
                    display_text=info["display_text"],
                    is_active=True,
                    is_deleted=False,
                    is_internal=info["is_internal"],
                )
            )
            seeded.append(slug)
        if seeded:
            await session.commit()
    return {"seeded": seeded, "unmapped_warnings": warnings}


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


async def ensure_superadmin_grants(session_factory) -> dict:
    """Give the hierarchy-0 system role every permission in the catalogue.

    Super admin is defined as "has everything", so this is enforced on every
    boot rather than relying on a one-off grant step: a permission seeded
    later (new route, mapper addition) would otherwise silently be missing.
    Idempotent, and it never touches any other role.
    """
    from src.components.auth.models import Role
    from src.components.default_role_permission.models import DefaultRolePermission

    SUPERADMIN_HIERARCHY = 0

    async with session_factory() as session:
        role = (
            await session.execute(
                select(Role).where(
                    Role.hierarchy == SUPERADMIN_HIERARCHY, Role.partner_id.is_(None)
                )
            )
        ).scalars().first()
        if role is None:
            return {"granted": 0, "role_id": None}
        role_id = role.id  # read inside the session; detached access would raise

        granted = (
            await session.execute(
                select(Permission.id).where(
                    Permission.id.not_in(
                        select(DefaultRolePermission.permission_id).where(
                            DefaultRolePermission.role_id == role_id
                        )
                    )
                )
            )
        ).scalars().all()

        for permission_id in granted:
            session.add(DefaultRolePermission(role_id=role_id, permission_id=permission_id))
        if granted:
            await session.commit()
    return {"granted": len(granted), "role_id": str(role_id)}
