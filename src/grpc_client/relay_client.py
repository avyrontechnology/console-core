"""Relay client (talko-role caller: console-core relay ko bulata hai).

Server counterpart: src/components/relay/rpc.py (RelayServiceGRPC).
Dono ek hi proto (relay.proto) ke do roop hain — Stub idhar,
Servicer udhar. Demo/test me yehi class "talko" ka role karti hai.
"""

from collections.abc import AsyncIterator

import grpc

from src.core.environment import ENV
from src.grpc_client.console_grpc_client import ConsoleGRPCClient
from src.loggers.console_rpc_logger import ConsoleRpcLogger
from src.pub import relay_pb2, relay_pb2_grpc

logger = ConsoleRpcLogger.get_logger()


class RelayClient(ConsoleGRPCClient):
    def __init__(self, server_address: str = "", api_key: str = ""):
        super().__init__(
            server_address=server_address or ENV.RELAY_GRPC_URL or "localhost:50051",
            api_key=api_key,
        )
        self.relay = relay_pb2_grpc.RelayServiceStub(self.channel)

    @ConsoleGRPCClient.call_with_retry
    async def route_call_status(
        self, call_id: str, vendor_config_id: str = "", target: str = "telephony"
    ) -> dict:
        request = relay_pb2.RouteCallStatusRequest(
            call_id=call_id, vendor_config_id=vendor_config_id, target=target
        )
        try:
            response = await self.relay.RouteCallStatus(
                request, timeout=self.DEFAULT_TIMEOUT
            )
            return {
                "call_id": response.call_id,
                "call_status": response.call_status,
                "connected": response.connected,
                "via": response.via,
            }
        except grpc.aio.AioRpcError as exc:
            logger.error(f"Relay RouteCallStatus failed for {call_id}: {exc.code()}")
            raise

    async def watch_call_status(
        self,
        call_id: str,
        vendor_config_id: str = "",
        target: str = "telephony",
        max_updates: int = 3,
        poll_interval_ms: int = 200,
    ) -> AsyncIterator[dict]:
        """Server-streaming caller. `async for` me chalao — har update
        aate hi milega, stream khatm hone ka wait nahi. Caller beech me
        tode (break) to generator band — server ko CANCEL jata hai."""
        request = relay_pb2.WatchCallStatusRequest(
            call_id=call_id,
            vendor_config_id=vendor_config_id,
            target=target,
            max_updates=max_updates,
            poll_interval_ms=poll_interval_ms,
        )
        try:
            async for update in self.relay.WatchCallStatus(request):
                yield {
                    "call_id": update.call_id,
                    "call_status": update.call_status,
                    "connected": update.connected,
                    "seq": update.seq,
                }
        except grpc.aio.AioRpcError as exc:
            logger.error(f"Relay WatchCallStatus failed for {call_id}: {exc.code()}")
            raise
