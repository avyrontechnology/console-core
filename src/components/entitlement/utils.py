from typing import Any, Dict, Optional

from src.components.common.datetime import DateTimeUtil
from src.components.db_constants.loader.constant import DbConstants
from src.components.entitlement.constants import PopupEligibleHierarchy
from src.components.order.constants import ServiceSubscriptionStatus

_MS_PER_MINUTE: int = 60 * 1000
_MS_PER_DAY: int = 24 * 60 * _MS_PER_MINUTE


class EntitlementUtils:
    """
    Returns {service_name: show_popup} based on subscription status, role, and cooldown.

    Rules:

    - SUSPENDED, CANCELED, PENDING_ACTIVATION:
    → Always show popup to ALL users (no role or cooldown check).

    - ACTIVE:
    → Only for eligible roles (Admin/Maintainer).
    → Show only if near expiry AND cooldown passed.

    - GRACE:
    → Only for eligible roles.
    → Show if cooldown passed.

    - Other statuses:
    → Never show popup.

    Cooldown:
    - Applied only for ACTIVE and GRACE.
    - Popup is shown again only after configured time since last dismissal.
    """
    @staticmethod
    def compute_show_popup(
        *,
        user_hierarchy: int,
        subscription_status: Dict[str, Any],
        popup_last_closed: Dict[str, Any],
    ) -> Dict[str, bool]:

        now_ms: int = int(DateTimeUtil.get_current_time())

        cooldown_ms: int = (
            DbConstants.SUBSCRIPTION_POPUP_FREQUENCY_MINUTES * _MS_PER_MINUTE
        )
        days_before_ms: int = (
            DbConstants.SUBSCRIPTION_POPUP_DAYS_BEFORE_EXPIRY * _MS_PER_DAY
        )

        is_eligible: bool = user_hierarchy <= PopupEligibleHierarchy.MAX

        result: Dict[str, bool] = {}

        for service, info in subscription_status.items():
            status: str = info.get("status", "")
            last_closed: Optional[int] = popup_last_closed.get(service)

            # Check if cooldown has passed
            cooldown_passed: bool = (
                last_closed is None or (now_ms - last_closed) >= cooldown_ms
            )

            # 1. ALWAYS SHOW for critical states (regardless of role)
            if status in {
                ServiceSubscriptionStatus.SUSPENDED,
                ServiceSubscriptionStatus.CANCELED,
                ServiceSubscriptionStatus.PENDING_ACTIVATION,
            }:
                result[service] = True
                continue

            # 2. Non-eligible users get nothing else
            if not is_eligible:
                result[service] = False
                continue

            # 3. Eligible user logic
            if status == ServiceSubscriptionStatus.ACTIVE:
                end_date: Optional[int] = info.get("entitlement_end_date")
                if end_date is None:
                    result[service] = False
                else:
                    time_until_expiry = end_date - now_ms
                    near_expiry = 0 < time_until_expiry <= days_before_ms
                    result[service] = near_expiry and cooldown_passed

            elif status == ServiceSubscriptionStatus.GRACE:
                result[service] = cooldown_passed

            else:
                # Unknown or other statuses (e.g. EXPIRED, etc.)
                result[service] = False

        return result
