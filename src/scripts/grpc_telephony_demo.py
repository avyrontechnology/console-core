"""End-to-end demo: mock plane + client + relay, ek command me.

Chalao (repo root se, console-service venv me grpc hai):
    /home/vikram-sengar/console-service/venv/bin/python src/scripts/grpc_telephony_demo.py

Ye script:
  Phase-2: mock plane (50052) -> TelephonyClient -> GetCallStatus + Hangup
  Phase-3: relay server (50053) -> talko-role stub -> RouteCallStatus
           (relay andar hi Phase-2 client se mock plane ko forward karta hai)
Yahi client-to-client via console-core ka proof hai.
"""

import asyncio
import os
import sys

import grpc

sys.path.insert(0, os.getcwd())

# Demo ke liye flag force-on (real deploy me .env se aayega).
os.environ["TELEPHONY_VIA_GRPC"] = "true"

from src.components.relay.rpc import RelayServiceGRPC  # noqa: E402
from src.grpc_client import helpers  # noqa: E402
from src.grpc_client.mock_telephony_server import serve  # noqa: E402
from src.grpc_client.telephony_client import TelephonyClient  # noqa: E402
from src.pub import relay_pb2  # noqa: E402
from src.pub.relay_pb2_grpc import (  # noqa: E402
    RelayServiceStub,
    add_RelayServiceServicer_to_server,
)


async def main():
    server_task = asyncio.create_task(serve(port=50052))
    await asyncio.sleep(1)  # mock ko uthne do
    try:
        result = await helpers.get_call_status(
            call_id="demo-call-123", vendor_config_id="demo-vendor"
        )
        print(f"\n>>> GetCallStatus result: {result}\n")

        # Hangup dedup proof: same key dobara — kaam ek baar.
        from src.grpc_client.factory import GrpcClientFactory, TELEPHONY

        client = GrpcClientFactory.get_service(TELEPHONY)
        first = await client.hangup_call(
            call_id="demo-call-123", idempotency_key="demo-key-1"
        )
        second = await client.hangup_call(
            call_id="demo-call-123", idempotency_key="demo-key-1"
        )
        print(f">>> Hangup first:  {first}")
        print(f">>> Hangup second: {second}\n")

        # Phase-3: talko bankar relay ko call karo (relay -> mock forward).
        tele_client = TelephonyClient(
            server_address="localhost:50052", api_key="demo-key"
        )
        relay_server = grpc.aio.server()
        add_RelayServiceServicer_to_server(
            RelayServiceGRPC(telephony_client=tele_client), relay_server
        )
        relay_server.add_insecure_port("[::]:50053")
        await relay_server.start()
        channel = grpc.aio.insecure_channel("localhost:50053")
        try:
            stub = RelayServiceStub(channel)
            routed = await stub.RouteCallStatus(
                relay_pb2.RouteCallStatusRequest(call_id="demo-call-123")
            )
            print(
                f">>> Relay RouteCallStatus: call_id={routed.call_id} "
                f"status={routed.call_status} connected={routed.connected} "
                f"via={routed.via}\n"
            )

            # Phase-4: server streaming — ek request, updates ka stream.
            from src.grpc_client.relay_client import RelayClient

            watcher = RelayClient(server_address="localhost:50053", api_key="demo-key")
            try:
                async for update in watcher.watch_call_status(
                    call_id="demo-call-123", max_updates=3, poll_interval_ms=100
                ):
                    print(f">>> Watch update: {update}")
                print()
            finally:
                await watcher.close_channel()
        finally:
            await channel.close()
            await relay_server.stop(None)
            await tele_client.close_channel()
    finally:
        server_task.cancel()


if __name__ == "__main__":
    asyncio.run(main())
