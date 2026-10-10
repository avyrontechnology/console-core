"""Factory: one shared client (channel) per service per process.

Why singleton: gRPC channel setup = TCP + HTTP/2 handshake + (TLS).
Har call par naya channel = har call par handshake = slow + socket
leak. Isliye factory ek baar banata hai, sab reuse karte hain.
Process restart par naya — koi shared state nahi, thread-safe by
construction (sirf read hota hai creation ke baad).
"""

from src.grpc_client.relay_client import RelayClient
from src.grpc_client.telephony_client import TelephonyClient

TELEPHONY = "telephony"
RELAY = "relay"

_BUILDERS = {
    TELEPHONY: TelephonyClient,
    RELAY: RelayClient,
}


class GrpcClientFactory:
    _instances: dict = {}

    @staticmethod
    def get_service(service_name: str):
        if service_name in _BUILDERS:
            if service_name not in GrpcClientFactory._instances:
                GrpcClientFactory._instances[service_name] = _BUILDERS[service_name]()
            return GrpcClientFactory._instances[service_name]
        raise ValueError(f"Unknown outbound gRPC service: {service_name}")

    @staticmethod
    def reset():
        """Tests ke liye: instances drop karo taaki har test fresh
        channel (fresh mock address) le. Prod me kabhi mat bulao."""
        GrpcClientFactory._instances = {}
