from typing import Any, Dict, List, Optional

from dependency_injector.wiring import Provide, inject
from fastapi import Depends, Query, Request
from fastapi.encoders import jsonable_encoder

from src.components.rbac.permission_dependency import PermissionDependency
from src.components.rbac.permission_injector import permission_check
from src.components.common.response import (
    APIResponse,
    BadRequestResponse,
    InternalServerErrorResponse,
    NotFoundResponse,
    ResourceCreatedResponse,
    SuccessNoContentResponse,
    SuccessResponse,
)
from src.components.team.error import TeamException, TeamNotFoundError
from src.components.team.models import Team, TeamMember
from src.components.team.schema import (
    TeamCreate,
    TeamMemberCreate,
    TeamMemberDetailResponse,
    TeamMemberResponse,
    TeamMemberUpdate,
    TeamPaginatedResponse,
    TeamResponse,
    TeamStrictHierarchyPolicy,
    TeamUpdate,
    UserAssociatedTeamsResponse,
    CurrentUserTeamItem
)
from src.components.team.service import TeamService
from src.core.container import Container
from src.loggers.console_service_logger import ConsoleServiceLogger

from fastapi import APIRouter


class TeamController:

    team_router: APIRouter = APIRouter()

    @team_router.post("/team", response_model=TeamResponse)
    @permission_check(PermissionDependency)
    @inject
    async def create_team(
        request: Request,
        data: TeamCreate,
        team_service: TeamService = Depends(Provide[Container.team_service]),
        logger: ConsoleServiceLogger = Depends(
            Provide[Container.console_service_logger]
        ),
    ) -> APIResponse:
        try:
            current_user: Dict[str, Any] = request.state.user
            team: Team = await team_service.create_team(data, current_user)
            return ResourceCreatedResponse(
                data=jsonable_encoder(TeamResponse.model_validate(team)),
                message="Team created successfully"
            )
        except TeamException as exc:
            logger.error("Create team failed: {}".format(str(exc)))
            return BadRequestResponse(str(exc))
        except Exception as exc:
            logger.error("Unexpected error in create_team: {}".format(exc))
            return InternalServerErrorResponse()

    @team_router.get("/teams", response_model=TeamPaginatedResponse)
    @permission_check(PermissionDependency)
    @inject
    async def get_teams(
        request: Request,
        search_by: Optional[str] = Query(None, description="filter teams by name"),
        limit: Optional[int] = Query(
            None, description="number of records per page", ge=1
        ),
        offset: Optional[int] = Query(
            None, description="zero-based page offset", ge=0
        ),
        team_service: TeamService = Depends(Provide[Container.team_service]),
        logger: ConsoleServiceLogger = Depends(
            Provide[Container.console_service_logger]
        ),
    ) -> APIResponse:
        if (limit is None) != (offset is None):
            return BadRequestResponse(
                detail="Both 'limit' and 'offset' must be provided together for pagination."
            )

        try:
            current_user: Dict[str, Any] = request.state.user
            result: TeamPaginatedResponse = await team_service.list_teams(
                current_user, search_by, limit, offset
            )
            return SuccessResponse(
                data=jsonable_encoder(result.data),
                message="Team fetched successfully",
                pagination={
                    "total_count": result.total_count,
                    "total_active": result.total_active,
                    "total_inactive": result.total_inactive,
                    "limit": result.limit,
                    "offset": result.offset,
                },
            )
        except TeamException as exc:
            logger.error("Get teams failed: {}".format(exc))
            return BadRequestResponse(str(exc))
        except Exception as exc:
            logger.error("Unexpected error in get_teams: {}".format(exc))
            return InternalServerErrorResponse()

    @team_router.get("/get_user_associated_teams")
    @permission_check(PermissionDependency)
    @inject
    async def get_user_associated_teams(
        request: Request,
        team_service: TeamService = Depends(Provide[Container.team_service]),
        logger: ConsoleServiceLogger = Depends(
            Provide[Container.console_service_logger]
        ),
    ) -> APIResponse:
        try:
            current_user: Dict[str, Any] = request.state.user
            result: List[UserAssociatedTeamsResponse] = (
                await team_service.get_user_associated_teams(current_user)
            )
            return SuccessResponse(
                message="Teams fetched successfully",
                data=[jsonable_encoder(entry) for entry in result]
            )
        except TeamException as exc:
            logger.error("Get user associated teams failed: {}".format(exc))
            return BadRequestResponse(str(exc))
        except Exception as exc:
            logger.error(
                "Unexpected error in get_user_associated_teams: {}".format(exc)
            )
            return InternalServerErrorResponse()

    @team_router.get("/team/current_user_teams")
    @permission_check(PermissionDependency)
    @inject
    async def get_current_user_teams(
        request: Request,
        team_service: TeamService = Depends(Provide[Container.team_service]),
        logger: ConsoleServiceLogger = Depends(
            Provide[Container.console_service_logger]
        ),
    ) -> APIResponse:
        try:
            current_user: Dict[str, Any] = request.state.user
            logger.info(
                "get_current_user_teams called by user_id={}".format(
                    current_user.get("user_id")
                )
            )
            result: List[CurrentUserTeamItem] = (
                await team_service.get_current_user_teams(current_user)
            )
            return SuccessResponse(
                message="Teams fetched successfully",
                data=[jsonable_encoder(entry) for entry in result]
            )
        except TeamException as exc:
            logger.error("Get current user teams failed: {}".format(exc))
            return BadRequestResponse(str(exc))
        except Exception as exc:
            logger.error(
                "Unexpected error in get_current_user_teams: {}".format(exc)
            )
            return InternalServerErrorResponse()

    @team_router.get("/team/{team_id}")
    @permission_check(PermissionDependency)
    @inject
    async def get_team_by_id(
        request: Request,
        team_id: int,
        team_service: TeamService = Depends(Provide[Container.team_service]),
        logger: ConsoleServiceLogger = Depends(
            Provide[Container.console_service_logger]
        ),
    ) -> APIResponse:
        try:
            current_user: Dict[str, Any] = request.state.user
            team: Team = await team_service.get_team(team_id, current_user)
            return SuccessResponse(
                message="Team fetched successfully",
                data=jsonable_encoder(TeamResponse.model_validate(team))
            )
        except TeamNotFoundError as exc:
            logger.error("Team {} not found: {}".format(team_id, exc))
            return NotFoundResponse(str(exc))
        except Exception as exc:
            logger.error("Unexpected error in get_team_by_id team_id={}: {}".format(team_id, exc))
            return InternalServerErrorResponse()

    @team_router.patch("/team/{team_id}")
    @permission_check(PermissionDependency)
    @inject
    async def update_team(
        request: Request,
        team_id: int,
        data: TeamUpdate,
        team_service: TeamService = Depends(Provide[Container.team_service]),
        logger: ConsoleServiceLogger = Depends(
            Provide[Container.console_service_logger]
        ),
    ) -> APIResponse:
        try:
            current_user: Dict[str, Any] = request.state.user
            team: Team = await team_service.update_team(team_id, data, current_user)
            return SuccessResponse(
                message="Team updated successfully",
                data=jsonable_encoder(TeamResponse.model_validate(team))
            )
        except TeamNotFoundError as exc:
            logger.error("Team {} not found for update: {}".format(team_id, exc))
            return NotFoundResponse(str(exc))
        except TeamException as exc:
            logger.error("Update team failed team_id={}: {}".format(team_id, exc))
            return BadRequestResponse(str(exc))
        except Exception as exc:
            logger.error("Unexpected error in update_team team_id={}: {}".format(team_id, exc))
            return InternalServerErrorResponse()

    @team_router.delete("/team/{team_id}")
    @permission_check(PermissionDependency)
    @inject
    async def delete_team(
        request: Request,
        team_id: int,
        team_service: TeamService = Depends(Provide[Container.team_service]),
        logger: ConsoleServiceLogger = Depends(
            Provide[Container.console_service_logger]
        ),
    ) -> APIResponse:
        try:
            current_user: Dict[str, Any] = request.state.user
            await team_service.delete_team(team_id, current_user)
            return SuccessNoContentResponse()
        except TeamNotFoundError as exc:
            logger.error("Team {} not found for delete: {}".format(team_id, exc))
            return NotFoundResponse(str(exc))
        except Exception as exc:
            logger.error("Unexpected error in delete_team team_id={}: {}".format(team_id, exc))
            return InternalServerErrorResponse()

    @team_router.post("/team/{team_id}/member", response_model=TeamMemberResponse)
    @permission_check(PermissionDependency)
    @inject
    async def add_team_member(
        request: Request,
        team_id: int,
        data: TeamMemberCreate,
        team_service: TeamService = Depends(Provide[Container.team_service]),
        logger: ConsoleServiceLogger = Depends(
            Provide[Container.console_service_logger]
        ),
    ) -> APIResponse:
        try:
            current_user: Dict[str, Any] = request.state.user
            member: TeamMember = await team_service.add_member(team_id, data, current_user)
            return ResourceCreatedResponse(
                message="Team member added successfully",
                data=jsonable_encoder(TeamMemberResponse.model_validate(member))
            )
        except TeamNotFoundError as exc:
            logger.error("Team {} not found when adding member: {}".format(team_id, exc))
            return NotFoundResponse(str(exc))
        except TeamException as exc:
            logger.error("Add member failed team_id={}: {}".format(team_id, exc))
            return BadRequestResponse(str(exc))
        except Exception as exc:
            logger.error("Unexpected error in add_team_member team_id={}: {}".format(team_id, exc))
            return InternalServerErrorResponse()

    @team_router.patch("/team/{team_id}/member/{member_user_id}", response_model=TeamMemberResponse)
    @permission_check(PermissionDependency)
    @inject
    async def update_team_member(
        request: Request,
        team_id: int,
        member_user_id: int,
        data: TeamMemberUpdate,
        team_service: TeamService = Depends(Provide[Container.team_service]),
        logger: ConsoleServiceLogger = Depends(
            Provide[Container.console_service_logger]
        ),
    ) -> APIResponse:
        try:
            current_user: Dict[str, Any] = request.state.user
            member: TeamMember = await team_service.update_member(
                team_id, member_user_id, data, current_user
            )
            return SuccessResponse(
                message= "Team member updated successfully",
                data=jsonable_encoder(TeamMemberResponse.model_validate(member))
            )
        except TeamNotFoundError as exc:
            logger.error("Team {} not found when updating member {}: {}".format(team_id, member_user_id, exc))
            return NotFoundResponse(str(exc))
        except TeamException as exc:
            logger.error("Update member failed team_id={} user_id={}: {}".format(team_id, member_user_id, exc))
            return BadRequestResponse(str(exc))
        except Exception as exc:
            logger.error("Unexpected error in update_team_member team_id={} user_id={}: {}".format(team_id, member_user_id, exc))
            return InternalServerErrorResponse()

    @team_router.delete("/team/{team_id}/member/{member_user_id}")
    @permission_check(PermissionDependency)
    @inject
    async def remove_team_member(
        request: Request,
        team_id: int,
        member_user_id: int,
        team_service: TeamService = Depends(Provide[Container.team_service]),
        logger: ConsoleServiceLogger = Depends(
            Provide[Container.console_service_logger]
        ),
    ) -> APIResponse:
        try:
            current_user: Dict[str, Any] = request.state.user
            await team_service.remove_member(team_id, member_user_id, current_user)
            return SuccessNoContentResponse()
        except TeamNotFoundError as exc:
            logger.error("Team {} not found when removing member {}: {}".format(team_id, member_user_id, exc))
            return NotFoundResponse(str(exc))
        except TeamException as exc:
            logger.error("Remove member failed team_id={} user_id={}: {}".format(team_id, member_user_id, exc))
            return BadRequestResponse(str(exc))
        except Exception as exc:
            logger.error("Unexpected error in remove_team_member team_id={} user_id={}: {}".format(team_id, member_user_id, exc))
            return InternalServerErrorResponse()

    @team_router.get("/team/{team_id}/members")
    @permission_check(PermissionDependency)
    @inject
    async def get_team_members(
        request: Request,
        team_id: int,
        limit: Optional[int] = Query(
            None, description="number of records per page", ge=1
        ),
        offset: Optional[int] = Query(
            None, description="zero-based page offset", ge=0
        ),
        team_service: TeamService = Depends(Provide[Container.team_service]),
        logger: ConsoleServiceLogger = Depends(
            Provide[Container.console_service_logger]
        ),
    ) -> APIResponse:
        if (limit is None) != (offset is None):
            return BadRequestResponse(
                detail="Both 'limit' and 'offset' must be provided together for pagination."
            )

        try:
            current_user: Dict[str, Any] = request.state.user
            rows, total_count = await team_service.get_members(
                team_id, current_user, limit, offset
            )
            return SuccessResponse(
                message="Team members fetched successfully",
                data=jsonable_encoder(
                    [TeamMemberDetailResponse.model_validate(r) for r in rows]
                ),
                pagination={
                    "total_count": total_count,
                    "limit": limit,
                    "offset": offset,
                },
            )
        except TeamNotFoundError as exc:
            logger.error("Team {} not found when fetching members: {}".format(team_id, exc))
            return NotFoundResponse(str(exc))
        except Exception as exc:
            logger.error("Unexpected error in get_team_members team_id={}: {}".format(team_id, exc))
            return InternalServerErrorResponse()

    @team_router.post("/team/strict_hierarchy_policy")
    @permission_check(PermissionDependency)
    @inject
    async def configure_team_strict_hierarchy(
        request: Request,
        policy: TeamStrictHierarchyPolicy,
        team_service: TeamService = Depends(Provide[Container.team_service]),
        logger: ConsoleServiceLogger = Depends(
            Provide[Container.console_service_logger]
        ),
    ) -> APIResponse:
        try:
            current_user: Dict[str, Any] = request.state.user
            result: Dict[str, Any] = await team_service.configure_team_strict_hierarchy(
                policy, current_user
            )
            return SuccessResponse(message="hierarchy configured successfully", data=jsonable_encoder(result))
        except TeamException as exc:
            logger.error("Configure strict hierarchy failed: {}".format(exc))
            return BadRequestResponse(str(exc))
        except Exception as exc:
            logger.error("Unexpected error in configure_team_strict_hierarchy: {}".format(exc))
            return InternalServerErrorResponse()
