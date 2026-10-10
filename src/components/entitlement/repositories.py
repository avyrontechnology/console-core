from contextlib import AbstractContextManager
from typing import Callable, List, Optional

from sqlalchemy import and_, func, or_, select, update
from sqlalchemy.orm import Session, selectinload

from src.components.common.datetime import DateTimeUtil
from src.components.entitlement.errors import EntitlementNotFoundError
from src.components.entitlement.models import Entitlement
from src.components.entitlement.schema import EntitlementCreate, EntitlementUpdate
from src.loggers.console_service_logger import ConsoleServiceLogger

current_ts: int = int(DateTimeUtil.get_current_time())


class EntitlementRepository:
    def __init__(
        self,
        session_factory: Callable[..., AbstractContextManager[Session]],
        logger: ConsoleServiceLogger = ConsoleServiceLogger(),
    ):
        self.session_factory = session_factory
        self.logger = logger

    # =========================================================================
    # CREATE
    # =========================================================================

    async def create_entitlement(self, data: EntitlementCreate) -> Entitlement:
        async with self.session_factory() as session:
            ent = Entitlement(**data.model_dump())
            session.add(ent)
            await session.commit()
            await session.refresh(ent)
            return ent

    # =========================================================================
    # FETCH
    # =========================================================================

    async def get_active_entitlement(
        self,
        partner_id: int,
        service_name: str,
    ) -> Optional[Entitlement]:
        """Fetch the most recent active, non-expired entitlement for a service."""
        async with self.session_factory() as session:
            stmt = (
                select(Entitlement)
                .options(selectinload(Entitlement.order))
                .where(
                    Entitlement.partner_id == partner_id,
                    Entitlement.service_name == service_name,
                    Entitlement.is_active.is_(True),
                    or_(
                        Entitlement.end_date.is_(None),
                        Entitlement.end_date >= current_ts,
                    ),
                )
                .order_by(Entitlement.start_date.desc())
            )
            result = await session.execute(stmt)
            return result.scalars().first()

    async def get_all_active_entitlements(self, partner_id: int) -> List[Entitlement]:
        """Fetch all currently active entitlements for a partner."""
        async with self.session_factory() as session:
            stmt = (
                select(Entitlement)
                .options(selectinload(Entitlement.order))
                .where(
                    Entitlement.partner_id == partner_id,
                    Entitlement.is_active.is_(True),
                    or_(
                        Entitlement.end_date.is_(None),
                        Entitlement.end_date >= current_ts,
                    ),
                )
                .order_by(Entitlement.start_date.desc())
            )
            result = await session.execute(stmt)
            return result.scalars().all()

    async def get_scheduled_entitlements(self, partner_id: int) -> List[Entitlement]:
        """
        Fetch entitlements that are scheduled to activate in the future.

        These are entitlements that:
          - Are NOT yet active (is_active=False)
          - Were NOT manually deactivated (is_manually_deactivated=False)
          - Have a future start_date (start_date > now)
          - Have not already expired (end_date is None OR end_date >= now)

        Used by the manual order service to prevent creating an order
        whose duration would overlap with an upcoming entitlement activation.
        Also used by the grace period eligibility guard.
        """
        async with self.session_factory() as session:
            stmt = (
                select(Entitlement)
                .options(selectinload(Entitlement.order))
                .where(
                    and_(
                        Entitlement.partner_id == partner_id,
                        Entitlement.is_active.is_(False),
                        Entitlement.is_manually_deactivated.is_(False),
                        Entitlement.start_date > current_ts,
                        or_(
                            Entitlement.end_date.is_(None),
                            Entitlement.end_date >= current_ts,
                        ),
                    )
                )
                .order_by(Entitlement.start_date.asc())
            )
            result = await session.execute(stmt)
            scheduled = result.scalars().all()

            self.logger.info(
                "Scheduled entitlements | partner_id={} count={}".format(
                    partner_id, len(scheduled)
                )
            )
            return scheduled

    async def get_entitlement_by_order_id(self, order_id: int) -> Optional[Entitlement]:
        """Fetch a single entitlement by order_id with order relationship loaded."""
        async with self.session_factory() as session:
            stmt = (
                select(Entitlement)
                .options(selectinload(Entitlement.order))
                .where(Entitlement.order_id == order_id)
            )
            result = await session.execute(stmt)
            return result.scalars().first()

    async def get_entitlements_by_order_id(self, order_id: int) -> List[Entitlement]:
        """
        Fetch ALL entitlements for an order (one per service).
        Use this instead of get_entitlement_by_order_id when all services
        need to be updated — e.g. updating start_date across all services.
        """
        async with self.session_factory() as session:
            stmt = (
                select(Entitlement)
                .options(selectinload(Entitlement.order))
                .where(Entitlement.order_id == order_id)
            )
            result = await session.execute(stmt)
            return result.scalars().all()

    async def get_entitlement_by_order_id_and_service(
        self, order_id: int, service_name: str
    ) -> Optional[Entitlement]:
        """
        Fetch the entitlement for a specific order + service combination.
        Used by grace settlement to update the correct per-service entitlement
        rather than always picking the first one for the order.
        """
        async with self.session_factory() as session:
            stmt = select(Entitlement).where(
                Entitlement.order_id == order_id,
                Entitlement.service_name == service_name,
            )
            result = await session.execute(stmt)
            return result.scalars().first()

    async def get_all_entitlements_for_partner(
        self, partner_id: int
    ) -> List[Entitlement]:
        """
        Fetch ALL entitlements for a partner regardless of is_active or end_date.
        Used exclusively by get_subscription_status to check the full picture
        (active, scheduled, manually deactivated) across all services.
        Do NOT use in business logic that only needs live entitlements.
        """
        async with self.session_factory() as session:
            stmt = (
                select(Entitlement)
                .options(selectinload(Entitlement.order))
                .where(Entitlement.partner_id == partner_id)
                .order_by(Entitlement.start_date.desc())
            )
            result = await session.execute(stmt)
            return result.scalars().all()

    # =========================================================================
    # UPDATE
    # =========================================================================

    async def update_entitlement(
        self, entitlement_id: int, data: EntitlementUpdate
    ) -> Entitlement:
        async with self.session_factory() as session:
            update_fields = {
                field: value
                for field, value in data.model_dump().items()
                if value is not None
            }

            stmt = (
                update(Entitlement)
                .where(Entitlement.id == entitlement_id)
                .values(**update_fields)
                .returning(Entitlement)
            )

            result = await session.execute(stmt)
            await session.commit()

            updated = result.scalar_one_or_none()
            if not updated:
                raise EntitlementNotFoundError(f"id={entitlement_id}")

            return updated

    async def update_entitlement_dates(
        self,
        entitlement_id: int,
        new_start_date: int,
        new_end_date: int,
        updated_by: Optional[int] = None,
    ) -> Entitlement:
        """
        Update start_date and end_date on a freshly-created entitlement.

        Called exclusively by the grace period settlement flow to backdate
        the new entitlement start and shorten its end by consumed grace days.

        Intentionally separate from update_entitlement_start_date
        (the partner-facing scheduled delay feature). Does NOT:
          - increment start_date_update_count
          - change is_active
        """
        async with self.session_factory() as session:
            stmt = (
                update(Entitlement)
                .where(Entitlement.id == entitlement_id)
                .values(
                    start_date=new_start_date,
                    end_date=new_end_date,
                    updated_by=updated_by,
                )
                .returning(Entitlement)
            )
            result = await session.execute(stmt)
            await session.commit()
            updated = result.scalar_one_or_none()
            if not updated:
                raise EntitlementNotFoundError(f"id={entitlement_id}")
            return updated

    async def update_entitlement_start_date(
        self,
        entitlement_id: int,
        new_start_date: int,
        new_end_date: int,
        user_id: int,
    ) -> Entitlement:
        """Update start/end date, deactivate, and increment modification counter."""
        async with self.session_factory() as session:
            stmt = (
                update(Entitlement)
                .where(Entitlement.id == entitlement_id)
                .values(
                    start_date=new_start_date,
                    end_date=new_end_date,
                    is_active=False,
                    start_date_update_count=func.coalesce(
                        Entitlement.start_date_update_count, 0
                    )
                    + 1,
                    updated_by=user_id,
                )
                .returning(Entitlement)
            )

            result = await session.execute(stmt)
            updated = result.scalar_one()
            await session.commit()
            await session.refresh(updated)

            return updated

    async def activate_pending_entitlements(self) -> int:
        """
        Activate all pending entitlements whose start date has arrived.
        Returns number of activated rows.
        """
        async with self.session_factory() as session:
            stmt = (
                update(Entitlement)
                .where(
                    Entitlement.start_date <= current_ts,
                    Entitlement.is_active.is_(False),
                    Entitlement.is_manually_deactivated.is_(False),
                    or_(
                        Entitlement.end_date.is_(None),
                        Entitlement.end_date >= current_ts,
                    ),
                )
                .values(is_active=True)
            )

            result = await session.execute(stmt)
            await session.commit()

            return result.rowcount or 0
