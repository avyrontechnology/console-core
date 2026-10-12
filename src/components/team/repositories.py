from uuid import UUID
from contextlib import AbstractContextManager
from typing import Any, Callable, Dict, List, Optional, Tuple

from sqlalchemy import and_, func, or_, select, update
from sqlalchemy.orm import Session

from src.components.auth.models import Role
from src.components.partner.models import Partner
from src.components.team.models import Team, TeamMember
from src.components.user.models import User
from src.loggers.console_service_logger import ConsoleServiceLogger


class TeamRepository:
    def __init__(
        self,
        session_factory: Callable[..., AbstractContextManager[Session]],
        console_service_logger: ConsoleServiceLogger = ConsoleServiceLogger(),
    ) -> None:
        self.__session_factory: Callable[..., AbstractContextManager[Session]] = (
            session_factory
        )
        self.__console_service_logger: ConsoleServiceLogger = console_service_logger

    # ----------------------------- lookups -------------------------------- #

    async def get_partner(self, partner_id: UUID) -> Optional[Partner]:
        try:
            async with self.__session_factory() as session:
                result = await session.execute(
                    select(Partner).where(
                        Partner.id == partner_id,
                        Partner.is_active == True,  # noqa: E712
                        Partner.is_deleted == False,  # noqa: E712
                    )
                )
                return result.scalar_one_or_none()
        except Exception as exc:
            self.__console_service_logger.error(
                "DB error in get_partner partner_id={}: {}".format(partner_id, exc)
            )
            raise exc

    async def get_user(self, user_id: UUID) -> Optional[User]:
        try:
            async with self.__session_factory() as session:
                result = await session.execute(
                    select(User).where(
                        User.id == user_id,
                        User.is_active == True,  # noqa: E712
                        User.is_deleted == False,  # noqa: E712
                    )
                )
                return result.scalar_one_or_none()
        except Exception as exc:
            self.__console_service_logger.error(
                "DB error in get_user user_id={}: {}".format(user_id, exc)
            )
            raise exc

    async def is_role_in_partner_catalog(self, role_id: UUID, partner_id: UUID) -> bool:
        """A role is usable by a partner if it is the partner's own custom role
        or a shared default role (``partner_id IS NULL``)."""
        try:
            async with self.__session_factory() as session:
                result = await session.execute(
                    select(Role.id).where(
                        Role.id == role_id,
                        Role.is_active == True,  # noqa: E712
                        Role.is_deleted == False,  # noqa: E712
                        or_(Role.partner_id == partner_id, Role.partner_id.is_(None)),
                    )
                )
                return result.scalar_one_or_none() is not None
        except Exception as exc:
            self.__console_service_logger.error(
                "DB error in is_role_in_partner_catalog role_id={} partner_id={}: {}".format(
                    role_id, partner_id, exc
                )
            )
            raise exc

    async def get_team_by_id(
        self, team_id: UUID, partner_id: Optional[UUID] = None
    ) -> Optional[Team]:
        try:
            async with self.__session_factory() as session:
                filters = [Team.id == team_id, Team.is_deleted == False]  # noqa: E712
                if partner_id is not None:
                    filters.append(Team.partner_id == partner_id)
                result = await session.execute(select(Team).where(and_(*filters)))
                return result.scalar_one_or_none()
        except Exception as exc:
            self.__console_service_logger.error(
                "DB error in get_team_by_id team_id={}: {}".format(team_id, exc)
            )
            raise exc

    async def get_teams_by_partner(self, partner_id: UUID) -> List[Team]:
        try:
            async with self.__session_factory() as session:
                result = await session.execute(
                    select(Team)
                    .where(
                        Team.partner_id == partner_id,
                        Team.is_deleted == False,  # noqa: E712
                    )
                    .order_by(Team.id)
                )
                return result.scalars().all()
        except Exception as exc:
            self.__console_service_logger.error(
                "DB error in get_teams_by_partner partner_id={}: {}".format(partner_id, exc)
            )
            raise exc

    async def list_teams_paginated(
        self,
        partner_id: UUID,
        search_by: Optional[str] = None,
        limit: Optional[int] = None,
        offset: Optional[int] = None,
    ) -> Tuple[List[Dict[str, Any]], int, int, int]:
        """Zero-based pagination (``row_offset = offset * limit``) over the
        partner's teams, optionally name-filtered. Returns
        ``(rows, total_count, total_active, total_inactive)`` where the
        counts reflect the full filtered set, independent of pagination.
        Each row also carries a ``member_count`` (live ``TeamMember`` count).
        """
        try:
            async with self.__session_factory() as session:
                filters: List[Any] = [
                    Team.partner_id == partner_id,
                    Team.is_deleted == False,  # noqa: E712
                ]
                if search_by:
                    filters.append(Team.name.ilike("%{}%".format(search_by)))

                member_count_subq = (
                    select(func.count(TeamMember.id))
                    .where(TeamMember.team_id == Team.id)
                    .correlate(Team)
                    .scalar_subquery()
                )

                query = (
                    select(
                        Team.id,
                        Team.name,
                        Team.slug,
                        Team.description,
                        Team.partner_id,
                        Team.parent_team_id,
                        Team.is_internal,
                        Team.is_active,
                        Team.created_at,
                        Team.updated_at,
                        member_count_subq.label("member_count"),
                    )
                    .where(*filters)
                    .order_by(Team.id)
                )

                total_count: int = (
                    await session.execute(
                        select(func.count()).select_from(
                            select(Team.id).where(*filters).subquery()
                        )
                    )
                ).scalar() or 0

                active_rows = (
                    await session.execute(
                        select(Team.is_active, func.count())
                        .where(*filters)
                        .group_by(Team.is_active)
                    )
                ).all()
                total_active: int = next(
                    (c for is_active, c in active_rows if is_active), 0
                )
                total_inactive: int = next(
                    (c for is_active, c in active_rows if not is_active), 0
                )

                if limit is not None and offset is not None:
                    query = query.offset(offset * limit).limit(limit)

                result = await session.execute(query)
                rows = [dict(row) for row in result.mappings().all()]
                return rows, total_count, total_active, total_inactive
        except Exception as exc:
            self.__console_service_logger.error(
                "DB error in list_teams_paginated partner_id={}: {}".format(
                    partner_id, exc
                )
            )
            raise exc

    async def get_teams_for_partner_users(
        self, partner_id: UUID
    ) -> List[Dict[str, Any]]:
        """Team memberships for every (active, non-deleted) user of *partner_id*,
        for the "user associated teams" endpoint. A LEFT JOIN keeps users with
        zero team memberships in the result (their team fields come back
        ``None``), so every partner user is represented, matching the
        equivalent user/service-board endpoint behavior.
        """
        try:
            async with self.__session_factory() as session:
                result = await session.execute(
                    select(
                        User.id.label("user_id"),
                        Team.id.label("team_id"),
                        Team.name,
                        Team.slug,
                        Team.description,
                        Team.is_active,
                        TeamMember.role_id,
                        TeamMember.id.label("team_member_id"),
                    )
                    .select_from(User)
                    .outerjoin(TeamMember, TeamMember.user_id == User.id)
                    .outerjoin(
                        Team,
                        and_(
                            Team.id == TeamMember.team_id,
                            Team.is_deleted == False,  # noqa: E712
                        ),
                    )
                    .where(
                        User.partner_id == partner_id,
                        User.is_deleted == False,  # noqa: E712
                        User.is_active == True,  # noqa: E712
                    )
                    .order_by(User.id, Team.id)
                )
                return [dict(row) for row in result.mappings().all()]
        except Exception as exc:
            self.__console_service_logger.error(
                "DB error in get_teams_for_partner_users partner_id={}: {}".format(
                    partner_id, exc
                )
            )
            raise exc

    async def get_member_counts_for_users(self, user_ids: List[int]) -> Dict[int, int]:
        """Batch member-count lookup: ``{user_id: team_count}`` for the given
        users, counting only active teams. Empty input is a no-op."""
        if not user_ids:
            return {}
        try:
            async with self.__session_factory() as session:
                result = await session.execute(
                    select(TeamMember.user_id, func.count())
                    .join(Team, Team.id == TeamMember.team_id)
                    .where(
                        TeamMember.user_id.in_(user_ids),
                        Team.is_deleted == False,  # noqa: E712
                        Team.is_active == True,  # noqa: E712
                    )
                    .group_by(TeamMember.user_id)
                )
                return {user_id: count for user_id, count in result.all()}
        except Exception as exc:
            self.__console_service_logger.error(
                "DB error in get_member_counts_for_users: {}".format(exc)
            )
            raise exc

    async def get_parent_chain_ids(self, team_id: UUID) -> List[int]:
        """Return the ids of all ancestors of ``team_id`` (walking parent links)."""
        try:
            async with self.__session_factory() as session:
                ancestors: List[int] = []
                seen: set = set()
                current_id: Optional[UUID] = team_id
                while current_id is not None and current_id not in seen:
                    seen.add(current_id)
                    result = await session.execute(
                        select(Team.parent_team_id).where(Team.id == current_id)
                    )
                    parent_id = result.scalar_one_or_none()
                    if parent_id is None:
                        break
                    ancestors.append(parent_id)
                    current_id = parent_id
                return ancestors
        except Exception as exc:
            self.__console_service_logger.error(
                "DB error in get_parent_chain_ids team_id={}: {}".format(team_id, exc)
            )
            raise exc

    # ----------------------------- mutations ------------------------------ #

    async def create_team(
        self,
        values: Dict[str, Any],
        user_id: UUID,
        finalize_slug: Callable[[Team], str],
    ) -> Team:
        """``values["slug"]`` must already hold a NOT-NULL-safe placeholder
        (Team.slug has no default). Once the row is flushed and its id is
        known, ``finalize_slug`` computes the real id-suffixed slug, which is
        applied before the transaction commits (two-pass, single transaction)."""
        try:
            async with self.__session_factory() as session:
                team = Team(**values, created_by=user_id)
                session.add(team)
                await session.flush()
                team.slug = finalize_slug(team)
                await session.commit()
                await session.refresh(team)
                self.__console_service_logger.info(
                    "Team created with id: {}".format(team.id)
                )
                return team
        except Exception as exc:
            self.__console_service_logger.error(
                "DB error in create_team: {}".format(exc)
            )
            raise exc

    async def update_team(self, team_id: UUID, values: Dict[str, Any], user_id: UUID) -> Team:
        try:
            async with self.__session_factory() as session:
                values = {**values, "updated_by": user_id}
                await session.execute(
                    update(Team).where(Team.id == team_id).values(**values)
                )
                await session.commit()
                result = await session.execute(select(Team).where(Team.id == team_id))
                return result.scalar_one()
        except Exception as exc:
            self.__console_service_logger.error(
                "DB error in update_team team_id={}: {}".format(team_id, exc)
            )
            raise exc

    async def soft_delete_team(self, team_id: UUID, user_id: UUID) -> None:
        try:
            async with self.__session_factory() as session:
                await session.execute(
                    update(Team)
                    .where(Team.id == team_id)
                    .values(is_deleted=True, is_active=False, deleted_by=user_id)
                )
                await session.commit()
        except Exception as exc:
            self.__console_service_logger.error(
                "DB error in soft_delete_team team_id={}: {}".format(team_id, exc)
            )
            raise exc

    # ----------------------------- membership ----------------------------- #

    async def get_member(self, team_id: UUID, user_id: UUID) -> Optional[TeamMember]:
        try:
            async with self.__session_factory() as session:
                result = await session.execute(
                    select(TeamMember).where(
                        TeamMember.team_id == team_id,
                        TeamMember.user_id == user_id,
                    )
                )
                return result.scalar_one_or_none()
        except Exception as exc:
            self.__console_service_logger.error(
                "DB error in get_member team_id={} user_id={}: {}".format(
                    team_id, user_id, exc
                )
            )
            raise exc

    async def add_member(
        self,
        team_id: UUID,
        user_id: UUID,
        role_id: Optional[UUID],
        created_by: UUID,
    ) -> TeamMember:
        try:
            async with self.__session_factory() as session:
                member = TeamMember(
                    team_id=team_id,
                    user_id=user_id,
                    role_id=role_id,
                    created_by=created_by,
                )
                session.add(member)
                await session.commit()
                await session.refresh(member)
                return member
        except Exception as exc:
            self.__console_service_logger.error(
                "DB error in add_member team_id={} user_id={}: {}".format(
                    team_id, user_id, exc
                )
            )
            raise exc

    async def remove_member(self, team_id: UUID, user_id: UUID) -> bool:
        try:
            async with self.__session_factory() as session:
                member = await session.execute(
                    select(TeamMember).where(
                        TeamMember.team_id == team_id,
                        TeamMember.user_id == user_id,
                    )
                )
                member_obj = member.scalar_one_or_none()
                if member_obj is None:
                    return False
                await session.delete(member_obj)
                await session.commit()
                return True
        except Exception as exc:
            self.__console_service_logger.error(
                "DB error in remove_member team_id={} user_id={}: {}".format(
                    team_id, user_id, exc
                )
            )
            raise exc

    async def update_member_role(
        self, team_id: UUID, user_id: UUID, role_id: Optional[UUID]
    ) -> Optional[TeamMember]:
        try:
            async with self.__session_factory() as session:
                result = await session.execute(
                    update(TeamMember)
                    .where(TeamMember.team_id == team_id, TeamMember.user_id == user_id)
                    .values(role_id=role_id)
                )
                await session.commit()
                if result.rowcount == 0:
                    return None
                fetched = await session.execute(
                    select(TeamMember).where(
                        TeamMember.team_id == team_id, TeamMember.user_id == user_id
                    )
                )
                return fetched.scalar_one_or_none()
        except Exception as exc:
            self.__console_service_logger.error(
                "DB error in update_member_role team_id={} user_id={}: {}".format(
                    team_id, user_id, exc
                )
            )
            raise exc

    async def get_members(self, team_id: UUID) -> List[TeamMember]:
        try:
            async with self.__session_factory() as session:
                result = await session.execute(
                    select(TeamMember).where(TeamMember.team_id == team_id)
                )
                return result.scalars().all()
        except Exception as exc:
            self.__console_service_logger.error(
                "DB error in get_members team_id={}: {}".format(team_id, exc)
            )
            raise exc

    async def get_members_paginated(
        self,
        team_id: UUID,
        limit: Optional[int] = None,
        offset: Optional[int] = None,
    ) -> Tuple[List[Dict[str, Any]], int]:
        """Members of a team joined with user_name and role_name.

        Pagination is zero-based and optional: pass both ``limit`` and
        ``offset`` to page (``row_offset = offset * limit``), or neither to
        get everything. Returns ``(rows, total_count)`` where ``total_count``
        reflects the full member set, independent of pagination.
        """
        try:
            async with self.__session_factory() as session:
                filters: List[Any] = [TeamMember.team_id == team_id]

                query = (
                    select(
                        TeamMember.id,
                        TeamMember.team_id,
                        TeamMember.user_id,
                        TeamMember.role_id,
                        User.name.label("user_name"),
                        Role.name.label("role_name"),
                    )
                    .select_from(TeamMember)
                    .join(User, User.id == TeamMember.user_id)
                    .outerjoin(Role, Role.id == TeamMember.role_id)
                    .where(*filters)
                    .order_by(TeamMember.id)
                )

                total_count: int = (
                    await session.execute(
                        select(func.count()).select_from(
                            select(TeamMember.id).where(*filters).subquery()
                        )
                    )
                ).scalar() or 0

                if limit is not None and offset is not None:
                    query = query.offset(offset * limit).limit(limit)

                result = await session.execute(query)
                rows = [dict(row) for row in result.mappings().all()]
                return rows, total_count
        except Exception as exc:
            self.__console_service_logger.error(
                "DB error in get_members_paginated team_id={}: {}".format(
                    team_id, exc
                )
            )
            raise exc

    async def get_user_teams(self, user_id: UUID) -> List[Team]:
        try:
            async with self.__session_factory() as session:
                result = await session.execute(
                    select(Team)
                    .join(TeamMember, TeamMember.team_id == Team.id)
                    .where(
                        TeamMember.user_id == user_id,
                        Team.is_deleted == False,  # noqa: E712
                        Team.is_active == True,  # noqa: E712
                    )
                )
                return result.scalars().all()
        except Exception as exc:
            self.__console_service_logger.error(
                "DB error in get_user_teams user_id={}: {}".format(user_id, exc)
            )
            raise exc

    async def get_teams_for_user(self, user_id: UUID) -> List[Dict[str, Any]]:
        """Active teams for a single user, including the user's role_id and
        role_name in each team (role fields are None if role_id is unset)."""
        try:
            self.__console_service_logger.info(
                "Fetching teams for user_id={}".format(user_id)
            )
            async with self.__session_factory() as session:
                result = await session.execute(
                    select(
                        Team.id,
                        Team.name,
                        TeamMember.role_id,
                        Role.name.label("role_name"),
                    )
                    .select_from(TeamMember)
                    .join(Team, Team.id == TeamMember.team_id)
                    .outerjoin(Role, Role.id == TeamMember.role_id)
                    .where(
                        TeamMember.user_id == user_id,
                        Team.is_deleted == False,  # noqa: E712
                        Team.is_active == True,  # noqa: E712
                    )
                    .order_by(Team.id)
                )
                rows = [dict(row) for row in result.mappings().all()]
                self.__console_service_logger.info(
                    "Found {} team(s) for user_id={}".format(len(rows), user_id)
                )
                return rows
        except Exception as exc:
            self.__console_service_logger.error(
                "DB error in get_teams_for_user user_id={}: {}".format(user_id, exc)
            )
            raise exc
