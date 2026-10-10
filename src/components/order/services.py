import math
from datetime import datetime, timedelta, timezone
from decimal import ROUND_HALF_UP, Decimal
from typing import Any, Dict, List, Optional

from dependency_injector.wiring import Provide
from fastapi import Depends

from src.components.common.datetime import DateTimeUtil
from src.components.db_constants.loader.constant import DbConstants
from src.components.entitlement.repositories import EntitlementRepository
from src.components.entitlement.services import EntitlementService
from src.components.grace.constants import GRACE_MS_PER_DAY
from src.components.grace.services import GraceService
from src.components.order.constants import (
    AMOUNT_ADDED_IN_WALLET,
    DAYS_PER_MONTH,
    STATUS_MAPPING,
    OrderEmailConstants,
    OrderType,
    PaymentMethod,
    ServiceSubscriptionStatus,
)
from src.components.order.errors import (
    AuthenticationRequiredError,
    InvalidUpgradeError,
    MissingPlanIdError,
    NoActiveEntitlementError,
    NoBillingForWalletError,
    OrderAlreadyProcessedError,
    OrderNotFoundError,
    PlanInactiveError,
    SelfServeManualOrderError,
)
from src.components.order.models import Order
from src.components.order.repositories import OrderRepository
from src.components.order.schema import (
    OrderBase,
    OrderBillingDetailsRequest,
    OrderResponse,
)
from src.components.partner.error import PartnerNotFoundError
from src.components.partner.repositories import PartnerRepository
from src.components.partner_config.constants import (
    PartnerConfigEnum,
    SubscriptionModeEnum,
)
from src.components.partner_config.schemas import PartnerConfigResponse
from src.components.partner_config.services import PartnerConfigService
from src.components.payment.enum import EntityNameEnum, PaymentStatusEnum
from src.components.payment.schema import InitiateOrderRequest, ValidateOrderRequest
from src.components.payment.services import PaymentService
from src.components.plan.constants import PlanCustomLimitKeys, PlanType
from src.components.plan.models import Plan
from src.components.plan.repositories import PlanRepository
from src.components.plan.utils import PlanUtils
from src.components.wallet.enum import Currency, ServiceName, TransactionType
from src.components.wallet.services import WalletService
from src.core.environment import ENV
from src.loggers.console_service_logger import ConsoleServiceLogger


class OrderService:
    """
    Handles the full order lifecycle:

      Self-serve flow   : initiate_order → (user pays) → validate_order / handle_webhook
      Manual flow       : create_manual_order (sales team, no gateway — handles both
                          fresh and renewal classification automatically)
      History & billing : get_order_history, get_billing_details
    """

    def __init__(
        self,
        order_repo: OrderRepository,
        payment_service: PaymentService,
        logger: ConsoleServiceLogger,
    ):
        self.order_repo = order_repo
        self.payment_service = payment_service
        self.logger = logger

    # =========================================================================
    # SELF-SERVE: INITIATE ORDER
    # =========================================================================

    async def initiate_order(
        self,
        order_data: OrderBase,
        user_context: Dict,
        entitlement_repo: EntitlementRepository = Depends(
            Provide["entitlement_repository"]
        ),
        plan_repo: PlanRepository = Depends(Provide["plan_repository"]),
        wallet_service: WalletService = Depends(Provide["wallet_service"]),
    ) -> Dict:
        """Creates an order and initiates payment."""
        try:
            partner_id: int = user_context.get("partner_id")
            user_id: int = user_context.get("user_id")
            self.logger.info(f"Creating order for partner_id={partner_id}")

            duration_in_days = None
            plan = None

            # Scenario 1: Only add-ons (requires active entitlement)
            if not order_data.plan_id and order_data.add_ons:
                active_entitlements: dict = await self._get_active_entitlements(
                    entitlement_repo, partner_id
                )
                self._validate_addons_entitlement(
                    order_data.add_ons, active_entitlements
                )
                duration_in_days = self._get_remaining_days_from_entitlements(
                    active_entitlements
                )

            # Scenario 2 & 3: Plan with or without add-ons
            if order_data.plan_id:
                plan = await self._validate_plan(order_data.plan_id, plan_repo)
                active_entitlements = await self._get_active_entitlements(
                    entitlement_repo, partner_id
                )

                if active_entitlements:
                    await self._check_hierarchy_downgrade(
                        partner_id, plan, entitlement_repo
                    )
                    duration_in_days = self._get_remaining_days_from_entitlements(
                        active_entitlements
                    )
                else:
                    duration_in_days = plan.duration * DAYS_PER_MONTH

            # Classify order type from partner's SUCCESS history (same logic as manual)
            # For add-only orders (no plan) classification is not applicable → FRESH
            if plan:
                order_type, _ = await self._classify_manual_order(
                    partner_id=partner_id,
                    new_plan=plan,
                )
            else:
                order_type = OrderType.FRESH

            if plan and plan.plan_type == PlanType.WALLET:
                wallet_calc = await self.calculate_amount(
                    order_data.amount, order_data.currency
                )
                order_data.amount = wallet_calc["final_amount"]  # Stored in DB + gateway
                self.logger.info(
                    "Wallet plan | base_amount={} final_amount={}".format(
                        wallet_calc["base_amount"], order_data.amount
                    )
                )

            order: Order = await self.order_repo.initiate_order(
                order_data,
                user_id,
                partner_id,
                duration_in_days,
                order_type=order_type,
            )

            # Store wallet_base_amount in additional_info after order is created
            if plan and plan.plan_type == PlanType.WALLET:
                order = await self.order_repo.update_order(
                    order.id,
                    {
                        "additional_info": {
                            **(order.additional_info or {}),
                            "wallet_base_amount": wallet_calc["base_amount"],
                        }
                    },
                    user_id,
                )

            gateway_order: Dict = await self._create_gateway_order(
                order, order_data, user_context
            )
            order: Order = await self.order_repo.update_order(
                order.id, {"merchant_transaction_id": gateway_order.get("id")}, user_id
            )

            self.logger.info(f"Order created successfully order_id={order.id}")

            await self._handle_wallet_transaction(
                order, user_id, partner_id, wallet_service
            )

            return self._build_order_response(order, gateway_order)

        except Exception as e:
            self.logger.error(f"Error in initiate_order: {e}")
            raise

    # =========================================================================
    # SELF-SERVE: VALIDATE ORDER
    # =========================================================================

    async def validate_order(
        self,
        merchant_transaction_id: str,
        payment_id: str,
        signature: str,
        current_user: dict,
        entitlement_service: EntitlementService = Depends(
            Provide["entitlement_service"]
        ),
        wallet_service: WalletService = Depends(Provide["wallet_service"]),
        entitlement_repo: Optional[EntitlementRepository] = Depends(
            Provide["entitlement_repository"]
        ),
        grace_service: Optional[GraceService] = Depends(Provide["grace_service"]),
    ) -> Dict:
        """Validates payment and updates order."""
        try:
            self.logger.info(
                "Validating order merchant_transaction_id={}".format(
                    merchant_transaction_id
                )
            )

            user_id: int = current_user.get("user_id")
            order: Order = await self.order_repo.get_order_by_merchant_transaction_id(
                merchant_transaction_id
            )

            # SUCCESS/REFUNDED are the only truly terminal states -- re-running
            # this would double-provision entitlements. FAILED is NOT locked
            # out here: it can be set prematurely (e.g. the abandoned-order
            # cleanup cron firing on a slow checkout) while the customer is
            # still completing a genuinely successful payment on Razorpay's
            # side, and Razorpay itself allows retrying a failed attempt on
            # the same order. Letting it fall through to the real signature
            # check below is what lets that late-arriving success self-heal
            # instead of the order staying wrongly FAILED forever.
            if order.status in (PaymentStatusEnum.SUCCESS, PaymentStatusEnum.REFUNDED):
                self.logger.warning(
                    "Order already finalized | order_id={} status={}".format(
                        order.id, order.status
                    )
                )
                raise OrderAlreadyProcessedError("Order has already been processed.")

            validate_payload = ValidateOrderRequest(
                order_id=merchant_transaction_id,
                payment_id=payment_id,
                signature=signature,
            )
            result: Dict[str, str] = await self.payment_service.validate_order(
                validate_payload, current_user
            )

            status_str = result.get("status", "").lower()
            new_status = STATUS_MAPPING.get(status_str, PaymentStatusEnum.FAILED)

            # Conditional on the order not already being SUCCESS/REFUNDED --
            # the atomic guard against a concurrent duplicate request (see
            # docstring on update_order_if_not_finalized). If this returns
            # None, another concurrent call already finalized the order
            # (and, if that happened to be a success, already provisioned
            # it) between our check above and now; skip re-provisioning
            # rather than double-crediting.
            updated_order: Optional[Order] = (
                await self.order_repo.update_order_if_not_finalized(
                    order_id=order.id,
                    update_data={
                        "merchant_transaction_id": merchant_transaction_id,
                        "status": new_status,
                        "payment_id": (
                            payment_id
                            if new_status == PaymentStatusEnum.SUCCESS
                            else None
                        ),
                    },
                    user_id=user_id,
                )
            )

            if updated_order is None:
                self.logger.warning(
                    "Skipping provisioning for merchant_transaction_id={}: "
                    "order already finalized by a concurrent request".format(
                        merchant_transaction_id
                    )
                )
                return result

            if new_status == PaymentStatusEnum.SUCCESS:
                await self._provision_on_payment_success(
                    order=updated_order,
                    user_id=user_id,
                    entitlement_service=entitlement_service,
                    wallet_service=wallet_service,
                    entitlement_repo=entitlement_repo,
                    grace_service=grace_service,
                )

            self.logger.info(
                "Order validated successfully merchant_transaction_id={}, status={}".format(
                    merchant_transaction_id, new_status
                )
            )
            return result

        except Exception as e:
            self.logger.error("Error in validate_order: {}".format(e))
            raise

    # =========================================================================
    # SELF-SERVE: WEBHOOK
    # =========================================================================

    async def handle_webhook(
        self,
        payload: Dict,
        raw_body: bytes,
        signature: str,
        entitlement_service: EntitlementService = Depends(
            Provide["entitlement_service"]
        ),
        wallet_service: WalletService = Depends(Provide["wallet_service"]),
        entitlement_repo: Optional[EntitlementRepository] = Depends(
            Provide["entitlement_repository"]
        ),
        grace_service: Optional[GraceService] = Depends(Provide["grace_service"]),
    ) -> Dict:
        """Called by payment gateway webhook. Updates payment and order status."""
        try:
            inner = payload.get("payload", {})
            payment = inner.get("payment", {}).get("entity", {})
            order_id = payment.get("order_id")
            self.logger.info("Processing webhook for order_id={}".format(order_id))

            processed = await self.payment_service.handle_webhook(
                payload=payload,
                raw_body=raw_body,
                signature=signature,
            )

            try:
                order: Order = (
                    await self.order_repo.get_order_by_merchant_transaction_id(
                        order_id
                    )
                )
            except OrderNotFoundError:
                # A validly-signed Razorpay webhook for an order we have no
                # local record of -- most commonly a payment collected
                # manually via the Razorpay Dashboard rather than through our
                # own checkout flow. Razorpay fires account-level webhooks for
                # those too, so this is an expected, benign case (not a
                # system failure): acknowledge it so Razorpay doesn't keep
                # retrying, instead of raising and 500-ing.
                self.logger.warning(
                    "Webhook received for order_id={} with no matching local "
                    "order -- likely created outside our order flow (e.g. "
                    "manually in the Razorpay Dashboard). Acknowledging "
                    "without further action.".format(order_id)
                )
                return {**processed, "order_id": order_id}

            if order.status != PaymentStatusEnum.PENDING:
                self.logger.info(
                    f"Skipping webhook - order {order.id} already {order.status}"
                )
                return processed

            status_str = processed.get("status", "").lower()
            updated_order = await self.order_repo.update_order(
                order_id=order.id,
                update_data={
                    "status": STATUS_MAPPING.get(status_str, PaymentStatusEnum.FAILED),
                    "payment_id": processed.get("payment_id"),
                    "payment_method": processed.get("payment_method"),
                },
                user_id=None,
            )

            if updated_order.status == PaymentStatusEnum.SUCCESS:
                await self._provision_on_payment_success(
                    order=updated_order,
                    user_id=order.created_by,
                    entitlement_service=entitlement_service,
                    wallet_service=wallet_service,
                    entitlement_repo=entitlement_repo,
                    grace_service=grace_service,
                )

            return processed

        except Exception as e:
            self.logger.error("Error in handle_webhook: {}".format(e))
            raise

    # =========================================================================
    # MANUAL ORDER: CREATE  (handles fresh, renewal, and upgrade in one flow)
    # =========================================================================

    async def create_manual_order(
        self,
        payload: Dict,
        current_user: dict,
        plan_repo: PlanRepository = Depends(Provide["plan_repository"]),
        partner_repo: PartnerRepository = Depends(Provide["partner_repository"]),
        entitlement_repo: EntitlementRepository = Depends(
            Provide["entitlement_repository"]
        ),
        entitlement_service: EntitlementService = Depends(
            Provide["entitlement_service"]
        ),
        grace_service: Optional[GraceService] = Depends(Provide["grace_service"]),
        partner_config_service: PartnerConfigService = Depends(
            Provide["partner_config_service"]
        ),
    ) -> Dict:
        """
        Sales-team endpoint: create a manual order and immediately provision
        the entitlement. No payment gateway is involved.

        Duration is derived automatically: plan.duration * DAYS_PER_MONTH.

        Classification logic (checked against partner's SUCCESS order history):
          1. Partner has no order history at all          → FRESH
          2. Partner has a prior order for this exact plan_id
             OR new plan hierarchy == latest plan hierarchy → RENEWAL
          3. New plan hierarchy > latest plan hierarchy   → upgrade, FRESH
             (sales team is moving partner to a higher tier)
          4. New plan hierarchy < latest plan hierarchy   → downgrade

        Entitlement guards:
          - Partner must have no currently-active entitlement.
          - If a scheduled entitlement exists, derived duration must be strictly
            less than days until it activates.
        """
        try:
            sales_user_id: int = current_user["user_id"]
            partner_id: int = payload["partner_id"]

            self.logger.info(
                "Manual order creation | partner_id={} plan_id={} sales_user={}".format(
                    partner_id, payload["plan_id"], sales_user_id
                )
            )

            # ── 0. Validate partner exists and is active ──────────────────────
            await self._validate_partner(partner_id, partner_repo)

            # ── 0.1. Validate subscription mode is not self-served ───────
            subscription_mode: (
                PartnerConfigResponse | list[PartnerConfigResponse] | None
            ) = await partner_config_service.get_partner_config_by_key(
                partner_id, PartnerConfigEnum.SUBSCRIPTION_MODE
            )
            if (
                subscription_mode is None
                or subscription_mode.value == SubscriptionModeEnum.SELF_SERVED
                or subscription_mode.value is None
            ):
                self.logger.info(
                    "Manual order creation attempted for self-served partner: {}.".format(
                        partner_id
                    )
                )
                raise SelfServeManualOrderError(
                    "Manual orders are not allowed for self-served partners."
                )

            # ── 1. Validate plan ─────────────────────────────────────────────
            plan: Plan = await self._validate_plan(payload["plan_id"], plan_repo)

            # ── 2. Classify: fresh / renewal / upgrade / downgrade ────────────
            order_type, latest_order = await self._classify_manual_order(
                partner_id=partner_id,
                new_plan=plan,
            )

            # ── 3. Entitlement guards ─────────────────────────────────────────
            await self._assert_no_active_entitlement(entitlement_repo, partner_id)

            duration_days: int = plan.duration * DAYS_PER_MONTH

            await self._assert_duration_within_scheduled_window(
                entitlement_repo, partner_id, duration_days
            )

            # ── 4. Persist order ──────────────────────────────────────────────
            order: Order = await self.order_repo.create_manual_order(
                partner_id=partner_id,
                plan_id=plan.id,
                add_ons=payload.get("add_ons") or {},
                amount=payload["amount"],
                currency=payload.get("currency") or plan.currency,
                duration_days=duration_days,
                created_by=sales_user_id,
                order_type=order_type,
                payment_method=payload["payment_method"],
                original_order_id=(
                    latest_order.id
                    if order_type == OrderType.RENEWAL and latest_order
                    else None
                ),
            )

            # ── 5. Branch on payment method ───────────────────────────────────
            if payload["payment_method"] == PaymentMethod.GATEWAY:
                # Initiate gateway — entitlement provisioned after payment
                # via validate_order / webhook, same as self-serve flow.
                gateway_order: Dict = await self._create_gateway_order(
                    order=order,
                    order_data=payload,
                    user_context={"partner_id": partner_id, "user_id": sales_user_id},
                )
                order = await self.order_repo.update_order(
                    order.id,
                    {"merchant_transaction_id": gateway_order.get("id")},
                    sales_user_id,
                )
                self.logger.info(
                    "Manual order gateway initiated | order_id={} order_type={}".format(
                        order.id, order_type
                    )
                )
                return self._build_order_response(order, gateway_order)

            else:
                # DIRECT — approve and provision immediately, then settle grace.
                provisioned_order: Order = (
                    await self._approve_and_provision_manual_order(
                        order=order,
                        sales_user_id=sales_user_id,
                        entitlement_service=entitlement_service,
                        entitlement_repo=entitlement_repo,
                        grace_service=grace_service,
                    )
                )
                self.logger.info(
                    "Manual order direct payment provisioned | order_id={} order_type={}".format(
                        order.id, order_type
                    )
                )
                return self._build_order_response(provisioned_order, gateway_order=None)

        except Exception as e:
            self.logger.error(
                "Error in create_manual_order | partner_id={} error={}".format(
                    payload["partner_id"], e
                )
            )
            raise

    # =========================================================================
    # ORDER HISTORY
    # =========================================================================

    async def get_order_history(
        self,
        filters: Dict[str, Any],
        limit: Optional[int] = None,
        offset: Optional[int] = None,
        partner_repo: PartnerRepository = Depends(Provide["partner_repository"]),
    ) -> tuple[List[Dict], int]:
        """
        Fetch paginated order history.

        Supports all existing filters plus:
          - is_manually_created (bool) : filter manual vs self-serve orders
          - order_type          (str)  : FRESH | RENEWAL | UPGRADE | DOWNGRADE
        """
        try:
            partner_ids: Optional[int] = filters.get("partner_ids")

            if partner_ids:
                await partner_repo.validate_partner_ids(partner_ids)

            orders_data, total_count = await self.order_repo.get_order_history(
                filters=filters, limit=limit, offset=offset
            )

            self.logger.info(f"Fetched {len(orders_data)} orders from repository")

            payment_gateway = ENV.PAYMENT_CLIENT

            order_responses: list = [
                self._build_order_history_response(order_dict, payment_gateway)
                for order_dict in orders_data
            ]

            return order_responses, total_count

        except Exception as e:
            self.logger.error(f"Error fetching order history: {e}")
            raise

    def _resolve_order_subscription_status(
        self,
        order: Dict[str, Any],
        entitlement: Optional[Dict[str, Any]],
    ) -> str:

        order_status = order.get("status")
        payment_method = order.get("payment_method")

        # ── 1. DIRECT manual order — no gateway, provisioned immediately.
        #       Resolve status from entitlement state like any other SUCCESS order.
        #       Fall through to entitlement checks below.
        if payment_method == PaymentMethod.DIRECT:
            if order_status == PaymentStatusEnum.FAILED:
                return ServiceSubscriptionStatus.PAYMENT_FAILED
            # SUCCESS → fall through to entitlement resolution

        # ── 2. Gateway order failed ───────────────────────────────────────────
        elif order_status == PaymentStatusEnum.FAILED:
            return ServiceSubscriptionStatus.PAYMENT_FAILED

        # ── 3. Gateway order still pending ───────────────────────────────────
        elif order_status == PaymentStatusEnum.PENDING:
            return ServiceSubscriptionStatus.PENDING_ACTIVATION

        # ── 4. No entitlement linked yet (edge case on SUCCESS) ───────────────
        if not entitlement:
            return ServiceSubscriptionStatus.SUSPENDED

        # ── 5. Manually deactivated ───────────────────────────────────────────
        if entitlement.get("is_manually_deactivated"):
            return ServiceSubscriptionStatus.CANCELED

        now_ms = int(DateTimeUtil.get_current_time())
        start_date = entitlement.get("start_date") or 0
        end_date = entitlement.get("end_date")
        is_active = entitlement.get("is_active", False)

        # ── 6. Live entitlement ───────────────────────────────────────────────
        if is_active and (end_date is None or end_date >= now_ms):
            return ServiceSubscriptionStatus.ACTIVE

        # ── 7. Scheduled (future start) ───────────────────────────────────────
        if not is_active and start_date > now_ms:
            return ServiceSubscriptionStatus.PENDING_ACTIVATION

        # ── 8. Expired, nothing else ──────────────────────────────────────────
        return ServiceSubscriptionStatus.SUSPENDED

    def _build_order_history_response(
        self,
        order_dict: Dict[str, Any],
        payment_gateway: str,
    ) -> Dict[str, Any]:
        order = order_dict.get("order", {})
        partner = order_dict.get("partner")
        plan = order_dict.get("plan")
        payment = order_dict.get("payment")
        entitlement = order_dict.get("entitlement")
        admin_user = order_dict.get("admin_user")

        plan_duration_days: int = self._calculate_plan_duration_days(plan)

        response = {
            **self._map_order_fields(order),
            **self._map_partner_fields(partner, admin_user),
            **self._map_plan_fields(plan, plan_duration_days),
            **self._map_entitlement_fields(entitlement),
            **self._map_payment_fields(payment, payment_gateway, order=order),
        }

        response["subscription_status"] = self._resolve_order_subscription_status(
            order=order,
            entitlement=entitlement,
        )

        return response

    def _map_order_fields(self, order: Dict[str, Any]) -> Dict[str, Any]:
        is_manually_created: bool = order.get("is_manually_created", False)
        order_type: str = order.get("order_type", OrderType.FRESH)

        return {
            "order_id": order.get("id"),
            "source": order.get("source"),
            "order_status": order.get("status"),
            "order_currency": order.get("currency"),
            "merchant_transaction_id": order.get("merchant_transaction_id"),
            "duration": order.get("duration"),
            "add_ons": order.get("add_ons"),
            "total_price": order.get("amount"),
            "order_created_at": order.get("created_at"),
            "order_created_by": order.get("created_by"),
            "order_updated_at": order.get("updated_at"),
            "order_updated_by": order.get("updated_by"),
            "is_manually_created": is_manually_created,
            "order_type": self._resolve_order_type(order_type),
            "payment_method": order.get("payment_method"),
            "original_order_id": order.get("original_order_id"),
        }

    def _map_partner_fields(
        self,
        partner: Optional[Dict[str, Any]],
        admin_user: Optional[Dict[str, Any]],
    ) -> Dict[str, Any]:
        return {
            "partner_id": partner.get("id") if partner else None,
            "partner_name": partner.get("name") if partner else None,
            "partner_gst_no": partner.get("gst_no") if partner else None,
            "partner_is_active": partner.get("is_active") if partner else None,
            "partner_email": admin_user.get("email") if admin_user else None,
            "partner_phone_number": (
                admin_user.get("phone_number") if admin_user else None
            ),
            "partner_country": partner.get("country") if partner else None,
            "partner_state": partner.get("state") if partner else None,
            "partner_city": partner.get("city") if partner else None,
        }

    def _map_plan_fields(
        self,
        plan: Optional[Dict[str, Any]],
        duration_in_days: int,
    ) -> Dict[str, Any]:
        return {
            "plan_id": plan.get("id") if plan else None,
            "plan_name": plan.get("name") if plan else None,
            "plan_type": plan.get("plan_type") if plan else None,
            "plan_duration_months": plan.get("duration") if plan else None,
            "duration_in_days": duration_in_days,
            "plan_limits": plan.get("limits") if plan else {},
            "plan_price": plan.get("price") if plan else 0,
            "plan_discount_percentage": plan.get("discount_percentage") if plan else 0,
        }

    def _map_entitlement_fields(
        self,
        entitlement: Optional[Dict[str, Any]],
    ) -> Dict[str, Any]:
        return {
            "entitlement_start_date": (
                entitlement.get("start_date") if entitlement else None
            ),
            "entitlement_end_date": (
                entitlement.get("end_date") if entitlement else None
            ),
            "entitlement_is_active": (
                entitlement.get("is_active") if entitlement else None
            ),
        }

    def _map_payment_fields(
        self,
        payment: Optional[Dict[str, Any]],
        payment_gateway: str,
        order: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        # DIRECT manual orders never create a Payment record — derive display
        # status from the order itself so the history row is not misleading.
        if (
            payment is None
            and order
            and order.get("payment_method") == PaymentMethod.DIRECT
            and order.get("status") == PaymentStatusEnum.SUCCESS
        ):
            return {
                "payment_gateway": None,
                "payment_status": PaymentStatusEnum.SUCCESS,
                "payment_date": order.get("created_at"),
                "payment_method": PaymentMethod.DIRECT,
            }

        return {
            "payment_gateway": payment_gateway,
            "payment_status": payment.get("payment_status") if payment else None,
            "payment_date": payment.get("created_at") if payment else None,
            "payment_method": payment.get("payment_method") if payment else None,
        }

    def _calculate_plan_duration_days(
        self,
        plan: Optional[Dict[str, Any]],
    ) -> int:
        return plan.get("duration", 0) * DAYS_PER_MONTH if plan else 0

    # =========================================================================
    # BILLING DETAILS
    # =========================================================================

    def _to_paisa(self, value: Decimal) -> Decimal:
        """Round a Decimal to the nearest whole paisa using ROUND_HALF_UP."""
        return value.quantize(Decimal("1"), rounding=ROUND_HALF_UP)

    def _to_float(self, value: Decimal) -> float:
        """Convert a finalised Decimal paisa amount to float for JSON output."""
        return float(value)

    async def get_billing_details(
        self,
        order_data: OrderBillingDetailsRequest,
        partner_id: Optional[int] = None,
        plan_repo: PlanRepository = Depends(Provide["plan_repository"]),
        entitlement_repo: EntitlementRepository = Depends(
            Provide["entitlement_repository"]
        ),
    ) -> Dict:
        """
        Calculate billing details with proper upgrade credit and add-on pricing.
        All intermediate amounts are kept as Decimal (paisa).
        Final JSON output converts to float only at the return boundary.
        """
        try:
            self._log_billing_request(partner_id, order_data)
            self._validate_authentication(order_data, partner_id)

            active_entitlements: dict = {}
            if partner_id:
                active_entitlements = await self._get_active_entitlements(
                    entitlement_repo, partner_id
                )

            plan: Optional[Plan] = await self._load_plan(order_data, plan_repo)

            if plan and plan.plan_type == PlanType.WALLET:
                raise NoBillingForWalletError(
                    "Billing details cannot be fetched for WALLET plan type"
                )

            if plan and plan.is_free_trial:
                raise NoBillingForWalletError(
                    "Billing details cannot be fetched for free trial plans"
                )

            billing_days: int = self._resolve_billing_days(
                plan, active_entitlements, partner_id
            )

            add_ons_by_service: Dict[str, dict] = self._split_addons_by_service(
                order_data.add_ons
            )
            services: set = self._resolve_services(plan, add_ons_by_service)

            if partner_id:
                self._validate_services_entitlements(active_entitlements, order_data)

            billing_breakdown: Dict = self._build_billing_breakdown(
                plan=plan,
                billing_days=billing_days,
                add_ons_by_service=add_ons_by_service,
                services=services,
                active_entitlements=active_entitlements,
            )

            final_response: Dict = self._calculate_final_totals(
                billing_days=billing_days,
                plan=plan,
                billing_breakdown=billing_breakdown,
            )

            self.logger.info(
                f"Billing details calculated | partner_id={partner_id} "
                f"total_payable={final_response['summary']['total_payable']}"
            )

            return final_response

        except Exception as exc:
            self.logger.error(
                f"Billing calculation error | partner_id={partner_id} error={exc}"
            )
            raise

    # ------------------------------------------------------------------
    # Billing days resolution
    # ------------------------------------------------------------------
    def _resolve_billing_days(
        self,
        plan: Optional[Plan],
        active_entitlements: Dict,
        partner_id: Optional[int],
    ) -> int:
        if not partner_id or not active_entitlements:
            if not plan:
                raise NoActiveEntitlementError(
                    "Cannot determine billing duration without plan or entitlements"
                )
            billing_days = plan.duration * DAYS_PER_MONTH
            self.logger.info(
                f"Using plan duration | months={plan.duration} days={billing_days}"
            )
        else:
            billing_days = self._get_remaining_days_from_entitlements(
                active_entitlements
            )
            self.logger.info(
                f"Using entitlement remaining days | billing_days={billing_days}"
            )

        if billing_days <= 0:
            raise NoActiveEntitlementError(
                "All entitlements have expired (0 remaining days). "
                "Cannot calculate billing for an expired period."
            )

        return billing_days

    def _get_remaining_days_from_entitlements(self, active_entitlements: Dict) -> int:
        if not active_entitlements:
            raise NoActiveEntitlementError(
                "No active entitlements found; cannot determine remaining days."
            )

        now = datetime.now(timezone.utc)

        max_remaining_days = max(
            max(
                math.ceil(
                    (
                        datetime.fromtimestamp(ent.end_date / 1000, tz=timezone.utc)
                        - now
                    ).total_seconds()
                    / 86400
                ),
                0,
            )
            for ent in active_entitlements.values()
        )
        return max_remaining_days

    def _validate_services_entitlements(
        self,
        active_entitlements: Dict,
        order_data: OrderBillingDetailsRequest,
    ):
        if not order_data.plan_id and order_data.add_ons:
            self._validate_addons_entitlement(order_data.add_ons, active_entitlements)

    def _get_current_plan_from_entitlement(
        self, service_name: str, active_entitlements: Dict
    ) -> Optional[Plan]:
        entitlement = active_entitlements.get(service_name)
        if entitlement and entitlement.order and entitlement.order.plan:
            return entitlement.order.plan
        return None

    def _build_billing_breakdown(
        self,
        plan: Optional[Plan],
        billing_days: int,
        add_ons_by_service: Dict[str, dict],
        services: set,
        active_entitlements: Dict,
    ) -> Dict:
        breakdown = {
            "plan_details": None,
            "add_ons_details": {},
            "plan_subtotal_before_credit": Decimal("0"),
            "plan_upgrade_credit": Decimal("0"),
            "plan_subtotal_after_credit": Decimal("0"),
            "plan_discount_amount": Decimal("0"),
            "plan_subtotal_after_discount": Decimal("0"),
            "addons_total": Decimal("0"),
            "addons_discount_amount": Decimal("0"),
        }

        plan_discount_percentage = Decimal("0")
        if plan:
            plan_discount_percentage = Decimal(str(plan.discount_percentage or 0))
            plan_breakdown = self._calculate_plan_pricing_with_upgrade(
                plan, billing_days, active_entitlements
            )
            breakdown["plan_details"] = plan_breakdown
            breakdown["plan_subtotal_before_credit"] = plan_breakdown[
                "subtotal_before_credit"
            ]
            breakdown["plan_upgrade_credit"] = plan_breakdown["upgrade_credit"]
            breakdown["plan_subtotal_after_credit"] = plan_breakdown[
                "subtotal_after_credit"
            ]
            breakdown["plan_discount_amount"] = plan_breakdown["discount_amount"]
            breakdown["plan_subtotal_after_discount"] = plan_breakdown[
                "total_after_discount"
            ]

        for service in services:
            service_addons = add_ons_by_service.get(service, {})
            if not service_addons:
                continue

            addon_breakdown = self._calculate_service_addons(
                service=service,
                add_ons=service_addons,
                billing_days=billing_days,
                plan=plan,
                discount_percentage=plan_discount_percentage,
            )

            breakdown["add_ons_details"][service] = addon_breakdown
            breakdown["addons_total"] += addon_breakdown["service_total"]
            breakdown["addons_discount_amount"] += addon_breakdown.get(
                "total_discount", Decimal("0")
            )

        return breakdown

    def _calculate_plan_pricing_with_upgrade(
        self,
        new_plan: Plan,
        billing_days: int,
        active_entitlements: Dict,
    ) -> Dict:
        billing_days_d = Decimal(str(billing_days))
        days_per_month_d = Decimal(str(DAYS_PER_MONTH))

        new_plan_price = Decimal(str(int(new_plan.price)))  # price is in paisa/month
        new_plan_price_per_day = new_plan_price / days_per_month_d
        new_plan_subtotal = new_plan_price_per_day * billing_days_d

        current_plan = self._get_current_plan_from_entitlement(
            new_plan.service_name, active_entitlements
        )

        upgrade_credit = Decimal("0")
        current_plan_name = None
        if current_plan:
            current_plan_price = Decimal(str(int(current_plan.price)))
            current_plan_price_per_day = current_plan_price / days_per_month_d
            upgrade_credit = current_plan_price_per_day * billing_days_d
            current_plan_name = current_plan.name
            self.logger.info(
                f"Plan upgrade | current={current_plan.name} new={new_plan.name} "
                f"credit={upgrade_credit} paisa"
            )

        net_plan_cost = new_plan_subtotal - upgrade_credit
        discount_percentage = Decimal(str(new_plan.discount_percentage or 0))
        discount_amount = self._to_paisa(net_plan_cost * discount_percentage / 100)
        plan_total_after_discount = net_plan_cost - discount_amount

        return {
            "plan_id": new_plan.id,
            "plan_name": new_plan.name,
            "service_name": new_plan.service_name,
            "tag": new_plan.tag,
            # keep as Decimal internally; caller converts at the return boundary
            "price_per_day": new_plan_price_per_day,
            "billing_days": billing_days,
            "subtotal_before_credit": new_plan_subtotal,
            "upgrade_credit": upgrade_credit,
            "subtotal_after_credit": net_plan_cost,
            "discount_percentage": discount_percentage,
            "discount_amount": discount_amount,
            "total_after_discount": plan_total_after_discount,
            "current_plan_name": current_plan_name,
        }

    # ------------------------------------------------------------------
    # Add-on pricing
    # ------------------------------------------------------------------
    def _calculate_service_addons(
        self,
        service: str,
        add_ons: dict,
        billing_days: int,
        plan: Optional[Plan],
        discount_percentage: Decimal = Decimal("0"),
    ) -> Dict:
        addon_items = []
        service_total = Decimal("0")
        total_discount = Decimal("0")

        billing_days_d = Decimal(str(billing_days))
        days_per_month_d = Decimal(str(DAYS_PER_MONTH))

        for addon_key, quantity in add_ons.items():
            quantity_d = Decimal(str(quantity))

            if addon_key == PlanCustomLimitKeys.Console.ACTIVE_USERS:
                if not plan:
                    raise MissingPlanIdError(
                        f"Cannot calculate '{PlanCustomLimitKeys.Console.ACTIVE_USERS}' "
                        f"add-on pricing. Plan ID required."
                    )
                price_per_day_per_unit = (
                    Decimal(str(int(plan.price))) / days_per_month_d
                )
            else:
                raw_price = self._get_addon_price(addon_key)
                price_per_day_per_unit = Decimal(str(raw_price))
                if price_per_day_per_unit == 0:
                    self.logger.warning(
                        f"No price for add-on | addon_key={addon_key} service={service}"
                    )

            addon_subtotal = price_per_day_per_unit * quantity_d * billing_days_d

            addon_discount = Decimal("0")
            if (
                addon_key == PlanCustomLimitKeys.Console.ACTIVE_USERS
                and discount_percentage > 0
            ):
                addon_discount = self._to_paisa(
                    addon_subtotal * discount_percentage / 100
                )
                total_discount += addon_discount

            addon_total = addon_subtotal - addon_discount

            addon_items.append(
                {
                    "addon_key": addon_key,
                    "quantity": quantity,
                    "price_per_day_per_unit": price_per_day_per_unit,
                    "billing_days": billing_days,
                    "subtotal": addon_subtotal,
                    "discount_percentage": (
                        discount_percentage
                        if addon_key == PlanCustomLimitKeys.Console.ACTIVE_USERS
                        else Decimal("0")
                    ),
                    "discount_amount": addon_discount,
                    "total": addon_total,
                }
            )

            service_total += addon_total

        return {
            "service_name": service,
            "items": addon_items,
            "total_discount": total_discount,
            "service_total": service_total,
        }

    def _calculate_final_totals(
        self,
        billing_days: int,
        plan: Optional[Plan],
        billing_breakdown: Dict,
    ) -> Dict:
        billing_days_d = Decimal(str(billing_days))
        days_per_month_d = Decimal(str(DAYS_PER_MONTH))

        plan_after_discount: Decimal = billing_breakdown["plan_subtotal_after_discount"]
        addons_total: Decimal = billing_breakdown["addons_total"]
        subtotal_after_discount = plan_after_discount + addons_total

        gst_amount = Decimal("0")
        gst_percentage = Decimal("0")
        total_payable = subtotal_after_discount

        if DbConstants.IS_GST_ENABLED:
            gst_percentage = Decimal(str(DbConstants.GST_PERCENTAGE))
            gst_amount = self._to_paisa(subtotal_after_discount * gst_percentage / 100)
            total_payable = subtotal_after_discount + gst_amount

        plan_before_credit: Decimal = billing_breakdown["plan_subtotal_before_credit"]
        upgrade_credit: Decimal = billing_breakdown["plan_upgrade_credit"]
        addons_discount: Decimal = billing_breakdown["addons_discount_amount"]

        addons_total_before_discount = addons_total + addons_discount

        subtotal_without_discount = max(
            plan_before_credit - upgrade_credit + addons_total_before_discount,
            Decimal("0"),
        )

        gst_on_full = Decimal("0")
        if DbConstants.IS_GST_ENABLED:
            gst_on_full = self._to_paisa(
                subtotal_without_discount * gst_percentage / 100
            )

        total_without_discount = subtotal_without_discount + gst_on_full
        total_savings = (
            billing_breakdown["plan_discount_amount"] + upgrade_credit + addons_discount
        )

        def _serialise_plan_details(pd: Optional[Dict]) -> Optional[Dict]:
            if pd is None:
                return None
            return {
                **{
                    k: v
                    for k, v in pd.items()
                    if k
                    not in (
                        "price_per_day",
                        "subtotal_before_credit",
                        "upgrade_credit",
                        "subtotal_after_credit",
                        "discount_amount",
                        "total_after_discount",
                        "discount_percentage",
                    )
                },
                "price_per_day": round(self._to_float(pd["price_per_day"]), 2),
                "subtotal_before_credit": round(
                    self._to_float(pd["subtotal_before_credit"]), 2
                ),
                "upgrade_credit": round(self._to_float(pd["upgrade_credit"]), 2),
                "subtotal_after_credit": round(
                    self._to_float(pd["subtotal_after_credit"]), 2
                ),
                "discount_percentage": float(pd["discount_percentage"]),
                "discount_amount": self._to_float(pd["discount_amount"]),
                "total_after_discount": round(
                    self._to_float(pd["total_after_discount"]), 2
                ),
            }

        def _serialise_addon_details(add_ons_details: Dict) -> Dict:
            out = {}
            for svc, svc_data in add_ons_details.items():
                items = []
                for item in svc_data.get("items", []):
                    items.append(
                        {
                            **{
                                k: v
                                for k, v in item.items()
                                if k
                                not in (
                                    "price_per_day_per_unit",
                                    "subtotal",
                                    "discount_percentage",
                                    "discount_amount",
                                    "total",
                                )
                            },
                            "price_per_day_per_unit": round(
                                self._to_float(item["price_per_day_per_unit"]), 2
                            ),
                            "subtotal": round(self._to_float(item["subtotal"]), 2),
                            "discount_percentage": float(item["discount_percentage"]),
                            "discount_amount": self._to_float(item["discount_amount"]),
                            "total": round(self._to_float(item["total"]), 2),
                        }
                    )
                out[svc] = {
                    "service_name": svc_data["service_name"],
                    "items": items,
                    "total_discount": self._to_float(svc_data["total_discount"]),
                    "service_total": self._to_float(svc_data["service_total"]),
                }
            return out

        # by _resolve_billing_days, but we document the invariant here.
        assert (
            billing_days > 0
        ), "billing_days must be > 0 — guarded in _resolve_billing_days"

        return {
            "duration_days": f"{billing_days} Days",
            "currency": plan.currency if plan else Currency.INDIA,
            "pricing_breakdown": {
                "plan": _serialise_plan_details(billing_breakdown.get("plan_details")),
                "add_ons": _serialise_addon_details(
                    billing_breakdown.get("add_ons_details", {})
                ),
            },
            "summary": {
                "plan_subtotal_before_credit": round(
                    self._to_float(billing_breakdown["plan_subtotal_before_credit"]), 2
                ),
                "plan_upgrade_credit": round(
                    self._to_float(billing_breakdown["plan_upgrade_credit"]), 2
                ),
                "plan_subtotal_after_credit": round(
                    self._to_float(billing_breakdown["plan_subtotal_after_credit"]), 2
                ),
                "plan_discount": round(
                    self._to_float(billing_breakdown["plan_discount_amount"]), 2
                ),
                "addons_discount": round(self._to_float(addons_discount), 2),
                "addons_total": round(self._to_float(addons_total), 2),
                "subtotal_after_discount": round(
                    self._to_float(subtotal_after_discount), 2
                ),
                "gst": {
                    "enabled": DbConstants.IS_GST_ENABLED,
                    "percentage": (
                        float(gst_percentage) if DbConstants.IS_GST_ENABLED else None
                    ),
                    "amount": self._to_float(gst_amount),
                },
                "total_payable": round(self._to_float(total_payable), 2),
                "total_payable_per_month": round(
                    self._to_float(total_payable / billing_days_d * days_per_month_d), 2
                ),
                "total_without_discount": round(
                    self._to_float(total_without_discount), 2
                ),
                "total_without_discount_per_month": round(
                    self._to_float(
                        total_without_discount / billing_days_d * days_per_month_d
                    ),
                    2,
                ),
                "total_savings": round(self._to_float(total_savings), 2),
            },
        }

    # =========================================================================
    # VALIDATION METHODS
    # =========================================================================

    async def _validate_partner(
        self, partner_id: int, partner_repo: PartnerRepository
    ) -> None:
        partner = await partner_repo.get_by_id(partner_id)
        if not partner:
            raise PartnerNotFoundError(
                "Partner with id {} does not exist.".format(partner_id)
            )
        if not partner.is_active:
            raise PartnerNotFoundError(
                "Partner with id {} is inactive.".format(partner_id)
            )

    async def _validate_plan(self, plan_id: int, plan_repo: PlanRepository) -> Plan:
        """Validate plan exists, is active, and not free trial."""
        plan = await plan_repo.get_plan_by_id(plan_id, active_only=True)
        if not plan:
            raise PlanInactiveError("Plan not found or inactive.")
        if plan.is_free_trial:
            raise InvalidUpgradeError(
                "Orders cannot be initiated for free trial plans."
            )
        return plan

    def _validate_authentication(
        self, order_data: OrderBillingDetailsRequest, partner_id: Optional[int]
    ):
        if partner_id is None and not order_data.plan_id:
            raise AuthenticationRequiredError(
                "plan_id is required for unauthenticated billing details request."
            )

    def _validate_addons_entitlement(
        self, add_ons: Dict[str, int], active_entitlements: Dict
    ):
        if not active_entitlements:
            raise NoActiveEntitlementError(
                "Cannot purchase add-ons without an active plan subscription."
            )

        add_ons_by_service = self._split_addons_by_service(add_ons)
        for service in add_ons_by_service.keys():
            if service not in active_entitlements:
                raise NoActiveEntitlementError(
                    f"You need an active subscription for service: {service} to buy its add-ons."
                )

    async def _check_hierarchy_downgrade(
        self, partner_id: int, new_plan: Plan, entitlement_repo: EntitlementRepository
    ):
        active_entitlements = await entitlement_repo.get_all_active_entitlements(
            partner_id
        )
        if not active_entitlements:
            return

        for ent in active_entitlements:
            if ent.order.plan and ent.order.plan.hierarchy > new_plan.hierarchy:
                raise InvalidUpgradeError(
                    f"You cannot downgrade to {new_plan.name}. "
                    f"Current plan: {ent.order.plan.name} (hierarchy: {ent.order.plan.hierarchy})"
                )

    async def _classify_manual_order(
        self,
        partner_id: int,
        new_plan: Plan,
    ) -> tuple[str, Optional[Order]]:
        """
        Classify a manual order based on the partner's latest SUCCESS order.

        Returns:
            (order_type, latest_order)
            order_type   — one of OrderType.FRESH | RENEWAL | UPGRADE | DOWNGRADE
            latest_order — most recent SUCCESS order, or None if no such order exists
        """
        latest_order: Optional[Order] = (
            await self.order_repo.get_latest_order_by_partner(partner_id)
        )

        if latest_order is None:
            self.logger.info(
                "Manual order classification | partner_id={} plan_id={} "
                "result=FRESH (no prior history)".format(partner_id, new_plan.id)
            )
            return OrderType.FRESH, None

        if not latest_order.plan:
            self.logger.warning(
                "Manual order classification | partner_id={} latest_order_id={} "
                "plan is None (deleted?) — treating as FRESH".format(
                    partner_id, latest_order.id
                )
            )
            return OrderType.FRESH, latest_order

        latest_hierarchy: int = latest_order.plan.hierarchy
        new_hierarchy: int = new_plan.hierarchy

        if new_plan.id == latest_order.plan.id:
            self.logger.info(
                "Manual order classification | partner_id={} plan_id={} "
                "result=RENEWAL (same plan)".format(partner_id, new_plan.id)
            )
            return OrderType.RENEWAL, latest_order

        if new_hierarchy > latest_hierarchy:
            self.logger.info(
                "Manual order classification | partner_id={} plan_id={} "
                "result=UPGRADE (new_hierarchy={} > latest={})".format(
                    partner_id, new_plan.id, new_hierarchy, latest_hierarchy
                )
            )
            return OrderType.UPGRADE, latest_order

        if new_hierarchy < latest_hierarchy:
            self.logger.info(
                "Manual order classification | partner_id={} plan_id={} "
                "result=DOWNGRADE (new_hierarchy={} < latest={})".format(
                    partner_id, new_plan.id, new_hierarchy, latest_hierarchy
                )
            )
            return OrderType.DOWNGRADE, latest_order

    async def _assert_no_active_entitlement(
        self, entitlement_repo: EntitlementRepository, partner_id: int
    ) -> None:
        active_entitlements = await entitlement_repo.get_all_active_entitlements(
            partner_id
        )
        if active_entitlements:
            raise InvalidUpgradeError(
                "Partner {} already has an active entitlement. "
                "Manual orders can only be created when there is no active subscription.".format(
                    partner_id
                )
            )

    async def _assert_duration_within_scheduled_window(
        self,
        entitlement_repo: EntitlementRepository,
        partner_id: int,
        requested_duration_days: int,
    ) -> None:
        """
        Guard against overlapping a scheduled (future-start) entitlement.

        If the partner has a scheduled entitlement that activates N days from now,
        the manual order's duration must be < N.
        """
        scheduled = await entitlement_repo.get_scheduled_entitlements(partner_id)
        if not scheduled:
            return

        now = datetime.now(timezone.utc)
        days_until_activation: int = min(
            max(
                (
                    datetime.fromtimestamp(ent.start_date / 1000, tz=timezone.utc) - now
                ).days,
                0,
            )
            for ent in scheduled
        )

        self.logger.info(
            "Scheduled entitlement guard | partner_id={} days_until_activation={} "
            "requested_duration={}".format(
                partner_id, days_until_activation, requested_duration_days
            )
        )

        if requested_duration_days >= days_until_activation:
            raise InvalidUpgradeError(
                "Requested duration of {} days would overlap a scheduled entitlement "
                "that activates in {} days. "
                "Duration must be strictly less than {} days.".format(
                    requested_duration_days,
                    days_until_activation,
                    days_until_activation,
                )
            )

    # =========================================================================
    # MANUAL ORDER PRIVATE HELPERS
    # =========================================================================

    def _resolve_manual_order_amount(
        self, custom_price_paisa: Optional[int], plan: Plan
    ) -> int:
        if custom_price_paisa is not None:
            self.logger.info(
                "Using sales-override price | custom_price_paisa={}".format(
                    custom_price_paisa
                )
            )
            return int(custom_price_paisa)
        return int(plan.price)

    async def _approve_and_provision_manual_order(
        self,
        order: Order,
        sales_user_id: int,
        entitlement_service: EntitlementService,
        entitlement_repo: Optional[EntitlementRepository] = None,
        grace_service: Optional[GraceService] = None,
    ) -> Order:
        """
        Mark a manual order as SUCCESS, provision its entitlement, then
        auto-settle any outstanding grace records per service.

        Grace settlement adjusts the new entitlement dates so that consumed
        grace days are deducted from end_date, and start_date is backdated
        to the first grace grant date for that service.
        """
        approved_order: Order = await self.order_repo.update_order(
            order_id=order.id,
            update_data={"status": PaymentStatusEnum.SUCCESS},
            user_id=sales_user_id,
        )
        await entitlement_service.upsert_entitlement(approved_order, sales_user_id)

        if (
            grace_service
            and entitlement_repo
            and approved_order.plan
            and approved_order.plan.modules
        ):
            await self._settle_grace_for_order(
                order=approved_order,
                user_id=sales_user_id,
                grace_service=grace_service,
                entitlement_repo=entitlement_repo,
            )

        return approved_order

    # =========================================================================
    # UTILITY METHODS
    # =========================================================================

    async def _get_active_entitlements(self, repo, partner_id: int) -> Dict:
        entitlements = await repo.get_all_active_entitlements(partner_id)
        self.logger.info(
            f"Active entitlements | partner_id={partner_id} count={len(entitlements)}"
        )
        return {ent.service_name: ent for ent in entitlements}

    async def _load_plan(self, order_data, plan_repo):
        if not order_data.plan_id:
            return None
        plan = await plan_repo.get_plan_by_id(order_data.plan_id, active_only=True)
        if not plan:
            raise PlanInactiveError(
                f"Plan with ID {order_data.plan_id} is not found or inactive"
            )
        return plan

    def _split_addons_by_service(self, add_ons: dict) -> Dict[str, dict]:
        if not add_ons:
            return {}

        service_lookup = {
            value: cls.__name__.lower()
            for cls in PlanCustomLimitKeys.__dict__.values()
            if isinstance(cls, type)
            for value in cls.__dict__.values()
        }

        grouped: Dict[str, dict] = {}
        for addon_key, qty in add_ons.items():
            service = service_lookup.get(addon_key)
            if not service:
                self.logger.warning(f"Unknown add-on key | addon_key={addon_key}")
                continue
            grouped.setdefault(service, {})[addon_key] = qty

        return grouped

    def _resolve_services(self, plan, add_ons_by_service: Dict) -> set:
        services = set(add_ons_by_service.keys())
        if plan:
            services |= set(
                PlanUtils.split_modules_by_service(plan.modules or {}).keys()
            )
        return services

    def _get_addon_price(self, addon_key: str) -> int:
        ADD_ON_PRICE_PER_DAY = {
            PlanCustomLimitKeys.Maglo.SERVICE_BOARDS: DbConstants.SERVICE_BOARD_ADD_ON_PRICE,
        }
        value = ADD_ON_PRICE_PER_DAY.get(addon_key, 0)
        try:
            return int(value)
        except (ValueError, TypeError):
            self.logger.error(
                f"Invalid add-on price | addon_key={addon_key} value={value}"
            )
            return 0

    def _resolve_order_type(self, order_type: str) -> str:
        valid = {
            OrderType.FRESH,
            OrderType.RENEWAL,
            OrderType.UPGRADE,
            OrderType.DOWNGRADE,
        }
        return order_type if order_type in valid else OrderType.FRESH

    def _log_billing_request(self, partner_id: Optional[int], order_data):
        self.logger.info(
            f"Calculating billing | partner_id={partner_id} "
            f"plan_id={order_data.plan_id} add_ons={order_data.add_ons}"
        )

    async def _create_gateway_order(
        self, order: Order, order_data, user_context: Dict
    ) -> Dict:
        """
        Initiate a payment gateway order.
        order_data can be an OrderBase instance or a validated dict —
        both expose amount and currency.
        """
        if isinstance(order_data, dict):
            amount = order_data["amount"]
            currency = order_data.get("currency") or order.currency
        else:
            amount = order_data.amount
            currency = order_data.currency

        initiate_payload = InitiateOrderRequest(
            partner_id=user_context.get("partner_id"),
            order_id=order.id,
            amount=amount,
            currency=currency,
            entity_name=EntityNameEnum.PLAN,
        )
        return await self.payment_service.create_order(initiate_payload, user_context)

    async def _handle_wallet_transaction(
        self, order: Order, user_id: int, partner_id: int, wallet_service: WalletService
    ) -> None:
        if not (order.plan_id and order.plan.plan_type == PlanType.WALLET):
            return

        self.logger.info(
            f"Wallet transaction | plan_type={PlanType.WALLET} partner_id={partner_id}"
        )

        await wallet_service.perform_transaction(
            current_user_id=user_id,
            partner_id=partner_id,
            transaction_type=TransactionType.CREDIT,
            amount=self._get_wallet_credit_amount(order),
            service_name=ServiceName.BABBLER,
            description=AMOUNT_ADDED_IN_WALLET,
            additional_info={"order_id": order.id},
            create_transaction=True,
            update_wallet=False,
        )

    async def _provision_on_payment_success(
        self,
        order: Order,
        user_id: int,
        entitlement_service: EntitlementService,
        wallet_service: WalletService,
        entitlement_repo: Optional[EntitlementRepository] = None,
        grace_service: Optional[GraceService] = None,
    ) -> None:
        """
        Shared post-payment provisioning used by validate_order and handle_webhook.
        Routes to wallet top-up or entitlement upsert based on plan type.

        After entitlement provisioning, outstanding grace records for each service
        in the order are automatically settled. If consumed days > 0, the new
        entitlement start_date is backdated to the first grace start and end_date
        is reduced accordingly.
        """
        if order.plan_id and order.plan.plan_type == PlanType.WALLET:
            self.logger.info(
                "Payment success → wallet top-up | plan_type={} partner_id={}".format(
                    PlanType.WALLET, order.partner_id
                )
            )
            await wallet_service.perform_transaction(
                current_user_id=user_id,
                partner_id=order.partner_id,
                transaction_type=TransactionType.CREDIT,
                amount=self._get_wallet_credit_amount(order),
                service_name=ServiceName.BABBLER,
                description=AMOUNT_ADDED_IN_WALLET,
                additional_info={"order_id": order.id},
                create_transaction=False,
                update_wallet=True,
            )
        else:
            await entitlement_service.upsert_entitlement(order, user_id)

            if grace_service and entitlement_repo and order.plan and order.plan.modules:
                await self._settle_grace_for_order(
                    order=order,
                    user_id=user_id,
                    grace_service=grace_service,
                    entitlement_repo=entitlement_repo,
                )

    async def _settle_grace_for_order(
        self,
        order: Order,
        user_id: int,
        grace_service: GraceService,
        entitlement_repo: EntitlementRepository,
    ) -> None:
        """
        Settle outstanding grace records for every service in the order's plan.

        For each service:
        1. Call grace_service.settle_grace — marks all ACTIVE/EXPIRED records
            as SETTLED and returns (first_grace_start_ms, total_consumed_days).
        2. If consumed days > 0, fetch the entitlement for this specific
            order + service and adjust its dates:
            - start_date = first_grace_start_ms
            - end_date   = first_grace_start_ms
                            + order.duration * GRACE_MS_PER_DAY
                            - total_consumed * GRACE_MS_PER_DAY
        """
        modules_by_service = PlanUtils.split_modules_by_service(order.plan.modules)
        now_ms: int = int(DateTimeUtil.get_current_time())

        for service_name in modules_by_service:
            try:
                first_start, total_consumed = await grace_service.settle_grace(
                    partner_id=order.partner_id,
                    service_name=service_name,
                    order_id=order.id,
                    payment_date_ms=now_ms,
                )

                if total_consumed > 0 and first_start is not None:
                    # Fetch the entitlement for THIS service specifically,
                    # not just the first entitlement found for the order.
                    ent = (
                        await entitlement_repo.get_entitlement_by_order_id_and_service(
                            order.id, service_name
                        )
                    )
                    if ent:
                        new_end = (
                            first_start
                            + (order.duration * GRACE_MS_PER_DAY)
                            - (total_consumed * GRACE_MS_PER_DAY)
                        )
                        await entitlement_repo.update_entitlement_dates(
                            entitlement_id=ent.id,
                            new_start_date=first_start,
                            new_end_date=new_end,
                            updated_by=user_id,
                        )
                        self.logger.info(
                            "Grace settled and entitlement adjusted | "
                            "order_id={} service={} consumed={} "
                            "new_start={} new_end={}".format(
                                order.id,
                                service_name,
                                total_consumed,
                                first_start,
                                new_end,
                            )
                        )
                    else:
                        self.logger.warning(
                            "Grace settled but no entitlement found for "
                            "order_id={} service={}".format(order.id, service_name)
                        )

            except Exception as e:
                # Grace settlement failure must never block payment success.
                # Entitlement is already provisioned — log and continue.
                self.logger.error(
                    "Grace settlement failed | order_id={} service={} error={}. "
                    "Entitlement provisioned with standard dates.".format(
                        order.id, service_name, e
                    )
                )

    def _build_order_response(
        self, order: Order, gateway_order: Optional[Dict]
    ) -> Dict:
        order_data = OrderResponse.model_validate(order).model_dump()
        order_data["plan_name"] = (
            order.plan.name if order.plan and order.plan_id else None
        )
        return {
            "order": order_data,
            "payment_gateway_order": gateway_order,
        }

    
    def __send_order_report_to_internal_partner(
            self, 
            attachments: List[dict]|dict, 
            timestamp:int, 
            email = Depends(Provide['email_service'])
        ):
        try:

            formatted_date = datetime.fromtimestamp(int(timestamp/1000)).strftime("%d-%B-%Y")
            email.send_email(
                to_emails=OrderEmailConstants.LIST_OF_RECIEVERS,
                subject=OrderEmailConstants.SUBJECT,
                body = {"report_period" : f"7 days {formatted_date}"},
                html_template='order_report.html',
                attachments = attachments
            )
            self.logger.info("email sent")
        except Exception as exp:
            self.logger.info(f"got an issue : {exp}")
            raise


    async def send_daily_order_report(
        self,
        wallet_service:WalletService = Depends(Provide['wallet_service'])
    ):
        try:
            # Calulating the time range : 1 Day before the current date
            # yesterday = datetime.now().date() - timedelta(days=1)
            # start_ts:int = int(datetime.combine(yesterday, datetime.min.time()).timestamp())*1000
            # end_ts:int = int(datetime.combine(yesterday, datetime.max.time()).timestamp())*1000
            # self.logger.info(f"Got the dates as {start_ts}, {end_ts}")

            today = int(datetime.timestamp(datetime.now()) * 1000)
            formatted_date = datetime.fromtimestamp(int(today/1000)).strftime('%d-%B-%Y')



            # Getting the CREDIT transactions form the Database for that Date
            list_of_mannual_orders:list[dict] = await self.order_repo.get_report_for_created_orders(
                current_ts = today, is_manually_created=True
            )
            self.logger.info(f"Got {len(list_of_mannual_orders)} mannual orders")
            csv_file_manual = await wallet_service.create_tranaction_csv(list_of_mannual_orders)
            self.logger.info("Got the CSV file")


            list_of_custom_orders:list[dict] = await self.order_repo.get_report_for_created_orders(
                current_ts = today, is_manually_created=False
            )
            self.logger.info(f"Got {len(list_of_custom_orders)} custom orders")
            csv_file_custom = await wallet_service.create_tranaction_csv(list_of_custom_orders)
            self.logger.info("Got the CSV file")
            
            # send an email and add transaction CSV as attachment
            attachments = []
            if csv_file_manual:
                attachments.append({
                    "filename" : f"Order_manual_{formatted_date}.csv", "content" : csv_file_manual
                })
            if csv_file_custom:
                attachments.append({
                    "filename" : f"Order_custom_{formatted_date}.csv", "content" : csv_file_custom
                })
            if not attachments:
                self.logger.info(
                    f"Could not find any transactions for {formatted_date}"
                )
                return
            
            self.__send_order_report_to_internal_partner(
                attachments=attachments,
                timestamp=today
            )
            
        except Exception as exp:
            self.logger.info(f"Got an excpetion while sending report mail : {exp}")
            raise
        ...

    async def send_approaching_renewal_report(
        self, 
        wallet_service:WalletService = Depends(Provide['wallet_service'])
    ):
        try:
            today = int(datetime.timestamp(datetime.now()) * 1000)
            formatted_date = datetime.fromtimestamp(int(today/1000)).strftime('%d-%B-%Y')

            list_of_orders_approaching_renewal = await self.order_repo.get_approaching_renewal_report(
                current_ts=today
            )

            attachments = []

            if list_of_orders_approaching_renewal:
                renewal_order_csv = await wallet_service.create_tranaction_csv(list_of_orders_approaching_renewal)
                attachments.append(
                    {
                        "filename" : f"approaching_renewal_report_{formatted_date}.csv",
                        "content" : renewal_order_csv
                    }
                )
            else:
                self.logger.info(
                    f"Could not find any orders to renew for {formatted_date}"
                )
                return
            self.__send_order_report_to_internal_partner(
                attachments=attachments,
                timestamp=today
            )
            
        except Exception as exp:
            self.logger.info(f"Got an excpetion while sending report mail : {exp}")
            raise

    
    async def send_expiry_overdue_order_report(
        self, 
        wallet_service:WalletService = Depends(Provide['wallet_service'])
    ):
        try:
            today = int(datetime.timestamp(datetime.now()) * 1000)
            formatted_date = datetime.fromtimestamp(int(today/1000)).strftime('%d-%B-%Y')

            list_of_expired_overdue_orders = await self.order_repo.get_expired_and_overdue_report(
                current_ts=today
            )

            attachments = []

            if list_of_expired_overdue_orders:
                expired_or_overdue_order_csv = await wallet_service.create_tranaction_csv(list_of_expired_overdue_orders)
                attachments.append(
                    {
                        "filename" : f"overdue_or_expiring_order_report_{formatted_date}.csv",
                        "content" : expired_or_overdue_order_csv
                    }
                )

            else:
                self.logger.info(
                    f"Could not find any overdue or expired orders for {formatted_date}"
                )
                return
            self.__send_order_report_to_internal_partner(
                attachments=attachments,
                timestamp=today
            )
            
        except Exception as exp:
            self.logger.info(f"Got an excpetion while sending report mail : {exp}")
            raise

    async def calculate_amount(
        self,
        amount: float,
        currency: str,
    ) -> Dict:
        """
        Calculate the final payable amount for a wallet top-up.

        Flow (per business rule):
        1. base_amount        = amount
        2. convenience_fee    = base_amount * WALLET_CONVENIENCE_FEE_PERCENTAGE / 100
                                (0.0 if IS_WALLET_CONVENIENCE_FEE_ENABLED is False)
        3. amount_after_fee   = base_amount + convenience_fee
        4. gst                = amount_after_fee * WALLET_GST_PERCENTAGE / 100
                                (0.0 if IS_WALLET_GST_ENABLED is False)
        5. final_amount       = amount_after_fee + gst, rounded to whole number

        Convenience fee is applied first; GST is calculated on (amount + fee).
        Both toggles are independent — either, both, or neither may be enabled.

        Rounding: only final_amount is rounded to a whole number (no decimals).
        Every other amount (base_amount, convenience_fee, subtotal, gst) is
        returned as the exact computed Decimal value, decimals included.
        """
        try:
            self.logger.info(
                "Calculating wallet amount | amount={} currency={}".format(
                    amount, currency
                )
            )

            base_amount = Decimal(str(amount))

            convenience_fee_percentage: Decimal = (
                Decimal(str(DbConstants.WALLET_CONVENIENCE_FEE_PERCENTAGE or 0))
                if DbConstants.IS_WALLET_CONVENIENCE_FEE_ENABLED
                else Decimal("0")
            )
            # exact — no paisa rounding here anymore
            convenience_fee: Decimal = base_amount * convenience_fee_percentage / 100
            amount_after_fee: Decimal = base_amount + convenience_fee

            gst_percentage: Decimal = (
                Decimal(str(DbConstants.WALLET_GST_PERCENTAGE or 0))
                if DbConstants.IS_WALLET_GST_ENABLED
                else Decimal("0")
            )
            # exact — no paisa rounding here anymore
            gst: Decimal = amount_after_fee * gst_percentage / 100
            final_amount: Decimal = amount_after_fee + gst

            response = {
                "base_amount": self._to_float(base_amount),
                "currency": currency,
                "is_convinience_fee_enabled": DbConstants.IS_WALLET_CONVENIENCE_FEE_ENABLED,
                "is_gst_enabled": DbConstants.IS_WALLET_GST_ENABLED,
                "convinience_fee_percentage": self._to_float(convenience_fee_percentage),
                "convinience_fee": self._to_float(convenience_fee),
                "subtotal": self._to_float(amount_after_fee),
                "gst_percentage": self._to_float(gst_percentage),
                "gst": self._to_float(gst),
                # only this one rounded to a whole number
                "final_amount": self._to_float(self._to_paisa(final_amount)),
            }

            self.logger.info(
                "Wallet amount calculated | base={} fee={} gst={} final={}".format(
                    response["base_amount"],
                    response["convinience_fee"],
                    response["gst"],
                    response["final_amount"],
                )
            )

            return response

        except Exception as e:
            self.logger.error(
                "Error in calculate_wallet_amount | amount={} currency={} error={}".format(
                    amount, currency, e
                )
            )
            raise

    def _get_wallet_credit_amount(self, order: Order) -> float:
        base = (
            order.additional_info.get("wallet_base_amount")
            if order.additional_info
            else None
        )
        return base / 100 if base is not None else order.amount / 100
