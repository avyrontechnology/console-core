"""Plan service layer."""

from uuid import UUID
from typing import List, Optional

from src.components.plan.errors import PlanNotFoundError
from src.components.plan.models import Plan
from src.components.plan.repositories import PlanRepository
from src.components.plan.schema import PlanBase, PlanUpdate
from src.loggers.console_service_logger import ConsoleServiceLogger


class PlanService:
    """Business logic for Plan operations. Converts repo exceptions into domain errors."""

    def __init__(self, plan_repository: PlanRepository, logger: ConsoleServiceLogger):
        self.__plan_repository: PlanRepository = plan_repository
        self.__logger: ConsoleServiceLogger = logger

    async def create_plan(self, plan_data: PlanBase, user_id: UUID) -> Plan:
        """Create new plan."""
        self.__logger.info(
            "Service: create_plan started name={}".format(plan_data.name)
        )
        try:
            plan: Plan = await self.__plan_repository.create_plan(plan_data, user_id)
            self.__logger.info("Service: create_plan completed id={}".format(plan.id))
            return plan
        except Exception as e:
            self.__logger.error(
                "Service: create_plan unexpected error name={} err={}".format(
                    plan_data.name, e
                )
            )
            raise

    async def get_active_plans(
        self,
        partner_id: Optional[UUID] = None,
        service_name: Optional[str] = None,
        plan_type: Optional[str] = None,
        duration: Optional[int] = None,
    ) -> List[Plan]:
        """Return all active plans with purchase status."""
        self.__logger.info("Service: get_active_plans started")
        try:
            plans: List[Plan] = await self.__plan_repository.get_active_plans(
                partner_id, service_name, plan_type, duration
            )
            self.__logger.info(
                "Service: get_active_plans returning {} plans".format(len(plans))
            )
            return plans
        except Exception as e:
            self.__logger.error(
                "Service: get_active_plans unexpected error err={}".format(e)
            )
            raise

    async def get_plan_by_id(self, plan_id: UUID) -> Plan:
        """Get a single plan or raise PlanNotFoundError."""
        try:
            self.__logger.info("Service: get_plan_by_id started id={}".format(plan_id))
            plan: Optional[Plan] = await self.__plan_repository.get_plan_by_id(plan_id)
            if not plan:
                self.__logger.info(
                    "Service: get_plan_by_id not found id={}".format(plan_id)
                )
                raise PlanNotFoundError(plan_id)
            return plan
        except Exception as e:
            self.__logger.error(
                "Service: get_plan_by_id unexpected error err={}".format(e)
            )
            raise

    async def update_plan(
        self, plan_id: UUID, plan_data: PlanUpdate, user_id: UUID
    ) -> Plan:
        """Update an existing plan."""
        self.__logger.info("Service: update_plan started id={}".format(plan_id))

        try:
            updated: Optional[Plan] = await self.__plan_repository.update_plan(
                plan_id, plan_data, user_id
            )
            if not updated:
                self.__logger.info(
                    "Service: update_plan not found id={}".format(plan_id)
                )
                raise PlanNotFoundError(plan_id)
            self.__logger.info("Service: update_plan succeeded id={}".format(plan_id))
            return updated
        except Exception as e:
            self.__logger.error(
                "Service: update_plan unexpected error id={} err={}".format(plan_id, e)
            )
            raise

    async def delete_plan(self, plan_id: UUID, user_id: UUID) -> None:
        """Soft delete a plan."""
        try:
            self.__logger.info("Service: delete_plan started id={}".format(plan_id))

            deleted: bool = await self.__plan_repository.delete_plan(plan_id, user_id)
            if not deleted:
                self.__logger.info(
                    "Service: delete_plan not found id={}".format(plan_id)
                )
                raise PlanNotFoundError(plan_id)

            self.__logger.info("Service: delete_plan completed id={}".format(plan_id))
        except Exception as e:
            self.__logger.error(
                "Service: delete_plan unexpected error id={} err={}".format(plan_id, e)
            )
            raise
