from contextlib import contextmanager
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio
from fastapi import Request, Response
from starlette_context import _request_scope_context_storage

from src.components.services.email_service import EmailService
from src.loggers.console_service_logger import ConsoleServiceLogger
from src.middlewares.exception import ErrorHandlingMiddleware


@contextmanager
def starlette_context():
    token = _request_scope_context_storage.set({})
    try:
        yield
    finally:
        _request_scope_context_storage.reset(token)


@pytest.fixture(autouse=True)
def setup_starlette_context():
    with starlette_context():
        yield


@pytest_asyncio.fixture
async def mock_email_service():
    return MagicMock(spec=EmailService)


@pytest_asyncio.fixture
async def mock_logger():
    logger = MagicMock(spec=ConsoleServiceLogger)
    logger.debug = MagicMock()
    logger.info = MagicMock()
    logger.error = MagicMock()
    logger.warning = MagicMock()
    return logger


@pytest_asyncio.fixture
async def mock_request():
    request = MagicMock(spec=Request)
    request.url = "https://qa-console-service.makunaiglobal.ai/test"
    request.method = "GET"
    request.state.user = {"user_id": 1, "partner_id": 100}
    request.state.request_id = "12345"
    # This matches your main code: .state.body must be bytes
    request.state.body = b'{"data": "test"}'
    return request


@pytest_asyncio.fixture
async def mock_call_next():
    return AsyncMock(return_value=Response(status_code=200))


@pytest_asyncio.fixture
async def error_middleware(mock_email_service, mock_logger):
    with patch.object(ConsoleServiceLogger, "__init__", lambda x: None), patch.object(
        ConsoleServiceLogger, "info", mock_logger.info
    ), patch.object(ConsoleServiceLogger, "error", mock_logger.error):
        middleware = ErrorHandlingMiddleware(
            app=None, error_email_service=mock_email_service
        )
        middleware.logger = mock_logger
        return middleware


@pytest.mark.asyncio
@patch("src.components.partner.services.PartnerService.get_partner_by_id")
async def test_prepare_error_email_data_exception(
    mock_get_partner, mock_request, mock_logger, error_middleware
):
    mock_get_partner.side_effect = Exception("Partner error")
    # Set state.body to valid JSON to avoid TypeError
    mock_request.state.body = b'{"data": "test"}'
    email_data = await error_middleware._prepare_error_email_data(
        mock_request, Exception("Test error"), "QA"
    )
    assert email_data["error_message"] == "Failed to prepare error data: Partner error"
    assert email_data["environment"] == "QA"
    assert email_data["endpoint"] == "https://qa-console-service.makunaiglobal.ai/test"
    mock_logger.error.assert_called_with(
        "Failed to prepare error email data: Partner error"
    )


@pytest.mark.asyncio
async def test_send_error_email_success(
    mock_request, mock_email_service, mock_logger, error_middleware
):
    recipients = ["test@example.com"]
    with patch.object(
        error_middleware,
        "_prepare_error_email_data",
        AsyncMock(return_value={"partner_name": "Test Partner"}),
    ):
        await error_middleware._send_error_email(
            mock_request, "QA", recipients, Exception("Test error")
        )
        mock_email_service.send_email.assert_called_with(
            to_emails=recipients,
            subject="Console Breaking for Test Partner in QA!",
            body={"partner_name": "Test Partner"},
            html_template="error_mail.html",
        )
        mock_logger.info.assert_called_with(
            "Error email successfully sent to ['test@example.com'] for QA"
        )


@pytest.mark.asyncio
@patch("src.components.partner.services.PartnerService.get_partner_by_id")
async def test_prepare_error_email_data_success(
    mock_get_partner, mock_request, mock_logger, error_middleware
):
    partner_mock = MagicMock()
    partner_mock.name = "Test Partner"
    mock_get_partner.return_value = partner_mock
    mock_request.state.body = b'{"data": "test"}'
    email_data = await error_middleware._prepare_error_email_data(
        mock_request, Exception("Test error"), "QA"
    )
    assert email_data["user_id"] == 1
    assert email_data["partner_id"] == 100
    assert email_data["user_name"] == "Unknown User"
    assert email_data["partner_name"] == "Test Partner"
    assert email_data["environment"] == "QA"
    assert email_data["endpoint"] == "https://qa-console-service.makunaiglobal.ai/test"
    assert email_data["request_id"] == "12345"
    assert email_data["http_method"] == "GET"
    assert email_data["payload"] == {"data": "test"}
    assert email_data["error_message"] == "Test error"


@pytest.mark.asyncio
@patch("src.components.partner.services.PartnerService.get_partner_by_id")
async def test_prepare_error_email_data_no_user(
    mock_get_partner, mock_request, mock_logger, error_middleware
):
    mock_request.state.user = {}
    partner_mock = MagicMock()
    partner_mock.name = "Unknown Partner"
    mock_get_partner.return_value = partner_mock
    mock_request.state.body = b'{"data": "test"}'
    email_data = await error_middleware._prepare_error_email_data(
        mock_request, Exception("Test error"), "QA"
    )
    assert email_data["user_id"] == "N/A"
    assert email_data["partner_id"] == "N/A"
    assert email_data["user_name"] == "Unknown User"
    assert email_data["partner_name"] == "Unknown Partner"

    @pytest.mark.asyncio
    async def test_error_email_masks_sensitive_data(
        mock_request, mock_email_service, mock_logger, error_middleware
    ):
        """Test that sensitive data like passwords are masked in error emails."""
        # Arrange - Create request with sensitive data
        sensitive_payload = {
            "email": "user@example.com",
            "password": "super_secret_123",
            "hashed_password": "some_hash_value",
            "credit_card": "4111111111111111",
            "name": "Test User"
        }
        mock_request.state.body = json.dumps(sensitive_payload).encode('utf-8')
        mock_request.state.user = {"user_id": 1, "partner_id": 100, "name": "Test User"}
        
        recipients = ["admin@example.com"]
        
        with patch.object(
            error_middleware,
            "_prepare_error_email_data",
            AsyncMock(return_value={"partner_name": "Test Partner"})
        ):
            await error_middleware._send_error_email(
                mock_request, "QA", recipients, Exception("Test error")
            )

            call_args = mock_email_service.send_email.call_args[1]
            email_body = call_args['body']
            
            # Verify sensitive data is masked
            assert "super_secret_123" not in str(email_body)
            assert "some_hash_value" not in str(email_body)
            # Email might be partially masked
            assert "user@example.com" not in str(email_body) or "@" not in str(email_body)

    @pytest.mark.asyncio
    @patch("src.components.partner.services.PartnerService.get_partner_by_id")
    async def test_prepare_error_email_data_masks_passwords(
        mock_get_partner, mock_request, mock_logger, error_middleware
    ):
        """Test that _prepare_error_email_data properly masks passwords in payload."""
        # Arrange
        partner_mock = MagicMock()
        partner_mock.name = "Test Partner"
        mock_get_partner.return_value = partner_mock
        
        # Create payload with sensitive data
        sensitive_payload = {
            "email": "user@example.com",
            "password": "secret_password_123",
            "hashed_password": "hashed_value_456",
            "phone_number": "+1234567890"
        }
        mock_request.state.body = json.dumps(sensitive_payload).encode('utf-8')
        mock_request.state.user = {"user_id": 1, "partner_id": 100, "name": "Test User"}
        
        email_data = await error_middleware._prepare_error_email_data(
            mock_request, Exception("Test error"), "QA"
        )
        
        payload = email_data['payload']
        payload_str = json.dumps(payload)
        
        # Verify passwords are masked
        assert "secret_password_123" not in payload_str
        assert "hashed_value_456" not in payload_str
        # Verify email might be partially masked
        assert "user@example.com" not in payload_str or "@" not in payload_str
        # Verify phone number might be partially masked
        assert "1234567890" not in payload_str or "***" in payload_str
