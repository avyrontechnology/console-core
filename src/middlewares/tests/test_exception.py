from contextlib import contextmanager
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio
from fastapi import Request, Response
from starlette_context import _request_scope_context_storage

from src.loggers.console_rpc_logger import ConsoleRpcLogger
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
async def mock_logger():
    logger = MagicMock()
    logger.debug = MagicMock()
    logger.info = MagicMock()
    logger.error = MagicMock()
    logger.warning = MagicMock()
    return logger


@pytest_asyncio.fixture
async def mock_request():
    request = MagicMock(spec=Request)
    request.url = "https://console-service.example.com/test"
    request.method = "GET"
    return request


@pytest_asyncio.fixture
async def error_middleware(mock_logger):
    middleware = ErrorHandlingMiddleware(app=None)
    middleware.logger = mock_logger
    return middleware


@pytest.mark.asyncio
async def test_dispatch_passes_through_200(mock_request, mock_logger, error_middleware):
    async def call_next(request):
        return Response(status_code=200)

    response = await error_middleware.dispatch(mock_request, call_next)
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_dispatch_logs_500_without_email(
    mock_request, mock_logger, error_middleware
):
    async def call_next(request):
        return Response(status_code=500)

    response = await error_middleware.dispatch(mock_request, call_next)
    assert response.status_code == 500
    mock_logger.warning.assert_called()


@pytest.mark.asyncio
async def test_dispatch_exception_returns_500_response(
    mock_request, mock_logger, error_middleware
):
    async def call_next(request):
        raise RuntimeError("boom")

    response = await error_middleware.dispatch(mock_request, call_next)
    assert response.status_code == 500
    mock_logger.error.assert_called()
