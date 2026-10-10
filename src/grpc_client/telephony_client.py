"""Telephony control-plane client (Phase-2: GetCallStatus + Hangup).

Contract: src/protos/telephony.proto (copied from talko).
Template: talko's TalkoTelephonyServiceClient.

Idempotency rule (Hangup): key metadata me jata hai
(x-idempotency-key), proto me nahi — isse talko ke contract se
divergence nahi hota. Key retry-loop ke BAHAR ek baar banti hai;
retry-wrapped inner method wahi key reuse karta hai. Agar key loop
ke andar banti to har retry par nayi key = server ko har attempt
naya action lagta = double hangup. Yehi bug sabse common hai.
"""

import uuid

import grpc

from src.grpc_client.console_grpc_client import ConsoleGRPCClient
from src.loggers.console_rpc_logger import ConsoleRpcLogger
from src.pub import telephony_pb2, telephony_pb2_grpc

logger = ConsoleRpcLogger.get_logger()

IDEMPOTENCY_KEY_HEADER = "x-idempotency-key"


class TelephonyClient(ConsoleGRPCClient):
    def __init__(self, server_address: str = "", api_key: str = ""):
        super().__init__(server_address=server_address, api_key=api_key)
        self.control = telephony_pb2_grpc.TelephonyControlStub(self.channel)

    @ConsoleGRPCClient.call_with_retry
    async def get_call_status(
        self, call_id: str, vendor_config_id: str = "", timeout: float = 0
    ) -> dict:
        """timeout=0 matlab DEFAULT_TIMEOUT. Relay jaise caller apna
        chhota deadline de sakte hain (budget chaining — neeche samjhaya)."""
        request = telephony_pb2.CallStatusRequest(
            call_id=call_id, vendor_config_id=vendor_config_id
        )
        try:
            response = await self.control.GetCallStatus(
                request, timeout=timeout or self.DEFAULT_TIMEOUT
            )
            return {
                "call_id": response.call_id or call_id,
                "call_status": response.call_status,
                "connected": response.connected,
            }
        except grpc.aio.AioRpcError as exc:
            logger.error(f"gRPC GetCallStatus failed for {call_id}: {exc.code()}")
            raise

    async def hangup_call(
        self,
        call_id: str,
        vendor_config_id: str = "",
        enable_ai_bridge: bool = False,
        idempotency_key: str = "",
    ) -> dict:
        """Hangup with idempotent retry. Key ek baar banti hai (yahan),
        retry loop (inner method) use reuse karta hai. Caller apni key
        de sake to do — nahi to call_id-scoped uuid banta hai."""
        key = idempotency_key or f"{call_id}:{uuid.uuid4()}"
        return await self._hangup_with_key(
            call_id=call_id,
            vendor_config_id=vendor_config_id,
            enable_ai_bridge=enable_ai_bridge,
            idempotency_key=key,
        )

    @ConsoleGRPCClient.call_with_retry
    async def _hangup_with_key(
        self,
        call_id: str,
        vendor_config_id: str,
        enable_ai_bridge: bool,
        idempotency_key: str,
    ) -> dict:
        request = telephony_pb2.HangupRequest(
            call_id=call_id,
            vendor_config_id=vendor_config_id,
            enable_ai_bridge=enable_ai_bridge,
        )
        try:
            response = await self.control.Hangup(
                request,
                timeout=self.DEFAULT_TIMEOUT,
                metadata=[(IDEMPOTENCY_KEY_HEADER, idempotency_key)],
            )
            return {
                "success": response.success,
                "message": response.message,
                "call_id": response.call_id or call_id,
                "idempotency_key": idempotency_key,
            }
        except grpc.aio.AioRpcError as exc:
            logger.error(f"gRPC Hangup failed for {call_id}: {exc.code()}")
            raise
