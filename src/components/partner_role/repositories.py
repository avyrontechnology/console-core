from uuid import UUID
from contextlib import AbstractContextManager
from typing import Any, Callable, Dict, List, Optional, Tuple

from sqlalchemy import func, insert, select, update
from sqlalchemy.orm import Session

from src.components.auth.models import Role
from src.components.common.datetime import DateTimeUtil
from src.components.default_role_permission.models import DefaultRolePermission
from src.components.partner.models import Partner
from src.components.partner_role.constants import DataScope, HIERARCHY_SPACING, MANAGER_ROLE_HIERARCHY
from src.components.user.models import User
from src.loggers.console_service_logger import ConsoleServiceLogger

# Temporary offset used while rebalancing to avoid transient unique collisions
# on (partner_id, hierarchy) before the final values are written.
_REBALANCE_TEMP_OFFSET: int = 10_000_000


class PartnerRoleRepository:
    def __init__(
        self,
        session_factory: Callable[..., AbstractContextManager[Session]],
        console_service_logger: ConsoleServiceLogger = ConsoleServiceLogger(),
    ) -> None:
        self.__session_factory: Callable[..., AbstractContextManager[Session]] = (
            session_factory
        )
        self.__console_service_logger: ConsoleServiceLogger = console_service_logger

    # ------------------------------ lookups ------------------------------- #

    async def get_partner(self, partner_id: UUID) -> Optional[Partner]:
        async with self.__session_factory() as session:
            result = await session.execute(
                select(Partner).where(
                    Partner.id == partner_id,
                    Partner.is_active == True,  # noqa: E712
                    Partner.is_deleted == False,  # noqa: E712
                )
            )
            return result.scalar_one_or_none()

    async def has_partner_roles(self, partner_id: UUID) -> bool:
        async with self.__session_factory() as session:
            result = await session.execute(
                select(Role.id).where(Role.partner_id == partner_id).limit(1)
            )
            return result.scalar_one_or_none() is not None

    async def get_partner_roles_ordered(self, partner_id: UUID) -> List[Role]:
        async with self.__session_factory() as session:
            result = await session.execute(
                select(Role)
                .where(
                    Role.partner_id == partner_id,
                    Role.is_deleted == False,  # noqa: E712
                )
                .order_by(Role.hierarchy)
            )
            return result.scalars().all()

    async def get_default_roles(self, is_internal: bool) -> List[Role]:
        async with self.__session_factory() as session:
            result = await session.execute(
                select(Role)
                .where(
                    Role.partner_id.is_(None),
                    Role.is_active == True,  # noqa: E712
                    Role.is_deleted == False,  # noqa: E712
                    Role.is_internal == is_internal,
                )
                .order_by(Role.hierarchy)
            )
            return result.scalars().all()

    @staticmethod
    async def __active_inactive_counts(
        session: Session, filters: List[Any]
    ) -> Tuple[int, int]:
        """Return (total_active, total_inactive) for rows matching *filters*."""
        rows = (
            await session.execute(
                select(Role.is_active, func.count())
                .where(*filters)
                .group_by(Role.is_active)
            )
        ).all()
        total_active: int = next((c for is_active, c in rows if is_active), 0)
        total_inactive: int = next((c for is_active, c in rows if not is_active), 0)
        return total_active, total_inactive

    async def get_partner_roles_paginated(
        self,
        partner_id: UUID,
        limit: Optional[int] = None,
        offset: Optional[int] = None,
    ) -> Tuple[List[Role], int, int, int]:
        """Zero-based pagination: page ``offset`` (starting at 0) of size
        ``limit``. When either is omitted, returns the full ordered list.

        Returns ``(roles, total_count, total_active, total_inactive)`` where
        the counts reflect the full filtered set, independent of pagination.
        """
        async with self.__session_factory() as session:
            filters: List[Any] = [
                Role.partner_id == partner_id,
                Role.is_deleted == False,  # noqa: E712
            ]
            query = select(Role).where(*filters).order_by(Role.hierarchy)

            total_count: int = (
                await session.execute(
                    select(func.count()).select_from(query.subquery())
                )
            ).scalar() or 0
            total_active, total_inactive = await self.__active_inactive_counts(
                session, filters
            )

            if limit is not None and offset is not None:
                query = query.offset(offset * limit).limit(limit)

            result = await session.execute(query)
            return result.scalars().all(), total_count, total_active, total_inactive

    async def get_default_roles_paginated(
        self,
        is_internal: bool,
        limit: Optional[int] = None,
        offset: Optional[int] = None,
    ) -> Tuple[List[Role], int, int, int]:
        """Zero-based pagination over the shared default catalog.

        Returns ``(roles, total_count, total_active, total_inactive)``;
        ``total_inactive`` is always 0 since defaults are always active.
        """
        async with self.__session_factory() as session:
            filters: List[Any] = [
                Role.partner_id.is_(None),
                Role.is_active == True,  # noqa: E712
                Role.is_deleted == False,  # noqa: E712
                Role.is_internal == is_internal,
            ]
            query = select(Role).where(*filters).order_by(Role.hierarchy)

            total_count: int = (
                await session.execute(
                    select(func.count()).select_from(query.subquery())
                )
            ).scalar() or 0
            total_active, total_inactive = await self.__active_inactive_counts(
                session, filters
            )

            if limit is not None and offset is not None:
                query = query.offset(offset * limit).limit(limit)

            result = await session.execute(query)
            return result.scalars().all(), total_count, total_active, total_inactive

    async def get_partner_role(
        self, role_id: UUID, partner_id: UUID
    ) -> Optional[Role]:
        async with self.__session_factory() as session:
            result = await session.execute(
                select(Role).where(
                    Role.id == role_id,
                    Role.partner_id == partner_id,
                    Role.is_deleted == False,  # noqa: E712
                )
            )
            return result.scalar_one_or_none()

    async def count_users_with_role(self, role_id: UUID) -> int:
        async with self.__session_factory() as session:
            result = await session.execute(
                select(func.count())
                .select_from(User)
                .where(
                    User.role_id == role_id,
                    User.is_deleted == False,  # noqa: E712
                )
            )
            return int(result.scalar() or 0)

    # ------------------------ copy-on-customize --------------------------- #

    async def materialize_catalog(
        self, partner_id: UUID, is_internal: bool, user_id: UUID
    ) -> None:
        """Snapshot the shared default catalog into partner-owned rows and
        repoint the partner's users + copy default permissions. Idempotent: a
        no-op once the partner already owns roles. Runs in one transaction."""
        async with self.__session_factory() as session:
            existing = await session.execute(
                select(Role.id).where(Role.partner_id == partner_id).limit(1)
            )
            if existing.scalar_one_or_none() is not None:
                return  None

            defaults: List[Role] = (
                await session.execute(
                    select(Role).where(
                        Role.partner_id.is_(None),
                        Role.is_active == True,
                        Role.is_deleted == False,
                        Role.is_internal == is_internal,
                    )
                )
            ).scalars().all()

            id_map: Dict[int, int] = {}
            for default in defaults:
                copy = Role(
                    name=default.name,
                    slug=default.slug,
                    hierarchy=default.hierarchy,
                    partner_id=partner_id,
                    data_scope=(
                        default.data_scope
                        or (DataScope.ALL.value if default.hierarchy <= MANAGER_ROLE_HIERARCHY else DataScope.SUBTREE.value)
                    ),
                    description=default.description,
                    is_internal=default.is_internal,
                    is_active=True,
                    is_deleted=False,
                    created_by=user_id,
                )
                session.add(copy)
                await session.flush()
                id_map[default.id] = copy.id

            if id_map:
                default_perms: List[DefaultRolePermission] = (
                    await session.execute(
                        select(DefaultRolePermission).where(
                            DefaultRolePermission.role_id.in_(list(id_map.keys()))
                        )
                    )
                ).scalars().all()
                if default_perms:
                    now: int = int(DateTimeUtil.get_current_time())
                    await session.execute(
                        insert(DefaultRolePermission).values([
                            {
                                "role_id": id_map[drp.role_id],
                                "permission_id": drp.permission_id,
                                "created_by": user_id,
                                "created_at": now,
                            }
                            for drp in default_perms
                        ])
                    )

                # Repoint the partner's users from each default role to its copy.
                for old_role_id, new_role_id in id_map.items():
                    await session.execute(
                        update(User)
                        .where(
                            User.partner_id == partner_id,
                            User.role_id == old_role_id,
                        )
                        .values(role_id=new_role_id)
                    )

            await session.commit()
            self.__console_service_logger.info(
                "Materialized {} default roles for partner {}".format(
                    len(id_map), partner_id
                )
            )

    # ------------------------------ mutations ----------------------------- #

    async def create_role(
        self,
        values: Dict[str, Any],
        user_id: UUID,
        finalize_slug: Callable[[Role], str],
        base_role_id: Optional[UUID] = None,
    ) -> Role:
        """``values["slug"]`` must already hold a NOT-NULL-safe placeholder
        (Role.slug has no default). Once the row is flushed and its id is
        known, ``finalize_slug`` computes the real id-suffixed slug, which is
        applied before the transaction commits (two-pass, single transaction).

        When ``base_role_id`` is given, the base role's DefaultRolePermission
        rows are bulk-copied onto the new role within the same transaction, so
        the role never exists in a half-seeded state (mirrors the copy block in
        ``materialize_catalog``). A base role with no permissions is a no-op.
        """
        async with self.__session_factory() as session:
            role: Role = Role(**values, created_by=user_id, is_active=True, is_deleted=False)
            session.add(role)
            await session.flush()
            role.slug = finalize_slug(role)

            if base_role_id is not None:
                base_perms: List[DefaultRolePermission] = (
                    await session.execute(
                        select(DefaultRolePermission).where(
                            DefaultRolePermission.role_id == base_role_id
                        )
                    )
                ).scalars().all()
                if base_perms:
                    now: int = int(DateTimeUtil.get_current_time())
                    await session.execute(
                        insert(DefaultRolePermission).values([
                            {
                                "role_id": role.id,
                                "permission_id": drp.permission_id,
                                "created_by": user_id,
                                "created_at": now,
                            }
                            for drp in base_perms
                        ])
                    )

            await session.commit()
            await session.refresh(role)
            return role

    async def update_role(self, role_id: UUID, values: Dict[str, Any], user_id: UUID) -> Role:
        async with self.__session_factory() as session:
            await session.execute(
                update(Role)
                .where(Role.id == role_id)
                .values(**values, updated_by=user_id)
            )
            await session.commit()
            result = await session.execute(select(Role).where(Role.id == role_id))
            return result.scalar_one()

    async def soft_delete_role(self, role_id: UUID, user_id: UUID) -> None:
        async with self.__session_factory() as session:
            await session.execute(
                update(Role)
                .where(Role.id == role_id)
                .values(is_deleted=True, is_active=False, deleted_by=user_id)
            )
            await session.commit()

    async def rebalance(self, partner_id: UUID, user_id: UUID) -> List[Role]:
        """Re-space the partner's hierarchy to wide multiples (order preserved).

        Done in two passes within one transaction to avoid transient unique
        collisions on (partner_id, hierarchy). ``role_id`` FKs are untouched, so
        user/team references stay valid.
        """
        async with self.__session_factory() as session:
            roles: List[Role] = (
                await session.execute(
                    select(Role)
                    .where(
                        Role.partner_id == partner_id,
                        Role.is_deleted == False,
                    )
                    .order_by(Role.hierarchy)
                )
            ).scalars().all()

            # Pass 1: move to unique temporary values.
            for idx, role in enumerate(roles):
                await session.execute(
                    update(Role)
                    .where(Role.id == role.id)
                    .values(hierarchy=_REBALANCE_TEMP_OFFSET + idx)
                )
            await session.flush()

            # Pass 2: assign the final, evenly spaced values.
            for idx, role in enumerate(roles):
                await session.execute(
                    update(Role)
                    .where(Role.id == role.id)
                    .values(hierarchy=(idx + 1) * HIERARCHY_SPACING, updated_by=user_id)
                )
            await session.commit()

            refreshed: List[Role] = (
                await session.execute(
                    select(Role)
                    .where(
                        Role.partner_id == partner_id,
                        Role.is_deleted == False,  # noqa: E712
                    )
                    .order_by(Role.hierarchy)
                )
            ).scalars().all()
            self.__console_service_logger.info(
                "Rebalanced {} roles for partner {}".format(len(refreshed), partner_id)
            )
            return refreshed
