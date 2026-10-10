"""Flag-gated wiring point (future call-sites yahi use karenge).

Pattern: har naya gRPC call pehle flag ke peeche aata hai.
TELEPHONY_VIA_GRPC=true  -> gRPC client (Phase-2, naya rasta)
anything else             -> {"via": "http"} fallback signal — caller
                           apna purana HTTP path chalaye (aaj ka behavior).

Isse rollback ek env change hai, deploy nahi. Jab gRPC stable ho
jaye, flag default true karke HTTP path hata do (Phase-2b).
"""

from src.core.environment import ENV
from src.grpc_client.factory import GrpcClientFactory, TELEPHONY
from src.loggers.console_rpc_logger import ConsoleRpcLogger

logger = ConsoleRpcLogger.get_logger()


def is_grpc_enabled() -> bool:
    return str(ENV.TELEPHONY_VIA_GRPC).lower() == "true"


async def get_call_status(call_id: str, vendor_config_id: str = "") -> dict:
    """Poll call signalling state. gRPC jab flag on, warna fallback."""
    if not is_grpc_enabled():
        logger.info(f"TELEPHONY_VIA_GRPC off — HTTP fallback for {call_id}")
        return {"via": "http", "call_id": call_id}
    client = GrpcClientFactory.get_service(TELEPHONY)
    result = await client.get_call_status(
        call_id=call_id, vendor_config_id=vendor_config_id
    )
    return {"via": "grpc", **result}
