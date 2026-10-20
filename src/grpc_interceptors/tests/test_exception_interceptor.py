from unittest.mock import MagicMock

import grpc
import pytest
from grpc_interceptor.exceptions import GrpcException

from src.grpc_interceptors.exception import AsyncExceptionToStatusInterceptor


class AbortError(Exception):
    """Mirrors what grpc.aio raises from ServicerContext.abort."""

    def __init__(self, code, details):
        super().__init__(f"{code}: {details}")
        self.code = code
        self.details = details


class FakeContext:
    def __init__(self):
        self.aborted: list[tuple[grpc.StatusCode, str]] = []

    async def abort(self, code, details):
        self.aborted.append((code, details))
        raise AbortError(code, details)


@pytest.mark.asyncio
async def test_grpc_exception_reaches_the_client_untouched():
    """abort() carries code + details; re-raising made grpc substitute the
    exception text ("Unexpected <class ...>: ") for the real message."""
    interceptor = AsyncExceptionToStatusInterceptor()
    context = FakeContext()

    async def handler(request, ctx):
        raise GrpcException(
            status_code=grpc.StatusCode.FAILED_PRECONDITION, details="Insufficient balance"
        )

    with pytest.raises(AbortError) as excinfo:
        await interceptor.intercept(handler, object(), context, "/svc/Method")

    assert excinfo.value.code == grpc.StatusCode.FAILED_PRECONDITION
    assert excinfo.value.details == "Insufficient balance"
    assert context.aborted == [(grpc.StatusCode.FAILED_PRECONDITION, "Insufficient balance")]


@pytest.mark.asyncio
async def test_streaming_path_aborts_with_status():
    interceptor = AsyncExceptionToStatusInterceptor()
    context = FakeContext()

    async def handler(request, ctx):
        raise GrpcException(status_code=grpc.StatusCode.INTERNAL, details="boom")
        yield  # pragma: no cover - makes this an async generator

    stream = await interceptor.intercept(handler, object(), context, "/svc/Stream")
    with pytest.raises(AbortError) as excinfo:
        async for _ in stream:
            pass  # pragma: no cover

    assert excinfo.value.code == grpc.StatusCode.INTERNAL
    assert excinfo.value.details == "boom"


@pytest.mark.asyncio
async def test_non_grpc_exceptions_are_not_swallowed():
    interceptor = AsyncExceptionToStatusInterceptor()

    async def handler(request, ctx):
        raise ValueError("unexpected")

    with pytest.raises(ValueError):
        await interceptor.intercept(handler, object(), MagicMock(), "/svc/Method")


@pytest.mark.asyncio
async def test_successful_call_passes_response_through():
    interceptor = AsyncExceptionToStatusInterceptor()
    context = FakeContext()

    async def handler(request, ctx):
        return "response-value"

    assert await interceptor.intercept(handler, object(), context, "/svc/Method") == "response-value"
    assert context.aborted == []