import json
from typing import Dict, List, Optional, Union

import requests
from jinja2 import Environment
from pydantic import BaseModel, EmailStr, ValidationError

from src.loggers.console_service_logger import ConsoleServiceLogger


class ValidateEmail(BaseModel):
    email: EmailStr


class EmailService:
    """Service class for handling email operations with SMTP server and API."""

    def __init__(
        self,
        logger: ConsoleServiceLogger,
        api_url: str,
        channel_key: str,
        sender_email: str,
        template_env: Environment,
    ):
        """Initialize EmailService with configurations and logging."""
        self.logger = logger
        self.api_url = api_url
        self.channel_key = channel_key
        self.sender_email = sender_email
        self.template_env = template_env

    def _validate_emails(self, emails: List[str], label: str) -> None:
        """Validate a list of email addresses."""
        if not emails:
            self.logger.error(f"{label} email list cannot be empty")
            raise ValueError(f"{label} email list cannot be empty")

        for email in emails:
            try:
                ValidateEmail(email=email)
            except ValidationError:
                self.logger.error(f"Invalid {label} email: {email}")
                raise ValueError(f"Invalid {label} email: {email}")

    def _render_html_content(
        self, body: Union[str, Dict], html_template: Optional[str] = None
    ) -> Optional[str]:
        """
        Render HTML template with provided body data.

        Args:
            body: Email content as string or dictionary for template rendering
            html_template: Optional HTML template filename

        Returns:
            Optional[str]: Rendered HTML content or None if no template is provided
        """
        if not html_template:
            return None
        try:
            self.logger.debug(f"Rendering HTML template: {html_template}")
            template = self.template_env.get_template(html_template)
            html_content = template.render(
                **body if isinstance(body, dict) else {"body": body}
            )
            return html_content
        except Exception as e:
            self.logger.error(
                f"Failed to render HTML template {html_template}: {str(e)}"
            )
            raise

    def send_email(
        self,
        to_emails: List[str],
        subject: str,
        body: Union[str, Dict],
        cc_emails: Optional[List[str]] = None,
        bcc_emails: Optional[List[str]] = None,
        html_template: Optional[str] = None,
        attachments: Optional[List[Dict[str, str]]] = None,
        channel_key: Optional[str] = None,
    ) -> Dict:
        """
        Send an email via the email microservice API.

        Args:
            to_emails: Recipient email addresses
            subject: Email subject
            body: Email body (string or dict for template)
            cc_emails: CC email addresses
            bcc_emails: BCC email addresses
            html_template: HTML template filename
            attachments: List of {'filename': str, 'content': str} (base64)

        Returns:
            Dict: API response
        """
        self.logger.info(f"Sending email to {to_emails} with subject: {subject}")
        self._validate_inputs(to_emails, subject, body, cc_emails, bcc_emails)
        payload = self._build_payload(
            to_emails, subject, body, cc_emails, bcc_emails, html_template, attachments
        )
        return self._make_api_call(payload, channel_key)

    def _validate_inputs(
        self,
        to_emails: List[str],
        subject: str,
        body: Union[str, Dict],
        cc_emails: Optional[List[str]],
        bcc_emails: Optional[List[str]],
    ) -> None:
        """Validate email inputs."""
        self._validate_emails(to_emails, "To")
        if cc_emails:
            self._validate_emails(cc_emails, "CC")
        if bcc_emails:
            self._validate_emails(bcc_emails, "BCC")
        if not subject or not isinstance(subject, str):
            self.logger.error("Subject must be a non-empty string")
            raise ValueError("Subject must be a non-empty string")
        if not body:
            self.logger.error("Body cannot be empty")
            raise ValueError("Body cannot be empty")

    def _build_payload(
        self,
        to_emails: List[str],
        subject: str,
        body: Union[str, Dict],
        cc_emails: Optional[List[str]],
        bcc_emails: Optional[List[str]],
        html_template: Optional[str],
        attachments: Optional[List[Dict[str, str]]],
    ) -> Dict:
        """Build the API payload."""
        payload = {
            "to_emails": to_emails,
            "cc_emails": cc_emails or [],
            "bcc_emails": bcc_emails or [],
            "subject": subject,
            "body": body if isinstance(body, str) else json.dumps(body),
        }
        if html_template:
            html_content = self._render_html_content(body, html_template)
            if html_content:
                payload["html_content"] = html_content
        if attachments:
            payload["attachments"] = attachments
        return payload

    def _make_api_call(self, payload: Dict, channel_key: Optional[str] = None) -> Dict:
        """Make API call with retry logic."""
        effective_channel = channel_key or self.channel_key
        headers = {
            "Content-Type": "application/json",
            "X-Channel-Key": effective_channel,
        }
        for attempt in range(3):
            try:
                response = requests.post(
                    self.api_url, json=payload, headers=headers, timeout=10
                )
                response.raise_for_status()
                result = response.json()
                self.logger.info(
                    f"Email sent: task_id={result.get('task_id')}, to={payload['to_emails']}"
                )
                return result
            except Exception as e:
                self.logger.warning(f"Attempt {attempt + 1} failed: {str(e)}")
                if attempt == 2:
                    self.logger.error(
                        f"Failed to send email after 3 attempts: {str(e)}"
                    )
                    raise ValueError(f"Email API call failed: {str(e)}")
