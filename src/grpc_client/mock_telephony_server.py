"""Mock telephony plane (DEV/TEST ONLY — prod image me mat jane do).

Fake TelephonyControl server: GetCallStatus (canned) + Hangup (dedup).
Real vendor plane (OTOBA) aane tak isi se client development + tests.

Chalao:  python -m src.grpc_client.mock_telephony_server
        (TELEPHONY_GRPC_URL=localhost:50052 par client connect karega)

Test knobs (class attributes — har test se pehle reset karo):
- MockTelephonyControl.fail_times: pehle N calls par UNAVAILABLE
  (retry test ke liye)
- MockTelephonyControl.require_api_key: set karne par x-api-key
  verify hoga, galat key par UNAUTHENTICATED (auth test ke liye)
- Dedup proof: hangup_actions (asli kaam) vs hangup_calls (aye kitne).
  Same key dobara = calls badhega, actions nahi.
"""

import asyncio

import grpc

from src.loggers.console_rpc_logger import ConsoleRpcLogger
from src.pub import telephony_pb2, telephony_pb2_grpc
from src.pub.telephony_pb2_grpc import add_TelephonyControlServicer_to_server

logger = ConsoleRpcLogger.get_logger()

PORT = 50052


class MockTelephonyControl(telephony_pb2_grpc.TelephonyControlServicer):
    fail_times: int = 0
    require_api_key: str = ""
    calls: int = 0
    hangup_calls: int = 0
    hangup_actions: int = 0
    seen_keys: dict = {}

    @classmethod
    def reset(cls):
        cls.fail_times = 0
        cls.require_api_key = ""
        cls.calls = 0
        cls.hangup_calls = 0
        cls.hangup_actions = 0
        cls.seen_keys = {}

    def _check_auth(self, context):
        if MockTelephonyControl.require_api_key:
            metadata = dict(context.invocation_metadata())
            if metadata.get("x-api-key") != MockTelephonyControl.require_api_key:
                return False
        return True

    async def GetCallStatus(self, request, context):
        MockTelephonyControl.calls += 1
        if not self._check_auth(context):
            await context.abort(grpc.StatusCode.UNAUTHENTICATED, "Invalid API key")
        if MockTelephonyControl.fail_times > 0:
            MockTelephonyControl.fail_times -= 1
            await context.abort(grpc.StatusCode.UNAVAILABLE, "mock transient failure")
        return telephony_pb2.CallStatusResponse(
            call_id=request.call_id,
            call_status="in-progress",
            connected=True,
        )

    async def Hangup(self, request, context):
        """Dedup on x-idempotency-key metadata. Same key dobara aaye to
        purana response wapas, naya action nahi. Key na ho to har call
        naya action (unsafe caller — aise mat bhejo)."""
        MockTelephonyControl.hangup_calls += 1
        if not self._check_auth(context):
            await context.abort(grpc.StatusCode.UNAUTHENTICATED, "Invalid API key")
        if MockTelephonyControl.fail_times > 0:
            MockTelephonyControl.fail_times -= 1
            await context.abort(grpc.StatusCode.UNAVAILABLE, "mock transient failure")
        metadata = dict(context.invocation_metadata())
        key = metadata.get("x-idempotency-key", "")
        if key and key in MockTelephonyControl.seen_keys:
            stored = MockTelephonyControl.seen_keys[key]
            return telephony_pb2.HangupResponse(
                success=stored["success"],
                message=stored["message"] + " (duplicate suppressed)",
                call_id=stored["call_id"],
            )
        MockTelephonyControl.hangup_actions += 1
        response = {"success": True, "message": "hung up", "call_id": request.call_id}
        if key:
            MockTelephonyControl.seen_keys[key] = response
        return telephony_pb2.HangupResponse(
            success=response["success"],
            message=response["message"],
            call_id=response["call_id"],
        )


async def serve(port: int = PORT):
    server = grpc.aio.server()
    add_TelephonyControlServicer_to_server(MockTelephonyControl(), server)
    server.add_insecure_port(f"[::]:{port}")
    await server.start()
    logger.info(f"Mock telephony plane serving GetCallStatus on :{port}")
    await server.wait_for_termination()


if __name__ == "__main__":
    asyncio.run(serve())
