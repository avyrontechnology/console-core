"""Grace Period Repository."""

from contextlib import AbstractContextManager
from typing import Callable, List, Optional, Tuple

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from src.components.common.datetime import DateTimeUtil
from src.components.grace.constants import GRACE_MS_PER_DAY, GraceStatus
from src.components.grace.models import GracePeriod
from src.loggers.console_service_logger import ConsoleServiceLogger


class GraceRepository:
    def __init__(
        self,
        session_factory: Callable[..., AbstractContextManager[Session]],
        logger: ConsoleServiceLogger,
    ):
        self.session_factory = session_factory
        self.logger = logger

    # =========================================================================
    # CREATE
    # =========================================================================

    async def create_grace(
        self,
        partner_id: int,
        service_name: str,
        remark: str,
        granted_days: int,
        attempt_number: int,
        created_by: int,
    ) -> GracePeriod:
        """
        Insert a new ACTIVE grace record.
        created_by (from MetaData base) stores the internal user who granted grace.
        """
        async with self.session_factory() as session:
            try:
                now_ms: int = int(DateTimeUtil.get_current_time())
                end_ms: int = now_ms + (granted_days * GRACE_MS_PER_DAY)

                grace = GracePeriod(
                    partner_id=partner_id,
                    service_name=service_name,
                    remark=remark,
                    granted_days=granted_days,
                    start_date=now_ms,
                    end_date=end_ms,
                    consumed_days=None,
                    status=GraceStatus.ACTIVE,
                    attempt_number=attempt_number,
                    settled_at=None,
                    settled_by_order_id=None,
                    created_by=created_by,
                )
                session.add(grace)
                await session.commit()
                await session.refresh(grace)
                self.logger.info(
                    "Grace created | id={} partner_id={} service={} days={} attempt={} created_by={}".format(
                        grace.id,
                        partner_id,
                        service_name,
                        granted_days,
                        attempt_number,
                        created_by,
                    )
                )
                return grace
            except Exception as e:
                await session.rollback()
                self.logger.error(
                    "Error creating grace | partner_id={} service={} error={}".format(
                        partner_id, service_name, e
                    )
                )
                raise

    # =========================================================================
    # FETCH
    # =========================================================================

    async def get_active_grace(
        self, partner_id: int, service_name: str
    ) -> Optional[GracePeriod]:
        """
        Return the single ACTIVE grace record for partner + service if it exists
        and its end_date has not yet passed (safety net for delayed Celery runs).
        """
        async with self.session_factory() as session:
            now_ms: int = int(DateTimeUtil.get_current_time())
            stmt = (
                select(GracePeriod)
                .where(
                    GracePeriod.partner_id == partner_id,
                    GracePeriod.service_name == service_name,
                    GracePeriod.status == GraceStatus.ACTIVE,
                    GracePeriod.end_date > now_ms,
                )
                .limit(1)
            )
            result = await session.execute(stmt)
            return result.scalars().first()

    async def get_all_active_for_partner(self, partner_id: int) -> List[GracePeriod]:
        """
        Return all ACTIVE grace records for a partner across all services.
        Filters by end_date > now as a safety net for delayed Celery runs.
        Used by get_grace_status and is_grace_active checks.
        """
        async with self.session_factory() as session:
            now_ms: int = int(DateTimeUtil.get_current_time())
            stmt = (
                select(GracePeriod)
                .where(
                    GracePeriod.partner_id == partner_id,
                    GracePeriod.status == GraceStatus.ACTIVE,
                    GracePeriod.end_date > now_ms,
                )
                .order_by(GracePeriod.start_date.desc())
            )
            result = await session.execute(stmt)
            return list(result.scalars().all())

    async def get_all_for_service(
        self, partner_id: int, service_name: str
    ) -> List[GracePeriod]:
        """Return all grace records for a partner + service, ordered by attempt_number ASC."""
        async with self.session_factory() as session:
            stmt = (
                select(GracePeriod)
                .where(
                    GracePeriod.partner_id == partner_id,
                    GracePeriod.service_name == service_name,
                )
                .order_by(GracePeriod.attempt_number.asc())
            )
            result = await session.execute(stmt)
            return list(result.scalars().all())

    async def get_all_for_partner(self, partner_id: int) -> List[GracePeriod]:
        """
        Return all grace records for a partner across all services,
        ordered by created_at ASC.
        Used by get_grace_status to calculate totals.
        """
        async with self.session_factory() as session:
            stmt = (
                select(GracePeriod)
                .where(GracePeriod.partner_id == partner_id)
                .order_by(GracePeriod.created_at.asc())
            )
            result = await session.execute(stmt)
            return list(result.scalars().all())

    async def count_attempts(self, partner_id: int, service_name: str) -> int:
        """Return total count of grace records for partner + service (all statuses)."""
        async with self.session_factory() as session:
            stmt = select(func.count(GracePeriod.id)).where(
                GracePeriod.partner_id == partner_id,
                GracePeriod.service_name == service_name,
            )
            result = await session.execute(stmt)
            return result.scalar() or 0

    async def get_unsettled_for_service(
        self, partner_id: int, service_name: str
    ) -> List[GracePeriod]:
        """
        Return all ACTIVE or EXPIRED (unsettled) grace records for partner + service,
        ordered by start_date ASC.
        Used by settle_all to calculate total consumed days.
        """
        async with self.session_factory() as session:
            stmt = (
                select(GracePeriod)
                .where(
                    GracePeriod.partner_id == partner_id,
                    GracePeriod.service_name == service_name,
                    GracePeriod.status.in_([GraceStatus.ACTIVE, GraceStatus.EXPIRED]),
                )
                .order_by(GracePeriod.start_date.asc())
            )
            result = await session.execute(stmt)
            return list(result.scalars().all())

    # =========================================================================
    # SETTLE
    # =========================================================================

    async def settle_all(
        self,
        partner_id: int,
        service_name: str,
        order_id: int,
        payment_date_ms: int,
    ) -> Tuple[Optional[int], int]:
        """
        Settle all unsettled (ACTIVE or EXPIRED) grace records for partner + service.

        For ACTIVE records:  consumed_days = floor((payment_date_ms - start_date) / MS_PER_DAY)
        For EXPIRED records: consumed_days = granted_days (full period already used)

        Returns:
            (first_grace_start_date_ms, total_consumed_days)
            first_grace_start_date_ms is None when no unsettled records exist.
        """
        async with self.session_factory() as session:
            try:
                now_ms: int = int(DateTimeUtil.get_current_time())
                records = await self.get_unsettled_for_service(partner_id, service_name)

                if not records:
                    return None, 0

                first_start: int = records[0].start_date
                total_consumed: int = 0

                for rec in records:
                    if rec.status == GraceStatus.ACTIVE:
                        elapsed = max(
                            int((payment_date_ms - rec.start_date) / GRACE_MS_PER_DAY),
                            0,
                        )
                        consumed = min(elapsed, rec.granted_days)
                    else:
                        # EXPIRED — full granted period was used
                        consumed = rec.granted_days

                    total_consumed += consumed

                    stmt = (
                        update(GracePeriod)
                        .where(GracePeriod.id == rec.id)
                        .values(
                            consumed_days=consumed,
                            status=GraceStatus.SETTLED,
                            settled_at=now_ms,
                            settled_by_order_id=order_id,
                            updated_by=None,
                        )
                    )
                    await session.execute(stmt)

                await session.commit()
                self.logger.info(
                    "Grace settled | partner_id={} service={} order_id={} "
                    "records={} total_consumed_days={}".format(
                        partner_id,
                        service_name,
                        order_id,
                        len(records),
                        total_consumed,
                    )
                )
                return first_start, total_consumed

            except Exception as e:
                await session.rollback()
                self.logger.error(
                    "Error settling grace | partner_id={} service={} error={}".format(
                        partner_id, service_name, e
                    )
                )
                raise

    # =========================================================================
    # EXPIRE (called by Celery task)
    # =========================================================================

    async def expire_overdue(self) -> int:
        """
        Bulk-mark all ACTIVE grace records whose end_date < now as EXPIRED.
        Sets consumed_days = granted_days (full period elapsed without payment).
        Called by the daily Celery task. Idempotent.

        Returns count of records expired.
        """
        async with self.session_factory() as session:
            try:
                now_ms: int = int(DateTimeUtil.get_current_time())
                stmt = (
                    update(GracePeriod)
                    .where(
                        GracePeriod.status == GraceStatus.ACTIVE,
                        GracePeriod.end_date < now_ms,
                    )
                    .values(
                        status=GraceStatus.EXPIRED,
                        consumed_days=GracePeriod.granted_days,
                    )
                )
                result = await session.execute(stmt)
                await session.commit()
                count = result.rowcount or 0
                self.logger.info("Grace expiry | expired {} record(s)".format(count))
                return count

            except Exception as e:
                await session.rollback()
                self.logger.error("Error in expire_overdue | error={}".format(e))
                raise
