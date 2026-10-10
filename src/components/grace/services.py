"""Grace Period Service."""

from typing import List, Optional, Tuple

from dependency_injector.wiring import Provide
from fastapi import Depends

from src.components.common.datetime import DateTimeUtil
from src.components.db_constants.loader.constant import DbConstants
from src.components.entitlement.repositories import EntitlementRepository
from src.components.grace.constants import GraceStatus
from src.components.grace.errors import (
    GraceAlreadyActiveError,
    GraceForbiddenError,
    GraceMaxAttemptsError,
    GraceNoPriorOrderError,
    GraceNotEligibleError,
)
from src.components.grace.models import GracePeriod
from src.components.grace.repositories import GraceRepository
from src.components.grace.schema import (
    GraceResponse,
    GraceStatusResponse,
    GrantGraceRequest,
)
from src.components.order.repositories import OrderRepository
from src.components.partner.error import PartnerNotFoundError
from src.components.partner.repositories import PartnerRepository
from src.components.plan.utils import PlanUtils
from src.loggers.console_service_logger import ConsoleServiceLogger


class GraceService:
    def __init__(
        self,
        grace_repository: GraceRepository,
        logger: ConsoleServiceLogger,
    ) -> None:
        self.grace_repo = grace_repository
        self.logger = logger

    # =========================================================================
    # PUBLIC: GRANT GRACE
    # =========================================================================

    async def grant_grace(
        self,
        payload: GrantGraceRequest,
        current_user: dict,
        entitlement_repo: EntitlementRepository = Depends(
            Provide["entitlement_repository"]
        ),
        order_repo: OrderRepository = Depends(Provide["order_repository"]),
        partner_repo: PartnerRepository = Depends(Provide["partner_repository"]),
    ) -> GraceResponse:
        """
        Grant a grace period to a partner after entitlement expiry.

        payload      — validated dict from GrantGraceRequest.validate_payload()
        service_name — NOT in request. Derived internally from the partner's
                       last SUCCESS order. Grace covers ALL services from that order.

        Guards (in order):
          1. Derive service names from last SUCCESS order (raises if none found).
          2. Per service: no active entitlement.
          3. Per service: no scheduled entitlement.
          4. Per service: attempts below MAX_GRACE_ATTEMPTS.
          5. Per service: no ACTIVE grace already exists.
          6. granted_days already validated by schema.

        One GracePeriod record is created per service. created_by (MetaData)
        stores who granted the grace.
        """
        partner_id: int = payload["partner_id"]
        granted_days: int = payload["granted_days"]
        remark: str = payload["remark"]
        created_by: int = current_user["user_id"]

        self.logger.info(
            "grant_grace started | partner_id={} granted_days={} created_by={}".format(
                partner_id, granted_days, created_by
            )
        )

        try:
            # ── Validate Partner id ──────────────────────────────────────────
            partner = await partner_repo.get_by_id(partner_id)
            if not partner:
                raise PartnerNotFoundError(
                    "Partner with id {} does not exist.".format(partner_id)
                )

            # ── Derive service names from last SUCCESS order ─────────────────
            service_names: List[str] = await self._get_service_names_from_last_order(
                order_repo, partner_id
            )

            # ── Per-service guards ───────────────────────────────────────────
            for service_name in service_names:
                await self._assert_no_active_entitlement(
                    entitlement_repo, partner_id, service_name
                )
                await self._assert_no_scheduled_entitlement(
                    entitlement_repo, partner_id, service_name
                )
                attempt_count: int = await self.grace_repo.count_attempts(
                    partner_id, service_name
                )
                if attempt_count >= DbConstants.MAX_GRACE_ATTEMPTS:
                    raise GraceMaxAttemptsError(
                        partner_id, service_name, DbConstants.MAX_GRACE_ATTEMPTS
                    )
                existing_active = await self.grace_repo.get_active_grace(
                    partner_id, service_name
                )
                if existing_active:
                    raise GraceAlreadyActiveError(partner_id, service_name)

            # ── Create one grace record per service ───────────────────────────
            created_graces: List[GracePeriod] = []
            for service_name in service_names:
                attempt_count: int = await self.grace_repo.count_attempts(
                    partner_id, service_name
                )
                grace: GracePeriod = await self.grace_repo.create_grace(
                    partner_id=partner_id,
                    service_name=service_name,
                    remark=remark,
                    granted_days=granted_days,
                    attempt_number=attempt_count + 1,
                    created_by=created_by,
                )
                created_graces.append(grace)
                self.logger.info(
                    "grant_grace record created | grace_id={} service={} attempt={}".format(
                        grace.id, service_name, grace.attempt_number
                    )
                )

            return self._to_response(created_graces[0])

        except (
            GraceForbiddenError,
            GraceNotEligibleError,
            GraceMaxAttemptsError,
            GraceAlreadyActiveError,
            GraceNoPriorOrderError,
        ):
            raise

        except Exception as exc:
            self.logger.error(
                "grant_grace unexpected error | partner_id={} error={}".format(
                    partner_id, repr(exc)
                )
            )
            raise

    # =========================================================================
    # PUBLIC: SETTLE GRACE
    # =========================================================================

    async def settle_grace(
        self,
        partner_id: int,
        service_name: str,
        order_id: int,
        payment_date_ms: Optional[int] = None,
    ) -> Tuple[Optional[int], int]:
        """
        Settle all unsettled grace records for partner + service after payment.

        Returns:
            (first_grace_start_date_ms, total_consumed_days)

        If no unsettled records exist: (None, 0) — caller does not adjust entitlement dates.
        """
        if payment_date_ms is None:
            payment_date_ms = int(DateTimeUtil.get_current_time())

        self.logger.info(
            "settle_grace started | partner_id={} service={} order_id={}".format(
                partner_id, service_name, order_id
            )
        )

        try:
            first_start, total_consumed = await self.grace_repo.settle_all(
                partner_id=partner_id,
                service_name=service_name,
                order_id=order_id,
                payment_date_ms=payment_date_ms,
            )

            self.logger.info(
                "settle_grace completed | partner_id={} service={} "
                "first_start={} total_consumed={}".format(
                    partner_id, service_name, first_start, total_consumed
                )
            )
            return first_start, total_consumed

        except Exception as exc:
            self.logger.error(
                "settle_grace unexpected error | partner_id={} service={} "
                "order_id={} error={}".format(
                    partner_id, service_name, order_id, repr(exc)
                )
            )
            raise

    # =========================================================================
    # PUBLIC: STATUS
    # =========================================================================

    async def get_grace_status(
        self,
        partner_id: int,
        partner_repo: PartnerRepository = Depends(Provide["partner_repository"]),
    ) -> GraceStatusResponse:
        """
        Return full grace status for a partner across all services.
        service_name is not required as input — derived from the last order internally.
        """
        try:

            # ── Validate Partner id ──────────────────────────────────────────
            partner = await partner_repo.get_by_id(partner_id)
            if not partner:
                raise PartnerNotFoundError(
                    "Partner with id {} does not exist.".format(partner_id)
                )

            all_records = await self.grace_repo.get_all_for_partner(partner_id)
            active_graces = await self.grace_repo.get_all_active_for_partner(partner_id)

            total_attempts = len(all_records)
            attempts_remaining = max(DbConstants.MAX_GRACE_ATTEMPTS - total_attempts, 0)

            total_consumed = sum(
                r.consumed_days
                for r in all_records
                if r.status == GraceStatus.SETTLED and r.consumed_days is not None
            )

            current_grace = active_graces[0] if active_graces else None
            latest = all_records[-1] if all_records else None

            return GraceStatusResponse(
                partner_id=partner_id,
                service_name=current_grace.service_name if current_grace else "",
                has_active_grace=len(active_graces) > 0,
                current_grace=(
                    self._to_response(current_grace) if current_grace else None
                ),
                total_attempts_used=total_attempts,
                attempts_remaining=attempts_remaining,
                total_consumed_days=total_consumed,
                created_by=latest.created_by if latest else None,
                created_at=latest.created_at if latest else None,
                granted_by_name=latest.granted_by_name if latest else None,
            )

        except Exception as exc:
            self.logger.error(
                "get_grace_status unexpected error | partner_id={} error={}".format(
                    partner_id, repr(exc)
                )
            )
            raise

    # =========================================================================
    # PRIVATE GUARDS
    # =========================================================================

    async def _assert_no_active_entitlement(
        self, entitlement_repo, partner_id: int, service_name: str
    ) -> None:
        """Raise GraceNotEligibleError if any active entitlement exists for partner + service."""
        active = await entitlement_repo.get_active_entitlement(
            partner_id=partner_id, service_name=service_name
        )
        if active:
            raise GraceNotEligibleError(
                partner_id, service_name, "partner has an active entitlement"
            )

    async def _assert_no_scheduled_entitlement(
        self, entitlement_repo, partner_id: int, service_name: str
    ) -> None:
        """Raise GraceNotEligibleError if a scheduled entitlement exists for partner + service."""
        scheduled = await entitlement_repo.get_scheduled_entitlements(partner_id)
        service_scheduled = [e for e in scheduled if e.service_name == service_name]
        if service_scheduled:
            raise GraceNotEligibleError(
                partner_id, service_name, "partner has a scheduled entitlement"
            )

    async def _get_service_names_from_last_order(
        self, order_repo, partner_id: int
    ) -> List[str]:
        """
        Fetch the partner's last SUCCESS order and extract service names from its
        plan modules. Raises GraceNoPriorOrderError if none found.
        """
        latest = await order_repo.get_latest_order_by_partner(partner_id)
        if not latest:
            raise GraceNoPriorOrderError(partner_id, "unknown")

        if not latest.plan or not latest.plan.modules:
            raise GraceNoPriorOrderError(partner_id, "unknown")

        modules_by_service = PlanUtils.split_modules_by_service(latest.plan.modules)
        service_names = list(modules_by_service.keys())

        if not service_names:
            raise GraceNoPriorOrderError(partner_id, "unknown")

        self.logger.info(
            "Derived services from last order | partner_id={} order_id={} services={}".format(
                partner_id, latest.id, service_names
            )
        )
        return service_names

    @staticmethod
    def _to_response(grace: GracePeriod) -> GraceResponse:
        return GraceResponse(
            grace_id=grace.id,
            partner_id=grace.partner_id,
            service_name=grace.service_name,
            granted_days=grace.granted_days,
            attempt_number=grace.attempt_number,
            start_date=grace.start_date,
            end_date=grace.end_date,
            status=grace.status,
            remark=grace.remark,
            consumed_days=grace.consumed_days,
            settled_at=grace.settled_at,
            settled_by_order_id=grace.settled_by_order_id,
            created_by=grace.created_by,
            created_at=grace.created_at,
            granted_by_name=grace.granted_by_name,
        )
