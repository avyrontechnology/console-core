import base64
import os

import grpc

from src.components.api_key.rpc import ApiKeyServiceGRPC
from src.components.auth.rpc import AuthServiceGRPC
from src.components.partner_meta_data.rpc import PartnerMetaDataServiceGrpc
from src.components.relay.rpc import RelayServiceGRPC
from src.components.user.rpc import UserServiceGRPC
from src.components.wallet.rpc import WalletServiceGRPC
from src.core.environment import ENV
from src.grpc_interceptors.auth_interceptor import ApiKeyAuthInterceptor
from src.grpc_interceptors.constants import VALID_SERVICE_KEYS
from src.grpc_interceptors.exception import AsyncExceptionToStatusInterceptor
from src.loggers.console_rpc_logger import ConsoleRpcLogger

# from src.core.container import Container
from src.main import container
from src.pub.api_key_service_pb2_grpc import add_ApiKeyServiceServicer_to_server
from src.pub.auth_pb2_grpc import (
    add_AuthServiceServicer_to_server,
    add_PartnerMetaDataServiceServicer_to_server,
)
from src.pub.user_pb2_grpc import add_UserServiceServicer_to_server
from src.pub.relay_pb2_grpc import add_RelayServiceServicer_to_server
from src.pub.partner_wallet_pb2_grpc import add_WalletRPCServiceServicer_to_server, WalletRPCServiceServicer
logger = ConsoleRpcLogger.get_logger()

CERT_CONTENT = ENV.CERT if ENV.CERT != "None" else None  # Plain string SSL certificate
KEY_CONTENT = ENV.KEY if ENV.KEY != "None" else None  # Plain string private key


def _load_ssl_credentials(cert: str, key: str) -> grpc.ServerCredentials | None:
    """
    Tries to load SSL credentials; returns None if files can't be read.
    """
    try:
        if not cert or not key:
            logger.warning(
                "SSL cert or key not provided in ENV. Falling back to insecure mode."
            )
            return None

        certificate_chain = base64.b64decode(CERT_CONTENT)
        private_key = base64.b64decode(KEY_CONTENT)

        logger.info("SSL credentials loaded successfully from ENV.")
        return grpc.ssl_server_credentials([(private_key, certificate_chain)])

    except Exception as e:
        logger.error(f"Failed to load SSL credentials: {e}")
        return None


async def serve():

    # Interceptors list
    console_interceptors = [
        ApiKeyAuthInterceptor(VALID_SERVICE_KEYS),
        AsyncExceptionToStatusInterceptor(),
    ]

    # creating Asynchronus GRPC server
    grpc_server = grpc.aio.server(interceptors=console_interceptors)

    logger.info("Starting server at port 50051")

    auth_service = AuthServiceGRPC(
        logger=logger,
        db_session_manager=container.db(),
    )

    partner_meta_data_service = PartnerMetaDataServiceGrpc(logger=logger)

    user_service = UserServiceGRPC(logger=logger)

    api_key_service = ApiKeyServiceGRPC(logger=logger)

    wallet_service = WalletServiceGRPC(logger=logger)

    relay_service = RelayServiceGRPC(logger=logger)

    add_AuthServiceServicer_to_server(auth_service, grpc_server)

    add_PartnerMetaDataServiceServicer_to_server(partner_meta_data_service, grpc_server)

    add_UserServiceServicer_to_server(user_service, grpc_server)

    add_ApiKeyServiceServicer_to_server(api_key_service, grpc_server)

    add_WalletRPCServiceServicer_to_server(wallet_service, grpc_server)

    add_RelayServiceServicer_to_server(relay_service, grpc_server)

    # Try secure port first
    server_credentials = _load_ssl_credentials(CERT_CONTENT, KEY_CONTENT)
    if server_credentials:
        grpc_server.add_secure_port("[::]:50051", server_credentials)
        logger.info("Running on secure channel (SSL)")
    else:
        grpc_server.add_insecure_port("[::]:50051")
        logger.warning("Running on insecure channel (no SSL)")

    await grpc_server.start()
    await grpc_server.wait_for_termination()

    logger.info("Server started at port 50051")


if __name__ == "__main__":
    # serve()
    import asyncio

    asyncio.run(serve())
