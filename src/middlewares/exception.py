import json
import traceback
from datetime import datetime
from typing import List, Tuple

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

from src.components.partner.models import Partner
from src.components.partner.services import PartnerService
from src.components.services.email_service import EmailService
from src.core.container import Container
from src.loggers.console_service_logger import ConsoleServiceLogger
from src.middlewares import constants
from src.components.auth.masker import mask_for_email

container = Container()

ENVIRONMENT_CONFIG = {
    "DEV": {
        "base_url": "http://int-console-service.makunaiglobal.ai",
        "recipients": constants.DEV_ERROR_MAIL_RECIPENTS,
    },
    "QA": {
        "base_url": "http://qa-console-service.makunaiglobal.ai",
        "recipients": constants.QA_ERROR_MAIL_RECIPENTS,
    },
    "PROD": {
        "base_url": "http://console-service.makunaiglobal.ai",
        "recipients": constants.PROD_ERROR_MAIL_RECIPENTS,
    },
}

MONITORED_ENVIRONMENTS = list(ENVIRONMENT_CONFIG.keys())


class ErrorHandlingMiddleware(BaseHTTPMiddleware):
    """
    Middleware for handling errors and triggering error notification emails.

    Captures exceptions and HTTP 500+ status codes, logs details,
    and triggers error notifications to configured recipients.
    """

    def __init__(self, app, error_email_service: EmailService):
        """
        Initialize the ErrorHandlingMiddleware.

        Args:
            app: The FastAPI application instance
            error_email_service: Instance of EmailService for sending error emails

        Raises:
            Exception: If initialization fails
        """
        super().__init__(app)
        self.logger = ConsoleServiceLogger()
        try:
            self.error_email_service = error_email_service
            self.environment_config = ENVIRONMENT_CONFIG
            self.monitored_environments = MONITORED_ENVIRONMENTS
            self.logger.info("ErrorHandlingMiddleware initialized successfully")
        except Exception as e:
            self.logger.error(f"Failed to initialize ErrorHandlingMiddleware: {str(e)}")
            raise

    def _get_environment_info(self, request_url: str) -> Tuple[str, List[str]]:
        """
        Determine the environment and recipients based on request URL.

        Args:
            request_url: The URL of the incoming request

        Returns:
            Tuple[str, List[str]]: Environment name and list of recipient emails

        Raises:
            Exception: If environment matching fails
        """
        self.logger.debug(f"Checking environment for URL: {request_url}")
        try:
            for env, config in self.environment_config.items():
                base_url = config["base_url"]
                if request_url.startswith(base_url):
                    self.logger.info(
                        f"Matched environment: {env} with base_url: {base_url}"
                    )
                    return env, config["recipients"]
            self.logger.warning(
                f"No environment matched for URL: {request_url}. No email will be sent."
            )
            return "UNKNOWN", []
        except Exception as e:
            self.logger.error(f"Failed to get environment info: {str(e)}")
            return "UNKNOWN", []

    async def _prepare_error_email_data(
        self, request: Request, error: Exception, environment: str
    ) -> dict:
        """
        Prepare data for error notification email.

        Args:
            request: FastAPI Request object
            error: Exception object
            environment: Deployment environment name

        Returns:
            dict: Data for email body
        """
        self.logger.debug("Preparing error email data")
        try:
            user_dict = getattr(request.state, "user", None)
            if user_dict and isinstance(user_dict, dict):
                partner_service: PartnerService = await container.partner_service()

                user_id: int = user_dict.get("user_id", "N/A")
                user_name: str = user_dict.get("name", "Unknown User")
                partner_id: int = request.state.user.get("partner_id", "N/A")
                partner_details: Partner = await partner_service.get_partner_by_id(
                    partner_id
                )
                partner_name: str = partner_details.name
            else:
                user_id = "N/A"
                partner_id = "N/A"
                user_name = "Unknown User"
                partner_name = "Unknown Partner"

            try:
                request_body = getattr(request.state, "body", None)
                raw_payload = (
                    json.loads(request_body.decode("utf-8"))
                    if request_body
                    else "No body"
                )
            except Exception as e:
                self.logger.warning(f"Failed to parse request body: {str(e)}")
                raw_payload = "Error parsing body"
            # This masks password fully + email/credential partially
            safe_payload = (
                mask_for_email(raw_payload)
                if isinstance(raw_payload, (dict, list))
                else raw_payload
            )

            return {
                "partner_id": partner_id,
                "partner_name": partner_name,
                "environment": environment.upper(),
                "endpoint": str(request.url),
                "request_id": getattr(request.state, "request_id", "N/A"),
                "http_method": request.method,
                "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "payload": safe_payload,   
                "user_id": user_id,
                "user_name": user_name,
                "error_message": str(error),
            }
        except Exception as e:
            self.logger.error(f"Failed to prepare error email data: {str(e)}")
            request_body = getattr(request.state, "body", None)
            try:
                raw_fallback = (
                    json.loads(request_body.decode("utf-8"))
                    if request_body
                    else "No body"
                )
            except Exception:
                raw_fallback = "Error parsing body"

            safe_fallback = (
                mask_for_email(raw_fallback)
                if isinstance(raw_fallback, (dict, list))
                else raw_fallback
            )

            return {
                "environment": environment.upper(),
                "endpoint": str(request.url),
                "request_id": getattr(request.state, "request_id", "N/A"),
                "http_method": request.method,
                "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "payload": safe_fallback, 
                "error_message": f"Failed to prepare error data: {str(e)}",
            }

    async def _send_error_email(
        self,
        request: Request,
        environment: str,
        recipients: List[str],
        error: Exception,
    ) -> None:
        """
        Trigger error notification email.

        Args:
            request: FastAPI Request object
            environment: Deployment environment name
            recipients: List of recipient email addresses
            error: Exception object

        Raises:
            Exception: If email sending fails (caught and logged)
        """
        self.logger.debug(
            f"Preparing to send error email for {environment} to {recipients}"
        )
        if not recipients:
            self.logger.warning("No recipients configured, skipping email")
            return

        try:
            email_data = await self._prepare_error_email_data(
                request, error, environment
            )
            subject = f"Console Breaking for {email_data.get('partner_name', 'Unknown Partner')} in {environment.upper()}!"
            self.error_email_service.send_email(
                to_emails=recipients,
                subject=subject,
                body=email_data,
                html_template="error_mail.html",
            )
            self.logger.info(
                f"Error email successfully sent to {recipients} for {environment}"
            )
        except Exception as email_error:
            self.logger.error(f"Failed to send error email: {str(email_error)}")

    async def dispatch(self, request: Request, call_next):
        """
        Process incoming requests and handle errors.

        Args:
            request: FastAPI Request object
            call_next: Function to call the next middleware or route handler

        Returns:
            Response: HTTP response or error response if an exception occurs

        Raises:
            Exception: Caught and handled to return error response
        """
        self.logger.info(f"Processing request: {request.method} {request.url}")

        try:
            response = await call_next(request)
            self.logger.debug(
                f"Request processed with status: {response.status_code} for {request.url}"
            )

            if response.status_code >= 500:
                self.logger.warning(
                    f"Server error detected: {response.status_code} for {request.url}"
                )
                try:
                    request_url = str(request.url)
                    environment, recipients = self._get_environment_info(request_url)

                    error_msg = getattr(
                        request,
                        "message",
                        f"Server error occurred: Status Code {response.status_code}",
                    )
                    await self._send_error_email(
                        request, environment, recipients, Exception(error_msg)
                    )
                except Exception as e:
                    self.logger.error(f"Error handling response: {str(e)}")

            return response

        except Exception as e:
            trace = traceback.format_exc()
            request_url = str(request.url)

            try:
                environment, recipients = self._get_environment_info(request_url)
                error_context = {
                    "url": request_url,
                    "method": request.method,
                    "environment": environment,
                    "error": str(e),
                    "trace": trace,
                }
                self.logger.error(f"Unhandled exception caught: {error_context}")

                await self._send_error_email(request, environment, recipients, e)

                return Response(
                    content=f"An error occurred in {environment} ({request_url}): {str(e)}",
                    status_code=500,
                    media_type="text/plain",
                )

            except Exception as response_error:
                self.logger.error(f"Failed to handle exception: {str(response_error)}")
                return Response(
                    content=f"Critical error processing request: {str(e)}",
                    status_code=500,
                    media_type="text/plain",
                )
