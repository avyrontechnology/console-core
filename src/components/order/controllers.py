from uuid import UUID
import json
from typing import Any, List, Optional

from dependency_injector.wiring import Provide, inject
from fastapi import APIRouter, Depends, Query, Request, status

from src.components.auth.constant import RoleDictKeys, TokenKeys
from src.components.auth.repositories import AuthRepository
from src.components.common.response import (
    BadRequestResponse,
    ForbiddenResponse,
    InternalServerErrorResponse,
    NotFoundResponse,
    ResourceCreatedResponse,
    SuccessResponse,
    ValidationErrorResponse,
)
from src.components.wallet.enum import ALL_CURRENCIES
from src.components.order.constants import (

    MAX_PARTNER_IDS_PER_REQUEST,
    OrderSource,
    OrderType,
)
from src.components.order.errors import (
    AuthenticationRequiredError,
    DurationValidationError,
    InvalidUpgradeError,
    MissingPlanIdError,
    NoActiveEntitlementError,
    NoBillingForWalletError,
    OrderAlreadyProcessedError,
    OrderNotFoundError,
    PlanInactiveError,
    SelfServeManualOrderError,
)
from src.components.common.constants import FieldType
from src.components.common.utility import SchemaValidator
from src.components.order.schema import (
    ManualOrderCreateRequest,
    OrderBase,
    OrderBillingDetailsRequest,
    OrderHistoryPaginatedResponse,
    OrderValidateRequest,
)
from src.components.order.services import OrderService
from src.components.partner.error import InvalidPartnerIdsError, PartnerNotFoundError
from src.components.payment.enum import PaymentStatusEnum
from src.components.payment.errors import PaymentError
from src.components.rbac.permission_injector import permission_check
from src.core.container import Container
from src.loggers.console_service_logger import ConsoleServiceLogger


class OrderController:
    order_router = APIRouter(prefix="/orders", tags=["Orders"])

    # =========================================================================
    # SELF-SERVE: INITIATE ORDER
    # =========================================================================

    @order_router.post(
        "/initiate", response_model=dict, status_code=status.HTTP_201_CREATED
    )
    @permission_check("console:initiate_order")
    @inject
    async def initiate_order(
        request: Request,
        order_data: OrderBase,
        order_service: OrderService = Depends(Provide[Container.order_service]),
        logger: ConsoleServiceLogger = Depends(
            Provide[Container.console_service_logger]
        ),
    ):
        try:
            current_user: dict = request.state.user
            logger.info(
                "Controller: initiate_order | partner_id={}".format(
                    current_user.get(TokenKeys.PARTNER_ID)
                )
            )

            result = await order_service.initiate_order(order_data, current_user)

            logger.info(
                "Controller: initiate_order success | order_id={}".format(
                    result["order"]["id"]
                )
            )
            return ResourceCreatedResponse(
                data=result, message="Order created and payment initiated"
            )

        except DurationValidationError as exc:
            logger.error("Controller: initiate_order | duration error | {}".format(exc))
            return BadRequestResponse(detail=str(exc))

        except InvalidUpgradeError as exc:
            logger.warning(
                "Controller: initiate_order | invalid upgrade | {}".format(exc)
            )
            return BadRequestResponse(detail=str(exc))

        except PlanInactiveError as exc:
            logger.error("Controller: initiate_order | plan inactive | {}".format(exc))
            return BadRequestResponse(detail=str(exc))

        except PartnerNotFoundError as exc:
            logger.error(
                "Controller: initiate_order | partner not found | {}".format(exc)
            )
            return NotFoundResponse(detail=str(exc))
        except PaymentError as exc:
            logger.error("Controller: initiate_order | payment error | {}".format(exc))
            return InternalServerErrorResponse(detail=str(exc))

        except NoActiveEntitlementError as exc:
            logger.warning(
                "Controller: initiate_order | no active entitlement | {}".format(exc)
            )
            return BadRequestResponse(detail=str(exc))

        except Exception as exc:
            logger.error(
                "Controller: initiate_order | unexpected error | {}".format(repr(exc))
            )
            return InternalServerErrorResponse(detail="Failed to create order")

    # =========================================================================
    # SELF-SERVE: VALIDATE ORDER
    # =========================================================================

    @order_router.post("/validate", response_model=dict)
    @permission_check("console:validate_order")
    @inject
    async def validate_order(
        request: Request,
        payload: OrderValidateRequest,
        order_service: OrderService = Depends(Provide[Container.order_service]),
        logger: ConsoleServiceLogger = Depends(
            Provide[Container.console_service_logger]
        ),
    ):
        try:
            current_user: dict = request.state.user
            logger.info(
                "Controller: validate_order | order_id={}".format(payload.order_id)
            )

            result = await order_service.validate_order(
                payload.order_id, payload.payment_id, payload.signature, current_user
            )

            logger.info(
                "Controller: validate_order success | status={}".format(
                    result["status"]
                )
            )
            return SuccessResponse(data=result, message="Order validated successfully")

        except OrderNotFoundError as exc:
            logger.error(
                "Controller: validate_order | order not found | {}".format(exc)
            )
            return NotFoundResponse(detail=str(exc))

        except OrderAlreadyProcessedError as exc:
            logger.error(
                "Controller: validate_order | already processed | {}".format(exc)
            )
            return BadRequestResponse(detail=str(exc))

        except Exception as exc:
            logger.error(
                "Controller: validate_order | unexpected error | {}".format(repr(exc))
            )
            return InternalServerErrorResponse(detail="Failed to validate order")

    # =========================================================================
    # MANUAL ORDER: CREATE
    # =========================================================================

    @order_router.post(
        "/manual",
        response_model=dict,
        status_code=status.HTTP_201_CREATED,
        summary="Create a manual order",
        description=(
            "Creates a manual order on behalf of a partner. "
            "Duration is derived from the plan automatically. "
            "Order type (FRESH / RENEWAL / UPGRADE) is classified from order history. "
            "Partner must have no active entitlement. "
            "payment_method=GATEWAY: initiates gateway SDK, entitlement provisioned after payment. "
            "payment_method=DIRECT: no gateway, entitlement provisioned immediately."
        ),
    )
    @permission_check("console:create_manual_order")
    @inject
    async def create_manual_order(
        request: Request,
        payload: ManualOrderCreateRequest,
        order_service: OrderService = Depends(Provide[Container.order_service]),
        logger: ConsoleServiceLogger = Depends(
            Provide[Container.console_service_logger]
        ),
    ):
        try:
            current_user: dict = request.state.user

            validated, error = payload.validate_payload()
            if error:
                logger.warning(
                    "Controller: create_manual_order | validation error | {}".format(
                        error
                    )
                )
                return BadRequestResponse(detail=error)

            # ── Authorization check ───────────────────────────────────────────
            # A user may only create a manual order for their own partner_id,
            # OR they must belong to an internal partner (sales team).
            # Non-internal users attempting to order for a different partner_id
            # are rejected with 403.
            request_partner_id: UUID = current_user.get(TokenKeys.PARTNER_ID)
            payload_partner_id: UUID = validated.get("partner_id")
            is_internal: bool = current_user.get("is_internal", False)

            if request_partner_id != payload_partner_id and not is_internal:
                logger.warning(
                    "Controller: create_manual_order | forbidden | "
                    "request_partner_id={} payload_partner_id={} is_internal={}".format(
                        request_partner_id, payload_partner_id, is_internal
                    )
                )
                return ForbiddenResponse(
                    detail="You do not have permission to create a manual order for partner {}.".format(
                        payload_partner_id
                    )
                )

            logger.info(
                "Controller: create_manual_order | partner_id={} sales_user={} is_internal={}".format(
                    payload_partner_id, current_user.get(TokenKeys.USER_ID), is_internal
                )
            )

            result = await order_service.create_manual_order(validated, current_user)

            logger.info(
                "Controller: create_manual_order success | order_id={} payment_method={}".format(
                    result["order"]["id"], payload.payment_method
                )
            )
            message = (
                "Manual order created — payment gateway initiated"
                if result.get("payment_gateway_order")
                else "Manual order created and entitlement provisioned"
            )
            return ResourceCreatedResponse(data=result, message=message)

        except PlanInactiveError as exc:
            logger.error(
                "Controller: create_manual_order | plan inactive | {}".format(exc)
            )
            return BadRequestResponse(detail=str(exc))

        except SelfServeManualOrderError as exc:
            logger.warning(
                "Controller: create_manual_order | self-serve partner manual order attempt | {}".format(
                    exc
                )
            )
            return BadRequestResponse(detail=str(exc))

        except InvalidUpgradeError as exc:
            logger.warning(
                "Controller: create_manual_order | invalid upgrade | {}".format(exc)
            )
            return BadRequestResponse(detail=str(exc))

        except PaymentError as exc:
            logger.error(
                "Controller: create_manual_order | payment error | {}".format(exc)
            )
            return InternalServerErrorResponse(detail=str(exc))

        except PartnerNotFoundError as exc:
            logger.error(
                "Controller: create_manual_order | partner not found or inactive | {}".format(
                    exc
                )
            )
            return NotFoundResponse(detail=str(exc))

        except Exception as exc:
            logger.error(
                "Controller: create_manual_order | unexpected error | {}".format(
                    repr(exc)
                )
            )
            return InternalServerErrorResponse(detail="Failed to create manual order")

    # =========================================================================
    # ORDER HISTORY
    # =========================================================================

    @order_router.get("/history")
    @permission_check("console:get_order_history")
    @inject
    async def get_order_history(
        request: Request,
        partner_ids: Optional[str] = Query(None),
        limit: int = Query(10, ge=1, le=500),
        offset: int = Query(1, ge=1, le=100),
        source: Optional[str] = Query(None),
        status: Optional[str] = Query(None),
        order_created_at_from: Optional[int] = Query(None),
        order_created_at_to: Optional[int] = Query(None),
        entitlement_start_date_from: Optional[int] = Query(None),
        entitlement_start_date_to: Optional[int] = Query(None),
        entitlement_end_date_from: Optional[int] = Query(None),
        entitlement_end_date_to: Optional[int] = Query(None),
        is_manually_created: Optional[bool] = Query(
            None,
            description=(
                "Filter by order origin. "
                "true = manually created by sales team, "
                "false = self-serve via payment gateway, "
                "omit = all orders."
            ),
        ),
        order_type: Optional[str] = Query(
            None,
            description=(
                "Filter by order_type with operator prefix. Examples:\n"
                "  order_type=FRESH              → eq  (exact match)\n"
                "  order_type=ne:FRESH           → !=  (not equal)\n"
                "  order_type=in:FRESH,RENEWAL   → IN  (any of)\n"
                "  order_type=not_in:UPGRADE,DOWNGRADE → NOT IN\n"
                "Omit to return all order types."
            ),
        ),
        order_service: OrderService = Depends(Provide[Container.order_service]),
        auth_repo: AuthRepository = Depends(Provide[Container.auth_repository]),
        logger: ConsoleServiceLogger = Depends(
            Provide[Container.console_service_logger]
        ),
    ):
        """
        Return paginated order history with optional filters.

        order_type filter values:
                    FRESH   — first manual order for this plan tier
          RENEWAL — same plan (or same hierarchy) re-ordered
          UPGRADE — manual order moving partner to higher-tier plan
          (no filter)    — all orders
        """
        try:
            current_user: dict = request.state.user
            current_user_id: UUID = current_user.get(TokenKeys.USER_ID)

            user_data: dict = await auth_repo.get_role_by_user_id(current_user_id)
            user_hierarchy: int = user_data.get(RoleDictKeys.HIERARCHY)
            is_superadmin: bool = user_hierarchy <= 0

            parsed_partner_ids: Optional[List[UUID]] = _parse_partner_ids(partner_ids)

            if parsed_partner_ids is not None:
                if len(parsed_partner_ids) > MAX_PARTNER_IDS_PER_REQUEST:
                    return BadRequestResponse(
                        detail="Maximum {} partner_ids allowed per request".format(
                            MAX_PARTNER_IDS_PER_REQUEST
                        )
                    )
                if not is_superadmin:
                    return ForbiddenResponse(
                        detail="Only internal roles can fetch orders by partner_ids."
                    )

            if not is_superadmin:
                parsed_partner_ids = [current_user.get(TokenKeys.PARTNER_ID)]

            date_range_error = _validate_date_ranges(
                entitlement_start_date_from,
                entitlement_start_date_to,
                entitlement_end_date_from,
                entitlement_end_date_to,
                order_created_at_from,
                order_created_at_to,
            )
            if date_range_error:
                return BadRequestResponse(detail=date_range_error)

            if source is not None:
                source_error = _validate_enum_value(source, OrderSource, "source")
                if source_error:
                    return BadRequestResponse(detail=source_error)

            if status is not None:
                status_error = _validate_enum_value(status, PaymentStatusEnum, "status")
                if status_error:
                    return BadRequestResponse(detail=status_error)

            parsed_order_type_filter = None
            if order_type is not None:
                parsed_order_type_filter, order_type_error = _parse_order_type_filter(
                    order_type, OrderType
                )
                if order_type_error:
                    return BadRequestResponse(detail=order_type_error)

            filters = {
                "partner_ids": parsed_partner_ids,
                "source": source,
                "status": status,
                "order_created_at_from": order_created_at_from,
                "order_created_at_to": order_created_at_to,
                "entitlement_start_date_from": entitlement_start_date_from,
                "entitlement_start_date_to": entitlement_start_date_to,
                "entitlement_end_date_from": entitlement_end_date_from,
                "entitlement_end_date_to": entitlement_end_date_to,
                "is_manually_created": is_manually_created,
                "order_type": parsed_order_type_filter,
            }

            logger.info(
                "Controller: get_order_history | partner_ids={} active_filters={}".format(
                    parsed_partner_ids,
                    {k: v for k, v in filters.items() if v is not None},
                )
            )

            orders, total_count = await order_service.get_order_history(
                filters, limit, offset
            )

            logger.info(
                "Controller: get_order_history success | count={} partner_ids={}".format(
                    len(orders), parsed_partner_ids
                )
            )

            response = OrderHistoryPaginatedResponse(
                total_count=total_count, limit=limit, offset=offset, data=orders
            )
            return SuccessResponse(data=response)

        except InvalidPartnerIdsError as exc:
            logger.warning(
                "Controller: get_order_history | invalid partner ids | {}".format(exc)
            )
            return BadRequestResponse(detail=str(exc))

        except AuthenticationRequiredError as exc:
            logger.error("Controller: get_order_history | auth error | {}".format(exc))
            return ForbiddenResponse(detail=str(exc))

        except OrderNotFoundError as exc:
            logger.error(
                "Controller: get_order_history | order not found | {}".format(exc)
            )
            return NotFoundResponse(detail=str(exc))

        except Exception as exc:
            logger.error(
                "Controller: get_order_history | unexpected error | {}".format(
                    repr(exc)
                )
            )
            return InternalServerErrorResponse(detail="Failed to fetch order history")

    # =========================================================================
    # BILLING DETAILS
    # =========================================================================

    @order_router.post("/billing-details")
    @permission_check("console:get_billing_details")
    @inject
    async def get_billing_details(
        request: Request,
        order_data: OrderBillingDetailsRequest,
        order_service: OrderService = Depends(Provide[Container.order_service]),
        logger: ConsoleServiceLogger = Depends(
            Provide[Container.console_service_logger]
        ),
    ):
        try:
            partner_id: Optional[UUID] = None

            if hasattr(request.state, "user") and request.state.user:
                current_user: dict = request.state.user
                partner_id = current_user.get(TokenKeys.PARTNER_ID)
                logger.info(
                    "Controller: get_billing_details | authenticated | partner_id={}".format(
                        partner_id
                    )
                )
            else:
                logger.info("Controller: get_billing_details | unauthenticated request")

            result: dict = await order_service.get_billing_details(
                order_data, partner_id
            )

            return SuccessResponse(result)

        except PlanInactiveError as exc:
            logger.warning(
                "Controller: get_billing_details | plan inactive | {}".format(exc)
            )
            return NotFoundResponse(detail=str(exc))

        except NoActiveEntitlementError as exc:
            logger.warning(
                "Controller: get_billing_details | no active entitlement | {}".format(
                    exc
                )
            )
            return BadRequestResponse(detail=str(exc))

        except NoBillingForWalletError as exc:
            logger.warning(
                "Controller: get_billing_details | wallet plan billing | {}".format(exc)
            )
            return BadRequestResponse(detail=str(exc))

        except InvalidUpgradeError as exc:
            logger.warning(
                "Controller: get_billing_details | invalid upgrade | {}".format(exc)
            )
            return BadRequestResponse(detail=str(exc))

        except MissingPlanIdError as exc:
            logger.warning(
                "Controller: get_billing_details | missing plan id | {}".format(exc)
            )
            return ValidationErrorResponse(detail=str(exc))

        except AuthenticationRequiredError as exc:
            logger.warning(
                "Controller: get_billing_details | auth required | {}".format(exc)
            )
            return BadRequestResponse(detail=str(exc))

        except ValueError as exc:
            logger.warning(
                "Controller: get_billing_details | validation error | {}".format(exc)
            )
            return ValidationErrorResponse(detail=str(exc))

        except Exception as exc:
            logger.error(
                "Controller: get_billing_details | unexpected error | {}".format(
                    repr(exc)
                )
            )
            return InternalServerErrorResponse(
                detail="Failed to fetch order billing details. Please try again later."
            )

    @order_router.get("/calculate-amount", response_model=dict)
    @inject
    async def calculate_amount(
        request: Request,
        amount: Any = Query(None),
        currency: Any = Query(None),
        order_service: OrderService = Depends(Provide[Container.order_service]),
        logger: ConsoleServiceLogger = Depends(
            Provide[Container.console_service_logger]
        ),
    ):
        try:
            logger.info(
                "Controller: calculate_amount | amount={} currency={}".format(
                    amount, currency
                )
            )

            validated, error = SchemaValidator.validate(
                {
                    "amount": {
                        "value": amount,
                        "required": True,
                        "type": FieldType.INTEGER,
                        "min": 100,
                        "max": 50000000,
                    },
                    "currency": {
                        "value": currency,
                        "required": True,
                        "type": FieldType.STRING,
                        "values": ALL_CURRENCIES,
                    },
                }
            )
            if error:
                return BadRequestResponse(detail=error)

            result = await order_service.calculate_amount(validated.get("amount"), validated.get("currency"))

            logger.info(
                "Controller: calculate_amount success | final_amount={}".format(
                    result["final_amount"]
                )
            )
            return SuccessResponse(
                data=result, message="Order amount calculated successfully"
            )

        except Exception as exc:
            logger.error(
                "Controller: calculate_amount | unexpected error | {}".format(
                    repr(exc)
                )
            )
            return InternalServerErrorResponse(
                detail="Failed to calculate order amount."
            )


# =============================================================================
# MODULE-LEVEL HELPERS
# Private helpers for the controller — no business logic, purely request parsing
# and input validation. Kept outside the class to stay lightweight and testable.
# =============================================================================


def _parse_partner_ids(raw_value: Optional[str]) -> Optional[List[UUID]]:
    """
    Parse the partner_ids query param into a list of UUIDs.

    Accepted formats:
      "<uuid>"                  → [UUID(...)]
      '["<uuid>", "<uuid>"]'    → [UUID(...), UUID(...)]

    Returns None if raw_value is None (no filter applied).
    Raises ValueError for unrecognised formats.
    """
    if raw_value is None:
        return None

    raw = raw_value.strip()

    try:
        if not raw.startswith("["):
            return [UUID(raw)]

        parsed = json.loads(raw)
        if not isinstance(parsed, list) or not parsed:
            raise ValueError("List must contain UUID strings only")
        return [UUID(str(item)) for item in parsed]

    except (ValueError, AttributeError, TypeError, json.JSONDecodeError) as exc:
        raise ValueError(
            "partner_ids must be a single UUID "
            'or a JSON list of UUIDs (e.g. ["<uuid>","<uuid>"]). '
            "Error: {}".format(exc)
        ) from exc


def _validate_date_ranges(
    ent_start_from: Optional[int],
    ent_start_to: Optional[int],
    ent_end_from: Optional[int],
    ent_end_to: Optional[int],
    order_from: Optional[int],
    order_to: Optional[int],
) -> Optional[str]:
    """
    Validate that every supplied date-range pair has from <= to.
    Returns an error message string if any pair is invalid, otherwise None.
    """
    checks = [
        ("entitlement_start_date_from", ent_start_from, ent_start_to),
        ("entitlement_end_date_from", ent_end_from, ent_end_to),
        ("order_created_at_from", order_from, order_to),
    ]

    for field_name, value_from, value_to in checks:
        if value_from and value_to and value_from > value_to:
            return "{} cannot be greater than its corresponding end date".format(
                field_name
            )

    return None


def _validate_enum_value(value: str, enum_class, field_name: str) -> Optional[str]:
    """
    Validate that value exists among the public attributes of enum_class.
    Returns an error message string if invalid, otherwise None.
    """
    allowed = {v for k, v in vars(enum_class).items() if not k.startswith("__")}
    if value not in allowed:
        return "Invalid {} '{}'. Allowed values: {}".format(
            field_name, value, sorted(allowed)
        )
    return None


def _parse_order_type_filter(raw: str, enum_class) -> tuple:
    """
    Parse the order_type query param into a structured filter dict consumed by
    OrderRepository._build_order_conditions.

    Supported formats:
      FRESH                       → {"op": "eq",     "values": ["FRESH"]}
      ne:FRESH                    → {"op": "ne",     "values": ["FRESH"]}
      in:FRESH,RENEWAL            → {"op": "in",     "values": ["FRESH", "RENEWAL"]}
      not_in:UPGRADE,DOWNGRADE    → {"op": "not_in", "values": ["UPGRADE", "DOWNGRADE"]}

    Returns (filter_dict, None) on success, (None, error_str) on failure.
    """
    _ALLOWED_OPS = {"eq", "ne", "in", "not_in"}
    allowed_values = {v for k, v in vars(enum_class).items() if not k.startswith("__")}

    if ":" in raw:
        op, _, values_str = raw.partition(":")
        op = op.strip().lower()
    else:
        op = "eq"
        values_str = raw

    if op not in _ALLOWED_OPS:
        return None, (
            "Invalid order_type operator '{}'. "
            "Supported: eq, ne, in, not_in. "
            "Examples: order_type=FRESH, order_type=ne:FRESH, "
            "order_type=in:FRESH,RENEWAL".format(op)
        )

    values = [v.strip().upper() for v in values_str.split(",") if v.strip()]
    if not values:
        return None, "order_type filter has no values after the operator prefix."

    invalid = [v for v in values if v not in allowed_values]
    if invalid:
        return None, (
            "Invalid order_type value(s): {}. Allowed: {}".format(
                invalid, sorted(allowed_values)
            )
        )

    if op in ("eq", "ne") and len(values) > 1:
        return None, (
            "Operator '{}' accepts only a single value. "
            "Use 'in' or 'not_in' for multiple values.".format(op)
        )

    return {"op": op, "values": values}, None
