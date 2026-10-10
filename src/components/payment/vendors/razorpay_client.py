import hashlib
import hmac
from typing import Any, Dict, Optional

import razorpay

from src.components.payment.enum import PaymentStatusEnum
from src.components.payment.errors import WebhookSignatureError
from src.components.payment.vendors.base_client import BasePaymentClient
from src.core.environment import ENV
from src.loggers.console_service_logger import ConsoleServiceLogger

logger = ConsoleServiceLogger.get_logger()


class RazorpayClient(BasePaymentClient):
    """
    Razorpay implementation of BasePaymentClient.

    Handles:
        - Client initialization
        - Order creation
        - Signature validation
        - Webhook parsing
    """

    def __init__(self) -> None:
        try:
            self._key_id: str = ENV.RAZORPAY_KEY_ID
            self._key_secret: str = ENV.RAZORPAY_KEY_SECRET
            self._webhook_secret: str = ENV.RAZORPAY_WEBHOOK_SECRET

            logger.info(
                "RazorpayClient initialized with key_id={}".format(self._key_id)
            )

            self.client: razorpay.Client = razorpay.Client(
                auth=(self._key_id, self._key_secret)
            )

        except Exception as e:
            logger.error("RazorpayClient: initialization failed: {}".format(e))
            raise e

    def initiate_order(
        self,
        amount: float,
        currency: str = "INR",
        notes: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Create an order on Razorpay.

        Args:
            amount (float): Amount in currency's smallest unit.
            currency (str): Currency code (default: INR).
            notes (dict | None): Metadata for the order.

        Returns:
            Dict[str, Any]: Response from Razorpay API.
        """
        try:
            order_data: Dict[str, Any] = {
                "amount": int(round(amount)),
                "currency": currency,
                "notes": notes or {},
            }

            logger.info(
                "RazorpayClient: creating order amount={} currency={}".format(
                    amount, currency
                )
            )

            response: Dict[str, Any] = self.client.order.create(order_data)

            logger.info(
                "RazorpayClient: order created successfully order_id={}".format(
                    response.get("id")
                )
            )

            return response

        except Exception as e:
            logger.error("RazorpayClient: order creation failed: {}".format(e))
            raise e

    def validate_signature(self, payload: Dict[str, Any]) -> bool:
        """
        Validate payment signature from Razorpay checkout.

        Args:
            payload (Dict[str, Any]): {order_id, payment_id, signature}

        Returns:
            bool: True if signature is valid else False.
        """
        try:
            order_id: Optional[str] = payload.get("order_id")
            payment_id: Optional[str] = payload.get("payment_id")
            signature: Optional[str] = payload.get("signature")

            logger.info(
                "RazorpayClient: validating signature for order_id={} payment_id={}".format(
                    order_id, payment_id
                )
            )

            msg: str = "{}|{}".format(order_id, payment_id)

            generated_signature: str = hmac.new(
                bytes(self._key_secret, "utf-8"), bytes(msg, "utf-8"), hashlib.sha256
            ).hexdigest()

            is_valid: bool = generated_signature == signature

            logger.info(
                "RazorpayClient: signature valid={} order_id={}".format(
                    is_valid, order_id
                )
            )

            return is_valid

        except Exception as e:
            logger.error("RazorpayClient: error validating signature: {}".format(e))
            return False

    def handle_callback(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """
        Parse Razorpay Webhook payload.

        Args:
            payload (Dict[str, Any]): Webhook JSON body.

        Returns:
            Dict[str, Any]:
                {
                    "order_id": str | None,
                    "payment_id": str | None,
                    "payment_method": str | None,
                    "status": str
                }
        """
        try:
            event: Optional[str] = payload.get("event")

            logger.info("RazorpayClient: handling webhook event={}...".format(event))

            inner: Dict[str, Any] = payload.get("payload", {})

            payment: Optional[Dict[str, Any]] = inner.get("payment", {}).get("entity")
            if payment:
                order_id: Optional[str] = payment.get("order_id")
                payment_id: Optional[str] = payment.get("id")
                payment_method: Optional[str] = payment.get("method")

                status_str: str = payment.get("status", "").lower()

                if status_str in ["captured", "paid"]:
                    status: PaymentStatusEnum = PaymentStatusEnum.SUCCESS
                elif status_str in ["authorized", "created"]:
                    status = PaymentStatusEnum.PENDING
                else:
                    status = PaymentStatusEnum.FAILED

                logger.info(
                    "RazorpayClient: webhook payment parsed order_id={} payment_id={} method={} status={}".format(
                        order_id, payment_id, payment_method, status
                    )
                )

                return {
                    "order_id": order_id,
                    "payment_id": payment_id,
                    "payment_method": payment_method,
                    "status": status,
                }

            order: Optional[Dict[str, Any]] = inner.get("order", {}).get("entity")
            if order:
                order_id = order.get("id")
                order_status_str: str = order.get("status", "").lower()

                status = (
                    PaymentStatusEnum.SUCCESS
                    if order_status_str == "paid"
                    else PaymentStatusEnum.FAILED
                )

                logger.info(
                    "RazorpayClient: webhook ORDER parsed order_id={} status={}".format(
                        order_id, status
                    )
                )

                return {
                    "order_id": order_id,
                    "payment_id": None,
                    "payment_method": None,
                    "status": status,
                }

            logger.error(
                "RazorpayClient: webhook missing payment/order entity. Payload={}".format(
                    payload
                )
            )

            return {
                "order_id": None,
                "payment_id": None,
                "payment_method": None,
                "status": PaymentStatusEnum.FAILED,
            }

        except Exception as e:
            logger.error("RazorpayClient: error parsing webhook: {}".format(e))
            return {
                "order_id": None,
                "payment_id": None,
                "payment_method": None,
                "status": PaymentStatusEnum.FAILED,
            }

    def verify_webhook_signature(
        self, raw_payload: str, received_signature: str
    ) -> bool:
        """
        Verify Razorpay webhook signature using the official utility method.

        Args:
            raw_payload: The raw request body as string (decoded utf-8)
            received_signature: Value from X-Razorpay-Signature header

        Returns:
            bool: True if valid, False otherwise

        Raises:
            razorpay.errors.SignatureVerificationError: If verification fails
        """
        try:
            if not self._webhook_secret:
                logger.error("Razorpay webhook secret not available")
                raise WebhookSignatureError("Webhook secret not configured")

            # Official SDK method
            self.client.utility.verify_webhook_signature(
                body=raw_payload,
                signature=received_signature,
                secret=self._webhook_secret,
            )

            logger.info("Razorpay webhook signature verified successfully")
            return True

        except razorpay.errors.SignatureVerificationError as sve:
            logger.error(f"Razorpay webhook signature verification failed: {sve}")
            raise WebhookSignatureError()
        except Exception as e:
            logger.error(f"Unexpected error during webhook signature verification: {e}")
            return False

    def fetch_order(self, order_id: str) -> Dict[str, Any]:
        """
        Fetch order details from Razorpay.
        """
        try:
            logger.info("RazorpayClient: fetching order_id={}".format(order_id))
            response = self.client.order.fetch(order_id)
            return response
        except Exception as e:
            logger.error("RazorpayClient: order fetch failed: {}".format(e))
            raise e

    def fetch_order_payments(self, order_id: str) -> Dict[str, Any]:
        """
        Fetch payments for an order from Razorpay.
        """
        try:
            logger.info("RazorpayClient: fetching payments for order_id={}".format(order_id))
            response = self.client.order.payments(order_id)
            return response
        except Exception as e:
            logger.error("RazorpayClient: order payments fetch failed: {}".format(e))
            raise e
