"""Relay servicer: talko/obotaai -> console-core -> target plane.

Yehi Phase-3 hai. talko seedha plane ko call karne ke bajaye
console-core ko bolta hai; console-core apne Phase-2 client se
forward karta hai. Fayde:
- auth/discovery ek jagah (rpc_main ka ApiKeyAuthInterceptor free me)
- rate-limit + audit ek jagah (neeche RelayRateLimiter/AuditTrail)
- talko ko plane ka address janne ki zaroorat nahi

Deadline budget (cascade timeout se bachne ke liye):
caller (5s) -> relay yahan 3s deta hai plane ko -> 2s bachta hai
jawab wapas bhejne ke liye. Har hop apna timeout chhota rakhta hai —
poora budget ek hop kha jaye to upar wala bekar me wait karta hai.

Target validation: unknown target par INVALID_ARGUMENT (fail fast),
taaki typo wale request plane tak pahuche hi nahi.
"""

import asyncio
import time
from collections import deque

import grpc

from src.core.environment import ENV
from src.grpc_client.factory import GrpcClientFactory, TELEPHONY
from src.loggers.console_rpc_logger import ConsoleRpcLogger
from src.pub import relay_pb2
from src.pub.relay_pb2_grpc import RelayServiceServicer

logger = ConsoleRpcLogger.get_logger()

RELAY_TIMEOUT = 3  # seconds for the downstream hop (caller budget 5s)


class RelayRateLimiter:
    """Fixed-window per-caller limiter (default 60 calls/min/key).

    Kyun fixed-window (sliding nahi): code 15 line, samajh 1 minute,
    relay jaise low-QPS gate ke liye kaafi. High-QPS hota to token
    bucket/Redis chahiye hota — woh Phase-3c hai, abhi nahi.
    """

    WINDOW_SECONDS = 60

    def __init__(self, limit_per_minute: int = 60):
        self.limit = limit_per_minute
        self._hits: dict = {}  # key -> [window_start, count]

    def allow(self, key: str) -> bool:
        now = time.monotonic()
        start, count = self._hits.get(key, (now, 0))
        if now - start >= self.WINDOW_SECONDS:
            start, count = now, 0
        if count >= self.limit:
            return False
        self._hits[key] = (start, count + 1)
        return True


class AuditTrail:
    """Bounded in-memory ring: kaun/kya/kab/natija.

    Prod me isko DB/queue me bhejo (yeh shape sikhane ke liye memory
    me hai — restart par ud jayega, isliye sirf trail, source of
    truth nahi). deque(maxlen) se memory leak nahi hota.
    """

    def __init__(self, maxlen: int = 1000):
        self.records = deque(maxlen=maxlen)

    def record(self, entry: dict):
        entry["ts"] = time.time()
        self.records.append(entry)
        logger.info(f"Relay audit: {entry}")


class RelayServiceGRPC(RelayServiceServicer):
    def __init__(
        self,
        logger=logger,
        telephony_client=None,
        rate_limiter=None,
        audit=None,
    ):
        self.logger = logger
        # Injectable for tests (in-process mock). Prod me None -> factory.
        self._telephony_client = telephony_client
        try:
            default_limit = int(ENV.RELAY_RATE_LIMIT_PER_MINUTE or 60)
        except ValueError:
            default_limit = 60
        self.limiter = rate_limiter or RelayRateLimiter(default_limit)
        self.audit = audit or AuditTrail()

    def _caller(self, context) -> str:
        metadata = dict(context.invocation_metadata())
        return metadata.get("x-api-key", "anonymous")

    async def _gate(self, request, context, method: str):
        """Target + rate-limit check. Returns (caller, target, started).
        Abort kare to wahi raise hota hai — caller ko aage badhne hi
        nahi deta (fail fast). Dono methods (unary + streaming) share."""
        started = time.monotonic()
        caller = self._caller(context)
        target = (request.target or "telephony").lower()
        if target != "telephony":
            self.audit.record(
                {
                    "method": method,
                    "caller": caller,
                    "call_id": request.call_id,
                    "outcome": "rejected",
                    "reason": f"unknown target {request.target!r}",
                    "latency_ms": int((time.monotonic() - started) * 1000),
                }
            )
            await context.abort(
                grpc.StatusCode.INVALID_ARGUMENT,
                f"unknown relay target: {request.target!r}",
            )
        if not self.limiter.allow(f"{caller}:{method}"):
            self.audit.record(
                {
                    "method": method,
                    "caller": caller,
                    "call_id": request.call_id,
                    "outcome": "rejected",
                    "reason": "rate limit",
                    "latency_ms": int((time.monotonic() - started) * 1000),
                }
            )
            await context.abort(
                grpc.StatusCode.RESOURCE_EXHAUSTED, "relay rate limit exceeded"
            )
        return caller, target, started

    async def RouteCallStatus(self, request, context):
        caller, target, started = await self._gate(request, context, "RouteCallStatus")
        client = self._telephony_client or GrpcClientFactory.get_service(TELEPHONY)
        self.logger.info(
            f"Relay RouteCallStatus call_id={request.call_id} target={target}"
        )
        try:
            result = await client.get_call_status(
                call_id=request.call_id,
                vendor_config_id=request.vendor_config_id,
                timeout=RELAY_TIMEOUT,
            )
        except grpc.aio.AioRpcError:
            self.logger.error(f"Relay downstream failed call_id={request.call_id}")
            self.audit.record(
                {
                    "method": "RouteCallStatus",
                    "caller": caller,
                    "call_id": request.call_id,
                    "outcome": "error",
                    "reason": "downstream failed",
                    "latency_ms": int((time.monotonic() - started) * 1000),
                }
            )
            raise
        self.audit.record(
            {
                "method": "RouteCallStatus",
                "caller": caller,
                "call_id": request.call_id,
                "outcome": "ok",
                "latency_ms": int((time.monotonic() - started) * 1000),
            }
        )
        return relay_pb2.RouteCallStatusResponse(
            call_id=result["call_id"],
            call_status=result["call_status"],
            connected=result["connected"],
            via="grpc",
        )

    async def WatchCallStatus(self, request, context):
        """Phase-4: server streaming. Caller ek request bhejta hai,
        relay N updates stream karta hai (khud plane ko poll karke).

        Streaming ke 3 niyam (yaad rakhna):
        1. `yield` per update — poora list ikattha karke mat bhejo.
        2. `context.cancelled()` check — caller beech me gaya to
           loop todo (warna dead caller ke liye plane ko poll karte
           rahoge). Note: ye SYNC bool hai (await nahi); purane grpc
           me `is_active()` tha — version ka farak hai.
        3. Rate-limit stream START par ek baar (har update par nahi).
        """
        caller, target, started = await self._gate(request, context, "WatchCallStatus")
        max_updates = request.max_updates or 3
        interval = (request.poll_interval_ms or 500) / 1000
        client = self._telephony_client or GrpcClientFactory.get_service(TELEPHONY)
        sent = 0
        try:
            for seq in range(1, max_updates + 1):
                if context.cancelled():
                    break
                result = await client.get_call_status(
                    call_id=request.call_id,
                    vendor_config_id=request.vendor_config_id,
                    timeout=RELAY_TIMEOUT,
                )
                sent += 1
                yield relay_pb2.CallStatusUpdate(
                    call_id=result["call_id"],
                    call_status=result["call_status"],
                    connected=result["connected"],
                    seq=seq,
                )
                await asyncio.sleep(interval)
        except grpc.aio.AioRpcError:
            self.logger.error(f"Relay watch downstream failed call_id={request.call_id}")
            self.audit.record(
                {
                    "method": "WatchCallStatus",
                    "caller": caller,
                    "call_id": request.call_id,
                    "outcome": "error",
                    "reason": "downstream failed",
                    "latency_ms": int((time.monotonic() - started) * 1000),
                }
            )
            raise
        self.audit.record(
            {
                "method": "WatchCallStatus",
                "caller": caller,
                "call_id": request.call_id,
                "outcome": "ok",
                "updates": sent,
                "latency_ms": int((time.monotonic() - started) * 1000),
            }
        )
