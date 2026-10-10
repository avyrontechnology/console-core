import asyncio
from typing import Any, Dict, List, Optional

from src.components.common.datetime import DateTimeUtil
from src.components.payment.client_factory import get_payment_client
from src.components.payment.enum import EntityNameEnum, PaymentStatusEnum
from src.components.payment.errors import (
    PaymentError,
    PaymentNotFoundError,
    PaymentValidationError,
    WebhookSignatureError,
)
from src.components.payment.models import Payment
from src.components.payment.repositories import PaymentRepository
from src.components.payment.schema import InitiateOrderRequest, ValidateOrderRequest
from src.core.environment import ENV
from src.loggers.console_service_logger import ConsoleServiceLogger


class PaymentService:
    """
    Service layer for dynamic payment operations.
    Handles order creation, validation, webhook processing, and history retrieval.
    """

    def __init__(
        self, repository: PaymentRepository, logger: ConsoleServiceLogger
    ) -> None:
        self.repo: PaymentRepository = repository
        self.logger: ConsoleServiceLogger = logger
        self.client = get_payment_client()

    async def create_order(
        self, payload: InitiateOrderRequest, user_context: dict
    ) -> Dict[str, Any]:
        """
        Create a payment order with the configured vendor.

        Args:
            payload (InitiateOrderRequest): Order creation request.

        Returns:
            Dict[str, Any]: Vendor order response.
        """
        try:
            self.logger.info(
                "Initiating payment for partner_id={}".format(payload.partner_id)
            )

            user_id: int = user_context.get("user_id")

            notes: Dict[str, Any] = {
                "partner_id": payload.partner_id,
                "entity": payload.entity_name,
            }

            max_retries: int = 3
            gateway_order: Optional[Dict[str, Any]] = None

            for attempt in range(1, max_retries + 1):
                try:
                    gateway_order = self.client.initiate_order(
                        amount=payload.amount, currency=payload.currency, notes=notes
                    )
                    break
                except Exception as ex:
                    self.logger.warning(
                        "Attempt {} failed while creating order: {}".format(attempt, ex)
                    )
                    if attempt == max_retries:
                        self.logger.error(
                            "Max retries reached while creating order. Raising PaymentError."
                        )
                        raise PaymentError(
                            "Failed to create payment order after {} attempts, error: {}".format(
                                max_retries, ex
                            )
                        )
                    await asyncio.sleep(0.2)

            if gateway_order is None:
                self.logger.error(  # extra log before raising
                    "Gateway order returned None. Raising PaymentError."
                )
                raise PaymentError("Failed to create payment order")

            payment: Payment = Payment(
                partner_id=payload.partner_id,
                amount=payload.amount,
                order_id=payload.order_id,
                entity_name=EntityNameEnum.PLAN,
                vendor=ENV.PAYMENT_CLIENT.upper(),
                payment_status=PaymentStatusEnum.PENDING,
                merchant_transaction_id=gateway_order.get("id"),
                created_by=user_id,
            )

            await self.repo.create_payment(payment)

            self.logger.info(
                "Payment order created successfully order_id={}".format(
                    payload.order_id
                )
            )

            return gateway_order

        except Exception as e:
            self.logger.error("Error in create_order: {}".format(e))
            raise PaymentError(str(e))

    async def validate_order(
        self, payload: ValidateOrderRequest, current_user: dict
    ) -> Dict[str, str]:
        """
        Validate Razorpay checkout signature and update payment status.

        Args:
            payload (ValidateOrderRequest): Signature validation request.

        Returns:
            Dict[str, str]: Validation status.
        """
        try:
            self.logger.info("Validating payment order_id={}".format(payload.order_id))

            payment: Optional[Payment] = await self.repo.get_payment_by_order_id(
                payload.order_id
            )

            if not payment:
                self.logger.error(
                    "Payment not found for order_id={}.".format(payload.order_id)
                )
                raise PaymentNotFoundError(payload.order_id)

            is_valid: bool = self.client.validate_signature(payload.model_dump())

            new_status: PaymentStatusEnum = (
                PaymentStatusEnum.SUCCESS if is_valid else PaymentStatusEnum.FAILED
            )

            self.logger.info(
                "Payment validation {} order_id={}".format(
                    "successful" if is_valid else "failed", payload.order_id
                )
            )

            await self.repo.update_payment(
                payment_id=payment.id,
                data={
                    "payment_status": new_status,
                    "updated_by": current_user.get("user_id"),
                },
            )

            return {
                "status": "success" if is_valid else "failed",
                "order_id": payload.order_id,
            }

        except Exception as e:
            self.logger.error("Error in validate_order: {}".format(e))
            raise PaymentValidationError(str(e))

    async def handle_webhook(
        self,
        payload: Dict[str, Any],
        raw_body: bytes,
        signature: str,
    ) -> Dict[str, Any]:
        """
        Handle payment webhook from payment gateway with signature verification.
        """
        try:
            if not signature:
                self.logger.error("Webhook signature header missing")
                raise WebhookSignatureError("Missing webhook signature")

            is_verified = self.client.verify_webhook_signature(
                raw_body.decode("utf-8"),
                signature,
            )
            if not is_verified:
                self.logger.error("Webhook signature verification failed")
                raise WebhookSignatureError("Invalid webhook signature")

            self.logger.info("Webhook signature verified successfully")

            self.logger.info("Processing payment webhook payload")

            processed: Dict[str, Any] = self.client.handle_callback(payload)

            order_id: Optional[str] = processed.get("order_id")

            payment: Optional[Payment] = None
            if order_id:
                payment: Optional[Payment] = await self.repo.get_payment_by_order_id(
                    order_id
                )

            if payment:
                await self.repo.update_payment(
                    payment.id,
                    {
                        "payment_status": processed.get("status"),
                        "payment_method": processed.get("payment_method"),
                        "payment_id": processed.get("payment_id"),
                        "additional_info": payload,
                    },
                )

                self.logger.info(
                    "Webhook updated payment_id={} order_id={} status={}".format(
                        processed.get("payment_id"), order_id, processed.get("status")
                    )
                )

            return processed

        except WebhookSignatureError:
            raise

        except Exception as e:
            self.logger.error("Error processing webhook: {}".format(e))
            raise PaymentError(str(e))

    def _resolve_gateway_outcome(self, payment: Payment) -> Optional[Dict[str, Any]]:
        """
        Ask the gateway what really happened to a stale PENDING payment:
        captured (-> SUCCESS), a dead end with no successful attempt
        (-> FAILED), or genuinely still in flight (-> None, leave PENDING
        for the next cycle).
        """
        if not payment.merchant_transaction_id:
            return None

        gateway_order = self.client.fetch_order(payment.merchant_transaction_id)
        if not gateway_order:
            return None

        order_status = gateway_order.get("status")
        if order_status == "paid":
            order_payments = self.client.fetch_order_payments(
                payment.merchant_transaction_id
            )
            for item in (order_payments or {}).get("items", []):
                if item.get("status") == "captured":
                    return {
                        "status": PaymentStatusEnum.SUCCESS,
                        "payment_id": item.get("id"),
                        "payment_method": item.get("method"),
                    }
            return None

        if order_status == "attempted":
            order_payments = self.client.fetch_order_payments(
                payment.merchant_transaction_id
            )
            items = (order_payments or {}).get("items", [])
            # Every attempt made on this order is a dead end, and nothing
            # is still authorized/created (i.e. nothing in flight) — a
            # genuine gateway failure, not a lost webhook for a success.
            if items and all(item.get("status") == "failed" for item in items):
                return {"status": PaymentStatusEnum.FAILED, "payment_id": items[-1].get("id")}
            return None

        # "created": no attempt has been made on this order yet.
        return None

    async def reconcile_pending_payments(self, batch_size: int = 100) -> Dict[str, int]:
        """
        Fallback for a webhook that never arrived: re-check payments still
        PENDING a while after creation directly against the gateway, and
        resolve them to SUCCESS or FAILED the same way the webhook would
        have. A payment the gateway still shows as genuinely in flight is
        left PENDING for the next cycle.
        """
        now_ms = DateTimeUtil.get_current_time()
        older_than_ms = now_ms - (3 * 60 * 1000)
        newer_than_ms = now_ms - (24 * 60 * 60 * 1000)

        payments = await self.repo.get_stale_pending_payments(
            older_than_ms=older_than_ms,
            newer_than_ms=newer_than_ms,
            limit=batch_size,
        )

        succeeded = 0
        failed = 0
        for payment in payments:
            try:
                outcome = self._resolve_gateway_outcome(payment)
                if not outcome:
                    continue

                if outcome["status"] == PaymentStatusEnum.SUCCESS:
                    await self.repo.update_payment(
                        payment.id,
                        {
                            "payment_status": PaymentStatusEnum.SUCCESS,
                            "payment_id": outcome.get("payment_id"),
                            "payment_method": outcome.get("payment_method"),
                        },
                    )
                    succeeded += 1
                    self.logger.info(
                        "Reconciliation: payment_id={} order_id={} confirmed captured at gateway".format(
                            payment.id, payment.order_id
                        )
                    )
                else:
                    await self.repo.update_payment(
                        payment.id,
                        {
                            "payment_status": PaymentStatusEnum.FAILED,
                            "payment_id": outcome.get("payment_id"),
                        },
                    )
                    failed += 1
                    self.logger.info(
                        "Reconciliation: payment_id={} order_id={} confirmed failed at gateway".format(
                            payment.id, payment.order_id
                        )
                    )
            except Exception as ex:
                self.logger.error(
                    "Reconciliation failed for payment_id={}: {}".format(payment.id, ex)
                )

        self.logger.info(
            "Reconciliation complete: checked={} succeeded={} failed={}".format(
                len(payments), succeeded, failed
            )
        )
        return {"checked": len(payments), "succeeded": succeeded, "failed": failed}

    async def get_payment_history_by_partner(
        self,
        partner_id: int,
        limit: Optional[int] = None,
        offset: Optional[int] = None,
    ) -> tuple[List[Payment], int]:
        """
        Retrieve payment history for a partner.
        """
        try:
            payments: List[Payment] = await self.repo.get_payments_by_partner(
                partner_id,
                limit,
                offset,
            )

            self.logger.info(
                "Fetched {} payments for partner_id={}".format(
                    len(payments), partner_id
                )
            )

            return payments

        except Exception as e:
            self.logger.error(
                "Error fetching payment history for partner_id={} error={}".format(
                    partner_id, e
                )
            )
            raise
