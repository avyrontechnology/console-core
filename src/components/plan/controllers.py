from typing import Any, List, Optional, Set

from dependency_injector.wiring import Provide, inject
from fastapi import APIRouter, Depends, Request, status

from src.components.common.response import (
    BadRequestResponse,
    InternalServerErrorResponse,
    NotFoundResponse,
    ResourceConflictResponse,
    ResourceCreatedResponse,
    SuccessResponse,
    ValidationErrorResponse,
)
from src.components.plan.constants import PlanType, Platform
from src.components.plan.errors import (
    PlanHierarchyExistsError,
    PlanNotFoundError,
    WalletPlanExistsError,
)
from src.components.plan.mapper import SERVICE_FEATURE_MAPPER
from src.components.plan.models import Plan
from src.components.plan.schema import PlanBase, PlanResponse, PlanUpdate
from src.components.plan.services import PlanService
from src.components.rbac.permission_dependency import PermissionDependency
from src.components.rbac.permission_injector import permission_check
from src.core.container import Container
from src.loggers.console_service_logger import ConsoleServiceLogger


class PlanController:
    """Defines plan-related endpoints."""

    plan_router = APIRouter(prefix="/plans", tags=["Plans"])

    @plan_router.post(
        "/create-plan",
        response_model=PlanResponse,
        status_code=status.HTTP_201_CREATED,
    )
    @permission_check(PermissionDependency)
    @inject
    async def create_plan(
        request: Request,
        plan_data: PlanBase,
        plan_service: PlanService = Depends(Provide[Container.plan_service]),
        logger: ConsoleServiceLogger = Depends(
            Provide[Container.console_service_logger]
        ),
    ):
        logger.info(f"Controller: create_plan started name={plan_data.name}")

        try:
            current_user: dict = request.state.user
            user_id: int = current_user.get("user_id")

            created_plan: Plan = await plan_service.create_plan(plan_data, user_id)
            logger.info(f"Controller: create_plan succeeded id={created_plan.id}")

            response_data = PlanResponse.model_validate(created_plan).model_dump()

            return ResourceCreatedResponse(
                data=response_data,
                message="Plan created successfully",
            )

        except PlanHierarchyExistsError as exc:
            logger.error(
                f"Controller: create_plan hierarchy exists hierarchy={plan_data.hierarchy}"
            )
            return ResourceConflictResponse(detail=str(exc))

        except WalletPlanExistsError as exc:
            logger.error(
                f"Controller: create_plan wallet plan exists name={plan_data.name}"
            )
            return ResourceConflictResponse(detail=str(exc))

        except Exception as e:
            logger.error(
                f"Controller: create_plan unexpected error name={plan_data.name} err={e}"
            )
            return InternalServerErrorResponse(detail="Failed to create plan")

    @plan_router.get("/get-plans", response_model=List[PlanResponse])
    @inject
    @permission_check(PermissionDependency)
    async def get_active_plans(
        request: Request,
        service_name: Optional[str] = None,
        plan_type: Optional[str] = None,
        duration: Optional[int] = None,
        plan_service: PlanService = Depends(Provide[Container.plan_service]),
        logger: ConsoleServiceLogger = Depends(
            Provide[Container.console_service_logger]
        ),
    ):
        logger.info("Controller: get_active_plans started")

        try:

            allowed_platforms: Set[str] = {
                value
                for key, value in vars(Platform).items()
                if not key.startswith("_") and isinstance(value, str)
            }

            allowed_plan_types: Set[str] = {
                value
                for key, value in vars(PlanType).items()
                if not key.startswith("_") and isinstance(value, str)
            }

            if service_name is not None and service_name not in allowed_platforms:
                logger.warning(f"Invalid service_name received: {service_name}")
                return ValidationErrorResponse(
                    detail=(
                        "Invalid service_name. Allowed values are: "
                        + ", ".join(sorted(allowed_platforms))
                    )
                )

            if plan_type is not None and plan_type not in allowed_plan_types:
                logger.warning(f"Invalid plan_type received: {plan_type}")
                return ValidationErrorResponse(
                    detail=(
                        "Invalid plan_type. Allowed values are: "
                        + ", ".join(sorted(allowed_plan_types))
                    )
                )

            partner_id: Optional[int] = None
            if hasattr(request.state, "user") and request.state.user:
                partner_id: int = request.state.user.get("partner_id")
                logger.info(
                    f"Controller: get_active_plans authenticated request partner_id={partner_id}"
                )
            else:
                logger.info("Controller: get_active_plans unauthenticated request")

            plans: List[Plan] = await plan_service.get_active_plans(
                partner_id, service_name, plan_type, duration
            )
            logger.info(f"Controller: get_active_plans fetched {len(plans)} plans")

            data: list[dict[str, Any]] = [
                PlanResponse.model_validate(plan).model_dump() for plan in plans
            ]

            return SuccessResponse(data=data)

        except Exception as e:
            logger.error(f"Controller: get_active_plans unexpected error err={e}")
            return InternalServerErrorResponse(detail="Failed to fetch plans")

    @plan_router.get("/get-plan-by-id/{plan_id}", response_model=PlanResponse)
    @inject
    @permission_check(PermissionDependency)
    async def get_plan_by_id(
        request: Request,
        plan_id: int,
        plan_service: PlanService = Depends(Provide[Container.plan_service]),
        logger: ConsoleServiceLogger = Depends(
            Provide[Container.console_service_logger]
        ),
    ):
        logger.info(f"Controller: get_plan_by_id started id={plan_id}")

        try:
            plan: Plan = await plan_service.get_plan_by_id(plan_id)
            logger.info(f"Controller: get_plan_by_id succeeded id={plan_id}")

            data = PlanResponse.model_validate(plan).model_dump()

            return SuccessResponse(data=data)

        except PlanNotFoundError as exc:
            logger.error(f"Controller: get_plan_by_id not found id={plan_id}")
            return NotFoundResponse(detail=str(exc))

        except Exception as e:
            logger.error(
                f"Controller: get_plan_by_id unexpected error id={plan_id} err={e}"
            )
            return InternalServerErrorResponse(detail="Failed to fetch plan")

    @plan_router.patch("/update-plan/{plan_id}", response_model=PlanResponse)
    @inject
    @permission_check(PermissionDependency)
    async def update_plan(
        request: Request,
        plan_id: int,
        plan_data: PlanUpdate,
        plan_service: PlanService = Depends(Provide[Container.plan_service]),
        logger: ConsoleServiceLogger = Depends(
            Provide[Container.console_service_logger]
        ),
    ):
        logger.info(f"Controller: update_plan started id={plan_id}")

        try:
            current_user: dict = request.state.user
            user_id: int = current_user.get("user_id")

            updated_plan: Plan = await plan_service.update_plan(
                plan_id, plan_data, user_id
            )
            logger.info(f"Controller: update_plan succeeded id={plan_id}")

            response_data = PlanResponse.model_validate(updated_plan).model_dump()

            return SuccessResponse(
                data=response_data,
                message="Plan updated successfully",
            )

        except PlanHierarchyExistsError as exc:
            logger.error(
                f"Controller: update_plan hierarchy exists hierarchy={plan_data.hierarchy}"
            )
            return ResourceConflictResponse(detail=str(exc))

        except PlanNotFoundError as exc:
            logger.error(f"Controller: update_plan not found id={plan_id}")
            return NotFoundResponse(detail=str(exc))

        except WalletPlanExistsError as exc:
            logger.error(
                f"Controller: update_plan wallet plan exists name={plan_data.name}"
            )
            return ResourceConflictResponse(detail=str(exc))

        except Exception as e:
            logger.error(
                f"Controller: update_plan unexpected error id={plan_id} err={e}"
            )
            return InternalServerErrorResponse(detail="Failed to update plan")

    @plan_router.delete("/delete-plan/{plan_id}")
    @inject
    @permission_check(PermissionDependency)
    async def delete_plan(
        request: Request,
        plan_id: int,
        plan_service: PlanService = Depends(Provide[Container.plan_service]),
        logger: ConsoleServiceLogger = Depends(
            Provide[Container.console_service_logger]
        ),
    ):
        logger.info(f"Controller: delete_plan started id={plan_id}")

        try:
            current_user: dict = request.state.user
            user_id: int = current_user.get("user_id")

            await plan_service.delete_plan(plan_id, user_id)
            logger.info(f"Controller: delete_plan succeeded id={plan_id}")

            return SuccessResponse(message="Plan deleted successfully")

        except PlanNotFoundError as exc:
            logger.error(f"Controller: delete_plan not found id={plan_id}")
            return NotFoundResponse(detail=str(exc))

        except Exception as e:
            logger.error(
                f"Controller: delete_plan unexpected error id={plan_id} err={e}"
            )
            return InternalServerErrorResponse(detail="Failed to delete plan")

    @plan_router.get("/get-modules")
    @inject
    @permission_check(PermissionDependency)
    async def get_modules(
        request: Request,
        service_name: Optional[str] = None,
        logger: ConsoleServiceLogger = Depends(
            Provide[Container.console_service_logger]
        ),
    ):
        """
        Returns platform-wise modules & features for the UI.
        Can optionally filter by service/platform using `service_name` query param.
        """
        logger.info(f"Controller: get_modules started service_name={service_name}")

        try:
            if service_name:
                key: str = service_name.lower()
                if key not in SERVICE_FEATURE_MAPPER:
                    allowed = ", ".join(SERVICE_FEATURE_MAPPER.keys())
                    logger.warning(f"Invalid service_name={key}")
                    return BadRequestResponse(
                        detail=f"Invalid service '{key}'. Allowed: {allowed}"
                    )

                logger.info(f"Returning modules for platform={key}")
                return SuccessResponse(
                    data={"modules": {key: SERVICE_FEATURE_MAPPER[key]}}
                )

            # Return all platforms if no filter provided
            logger.info("Returning modules for all platforms")
            return SuccessResponse(data={"modules": SERVICE_FEATURE_MAPPER})

        except Exception as e:
            logger.error(f"Controller: get_modules unexpected error err={e}")
            return InternalServerErrorResponse(detail="Failed to fetch modules")
