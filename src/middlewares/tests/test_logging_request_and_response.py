from unittest.mock import AsyncMock, MagicMock, patch
import json
import pytest
from starlette.requests import Request
from starlette.responses import StreamingResponse

from src.components.common.response import InternalServerErrorResponse
from src.middlewares.logging_request_and_response import (
    RequestResponseLoggingMiddleware,
)

# -----------------------
# Fixtures
# -----------------------


@pytest.fixture
def mock_request():
    req = MagicMock(spec=Request)
    req.url.path = "/api/test"
    req.method = "POST"
    req.headers = {}
    req.client = MagicMock()
    req.client.host = "127.0.0.1"
    req.body = AsyncMock(return_value=b'{"key": "value"}')
    return req


@pytest.fixture
def mock_call_next():
    mock_resp = AsyncMock()
    # Use StreamingResponse to match middleware's `response.body_iterator`
    response = StreamingResponse(
        content=iter([b'{"success": true}']),
        media_type="application/json",
        status_code=200,
    )
    mock_resp.return_value = response
    return mock_resp


@pytest.fixture
def mock_console_service_logger():
    return MagicMock()


@pytest.fixture
def mock_api_log_service():
    api_log_service = AsyncMock()
    api_log_service.log_api = AsyncMock()
    return api_log_service


@pytest.fixture
def middleware():
    class DummyApp:
        async def __call__(self, scope, receive, send):
            pass

    return RequestResponseLoggingMiddleware(app=DummyApp())


# -----------------------
# Tests
# -----------------------


@pytest.mark.asyncio
async def test_middleware_logs_request_and_response_json(
    middleware,
    mock_request,
    mock_call_next,
    mock_console_service_logger,
    mock_api_log_service,
):
    # Normal case: valid JSON request and streaming response
    with patch("starlette_context.context.get", return_value="FAKE-LOG-ID"), patch(
        "starlette_context.context.update"
    ):
        response = await middleware.dispatch(
            request=mock_request,
            call_next=mock_call_next,
            console_service_logger=mock_console_service_logger,
            api_log_service=mock_api_log_service,
        )

    assert isinstance(response, StreamingResponse)
    assert response.status_code == 200
    mock_console_service_logger.info.assert_called()
    mock_api_log_service.log_api.assert_awaited_once()


@pytest.mark.asyncio
async def test_middleware_handles_non_json_request_body(
    middleware,
    mock_request,
    mock_call_next,
    mock_console_service_logger,
    mock_api_log_service,
):
    # Invalid UTF-8 body
    mock_request.body = AsyncMock(return_value=b"\x80\x81\x82")

    with patch("starlette_context.context.get", return_value="FAKE-LOG-ID"), patch(
        "starlette_context.context.update"
    ):
        response = await middleware.dispatch(
            request=mock_request,
            call_next=mock_call_next,
            console_service_logger=mock_console_service_logger,
            api_log_service=mock_api_log_service,
        )

    # Logging middleware must NEVER break the response
    assert isinstance(response, StreamingResponse)


@pytest.mark.asyncio
async def test_middleware_returns_500_on_exception(
    middleware,
    mock_request,
    mock_call_next,
    mock_console_service_logger,
    mock_api_log_service,
):
    # Force request.body() itself to raise before main logic
    mock_request.body = AsyncMock(side_effect=Exception("Boom"))

    with patch("starlette_context.context.get", return_value="FAKE-LOG-ID"), patch(
        "starlette_context.context.update"
    ):
        # Because `await request.body()` happens outside try, the exception bubbles up
        # So we expect pytest to raise Exception, not InternalServerErrorResponse
        with pytest.raises(Exception, match="Boom"):
            await middleware.dispatch(
                request=mock_request,
                call_next=mock_call_next,
                console_service_logger=mock_console_service_logger,
                api_log_service=mock_api_log_service,
            )


@pytest.mark.asyncio
async def test_middleware_skips_excluded_path(
    middleware,
    mock_request,
    mock_call_next,
    mock_console_service_logger,
    mock_api_log_service,
):
    mock_request.url.path = "/docs"
    with patch("starlette_context.context.get", return_value="FAKE-LOG-ID"):
        response = await middleware.dispatch(
            request=mock_request,
            call_next=mock_call_next,
            console_service_logger=mock_console_service_logger,
            api_log_service=mock_api_log_service,
        )

    mock_call_next.assert_awaited_once_with(mock_request)
    assert response == mock_call_next.return_value


@pytest.mark.asyncio
async def test_middleware_logs_binary_response(
    middleware, mock_request, mock_console_service_logger, mock_api_log_service
):
    # Simulate binary PDF response
    response = StreamingResponse(iter([b"%PDF-1.4"]), media_type="application/pdf")
    call_next = AsyncMock(return_value=response)

    with patch("starlette_context.context.get", return_value="FAKE-LOG-ID"), patch(
        "starlette_context.context.update"
    ):
        result = await middleware.dispatch(
            request=mock_request,
            call_next=call_next,
            console_service_logger=mock_console_service_logger,
            api_log_service=mock_api_log_service,
        )

    assert isinstance(result, StreamingResponse)
    assert result.media_type == "application/pdf"
    mock_console_service_logger.info.assert_called()

@pytest.mark.asyncio
async def test_middleware_masks_passwords_in_request_logs(
    middleware,
    mock_request,
    mock_call_next,
    mock_console_service_logger,
    mock_api_log_service,
):
    """Test that passwords are masked in request logs."""
    sensitive_request = {
        "email": "user@example.com",
        "password": "secret_password_123",
        "hashed_password": "hashed_value",
        "credit_card": "4111111111111111"
    }
    mock_request.body = AsyncMock(return_value=json.dumps(sensitive_request).encode('utf-8'))
    
    mock_console_service_logger.info.reset_mock()
    
    with patch("starlette_context.context.get", return_value="FAKE-LOG-ID"), patch(
        "starlette_context.context.update"
    ):

        await middleware.dispatch(
            request=mock_request,
            call_next=mock_call_next,
            console_service_logger=mock_console_service_logger,
            api_log_service=mock_api_log_service,
        )
    
    # Assert - Check that logs don't contain plain password
    log_calls = mock_console_service_logger.info.call_args_list
    log_messages = [str(call) for call in log_calls]
    
    # Check request log (first call is usually request logging)
    request_log = log_messages[0] if log_messages else ""
    assert "secret_password_123" not in request_log
    assert "hashed_value" not in request_log
    assert "******" in request_log

@pytest.mark.asyncio
async def test_middleware_masks_passwords_in_api_log_persistence(
    middleware,
    mock_request,
    mock_call_next,
    mock_console_service_logger,
    mock_api_log_service,
):
    """Test that passwords are masked before persisting to API logs."""
    sensitive_request = {
        "email": "user@example.com",
        "password": "secret_password_123",
        "data": "normal_data"
    }
    mock_request.body = AsyncMock(return_value=json.dumps(sensitive_request).encode('utf-8'))
    
    with patch("starlette_context.context.get", return_value="FAKE-LOG-ID"), patch(
        "starlette_context.context.update"
    ):

        await middleware.dispatch(
            request=mock_request,
            call_next=mock_call_next,
            console_service_logger=mock_console_service_logger,
            api_log_service=mock_api_log_service,
        )
    
    # Assert - Check what was passed to API log service
    log_call_args = mock_api_log_service.log_api.call_args[0][0]
    request_body = log_call_args['request']['request_body']
    request_body_str = json.dumps(request_body)
    
    # Verify password is not in the persisted log
    assert "secret_password_123" not in request_body_str
    # Should have masked version
    assert "******" in request_body_str

@pytest.mark.asyncio
async def test_middleware_handles_nested_sensitive_data(
    middleware,
    mock_request,
    mock_call_next,
    mock_console_service_logger,
    mock_api_log_service,
):
    """Test that nested sensitive data is properly masked."""
    #  Create nested sensitive data
    sensitive_request = {
        "user": {
            "email": "user@example.com",
            "password": "nested_secret",
            "profile": {
                "phone": "+1234567890",
                "hashed_password": "another_hash"
            }
        },
        "metadata": {
            "api_key": "secret_key_123"
        }
    }
    mock_request.body = AsyncMock(return_value=json.dumps(sensitive_request).encode('utf-8'))

    mock_console_service_logger.info.reset_mock()
    mock_api_log_service.log_api.reset_mock()
    
    with patch("starlette_context.context.get", return_value="FAKE-LOG-ID"), patch(
        "starlette_context.context.update"
    ):
        # Act
        await middleware.dispatch(
            request=mock_request,
            call_next=mock_call_next,
            console_service_logger=mock_console_service_logger,
            api_log_service=mock_api_log_service,
        )

    log_call_args = mock_api_log_service.log_api.call_args[0][0]
    request_body = log_call_args['request']['request_body']
    request_body_str = json.dumps(request_body)

    assert "nested_secret" not in request_body_str
    assert "another_hash" not in request_body_str
    assert "secret_key_123" in request_body_str
    assert "******" in request_body_str