"""Relay e2e tests: talko(role) -> relay -> mock plane.

Do in-process server: mock telephony plane (neeche) + relay server
(beech me, TelephonyClient inject karke). Caller RelayServiceStub
hai — bilkul waise jaise talko call karega.
"""

import grpc
import pytest
import pytest_asyncio

from src.components.relay.rpc import (
    AuditTrail,
    RelayRateLimiter,
    RelayServiceGRPC,
)
from src.grpc_client.mock_telephony_server import MockTelephonyControl
from src.grpc_client.relay_client import RelayClient
from src.grpc_client.telephony_client import TelephonyClient
from src.pub import relay_pb2
from src.pub.relay_pb2_grpc import (
    RelayServiceStub,
    add_RelayServiceServicer_to_server,
)
from src.pub.telephony_pb2_grpc import add_TelephonyControlServicer_to_server


@pytest_asyncio.fixture
async def plane_address():
    MockTelephonyControl.reset()
    server = grpc.aio.server()
    add_TelephonyControlServicer_to_server(MockTelephonyControl(), server)
    port = server.add_insecure_port("localhost:0")
    await server.start()
    yield f"localhost:{port}"
    await server.stop(None)
    MockTelephonyControl.reset()


@pytest_asyncio.fixture
async def relay_stub(plane_address):
    tele_client = TelephonyClient(server_address=plane_address, api_key="k")
    relay = RelayServiceGRPC(telephony_client=tele_client)
    server = grpc.aio.server()
    add_RelayServiceServicer_to_server(relay, server)
    port = server.add_insecure_port("localhost:0")
    await server.start()
    channel = grpc.aio.insecure_channel(f"localhost:{port}")
    yield RelayServiceStub(channel)
    await channel.close()
    await server.stop(None)
    await tele_client.close_channel()


@pytest.mark.asyncio
async def test_route_call_status_end_to_end(relay_stub):
    res = await relay_stub.RouteCallStatus(
        relay_pb2.RouteCallStatusRequest(call_id="call-20")
    )
    assert res.call_id == "call-20"
    assert res.call_status == "in-progress"
    assert res.connected is True
    assert res.via == "grpc"
    assert MockTelephonyControl.calls == 1  # plane tak pahucha


@pytest.mark.asyncio
async def test_route_unknown_target_rejected_fast(relay_stub):
    with pytest.raises(grpc.aio.AioRpcError) as exc_info:
        await relay_stub.RouteCallStatus(
            relay_pb2.RouteCallStatusRequest(call_id="call-21", target="nope")
        )
    assert exc_info.value.code() == grpc.StatusCode.INVALID_ARGUMENT
    assert MockTelephonyControl.calls == 0  # plane ko chhua tak nahi


@pytest.mark.asyncio
async def test_route_downstream_down_propagates():
    dead_client = TelephonyClient(server_address="localhost:1", api_key="k")
    relay = RelayServiceGRPC(telephony_client=dead_client)
    server = grpc.aio.server()
    add_RelayServiceServicer_to_server(relay, server)
    port = server.add_insecure_port("localhost:0")
    await server.start()
    channel = grpc.aio.insecure_channel(f"localhost:{port}")
    try:
        with pytest.raises(grpc.aio.AioRpcError):
            await channel.unary_unary("/relay.RelayService/RouteCallStatus")(
                relay_pb2.RouteCallStatusRequest(call_id="call-22").SerializeToString()
            )
    finally:
        await channel.close()
        await server.stop(None)
        await dead_client.close_channel()


@pytest_asyncio.fixture
async def relay_server(plane_address):
    """Relay server ka address + RelayClient (talko-role caller)."""
    tele_client = TelephonyClient(server_address=plane_address, api_key="k")
    relay = RelayServiceGRPC(telephony_client=tele_client)
    server = grpc.aio.server()
    add_RelayServiceServicer_to_server(relay, server)
    port = server.add_insecure_port("localhost:0")
    await server.start()
    client = RelayClient(server_address=f"localhost:{port}", api_key="k")
    yield client
    await client.close_channel()
    await server.stop(None)
    await tele_client.close_channel()


@pytest.mark.asyncio
async def test_route_via_relay_client(relay_server):
    res = await relay_server.route_call_status(call_id="call-30")
    assert res["call_status"] == "in-progress"
    assert res["via"] == "grpc"


@pytest.mark.asyncio
async def test_watch_streams_updates_in_order(relay_server):
    updates = [
        u
        async for u in relay_server.watch_call_status(
            call_id="call-31", max_updates=3, poll_interval_ms=10
        )
    ]
    assert [u["seq"] for u in updates] == [1, 2, 3]
    assert all(u["connected"] is True for u in updates)
    assert MockTelephonyControl.calls == 3  # relay ne plane ko 3 baar poll kiya


@pytest.mark.asyncio
async def test_watch_unknown_target_rejected(relay_server):
    with pytest.raises(grpc.aio.AioRpcError) as exc_info:
        async for _ in relay_server.watch_call_status(
            call_id="call-32", target="nope"
        ):
            pass
    assert exc_info.value.code() == grpc.StatusCode.INVALID_ARGUMENT


@pytest.mark.asyncio
async def test_rate_limit_blocks_third_call(plane_address):
    tele_client = TelephonyClient(server_address=plane_address, api_key="k")
    audit = AuditTrail()
    relay = RelayServiceGRPC(
        telephony_client=tele_client,
        rate_limiter=RelayRateLimiter(limit_per_minute=2),
        audit=audit,
    )
    server = grpc.aio.server()
    add_RelayServiceServicer_to_server(relay, server)
    port = server.add_insecure_port("localhost:0")
    await server.start()
    channel = grpc.aio.insecure_channel(f"localhost:{port}")
    try:
        stub = RelayServiceStub(channel)
        req = relay_pb2.RouteCallStatusRequest(call_id="call-33")
        await stub.RouteCallStatus(req)
        await stub.RouteCallStatus(req)
        with pytest.raises(grpc.aio.AioRpcError) as exc_info:
            await stub.RouteCallStatus(req)
        assert exc_info.value.code() == grpc.StatusCode.RESOURCE_EXHAUSTED
        outcomes = [r["outcome"] for r in audit.records]
        assert outcomes == ["ok", "ok", "rejected"]
    finally:
        await channel.close()
        await server.stop(None)
        await tele_client.close_channel()
