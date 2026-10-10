"""Outbound gRPC clients (console-core as CLIENT — Phase-2).

Server side lives in src/rpc_main.py (port 50051). This package is the
opposite direction: console-core calling other planes (telephony, ...).
"""

from src.grpc_client.console_grpc_client import ConsoleGRPCClient
from src.grpc_client.factory import GrpcClientFactory
from src.grpc_client.relay_client import RelayClient
from src.grpc_client.telephony_client import TelephonyClient

__all__ = ["ConsoleGRPCClient", "GrpcClientFactory", "RelayClient", "TelephonyClient"]
