"""Base class for outbound gRPC clients (console-core as CLIENT).

Template: talko's TalkoGRPCClient (talko/src/grpc_client/grpc_client.py).
Differences from talko's version:
- server address + api key come from console-core ENV
  (TELEPHONY_GRPC_URL / TELEPHONY_GRPC_API_KEY), not hardcoded
  localhost:50051 (talko's NOTE says its literals are dormant leftovers).
- timeout is set per-call (deadline), so a slow callee can't hang us.

Channel rule (yaad rakhna): channel banane me TCP+HTTP/2 handshake
hota hai — isliye channel ko REUSE karo (factory me singleton),
har call par naya channel mat banao.
"""

import asyncio
import base64
from functools import wraps

import grpc

from src.core.environment import ENV
from src.grpc_client.client_interceptor import ApiKeyClientInterceptor
from src.loggers.console_rpc_logger import ConsoleRpcLogger

logger = ConsoleRpcLogger.get_logger()


class ConsoleGRPCClient:
    MAX_RETRIES = 3
    RETRY_DELAY = 2  # seconds, linear backoff between attempts
    DEFAULT_TIMEOUT = 5  # seconds per attempt (deadline)

    def __init__(self, server_address: str = "", api_key: str = ""):
        self.server_address = server_address or ENV.TELEPHONY_GRPC_URL
        self.api_key = api_key or ENV.TELEPHONY_GRPC_API_KEY
        logger.info(f"Initializing ConsoleGRPCClient -> {self.server_address}")
        self.channel = self.create_channel(self.server_address)

    def create_channel(self, server_address: str):
        interceptor = ApiKeyClientInterceptor(api_key=self.api_key)
        if ENV.CERT != "None":
            logger.info(f"Secure gRPC channel -> {server_address}")
            ca_cert = base64.b64decode(ENV.CERT)
            credentials = grpc.ssl_channel_credentials(root_certificates=ca_cert)
            return grpc.aio.secure_channel(
                server_address, credentials, interceptors=[interceptor]
            )
        logger.info(f"Insecure gRPC channel -> {server_address}")
        return grpc.aio.insecure_channel(server_address, interceptors=[interceptor])

    async def close_channel(self):
        if self.channel:
            await self.channel.close()

    @staticmethod
    def call_with_retry(func):
        """Retry transient failures; GetCallStatus is read-only so
        retrying is side-effect free (Hangup jaisa nahi)."""

        @wraps(func)
        async def wrapper(*args, **kwargs):
            for attempt in range(ConsoleGRPCClient.MAX_RETRIES):
                try:
                    return await func(*args, **kwargs)
                except grpc.aio.AioRpcError as exc:
                    logger.error(f"gRPC error in {func.__name__}: {exc.code()} {exc.details()}")
                    if attempt < ConsoleGRPCClient.MAX_RETRIES - 1:
                        await asyncio.sleep(ConsoleGRPCClient.RETRY_DELAY)
                    else:
                        logger.error(f"{func.__name__} failed after {ConsoleGRPCClient.MAX_RETRIES} attempts")
                        raise

        return wrapper
