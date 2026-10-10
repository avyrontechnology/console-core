"""Plan Repository layer."""

from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from src.components.entitlement.models import Entitlement
from src.components.order.models import Order
from src.components.plan.constants import PlanCustomLimitKeys, PlanType
from src.components.plan.errors import PlanHierarchyExistsError, WalletPlanExistsError
from src.components.plan.models import Plan
from src.components.plan.schema import PlanBase, PlanUpdate
from src.loggers.console_service_logger import ConsoleServiceLogger


def _now_epoch_ms() -> int:
    return int(datetime.now(timezone.utc).timestamp() * 1000)


class PlanRepository:
    """Repository for Plan entity operations."""

    def __init__(
        self, session_factory: Callable[..., AsyncSession], logger: ConsoleServiceLogger
    ):
        self.__session_factory = session_factory
        self.__logger = logger

    async def create_plan(self, plan_data: PlanBase, user_id: int) -> Plan:
        self.__logger.info(
            "Repository: create_plan started for name={}".format(plan_data.name)
        )
        try:
            async with self.__session_factory() as session:
                if plan_data.plan_type and plan_data.plan_type == PlanType.WALLET:
                    stmt = select(Plan).where(
                        Plan.plan_type == PlanType.WALLET, Plan.is_active.is_(True)
                    )
                    wallet_result = await session.execute(stmt)
                    wallet_plan = wallet_result.scalars().first()

                    if wallet_plan:
                        self.__logger.info(
                            "An active plan with type wallet already exists with id: {}".format(
                                wallet_plan.id
                            )
                        )
                        raise WalletPlanExistsError(
                            f"An active wallet plan already exists (ID: {wallet_plan.id}). Only one active wallet plan is allowed."
                        )

                existing_hierarchy_plan = select(Plan).where(
                    Plan.hierarchy == plan_data.hierarchy
                )
                hierarchy_result = await session.execute(existing_hierarchy_plan)
                hierarchy_plan = hierarchy_result.scalars().first()
                if hierarchy_plan:
                    self.__logger.info(
                        "A plan with hierarchy {} already exists with id: {}".format(
                            plan_data.hierarchy, hierarchy_plan.id
                        )
                    )
                    raise PlanHierarchyExistsError(plan_data.hierarchy)

                default_plan_limits: Dict[str, int] = {
                    PlanCustomLimitKeys.Console.ACTIVE_USERS: 1,
                    PlanCustomLimitKeys.Maglo.SERVICE_BOARDS: 1,
                }

                plan = Plan(
                    name=plan_data.name,
                    description=plan_data.description,
                    price=plan_data.price,
                    discount_percentage=plan_data.discount_percentage,
                    currency=plan_data.currency,
                    limits=default_plan_limits,
                    modules=plan_data.modules,
                    plan_type=plan_data.plan_type,
                    tag=plan_data.tag,
                    hierarchy=plan_data.hierarchy,
                    service_name=plan_data.service_name,
                    is_free_trial=plan_data.is_free_trial,
                    otc_charge=plan_data.otc_charge or 0.0,
                    created_by=user_id,
                    duration=plan_data.duration,
                )

                session.add(plan)
                await session.commit()
                await session.refresh(plan)
                self.__logger.info(
                    "Repository: create_plan committed id={}".format(plan.id)
                )
                return plan
        except IntegrityError as e:
            await session.rollback()
            self.__logger.error(
                "Repository: create_plan IntegrityError for name={}: {}".format(
                    plan_data.name, e
                )
            )
            raise
        except Exception as e:
            self.__logger.error(
                "Repository: create_plan unexpected error for name={}: {}".format(
                    plan_data.name, e
                )
            )
            raise

    async def get_plan_by_id(
        self, plan_id: int, active_only: bool = False, partner_id: Optional[int] = None
    ) -> Optional[Plan]:
        """Fetch a single plan by ID."""
        self.__logger.info("Repository: get_plan_by_id started id={}".format(plan_id))
        try:
            async with self.__session_factory() as session:
                stmt = select(Plan).where(Plan.id == plan_id)
                if active_only:
                    stmt = stmt.where(Plan.is_active.is_(True))
                result = await session.execute(stmt)
                plan = result.scalar_one_or_none()

                if plan:
                    plan_with_status = await self._check_purchase_status(
                        session, [plan], partner_id
                    )
                    return plan_with_status[0] if plan_with_status else None
                return plan
        except Exception as e:
            self.__logger.error(
                "Repository: get_plan_by_id failed id={}: {}".format(plan_id, e)
            )
            raise

    async def get_active_plans(
        self,
        partner_id: Optional[int] = None,
        service_name: Optional[str] = None,
        plan_type: Optional[str] = None,
        duration: Optional[int] = None,
    ) -> List[Plan]:
        """Retrieve all active plans with purchase status if partner_id is provided."""
        self.__logger.info("Repository: get_active_plans started")
        try:
            async with self.__session_factory() as session:
                stmt = (
                    select(Plan)
                    .where(Plan.is_active.is_(True))
                    .order_by(Plan.hierarchy.asc())
                )

                if service_name:
                    stmt = stmt.where(Plan.service_name == service_name)

                if plan_type:
                    stmt = stmt.where(Plan.plan_type == plan_type)

                if duration:
                    stmt = stmt.where(Plan.duration == duration)

                result = await session.execute(stmt)
                plans = result.scalars().all()

                # Check purchase status
                plans_with_status = await self._check_purchase_status(
                    session, plans, partner_id
                )

                return plans_with_status
        except Exception as e:
            self.__logger.error("Repository: get_active_plans failed: {}".format(e))
            raise

    async def update_plan(
        self, plan_id: int, plan_data: PlanUpdate, user_id: Optional[int] = None
    ) -> Optional[Plan]:
        self.__logger.info("Repository: update_plan started id={}".format(plan_id))
        try:
            async with self.__session_factory() as session:
                # Validate existence
                existing_plan = await self.get_plan_by_id(plan_id)
                if not existing_plan:
                    self.__logger.warning(
                        "Repository: update_plan plan not found or inactive id={}".format(
                            plan_id
                        )
                    )
                    return None

                update_data: Dict[str, Any] = plan_data.model_dump(exclude_none=True)

                # Nothing to update
                if not update_data:
                    self.__logger.info(
                        f"Repository: update_plan no fields provided id={plan_id}"
                    )
                    return existing_plan

                is_setting_wallet_type = plan_data.plan_type == PlanType.WALLET
                is_activating_plan = plan_data.is_active is True

                if is_setting_wallet_type or (
                    existing_plan.plan_type == PlanType.WALLET and is_activating_plan
                ):
                    # Check if any other active wallet plan exists
                    stmt = select(Plan).where(
                        Plan.plan_type == PlanType.WALLET,
                        Plan.is_active.is_(True),
                        Plan.id != plan_id,
                    )
                    wallet_result = await session.execute(stmt)
                    wallet_plan = wallet_result.scalars().first()
                    if wallet_plan:
                        self.__logger.info(
                            f"Cannot activate or set to WALLET: active wallet plan already exists with id: {wallet_plan.id}"
                        )
                        raise WalletPlanExistsError(
                            f"An active wallet plan already exists (ID: {wallet_plan.id}). Only one active wallet plan is allowed."
                        )
                if plan_data.hierarchy is not None:
                    existing_hierarchy_plan = select(Plan).where(
                        Plan.hierarchy == plan_data.hierarchy
                    )
                    hierarchy_result = await session.execute(existing_hierarchy_plan)
                    hierarchy_plan = hierarchy_result.scalars().first()
                    if hierarchy_plan:
                        self.__logger.info(
                            "A plan with hierarchy {} already exists with id: {}".format(
                                plan_data.hierarchy, hierarchy_plan.id
                            )
                        )
                        raise PlanHierarchyExistsError(plan_data.hierarchy)

                update_data.update(
                    {
                        "updated_by": user_id,
                        "updated_at": _now_epoch_ms(),
                    }
                )

                stmt = (
                    update(Plan)
                    .where(Plan.id == plan_id)
                    .values(**update_data)
                    .execution_options(synchronize_session="fetch")
                )
                await session.execute(stmt)
                await session.commit()

                updated = await session.get(Plan, plan_id)
                await session.refresh(updated)

                # Detach instance so no lazy loads later trigger error
                session.expunge(updated)

                if updated:
                    self.__logger.info(
                        "Repository: update_plan succeeded id={}".format(updated.id)
                    )
                else:
                    self.__logger.warning(
                        "Repository: update_plan no rows updated id={}".format(plan_id)
                    )
                return updated
        except IntegrityError as e:
            self.__logger.error(
                "Repository: update_plan IntegrityError name={}: {}".format(
                    plan_data.name, e
                )
            )
            raise
        except Exception as e:
            self.__logger.error(
                "Repository: update_plan unexpected error id={}: {}".format(plan_id, e)
            )
            raise

    async def delete_plan(self, plan_id: int, user_id: int) -> bool:
        self.__logger.info("Repository: delete_plan started id={}".format(plan_id))
        try:
            # Validate existence
            existing_plan = await self.get_plan_by_id(plan_id)
            if not existing_plan or not existing_plan.is_active:
                self.__logger.warning(
                    "Repository: delete_plan plan not found or inactive id={}".format(
                        plan_id
                    )
                )
                return False

            async with self.__session_factory() as session:
                stmt = (
                    update(Plan)
                    .where(Plan.id == plan_id, Plan.is_active.is_(True))
                    .values(
                        is_active=False,
                        deleted_at=_now_epoch_ms(),
                        updated_by=user_id,
                        deleted_by=user_id,
                    )
                    .execution_options(synchronize_session="fetch")
                )
                result = await session.execute(stmt)
                await session.commit()
                rowcount = result.rowcount if hasattr(result, "rowcount") else 0
                self.__logger.info(
                    "Repository: delete_plan affected rows={} for id={}".format(
                        rowcount, plan_id
                    )
                )
                return rowcount > 0
        except Exception as e:
            self.__logger.error(
                "Repository: delete_plan failed id={}: {}".format(plan_id, e)
            )
            raise

    async def _check_purchase_status(
        self, session, plans: List[Plan], partner_id: Optional[int] = None
    ) -> List[Plan]:
        """Helper method to check and set purchase status for plans."""
        if partner_id:
            # Fetch active entitlements for the partner
            entitlement_stmt = select(Entitlement.order_id).where(
                Entitlement.partner_id == partner_id,
                Entitlement.is_active.is_(True),
            )
            entitlement_result = await session.execute(entitlement_stmt)
            active_order_ids = {row[0] for row in entitlement_result.fetchall()}

            # Get plan_ids from those orders
            purchased_plan_ids = set()
            if active_order_ids:
                order_stmt = select(Order.plan_id).where(Order.id.in_(active_order_ids))
                order_result = await session.execute(order_stmt)
                purchased_plan_ids = {
                    row[0] for row in order_result.fetchall() if row[0]
                }

            # Mark plans as purchased or not
            for plan in plans:
                plan.is_purchased = plan.id in purchased_plan_ids
        else:
            # No partner_id, mark all as not purchased
            for plan in plans:
                plan.is_purchased = False

        return plans
