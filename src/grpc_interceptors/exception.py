from typing import Any, Callable
import grpc
from grpc_interceptor.exceptions import GrpcException
from grpc_interceptor.server import AsyncServerInterceptor


class AsyncExceptionToStatusInterceptor(AsyncServerInterceptor):
    async def intercept(
        self,
        method: Callable,
        request_or_iterator: Any,
        context: grpc.ServicerContext,
        method_name: str,
    ) -> Any:
        try:
            response_or_iterator = method(request_or_iterator, context)

            # If method returns a coroutine (i.e., unary), await it
            if not hasattr(response_or_iterator, "__aiter__"):
                return await response_or_iterator
        except GrpcException as e:
            await context.set_code(e.status_code)
            await context.set_details(e.details)
            raise

        # If it's a streaming method (returns async generator), yield items
        return self._intercept_streaming(response_or_iterator, context)

    async def _intercept_streaming(self, iterator, context):
        try:
            async for item in iterator:
                yield item
        except GrpcException as e:
            await context.set_code(e.status_code)
            await context.set_details(e.details)
            raise
