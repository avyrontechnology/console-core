from typing import Any, Dict, List

from dependency_injector.wiring import Provide, inject
from fastapi import APIRouter, Depends, Query, Request

from src.components.auth.constant import TokenKeys
from src.components.common.response import (
    BadRequestResponse,
    InternalServerErrorResponse,
    SuccessResponse,
    UnauthorizedResponse,
)
from src.components.order.errors import OrderNotFoundError
from src.components.order.services import OrderService
from src.components.payment.errors import WebhookSignatureError
from src.components.payment.schema import PaymentHistoryPaginatedResponse
from src.components.payment.services import PaymentService
from src.components.rbac.permission_dependency import PermissionDependency
from src.components.rbac.permission_injector import permission_check
from src.core.container import Container
from src.loggers.console_service_logger import ConsoleServiceLogger


class PaymentController:
    """Controller handling all payment-related payment routes."""

    payment_router = APIRouter(prefix="/payment", tags=["Payment"])

    @payment_router.get("/history")
    @permission_check(PermissionDependency)
    @inject
    async def get_payment_history(
        request: Request,
        limit: int = Query(..., ge=1, le=100),
        offset: int = Query(..., ge=1),
        payment_service: PaymentService = Depends(Provide[Container.payment_service]),
        logger: ConsoleServiceLogger = Depends(
            Provide[Container.console_service_logger]
        ),
    ):
        """
        Fetch payment history for a partner.

        Args:
            request (Request): FastAPI request with authenticated user.
            payment_service (PaymentService): Payment service DI.
            logger (ConsoleServiceLogger): Logger instance DI.
        """
        try:
            partner_id: int = request.state.user.get(TokenKeys.PARTNER_ID)

            logger.info("Fetching payment history for partner_id={}".format(partner_id))

            payments, total_count = (
                await payment_service.get_payment_history_by_partner(
                    partner_id, limit, offset
                )
            )

            payments_dict: List[Dict[str, Any]] = [
                {
                    column.name: getattr(payment, column.name)
                    for column in payment.__table__.columns
                }
                for payment in payments
            ]

            response = PaymentHistoryPaginatedResponse(
                total_count=total_count, limit=limit, offset=offset, data=payments_dict
            )

            return SuccessResponse(
                response, message="Payment history fetched successfully"
            )

        except Exception as ex:
            logger.error("Error fetching payment history: {}".format(str(ex)))
            return InternalServerErrorResponse(str(ex))

    @payment_router.post("/webhook")
    @inject
    async def payment_webhook(
        request: Request,
        order_service: OrderService = Depends(Provide[Container.order_service]),
        logger: ConsoleServiceLogger = Depends(
            Provide[Container.console_service_logger]
        ),
    ):
        """
        Handle payment gateway webhook.

        Args:
            request (Request): Incoming webhook request containing JSON payload.
            order_service (OrderService): Order service DI used for payment handling.
            logger (ConsoleServiceLogger): Logger instance DI.
        """
        try:
            raw_body = await request.body()
            signature: str = request.headers.get("X-Razorpay-Signature")

            if not signature:
                logger.error("Webhook missing Signature header")
                return BadRequestResponse(detail="Missing Signature header")

            payload: Dict[str, Any] = await request.json()
            logger.info("Received payment webhook payload: {}".format(payload))

            result: Dict[str, Any] = await order_service.handle_webhook(
                payload=payload, raw_body=raw_body, signature=signature
            )

            logger.info(
                "Webhook processed successfully for order_id={}".format(
                    result.get("order_id")
                )
            )

            return SuccessResponse(result, message="Webhook processed successfully")

        except WebhookSignatureError as wse:
            logger.error("Webhook signature verification failed: {}".format(str(wse)))
            return UnauthorizedResponse(detail=str(wse))
        except OrderNotFoundError as onfe:
            # Defense in depth: OrderService.handle_webhook already
            # acknowledges an unrecognized order internally and shouldn't
            # raise this, but if any future code path does, treat it the
            # same way here rather than falling through to the generic
            # 500 -- a validly-signed webhook for an order we don't have
            # locally is expected (e.g. one created outside our checkout
            # flow), not a system failure worth alerting the team on.
            logger.warning(
                "Webhook referenced an order we have no record of: {}".format(
                    str(onfe)
                )
            )
            return SuccessResponse(
                {"acknowledged": True}, message="Webhook acknowledged"
            )
        except Exception as ex:
            logger.error("Error processing payment webhook: {}".format(str(ex)))
            return InternalServerErrorResponse(str(ex))
