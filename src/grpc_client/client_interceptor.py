"""Client-side API-key interceptor (outbound).

Mirror of talko's TalkoApiKeyClientInterceptor: attaches
``x-api-key`` metadata to every unary-unary call so the callee's
server-side interceptor (like our own ApiKeyAuthInterceptor) can
verify us. Server interceptors VERIFY keys, client interceptors ATTACH
them — yehi dono ka farak hai, interview me yahi poocha jata hai.
"""

from grpc.aio import UnaryUnaryClientInterceptor


class ApiKeyClientInterceptor(UnaryUnaryClientInterceptor):
    def __init__(self, api_key: str):
        self.api_key = api_key

    async def intercept_unary_unary(self, continuation, call_details, request):
        metadata = list(call_details.metadata or [])
        metadata.append(("x-api-key", self.api_key))

        class _ClientCallDetails:
            def __init__(self):
                self.method = call_details.method
                self.timeout = call_details.timeout
                self.metadata = metadata
                self.credentials = getattr(call_details, "credentials", None)
                self.wait_for_ready = getattr(call_details, "wait_for_ready", None)
                self.compression = getattr(call_details, "compression", None)

        return await continuation(_ClientCallDetails(), request)
