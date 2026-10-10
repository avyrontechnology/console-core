"""Phase-2 client tests (mock plane ke against, real server nahi chahiye).

Har test apna in-process mock server uthata hai (ephemeral port),
isliye port clash nahi hota aur CI me bhi chalta hai.
Factory singleton use NAHI kiya — TelephonyClient seedha banaya taaki
test alag-alag address/key le sake.
Repo convention: async tests par @pytest.mark.asyncio (strict mode).
"""

import grpc
import pytest
import pytest_asyncio

from src.grpc_client.mock_telephony_server import MockTelephonyControl
from src.grpc_client.telephony_client import TelephonyClient
from src.pub.telephony_pb2_grpc import add_TelephonyControlServicer_to_server


@pytest_asyncio.fixture
async def mock_address():
    MockTelephonyControl.reset()
    server = grpc.aio.server()
    add_TelephonyControlServicer_to_server(MockTelephonyControl(), server)
    port = server.add_insecure_port("localhost:0")  # free port, OS dega
    await server.start()
    yield f"localhost:{port}"
    await server.stop(None)
    MockTelephonyControl.reset()


@pytest.mark.asyncio
async def test_get_call_status_happy_path(mock_address):
    client = TelephonyClient(server_address=mock_address, api_key="test-key")
    try:
        result = await client.get_call_status(call_id="call-1")
    finally:
        await client.close_channel()
    assert result["call_id"] == "call-1"
    assert result["call_status"] == "in-progress"
    assert result["connected"] is True
    assert MockTelephonyControl.calls == 1


@pytest.mark.asyncio
async def test_get_call_status_retries_transient_failure(mock_address):
    MockTelephonyControl.fail_times = 2  # pehle 2 calls UNAVAILABLE
    client = TelephonyClient(server_address=mock_address, api_key="test-key")
    try:
        result = await client.get_call_status(call_id="call-2")
    finally:
        await client.close_channel()
    assert result["connected"] is True
    assert MockTelephonyControl.calls == 3  # 2 fail + 1 pass


@pytest.mark.asyncio
async def test_get_call_status_bad_key_unauthenticated(mock_address):
    MockTelephonyControl.require_api_key = "correct-key"
    client = TelephonyClient(server_address=mock_address, api_key="wrong-key")
    try:
        with pytest.raises(grpc.aio.AioRpcError) as exc_info:
            await client.get_call_status(call_id="call-3")
    finally:
        await client.close_channel()
    assert exc_info.value.code() == grpc.StatusCode.UNAUTHENTICATED


@pytest.mark.asyncio
async def test_hangup_happy_path(mock_address):
    client = TelephonyClient(server_address=mock_address, api_key="test-key")
    try:
        result = await client.hangup_call(call_id="call-10")
    finally:
        await client.close_channel()
    assert result["success"] is True
    assert result["call_id"] == "call-10"
    assert MockTelephonyControl.hangup_actions == 1


@pytest.mark.asyncio
async def test_hangup_same_key_twice_single_action(mock_address):
    """Dobara bhejo, kaam ek baar — dedup ka core proof."""
    client = TelephonyClient(server_address=mock_address, api_key="test-key")
    try:
        first = await client.hangup_call(call_id="call-11", idempotency_key="key-abc")
        second = await client.hangup_call(call_id="call-11", idempotency_key="key-abc")
    finally:
        await client.close_channel()
    assert first["success"] is True
    assert "duplicate suppressed" in second["message"]
    assert MockTelephonyControl.hangup_calls == 2  # aye 2 baar
    assert MockTelephonyControl.hangup_actions == 1  # kaam 1 baar


@pytest.mark.asyncio
async def test_hangup_retry_keeps_same_key(mock_address):
    """Pehli attempt network-fail -> retry SAME key se -> server par
    1 hi action. Yahi prove karta hai key loop ke bahar banti hai
    (ander banti to retry par nayi key = 2 actions)."""
    MockTelephonyControl.fail_times = 1  # pehli attempt UNAVAILABLE
    client = TelephonyClient(server_address=mock_address, api_key="test-key")
    try:
        result = await client.hangup_call(call_id="call-12", idempotency_key="key-retry")
    finally:
        await client.close_channel()
    assert result["success"] is True
    assert result["idempotency_key"] == "key-retry"
    assert MockTelephonyControl.hangup_calls == 2  # fail + retry
    assert MockTelephonyControl.hangup_actions == 1  # kaam 1 baar


@pytest.mark.asyncio
async def test_hangup_different_keys_two_actions(mock_address):
    client = TelephonyClient(server_address=mock_address, api_key="test-key")
    try:
        await client.hangup_call(call_id="call-13", idempotency_key="key-1")
        await client.hangup_call(call_id="call-13", idempotency_key="key-2")
    finally:
        await client.close_channel()
    assert MockTelephonyControl.hangup_actions == 2
