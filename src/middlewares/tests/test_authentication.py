from uuid import UUID
import json
from contextlib import contextmanager
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio
from fastapi import Request, Response
from starlette_context import _request_scope_context_storage, context

from src.components.auth.util import AuthUtility
from src.components.common.response import (
    InternalServerErrorResponse,
    UnauthorizedResponse,
)
from src.components.session_mangement.models import UserSession
from src.components.session_mangement.services import UserSessionService
from src.loggers.console_service_logger import ConsoleServiceLogger
from src.middlewares import AuthMiddleware


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
async def auth_middleware():
    return AuthMiddleware(app=None)


@pytest_asyncio.fixture
async def mock_request():
    request = MagicMock(spec=Request)
    request.headers = {}
    request.state = MagicMock()
    request.url.path = "/api/test"
    return request


@pytest_asyncio.fixture
async def mock_call_next():
    return AsyncMock(return_value=Response())


@pytest_asyncio.fixture
async def mock_auth_utility():
    auth_utility = MagicMock(spec=AuthUtility)
    auth_utility.decode_access_token = MagicMock(
        return_value={"user_session_id": "123", "user_id": "456"}
    )
    return auth_utility


@pytest_asyncio.fixture
async def mock_user_session_service():
    user_session_service = MagicMock(spec=UserSessionService)
    user_session_service.get_user_session = AsyncMock(
        return_value=UserSession(id="123", is_active=True)
    )
    return user_session_service


@pytest_asyncio.fixture
async def mock_console_service_logger():
    return MagicMock(spec=ConsoleServiceLogger)


@pytest.mark.asyncio
async def test_excluded_path(auth_middleware, mock_request, mock_call_next, mock_console_service_logger):
    from types import SimpleNamespace

    mock_request.url.path = "/console-service/v1/do_login"
    mock_request.scope = {"route": SimpleNamespace(name="do_login")}
    response = await auth_middleware.dispatch(mock_request, mock_call_next, console_service_logger=mock_console_service_logger)
    assert response == mock_call_next.return_value
    mock_call_next.assert_called_once_with(mock_request)


@pytest.mark.asyncio
async def test_missing_authorization_header(
    auth_middleware, mock_request, mock_call_next, mock_console_service_logger
):
    response = await auth_middleware.dispatch(
        mock_request, mock_call_next, console_service_logger=mock_console_service_logger
    )
    assert isinstance(response, UnauthorizedResponse)
    assert json.loads(response.body.decode())["detail"] == "Unauthorized User"
    mock_console_service_logger.error.assert_called_with(
        "Missing or invalid Authorization header"
    )


@pytest.mark.asyncio
async def test_invalid_authorization_header_format(
    auth_middleware, mock_request, mock_call_next, mock_console_service_logger
):
    mock_request.headers = {"Authorization": "Invalid"}
    response = await auth_middleware.dispatch(
        mock_request, mock_call_next, console_service_logger=mock_console_service_logger
    )
    assert isinstance(response, UnauthorizedResponse)
    assert json.loads(response.body.decode())["detail"] == "Unauthorized User"
    mock_console_service_logger.error.assert_called_with(
        "Missing or invalid Authorization header"
    )


@pytest.mark.asyncio
async def test_logout_path(
    auth_middleware, mock_request, mock_call_next, mock_console_service_logger
):
    mock_request.url.path = "/console-service/v1/logout"
    mock_request.headers = {"Authorization": "Bearer valid_token"}
    response = await auth_middleware.dispatch(
        mock_request, mock_call_next, console_service_logger=mock_console_service_logger
    )
    assert response == mock_call_next.return_value
    assert mock_request.state.token == "valid_token"
    mock_console_service_logger.info.assert_any_call("Logging out request...")
    mock_call_next.assert_called_once_with(mock_request)


@pytest.mark.asyncio
async def test_invalid_token(
    auth_middleware,
    mock_request,
    mock_call_next,
    mock_auth_utility,
    mock_console_service_logger,
):
    mock_request.headers = {"Authorization": "Bearer invalid_token"}
    mock_auth_utility.decode_access_token.return_value = None
    response = await auth_middleware.dispatch(
        mock_request,
        mock_call_next,
        auth_utility=mock_auth_utility,
        console_service_logger=mock_console_service_logger,
    )
    assert isinstance(response, UnauthorizedResponse)
    assert json.loads(response.body.decode())["detail"] == "Token is expired or invalid"
    mock_console_service_logger.error.assert_called_with("Invalid or expired token")


@pytest.mark.asyncio
async def test_missing_user_session_id(
    auth_middleware,
    mock_request,
    mock_call_next,
    mock_auth_utility,
    mock_console_service_logger,
):
    mock_request.headers = {"Authorization": "Bearer valid_token"}
    mock_auth_utility.decode_access_token.return_value = {"user_id": "456"}
    response = await auth_middleware.dispatch(
        mock_request,
        mock_call_next,
        auth_utility=mock_auth_utility,
        console_service_logger=mock_console_service_logger,
    )
    assert isinstance(response, UnauthorizedResponse)
    assert json.loads(response.body.decode())["detail"] == "Token is expired or invalid"
    mock_console_service_logger.error.assert_called_with(
        "User Session not found in token payload: None"
    )


@pytest.mark.asyncio
async def test_inactive_session(
    auth_middleware,
    mock_request,
    mock_call_next,
    mock_auth_utility,
    mock_user_session_service,
    mock_console_service_logger,
):
    mock_request.headers = {"Authorization": "Bearer valid_token"}
    mock_user_session_service.get_user_session.return_value = UserSession(
        id="123", is_active=False
    )
    response = await auth_middleware.dispatch(
        mock_request,
        mock_call_next,
        auth_utility=mock_auth_utility,
        user_session_service=mock_user_session_service,
        console_service_logger=mock_console_service_logger,
    )
    assert isinstance(response, UnauthorizedResponse)
    assert json.loads(response.body.decode())["detail"] == "Token is expired or invalid"
    mock_console_service_logger.info.assert_called_with(
        "Active session not found for user with session_id: 123"
    )


@pytest.mark.asyncio
async def test_successful_authentication(
    auth_middleware,
    mock_request,
    mock_call_next,
    mock_auth_utility,
    mock_user_session_service,
    mock_console_service_logger,
):
    mock_request.headers = {"Authorization": "Bearer valid_token"}
    response = await auth_middleware.dispatch(
        mock_request,
        mock_call_next,
        auth_utility=mock_auth_utility,
        user_session_service=mock_user_session_service,
        console_service_logger=mock_console_service_logger,
    )
    assert response == mock_call_next.return_value
    assert mock_request.state.user == {"user_session_id": "123", "user_id": "456"}
    assert context.get("user") == {"user_session_id": "123", "user_id": "456"}
    mock_console_service_logger.debug.assert_called_with(
        "Added state to request for user {'user_session_id': '123', 'user_id': '456'}"
    )
    mock_call_next.assert_called_once_with(mock_request)


@pytest.mark.asyncio
async def test_internal_server_error(
    auth_middleware,
    mock_request,
    mock_call_next,
    mock_auth_utility,
    mock_console_service_logger,
):
    mock_request.headers = {"Authorization": "Bearer valid_token"}
    mock_auth_utility.decode_access_token.side_effect = Exception("Unexpected error")
    response = await auth_middleware.dispatch(
        mock_request,
        mock_call_next,
        auth_utility=mock_auth_utility,
        console_service_logger=mock_console_service_logger,
    )
    assert isinstance(response, InternalServerErrorResponse)
    assert json.loads(response.body.decode())["detail"] == "Internal Server Error"
    mock_console_service_logger.error.assert_called_with(
        "Internal Server Error: Unexpected error"
    )

@pytest.mark.asyncio
async def test_api_key_success_flow():
    mock_request = MagicMock()
    mock_request.url.path = "/some/protected/path"
    mock_request.headers = {"API-KEY": "valid_key"}

    # call_next mock
    mock_call_next = AsyncMock(return_value="OK")

    # Mock API Key service return object
    mock_api_key_details = MagicMock(
        is_active=True,
        partner_id=UUID("12312312-3123-1231-2312-312312312312"),
        expires_at=None,
        scopes=["console:get_all_users"],
        user_context={"user_id": "99999999-9999-9999-9999-999999999999"},
        id=UUID("11111111-1111-1111-1111-111111111111"),
    )

    # Mock system admin user
    mock_admin_user = MagicMock(id= UUID("99999999-9999-9999-9999-999999999999"), role_id= UUID("77777777-7777-7777-7777-777777777777"))

    middleware = AuthMiddleware(app=MagicMock())

    # Patch dependencies
    with patch(
        "src.middlewares.authentication.ApiKeyService"
    ) as ApiKeyServiceMock, patch(
        "src.middlewares.authentication.UserRepository"
    ) as UserRepoMock, patch(
        "src.middlewares.authentication.ConsoleServiceLogger"
    ) as LoggerMock:

        api_key_service = ApiKeyServiceMock.return_value
        api_key_service.validate_api_key = AsyncMock(return_value=mock_api_key_details)

        user_repo = UserRepoMock.return_value
        user_repo.get_system_admin_user = AsyncMock(return_value=mock_admin_user)

        logger = LoggerMock.return_value

        # Run middleware
        response = await middleware._handle_api_key(
            request=mock_request,
            api_key="valid_key",
            call_next=mock_call_next,
            api_key_service=api_key_service,
            user_repository=user_repo,
            console_service_logger=logger,
        )

    # Assertions
    mock_call_next.assert_awaited_once()

    assert response == "OK"
    assert mock_request.state.user == {"user_id": UUID("99999999-9999-9999-9999-999999999999"), "partner_id": UUID("12312312-3123-1231-2312-312312312312"), "role_id": None}
    assert mock_request.state.api_key == {"scopes": ["console:get_all_users"], "key_id": "11111111-1111-1111-1111-111111111111"}


@pytest.mark.asyncio
async def test_api_key_invalid_branch():
    mock_request = MagicMock()
    mock_request.url.path = "/x"
    mock_request.headers = {"API-KEY": "invalid_key"}

    mock_call_next = AsyncMock()

    middleware = AuthMiddleware(app=MagicMock())

    api_key_service = MagicMock()
    api_key_service.validate_api_key = AsyncMock(return_value=None)

    user_repo = MagicMock()
    logger = MagicMock()

    response = await middleware._handle_api_key(
        request=mock_request,
        api_key="invalid_key",
        call_next=mock_call_next,
        api_key_service=api_key_service,
        user_repository=user_repo,
        console_service_logger=logger,
    )

    assert isinstance(response, UnauthorizedResponse)
    assert json.loads(response.body.decode())["detail"] == "Invalid API Key"


@pytest.mark.asyncio
async def test_api_key_inactive_branch():
    mock_request = MagicMock()
    mock_request.url.path = "/x"
    mock_request.headers = {"API-KEY": "inactive_key"}

    mock_call_next = AsyncMock()

    middleware = AuthMiddleware(app=MagicMock())

    api_key_details = MagicMock(is_active=False, partner_id= UUID("77777777-7777-7777-7777-777777777777"))

    api_key_service = MagicMock()
    api_key_service.validate_api_key = AsyncMock(return_value=api_key_details)

    user_repo = MagicMock()
    logger = MagicMock()

    response = await middleware._handle_api_key(
        request=mock_request,
        api_key="inactive_key",
        call_next=mock_call_next,
        api_key_service=api_key_service,
        user_repository=user_repo,
        console_service_logger=logger,
    )

    assert isinstance(response, UnauthorizedResponse)
    assert json.loads(response.body.decode())["detail"] == "Inactive API Key"


@pytest.mark.asyncio
async def test_api_key_system_admin_missing_branch():
    mock_request = MagicMock()
    mock_request.url.path = "/x"
    mock_request.headers = {"API-KEY": "valid_key"}

    mock_call_next = AsyncMock()

    middleware = AuthMiddleware(app=MagicMock())

    api_key_details = MagicMock(
        is_active=True,
        partner_id=UUID("99999999-9999-9999-9999-999999999999"),
        expires_at=None,
        scopes=[],
        user_context=None,
        id=UUID("22222222-2222-2222-2222-222222222222"),
    )

    api_key_service = MagicMock()
    api_key_service.validate_api_key = AsyncMock(return_value=api_key_details)

    user_repo = MagicMock()
    user_repo.get_system_admin_user = AsyncMock(return_value=None)

    logger = MagicMock()

    response = await middleware._handle_api_key(
        request=mock_request,
        api_key="valid_key",
        call_next=mock_call_next,
        api_key_service=api_key_service,
        user_repository=user_repo,
        console_service_logger=logger,
    )

    assert isinstance(response, UnauthorizedResponse)
    assert json.loads(response.body.decode())["detail"] == "System admin not found"
