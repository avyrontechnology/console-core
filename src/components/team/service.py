from uuid import UUID
from typing import Any, Dict, List, Optional, Tuple

from src.components.audit_log.schema import AuditLogSchema
from src.components.audit_log.services import AuditService
from src.components.common.actions import AuditActions
from src.components.common.constants import CurrentUserMap
from src.components.common.resources import Resource
from src.components.partner.models import Partner
from src.components.partner_config.constants import PartnerConfigEnum
from src.components.partner_config.schemas import PartnerConfigData, PartnerConfigResponse
from src.components.partner_config.services import PartnerConfigService
from src.components.team.constants import (
    TeamExceptionMsg,
    TeamStrictHierarchyMode,
)
from src.components.team.error import TeamException, TeamNotFoundError
from src.components.team.models import Team, TeamMember
from src.components.team.repositories import TeamRepository
from src.components.team.schema import (
    TeamCreate,
    TeamListItemResponse,
    TeamMemberCreate,
    TeamMemberUpdate,
    TeamPaginatedResponse,
    TeamStrictHierarchyPolicy,
    TeamUpdate,
    UserAssociatedTeamItem,
    UserAssociatedTeamsResponse,
    CurrentUserTeamItem
)
from src.components.user.models import User
from src.core.redis import RedisCache
from src.loggers.console_service_logger import ConsoleServiceLogger

# Matches Team.slug's column length (String(128)) in src/components/team/models.py.
TEAM_SLUG_MAX_LENGTH: int = 128


class TeamService:
    def __init__(
        self,
        team_repository: TeamRepository,
        console_service_logger: ConsoleServiceLogger,
        audit_service: AuditService,
        partner_config_service: PartnerConfigService,
    ) -> None:
        self.__team_repository: TeamRepository = team_repository
        self.__console_service_logger: ConsoleServiceLogger = console_service_logger
        self.__audit_service: AuditService = audit_service
        self.__partner_config_service: PartnerConfigService = partner_config_service

    async def __invalidate_user_teams_cache(
        self, partner_id: UUID, user_id: UUID
    ) -> None:
        # Team-cache invalidation retired with the external cache consumer;
        # membership changes need no cache busts anymore.
        return None

    # ------------------------------ helpers ------------------------------- #

    async def __ensure_teams_enabled(self, partner_id: UUID) -> None:
        config: Optional[PartnerConfigResponse] = (
            await self.__partner_config_service.get_partner_config_by_key(
                partner_id, PartnerConfigEnum.IS_TEAMS_ENABLED.value
            )
        )
        if not (config and getattr(config, "value", False)):
            self.__console_service_logger.error(
                "Teams not enabled for partner {}".format(partner_id)
            )
            raise TeamException(TeamExceptionMsg.TEAMS_NOT_ENABLED)

    async def __validate_parent(
        self, partner_id: UUID, parent_team_id: UUID, team_id: Optional[UUID] = None
    ) -> None:
        parent: Optional[Team] = await self.__team_repository.get_team_by_id(parent_team_id)
        if parent is None:
            self.__console_service_logger.error(
                "Parent team {} not found for partner {}".format(parent_team_id, partner_id)
            )
            raise TeamException(TeamExceptionMsg.PARENT_NOT_FOUND)
        if parent.partner_id != partner_id:
            self.__console_service_logger.error(
                "Parent team {} belongs to a different partner (expected {})".format(
                    parent_team_id, partner_id
                )
            )
            raise TeamException(TeamExceptionMsg.PARENT_DIFFERENT_PARTNER)
        if team_id is not None:
            if parent_team_id == team_id:
                self.__console_service_logger.error(
                    "Cycle detected: team {} cannot be its own parent".format(team_id)
                )
                raise TeamException(TeamExceptionMsg.PARENT_CYCLE)
            ancestor_ids: List[int] = await self.__team_repository.get_parent_chain_ids(
                parent_team_id
            )
            if team_id in ancestor_ids:
                self.__console_service_logger.error(
                    "Cycle detected: team {} is an ancestor of parent {}".format(
                        team_id, parent_team_id
                    )
                )
                raise TeamException(TeamExceptionMsg.PARENT_CYCLE)

    async def __validate_member_role(
        self, partner_id: UUID, role_id: Optional[UUID]
    ) -> None:
        if role_id is None:
            return
        is_valid: bool = await self.__team_repository.is_role_in_partner_catalog(
            role_id, partner_id
        )
        if not is_valid:
            self.__console_service_logger.error(
                "Role {} not in catalog for partner {}".format(role_id, partner_id)
            )
            raise TeamException(TeamExceptionMsg.ROLE_NOT_IN_CATALOG)

    # ------------------------------ teams --------------------------------- #

    @staticmethod
    def __normalize_name(name: str) -> str:
        return "_".join(name.strip().split())

    @staticmethod
    def __build_slug(normalized_name: str, team_id: UUID) -> str:
        """Derive a team's slug from its own name and id: ``{normalized_name}_{id}``."""
        suffix: str = "_{}".format(team_id)
        available_length: int = TEAM_SLUG_MAX_LENGTH - len(suffix)
        return normalized_name[:available_length] + suffix

    async def create_team(self, data: TeamCreate, current_user: Dict[str, Any]) -> Team:
        partner_id: UUID = data.partner_id
        user_id: UUID = current_user.get(CurrentUserMap.USER_ID)

        is_interal: bool = current_user.get("is_internal")
        if not is_interal and partner_id != current_user.get(CurrentUserMap.PARTNER_ID):
            self.__console_service_logger.error(
                "Unauthorized team create attempt by user {} for partner {}".format(
                    user_id, partner_id
                )
            )
            raise TeamException("only internal user or current partners user can create team")

        self.__console_service_logger.info(
            "Creating team '{}' for partner {}".format(data.name, partner_id)
        )

        await self.__ensure_teams_enabled(partner_id)

        partner: Optional[Partner] = await self.__team_repository.get_partner(partner_id)
        if partner is None:
            self.__console_service_logger.error(
                "Partner {} not found when creating team".format(partner_id)
            )
            raise TeamException(TeamExceptionMsg.PARTNER_NOT_FOUND)

        if data.parent_team_id is not None:
            await self.__validate_parent(partner_id, data.parent_team_id)

        normalized_name: str = self.__normalize_name(data.name)
        values: Dict[str, Any] = {
            "name": data.name,
            # Placeholder: Team.slug is NOT NULL and has no default, so a valid
            # value must exist before the initial insert. Replaced below with
            # the real {name}_{id} slug once the row's id is known.
            "slug": normalized_name,
            "description": data.description,
            "partner_id": partner_id,
            "parent_team_id": data.parent_team_id,
            "is_internal": bool(partner.is_internal),
        }
        team: Team = await self.__team_repository.create_team(
            values, user_id, lambda t: self.__build_slug(normalized_name, t.id)
        )

        # A newly created team must appear in the partner-teams cache
        # reads (gRPC_GET_PARTNER_TEAMS_PARTNER:{partner_id}, TTL one
        # week). Without this, that stale list omits the team until a member
        # mutation or the TTL clears it. See map_team_to_board's partner check.

        await self.__audit_service.log_action(
            AuditLogSchema(
                action=AuditActions.create,
                resource=Resource.team,
                resource_id=team.id,
                resource_current_state=str({**values, "slug": team.slug}),
                performed_by=user_id,
                details="Team created with id: {}".format(team.id),
            )
        )
        return team

    async def get_team(self, team_id: UUID, current_user: Dict[str, Any]) -> Team:
        partner_id: UUID = current_user.get(CurrentUserMap.PARTNER_ID)
        team: Optional[Team] = await self.__team_repository.get_team_by_id(team_id, partner_id)
        if team is None:
            raise TeamNotFoundError(team_id)
        return team

    async def list_teams(
        self,
        current_user: Dict[str, Any],
        search_by: Optional[str] = None,
        limit: Optional[int] = None,
        offset: Optional[int] = None,
    ) -> TeamPaginatedResponse:
        """Pagination is zero-based and optional: pass both ``limit`` and
        ``offset`` to page (row_offset = offset * limit), or neither to get
        everything."""
        partner_id: UUID = current_user.get(CurrentUserMap.PARTNER_ID)
        await self.__ensure_teams_enabled(partner_id)

        rows, total_count, total_active, total_inactive = (
            await self.__team_repository.list_teams_paginated(
                partner_id, search_by, limit, offset
            )
        )
        return TeamPaginatedResponse(
            total_count=total_count,
            total_active=total_active,
            total_inactive=total_inactive,
            limit=limit,
            offset=offset,
            data=[TeamListItemResponse.model_validate(r) for r in rows],
        )

    async def get_user_associated_teams(
        self, current_user: Dict[str, Any]
    ) -> List[UserAssociatedTeamsResponse]:
        """Team memberships for every user of the current user's partner (not
        just the caller) — one entry per user, present even with zero teams."""
        partner_id: UUID = current_user.get(CurrentUserMap.PARTNER_ID)
        await self.__ensure_teams_enabled(partner_id)

        rows: List[Dict[str, Any]] = (
            await self.__team_repository.get_teams_for_partner_users(partner_id)
        )

        teams_by_user: Dict[int, List[Dict[str, Any]]] = {}
        for row in rows:
            team_rows: List[Dict[str, Any]] = teams_by_user.setdefault(
                row["user_id"], []
            )
            if row["team_id"] is not None:
                team_rows.append(row)

        return [
            UserAssociatedTeamsResponse(
                user_id=user_id,
                team_count=len(team_rows),
                teams=[UserAssociatedTeamItem.model_validate(r) for r in team_rows],
            )
            for user_id, team_rows in teams_by_user.items()
        ]

    async def update_team(
        self, team_id: UUID, data: TeamUpdate, current_user: Dict[str, Any]
    ) -> Team:
        partner_id: UUID = current_user.get(CurrentUserMap.PARTNER_ID)
        user_id: UUID = current_user.get(CurrentUserMap.USER_ID)

        team: Optional[Team] = await self.__team_repository.get_team_by_id(team_id, partner_id)
        if team is None:
            raise TeamNotFoundError(team_id)

        update_values: Dict[str, Any] = data.model_dump(exclude_unset=True)
        if "parent_team_id" in update_values and update_values["parent_team_id"]:
            await self.__validate_parent(
                partner_id, update_values["parent_team_id"], team_id=team_id
            )

        updated: Team = await self.__team_repository.update_team(
            team_id, update_values, user_id
        )

        # name / parent_team_id are cached in the partner-teams list
        # reads; drop it so a rename or reparent isn't stale for up to a week.

        await self.__audit_service.log_action(
            AuditLogSchema(
                action=AuditActions.update,
                resource=Resource.team,
                resource_id=team_id,
                resource_current_state=str(update_values),
                performed_by=user_id,
                details="Team updated id: {}".format(team_id),
            )
        )
        return updated

    async def delete_team(self, team_id: UUID, current_user: Dict[str, Any]) -> None:
        partner_id: UUID = current_user.get(CurrentUserMap.PARTNER_ID)
        user_id: UUID = current_user.get(CurrentUserMap.USER_ID)

        team: Optional[Team] = await self.__team_repository.get_team_by_id(team_id, partner_id)
        if team is None:
            raise TeamNotFoundError(team_id)

        await self.__team_repository.soft_delete_team(team_id, user_id)

        await self.__audit_service.log_action(
            AuditLogSchema(
                action=AuditActions.delete,
                resource=Resource.team,
                resource_id=team_id,
                performed_by=user_id,
                details="Team soft-deleted id: {}".format(team_id),
            )
        )

    # ---------------------------- membership ------------------------------ #

    async def add_member(
        self, team_id: UUID, data: TeamMemberCreate, current_user: Dict[str, Any]
    ) -> TeamMember:
        partner_id: UUID = current_user.get(CurrentUserMap.PARTNER_ID)
        user_id: UUID = current_user.get(CurrentUserMap.USER_ID)

        team: Optional[Team] = await self.__team_repository.get_team_by_id(team_id, partner_id)
        if team is None:
            raise TeamNotFoundError(team_id)

        member_user: Optional[User] = await self.__team_repository.get_user(data.user_id)
        if member_user is None:
            self.__console_service_logger.error(
                "User {} not found when adding to team {}".format(data.user_id, team_id)
            )
            raise TeamException(TeamExceptionMsg.MEMBER_USER_NOT_FOUND)
        if member_user.partner_id != partner_id:
            self.__console_service_logger.error(
                "User {} belongs to a different partner (expected {})".format(
                    data.user_id, partner_id
                )
            )
            raise TeamException(TeamExceptionMsg.MEMBER_DIFFERENT_PARTNER)

        await self.__validate_member_role(partner_id, data.role_id)

        if await self.__team_repository.get_member(team_id, data.user_id) is not None:
            self.__console_service_logger.error(
                "User {} is already a member of team {}".format(data.user_id, team_id)
            )
            raise TeamException(TeamExceptionMsg.DUPLICATE_MEMBER)

        member: TeamMember = await self.__team_repository.add_member(
            team_id=team_id,
            user_id=data.user_id,
            role_id=data.role_id,
            created_by=user_id,
        )
        await self.__audit_service.log_action(
            AuditLogSchema(
                action=AuditActions.create,
                resource=Resource.team_member,
                resource_id=member.id,
                resource_current_state=str(data.model_dump()),
                performed_by=user_id,
                details="Member {} added to team {}".format(data.user_id, team_id),
            )
        )
        return member

    async def remove_member(
        self, team_id: UUID, member_user_id: UUID, current_user: Dict[str, Any]
    ) -> None:
        partner_id: UUID = current_user.get(CurrentUserMap.PARTNER_ID)
        user_id: UUID = current_user.get(CurrentUserMap.USER_ID)

        team: Optional[Team] = await self.__team_repository.get_team_by_id(team_id, partner_id)
        if team is None:
            raise TeamNotFoundError(team_id)

        removed: bool = await self.__team_repository.remove_member(team_id, member_user_id)
        if not removed:
            self.__console_service_logger.error(
                "Member {} not found in team {} for removal".format(member_user_id, team_id)
            )
            raise TeamException(TeamExceptionMsg.MEMBER_NOT_FOUND)

        await self.__audit_service.log_action(
            AuditLogSchema(
                action=AuditActions.delete,
                resource=Resource.team_member,
                resource_id=team_id,
                performed_by=user_id,
                details="Member {} removed from team {}".format(
                    member_user_id, team_id
                ),
            )
        )

    async def update_member(
        self,
        team_id: UUID,
        member_user_id: UUID,
        data: TeamMemberUpdate,
        current_user: Dict[str, Any],
    ) -> TeamMember:
        partner_id: UUID = current_user.get(CurrentUserMap.PARTNER_ID)
        user_id: UUID = current_user.get(CurrentUserMap.USER_ID)

        team: Optional[Team] = await self.__team_repository.get_team_by_id(team_id, partner_id)
        if team is None:
            raise TeamNotFoundError(team_id)

        await self.__validate_member_role(partner_id, data.role_id)

        updated: Optional[TeamMember] = await self.__team_repository.update_member_role(
            team_id, member_user_id, data.role_id
        )
        if updated is None:
            self.__console_service_logger.error(
                "Member {} not found in team {} for update".format(member_user_id, team_id)
            )
            raise TeamException(TeamExceptionMsg.MEMBER_NOT_FOUND)

        await self.__audit_service.log_action(
            AuditLogSchema(
                action=AuditActions.update,
                resource=Resource.team_member,
                resource_id=updated.id,
                resource_current_state=str(data.model_dump()),
                performed_by=user_id,
                details="Member {} role updated in team {}".format(
                    member_user_id, team_id
                ),
            )
        )
        return updated

    async def get_members(
        self,
        team_id: UUID,
        current_user: Dict[str, Any],
        limit: Optional[int] = None,
        offset: Optional[int] = None,
    ) -> Tuple[List[Dict[str, Any]], int]:
        """Team members with user_name/role_name attached. Pagination is
        zero-based and optional: pass both ``limit`` and ``offset`` to page,
        or neither to get everything. Returns ``(rows, total_count)``."""
        partner_id: UUID = current_user.get(CurrentUserMap.PARTNER_ID)
        team: Optional[Team] = await self.__team_repository.get_team_by_id(team_id, partner_id)
        if team is None:
            raise TeamNotFoundError(team_id)
        return await self.__team_repository.get_members_paginated(team_id, limit, offset)

    # --------------------- strict-hierarchy policy ------------------------ #

    async def configure_team_strict_hierarchy(
        self, policy: TeamStrictHierarchyPolicy, current_user: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Set the partner's strict-hierarchy-in-teams mode (off/full/partial).

        For PARTIAL mode a ``start_role_id`` must be tagged and must belong to
        the partner's effective role catalog. Enforcement of the resolved policy
        lives in the scope resolver; this only stores the configuration.
        """
        partner_id: UUID = current_user.get(CurrentUserMap.PARTNER_ID)
        user_id: UUID = current_user.get(CurrentUserMap.USER_ID)

        await self.__ensure_teams_enabled(partner_id)

        start_role_id: Optional[UUID] = None
        if policy.mode == TeamStrictHierarchyMode.PARTIAL:
            if policy.start_role_id is None:
                self.__console_service_logger.error(
                    "start_role_id required for PARTIAL mode for partner {}".format(partner_id)
                )
                raise TeamException(TeamExceptionMsg.START_ROLE_REQUIRED)
            valid: bool = await self.__team_repository.is_role_in_partner_catalog(
                policy.start_role_id, partner_id
            )
            if not valid:
                self.__console_service_logger.error(
                    "Role {} is not a valid start role for partner {}".format(
                        policy.start_role_id, partner_id
                    )
                )
                raise TeamException(TeamExceptionMsg.INVALID_START_ROLE)
            start_role_id = policy.start_role_id

        config_payload: PartnerConfigData = PartnerConfigData(
            team_strict_hierarchy_mode=policy.mode.value,
            team_strict_hierarchy_start_role_id=start_role_id,
        )
        await self.__partner_config_service.update_partner_config(
            partner_id, config_payload, current_user
        )

        await self.__audit_service.log_action(
            AuditLogSchema(
                action=AuditActions.update,
                resource=Resource.team,
                resource_id=None,
                resource_current_state=str(policy.model_dump()),
                performed_by=user_id,
                details="Team strict-hierarchy policy set to {}".format(
                    policy.mode.value
                ),
            )
        )
        return {
            "mode": policy.mode.value,
            "start_role_id": start_role_id,
        }

    async def get_user_teams(self, user_id: UUID) -> List[Team]:
        return await self.__team_repository.get_user_teams(user_id)

    async def get_current_user_teams(
        self, current_user: Dict[str, Any]
    ) -> List[CurrentUserTeamItem]:
        try:
            """Teams the *currently logged-in* user belongs to, with their role
            in each. Unlike get_user_associated_teams, this is scoped to a single
            user (the caller), not the whole partner."""
            user_id: UUID = current_user.get(CurrentUserMap.USER_ID)
            self.__console_service_logger.info(
                "Fetching current-user teams for user_id={}".format(user_id)
            )
            rows: List[Dict[str, Any]] = await self.__team_repository.get_teams_for_user(
                user_id
            )
            self.__console_service_logger.info(
                "Returning {} team(s) for current user_id={}".format(len(rows), user_id)
            )
            return [CurrentUserTeamItem.model_validate(r) for r in rows]
        except Exception as exec:
            self.__console_service_logger.error(f"An unexpected error occured: {exec}")
            raise exec
