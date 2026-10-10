from typing import Any, Callable
import grpc
from grpc_interceptor.server import AsyncServerInterceptor
from grpc_interceptor.exceptions import GrpcException

'''
Client side Handling Example
try:
    response = await stub.YourRpcMethod(request, metadata=[("x-api-key", "WRONG_KEY")])
except grpc.aio.AioRpcError as e:
    if e.code() == grpc.StatusCode.UNAUTHENTICATED:
        raise ServiceNotAuthorizedError(e.details())
    else:
        raise

'''
class UnauthenticatedError(GrpcException):
    status_code = grpc.StatusCode.UNAUTHENTICATED
    details = "Invalid API key"

class ApiKeyAuthInterceptor(AsyncServerInterceptor):

    def __init__(self, valid_keys: dict):
        self.valid_keys = valid_keys

    async def intercept(
        self,
        method: Callable,
        request_or_iterator: Any,
        context: grpc.ServicerContext,
        method_name: str,
    ) -> Any:
        metadata = dict(context.invocation_metadata())
        api_key = metadata.get("x-api-key")

        if api_key not in self.valid_keys.values():
            await context.abort(grpc.StatusCode.UNAUTHENTICATED, "Invalid API key")
 

        # Call the method (unary or stream)
        response_or_iterator = method(request_or_iterator, context)

        if hasattr(response_or_iterator, "__aiter__"):
            return self._intercept_streaming(response_or_iterator, context)

        return await response_or_iterator

    async def _intercept_streaming(self, iterator, context):
        try:
            async for item in iterator:
                yield item
        except grpc.RpcError as e:
            await context.abort(e.code(), e.details())
