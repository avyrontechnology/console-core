from uuid import UUID
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Set

from dateutil.relativedelta import relativedelta
from dependency_injector.wiring import Provide
from fastapi import Depends

from src.components.auth.constant import RoleDictKeys
from src.components.auth.repositories import AuthRepository
from src.components.common.constants import CurrentUserMap
from src.components.common.datetime import DateTimeUtil
from src.components.db_constants.loader.constant import DbConstants
from src.components.entitlement.errors import (
    EntitlementNotEligibleForStartDateUpdateError,
    EntitlementStartDateUpdateLimitExceededError,
    EntitlementStartDateUpdateWindowExpiredError,
    NoPermissionToUpdateEntitlementError,
    OrderNotFoundForEntitlementError,
)
from src.components.entitlement.models import Entitlement
from src.components.entitlement.repositories import EntitlementRepository
from src.components.entitlement.schema import (
    EntitlementCreate,
    EntitlementUpdate,
    UpdateEntitlementStartDateRequest,
)
from src.components.grace.models import GracePeriod
from src.components.grace.repositories import GraceRepository
from src.components.order.constants import ServiceSubscriptionStatus
from src.components.order.models import Order
from src.components.plan.constants import Platform
from src.components.plan.utils import PlanUtils
from src.components.user.repositories import UserRepository
from src.loggers.console_service_logger import ConsoleServiceLogger


class EntitlementService:
    def __init__(
        self,
        entitlement_repository: EntitlementRepository,
        logger: ConsoleServiceLogger,
    ) -> None:
        self.repo: EntitlementRepository = entitlement_repository
        self.logger: ConsoleServiceLogger = logger

    async def upsert_entitlement(
        self,
        order: Order,
        user_id: Optional[UUID] = None,
    ) -> List[Entitlement]:
        """
        Create or update entitlements for an order.
        """
        try:
            self.logger.info(
                "Upsert entitlement started for order_id={}, partner_id={}".format(
                    order.id, order.partner_id
                )
            )

            plan_modules: List[str] = order.plan.modules if order.plan_id else []
            add_ons: Dict[str, int] = order.add_ons if order.add_ons else []

            modules_by_service: Dict[str, List[str]] = (
                PlanUtils.split_modules_by_service(plan_modules)
            )
            limits_by_service: Dict[str, Dict[str, Any]] = (
                PlanUtils.split_limits_by_service(add_ons)
            )

            if not modules_by_service and not limits_by_service:
                self.logger.warning(
                    "No modules or limits found for order_id={}, partner_id={}. Skipping entitlement creation.".format(
                        order.id, order.partner_id
                    )
                )
                return []

            all_service_names: Set[str] = set(modules_by_service.keys()) | set(
                limits_by_service.keys()
            )

            updated_entitlements: List[Entitlement] = []

            for service_name in all_service_names:
                existing: Optional[Entitlement] = (
                    await self.repo.get_active_entitlement(
                        partner_id=order.partner_id,
                        service_name=service_name,
                    )
                )

                service_modules: List[str] = modules_by_service.get(service_name, [])
                service_limits: Dict[str, Any] = limits_by_service.get(service_name, {})

                if existing:
                    updated: Entitlement = await self._update_entitlement(
                        existing,
                        service_modules,
                        service_limits,
                        user_id,
                        order.partner_id,
                    )
                    updated_entitlements.append(updated)
                else:
                    created: Entitlement = await self._create_entitlement(
                        order,
                        service_name,
                        service_modules,
                        service_limits,
                        user_id,
                    )
                    updated_entitlements.append(created)

            if not updated_entitlements:
                self.logger.warning(
                    "No entitlements created or updated for order_id={}, partner_id={}".format(
                        order.id, order.partner_id
                    )
                )
            else:
                self.logger.info(
                    "Upsert entitlement completed for order_id={}, total_entitlements={}".format(
                        order.id, len(updated_entitlements)
                    )
                )

            return updated_entitlements

        except Exception as e:
            self.logger.error(
                "Error in upserting entitlements for order_id={}, partner_id={}: {}".format(
                    order.id, order.partner_id, repr(e)
                )
            )
            raise

    async def update_entitlement_start_date(
        self,
        payload_data: UpdateEntitlementStartDateRequest,
        current_user: dict,
        auth_repo: AuthRepository = Depends(Provide["auth_repository"]),
    ) -> List[Entitlement]:
        """
        Update the start date of ALL entitlements linked to an order.

        An order can provision one entitlement per service (e.g. console,
        talko). All of them share the same order duration so they must all be
        updated together when the partner reschedules the start date.

        Validations (applied once using the first entitlement as the reference):
        1. At least one entitlement must exist for the given order_id.
        2. Entitlements must be "fresh" (not previously updated from another order).
        3. Update count must not exceed max allowed (checked across all entitlements).
        4. Update must be within the time window from creation.
        5. New start date must differ from the current one.
        """
        try:
            order_id: UUID = payload_data.order_id
            new_start_date: int = payload_data.start_date
            user_id: UUID = current_user.get(CurrentUserMap.USER_ID)
            partner_id: UUID = current_user.get(CurrentUserMap.PARTNER_ID)

            self.logger.info(
                "Updating entitlement start date for order_id={}, new_start_date={}, user_id={}".format(
                    order_id, new_start_date, user_id
                )
            )

            user_data: dict = await auth_repo.get_role_by_user_id(user_id)
            user_hierarchy: int = user_data.get(RoleDictKeys.HIERARCHY)
            is_superadmin: bool = user_hierarchy <= 0

            # ── Fetch ALL entitlements for this order (one per service) ───────
            entitlements: List[Entitlement] = (
                await self.repo.get_entitlements_by_order_id(order_id)
            )

            if not entitlements:
                self.logger.error(
                    "No entitlements found for order_id={}".format(order_id)
                )
                raise OrderNotFoundForEntitlementError(order_id)

            # ── Use the first as the reference for shared validations ─────────
            reference: Entitlement = entitlements[0]

            if not is_superadmin and reference.partner_id != partner_id:
                self.logger.error(
                    "User id={} does not have permission to update entitlement for order_id={}".format(
                        user_id, order_id
                    )
                )
                raise NoPermissionToUpdateEntitlementError(
                    "You do not have permission to update this entitlement."
                )

            # ── Freshness check ───────────────────────────────────────────────
            # Fresh means: the entitlement was created with this order, not
            # carried over from a previous one. Check on the reference is enough
            # because all entitlements for an order share the same order lineage.
            additional_info = reference.additional_info or {}
            previous_order_ids = additional_info.get("previous_order_ids", [])

            if previous_order_ids:
                self.logger.warning(
                    "Entitlement id={} is not fresh. It has previous orders: {}".format(
                        reference.id, previous_order_ids
                    )
                )
                raise EntitlementNotEligibleForStartDateUpdateError(
                    "Start date changes are allowed only for fresh entitlements."
                )

            # ── Update count check — use the max across all entitlements ──────
            max_update_count: int = DbConstants.ENT_START_DATE_UPDATE_MAX_COUNT
            max_current_count: int = max(
                e.start_date_update_count or 0 for e in entitlements
            )

            if max_current_count >= max_update_count:
                self.logger.error(
                    "Update limit exceeded for order_id={}. Current: {}, Max: {}".format(
                        order_id, max_current_count, max_update_count
                    )
                )
                raise EntitlementStartDateUpdateLimitExceededError(
                    current_count=max_current_count, max_allowed=max_update_count
                )

            # ── Time window check ─────────────────────────────────────────────
            update_window_hours: int = (
                DbConstants.ENTITLEMENT_START_DATE_UPDATE_WINDOW_HOURS
            )
            current_time_ms: int = int(DateTimeUtil.get_current_time())
            time_since_creation_hours: float = (
                current_time_ms - reference.created_at
            ) / (1000 * 60 * 60)

            if time_since_creation_hours > update_window_hours:
                self.logger.error(
                    "Update window expired for order_id={}. Created {:.2f} hours ago, window is {} hours".format(
                        order_id, time_since_creation_hours, update_window_hours
                    )
                )
                raise EntitlementStartDateUpdateWindowExpiredError(
                    hours_window=update_window_hours
                )

            # ── Same-date guard ───────────────────────────────────────────────
            if new_start_date == reference.start_date:
                self.logger.error(
                    "New start date is the same as current start date for order_id={}".format(
                        order_id
                    )
                )
                raise EntitlementNotEligibleForStartDateUpdateError(
                    "New start date must be different from the current start date."
                )

            # ── Calculate new end date (same duration for all services) ───────
            duration_days: int = reference.order.duration
            start_datetime: datetime = datetime.fromtimestamp(
                new_start_date / 1000, tz=timezone.utc
            )
            end_datetime: datetime = start_datetime + relativedelta(days=duration_days)
            new_end_date: int = int(end_datetime.timestamp() * 1000)

            self.logger.info(
                "Calculated new end_date={} based on start_date={} and duration={} days for order_id={}".format(
                    new_end_date, new_start_date, duration_days, order_id
                )
            )

            # ── Update ALL entitlements for this order ────────────────────────
            updated_entitlements: List[Entitlement] = []
            for entitlement in entitlements:
                updated: Entitlement = await self.repo.update_entitlement_start_date(
                    entitlement_id=entitlement.id,
                    new_start_date=new_start_date,
                    new_end_date=new_end_date,
                    user_id=user_id,
                )
                updated_entitlements.append(updated)

            self.logger.info(
                "Successfully updated {} entitlement(s) for order_id={}. "
                "new_start_date={}, new_end_date={}, update_count={}".format(
                    len(updated_entitlements),
                    order_id,
                    new_start_date,
                    new_end_date,
                    max_current_count + 1,
                )
            )

            return updated_entitlements

        except Exception as e:
            self.logger.error(
                "Error updating entitlement start date for order_id={}, error={}".format(
                    payload_data.order_id, repr(e)
                )
            )
            raise

    async def activate_pending_entitlements(self) -> int:
        try:
            self.logger.info("Starting activation of pending entitlements")

            activated_count: int = await self.repo.activate_pending_entitlements()

            if activated_count == 0:
                self.logger.info("No entitlements found to activate")
            else:
                self.logger.info(
                    f"Successfully activated {activated_count} entitlements"
                )

            return activated_count
        except Exception as e:
            self.logger.error(
                "Error activating pending entitlements: {}".format(repr(e))
            )
            raise

    async def _update_entitlement(
        self,
        existing: Entitlement,
        service_modules: List[str],
        service_limits: Dict[str, Any],
        user_id: Optional[UUID],
        partner_id: UUID,
    ) -> Entitlement:

        merged_modules: List[str] = self._merge_modules(
            existing.modules, service_modules
        )
        merged_limits: Dict[str, Any] = self._merge_limits(
            existing.limits, service_limits
        )

        additional_info = existing.additional_info or {}
        previous_order_ids = additional_info.get("previous_order_ids", [])

        if existing.order_id:
            if existing.order_id not in previous_order_ids:
                previous_order_ids.append(existing.order_id)

        additional_info["previous_order_ids"] = previous_order_ids

        update_data: EntitlementUpdate = EntitlementUpdate(
            modules=merged_modules,
            limits=merged_limits,
            updated_by=user_id,
        )

        updated: Entitlement = await self.repo.update_entitlement(
            existing.id, update_data
        )
        self.logger.info(
            "Updated entitlement id={} for service='{}', partner_id={}".format(
                existing.id, existing.service_name, partner_id
            )
        )
        return updated

    async def _create_entitlement(
        self,
        order: Order,
        service_name: str,
        service_modules: List[str],
        service_limits: Dict[str, Any],
        user_id: Optional[UUID],
    ) -> Entitlement:

        end_datetime: datetime = datetime.now(timezone.utc) + relativedelta(
            days=order.duration
        )
        end_ts: int = int(end_datetime.timestamp() * 1000)

        create_data: EntitlementCreate = EntitlementCreate(
            order_id=order.id,
            partner_id=order.partner_id,
            service_name=service_name,
            modules=service_modules,
            limits=service_limits,
            created_by=user_id,
            end_date=end_ts,
        )

        ent: Entitlement = await self.repo.create_entitlement(create_data)
        self.logger.info(
            "Created new entitlement id={} for service='{}', partner_id={}".format(
                ent.id, service_name, order.partner_id
            )
        )
        return ent

    def _merge_modules(
        self,
        existing_modules: Optional[List[str]],
        new_modules: List[str],
    ) -> List[str]:
        merged: List[str] = list(set(existing_modules or []) | set(new_modules))
        return merged

    def _merge_limits(
        self,
        existing_limits: Optional[Dict[str, Any]],
        new_limits: Dict[str, Any],
    ) -> Dict[str, Any]:

        merged: Dict[str, Any] = dict(existing_limits or {})

        for key, new_val in new_limits.items():
            old_val: Any = merged.get(key)

            if isinstance(new_val, (int, float)) and isinstance(
                old_val, (int, float, type(None))
            ):
                merged[key] = (old_val or 0) + new_val
            else:
                merged[key] = new_val

        return merged

    # =========================================================================
    # SUBSCRIPTION STATUS
    # =========================================================================

    async def get_subscription_status(
        self,
        partner_id: UUID,
        grace_repo: GraceRepository,
    ) -> Dict[str, Any]:
        all_entitlements: List[Entitlement] = (
            await self.repo.get_all_entitlements_for_partner(partner_id)
        )
        scheduled_entitlements: List[Entitlement] = (
            await self.repo.get_scheduled_entitlements(partner_id)
        )

        all_service_names: set[str] = {e.service_name for e in all_entitlements} | {
            e.service_name for e in scheduled_entitlements
        }

        DEFAULT_SUSPENDED: Dict[str, Any] = {
            "status": ServiceSubscriptionStatus.SUSPENDED,
            "entitlement_start_date": None,
            "entitlement_end_date": None,
        }
        result: Dict[str, Any] = {
            Platform.CONSOLE: DEFAULT_SUSPENDED.copy(),
            Platform.OBOTAAI: DEFAULT_SUSPENDED.copy(),
        }

        if not all_service_names:
            self.logger.info(
                "get_subscription_status | partner_id={} | no entitlement history, "
                "defaulting all services to suspended".format(partner_id)
            )
            return result

        for service_name in all_service_names:
            status, details = await self._resolve_service_status(
                partner_id=partner_id,
                service_name=service_name,
                all_entitlements=all_entitlements,
                scheduled_entitlements=scheduled_entitlements,
                grace_repo=grace_repo,
            )
            result[service_name] = self._build_service_status_dict(status, details)

        self.logger.info(
            "get_subscription_status | partner_id={} | {}".format(
                partner_id,
                {s: v["status"] for s, v in result.items()},
            )
        )
        return result

    async def _resolve_service_status(
        self,
        partner_id: UUID,
        service_name: str,
        all_entitlements: List[Entitlement],
        scheduled_entitlements: List[Entitlement],
        grace_repo: GraceRepository,
    ) -> tuple[str, Optional[Dict[str, Any]]]:
        """
        Resolve status for a single service using the following priority:

            1. CANCELED           — entitlement manually deactivated
            2. ACTIVE             — live entitlement, not expired
            3. GRACE              — no active entitlement but active grace record exists
            4. PENDING_ACTIVATION — scheduled entitlement with a future start_date
            5. SUSPENDED          — none of the above
        """
        now_ms: int = int(DateTimeUtil.get_current_time())
        service_entitlements: List[Entitlement] = [
            e for e in all_entitlements if e.service_name == service_name
        ]

        canceled: Optional[Entitlement] = self._find_canceled(service_entitlements)
        if canceled:
            return ServiceSubscriptionStatus.CANCELED, {
                "entitlement_id": canceled.id,
                "entitlement_start_date": canceled.start_date,
                "entitlement_end_date": canceled.end_date,
            }

        active: Optional[Entitlement] = self._find_active(service_entitlements, now_ms)
        if active:
            return ServiceSubscriptionStatus.ACTIVE, {
                "entitlement_id": active.id,
                "entitlement_start_date": active.start_date,
                "entitlement_end_date": active.end_date,
                "order_id": active.order_id,
            }

        grace: Optional[GracePeriod] = await self._find_active_grace(
            grace_repo, partner_id, service_name, now_ms
        )
        if grace:
            last_entitlement: Optional[Entitlement] = (
                self._find_last_expired_entitlement(service_entitlements, now_ms)
            )
            return ServiceSubscriptionStatus.GRACE, {
                "grace_id": grace.id,
                "granted_days": grace.granted_days,
                "grace_start_date": grace.start_date,
                "grace_end_date": grace.end_date,
                "attempt_number": grace.attempt_number,
                "entitlement_id": last_entitlement.id if last_entitlement else None,
                "entitlement_start_date": (
                    last_entitlement.start_date if last_entitlement else None
                ),
                "entitlement_end_date": (
                    last_entitlement.end_date if last_entitlement else None
                ),
            }

        scheduled: Optional[Entitlement] = self._find_scheduled(
            scheduled_entitlements, service_name, now_ms
        )
        if scheduled:
            return ServiceSubscriptionStatus.PENDING_ACTIVATION, {
                "entitlement_id": scheduled.id,
                "entitlement_start_date": scheduled.start_date,
                "entitlement_end_date": scheduled.end_date,
                "order_id": scheduled.order_id,
            }

        return ServiceSubscriptionStatus.SUSPENDED, None

    @staticmethod
    def _find_canceled(
        service_entitlements: List[Entitlement],
    ) -> Optional[Entitlement]:
        return next(
            (e for e in service_entitlements if e.is_manually_deactivated),
            None,
        )

    @staticmethod
    def _find_active(
        service_entitlements: List[Entitlement],
        now_ms: int,
    ) -> Optional[Entitlement]:
        return next(
            (
                e
                for e in service_entitlements
                if e.is_active
                and not e.is_manually_deactivated
                and (e.end_date is None or e.end_date >= now_ms)
            ),
            None,
        )

    @staticmethod
    async def _find_active_grace(
        grace_repo: GraceRepository,
        partner_id: UUID,
        service_name: str,
        now_ms: int,
    ) -> Optional[GracePeriod]:
        record: Optional[GracePeriod] = await grace_repo.get_active_grace(
            partner_id, service_name
        )
        if record and record.end_date and record.end_date > now_ms:
            return record
        return None

    @staticmethod
    def _find_last_expired_entitlement(
        service_entitlements: List[Entitlement],
        now_ms: int,
    ) -> Optional[Entitlement]:
        """Most recent entitlement whose end_date has already passed."""
        return next(
            (
                e
                for e in sorted(
                    service_entitlements,
                    key=lambda e: e.end_date or 0,
                    reverse=True,
                )
                if e.end_date and e.end_date < now_ms
            ),
            None,
        )

    @staticmethod
    def _find_scheduled(
        scheduled_entitlements: List[Entitlement],
        service_name: str,
        now_ms: int,
    ) -> Optional[Entitlement]:
        return next(
            (
                e
                for e in scheduled_entitlements
                if e.service_name == service_name
                and e.start_date
                and e.start_date > now_ms
            ),
            None,
        )

    @staticmethod
    def _build_service_status_dict(
        status: str,
        details: Optional[Dict[str, Any]],
    ) -> Dict[str, Any]:
        base: Dict[str, Any] = {
            "status": status,
            "entitlement_start_date": (
                details.get("entitlement_start_date") if details else None
            ),
            "entitlement_end_date": (
                details.get("entitlement_end_date") if details else None
            ),
        }

        if status == ServiceSubscriptionStatus.GRACE and details:
            base["grace_start_date"] = details.get("grace_start_date")
            base["grace_end_date"] = details.get("grace_end_date")

        return base

    async def dismiss_popup(
        self,
        user_id: UUID,
        service_name: str,
        user_repo: UserRepository = Depends(Provide["user_repository"]),
    ) -> None:
        """
        Updates popup_last_closed[service_name] = now_ms on User.additional_info.
        Called when user dismisses the popup for a service.
        """
        try:
            await user_repo.update_popup_last_closed(
                user_id=user_id,
                service_name=service_name,
            )
            self.logger.info(
                "Popup dismissed | user_id={} service={}".format(user_id, service_name)
            )
        except Exception as e:
            self.logger.error(
                "Error dismissing popup | user_id={} service={} error={}".format(
                    user_id, service_name, repr(e)
                )
            )
            raise
