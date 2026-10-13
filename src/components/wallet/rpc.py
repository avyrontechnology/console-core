from dependency_injector.wiring import Provide, inject
from fastapi import Depends
from grpc import StatusCode
from grpc_interceptor.exceptions import GrpcException

from src.core.container import Container
from src.components.common.rpc_uuid import parse_uuid_list, uuid_list_str, uuid_str
from src.components.wallet.services import WalletService
from src.pub.partner_wallet_pb2 import (
    GetWalletsByPartnerIdsRequest,
    GetWalletsByPartnerIdsResponse,
    WalletDebitRequest,
    WalletDebitResponse,
    WalletRPCResponse,
)

from src.pub.partner_wallet_pb2_grpc import WalletRPCService 

class WalletServiceGRPC(WalletRPCService):
    def __init__(self, logger):
        self.__logger = logger

    @inject
    async def GetWalletsByPartnerIds(
        self,
        request: GetWalletsByPartnerIdsRequest,
        context,
        wallet_service: WalletService = Depends(
            Provide[Container.wallet_service]
        ),
    ):
        partner_ids = parse_uuid_list(request.partner_ids, "partner_ids")

        try:
            self.__logger.info(
                f"[gRPC]: Fetching wallet details for partner_ids={uuid_list_str(partner_ids)}"
            )

            wallets = await wallet_service.get_wallets_by_partner_ids(
                partner_ids=partner_ids
            )

            response = GetWalletsByPartnerIdsResponse(
                wallets=[
                    WalletRPCResponse(
                        id=uuid_str(wallet.id),
                        partner_id=uuid_str(wallet.partner_id),
                        balance=wallet.balance,
                        frozen_balance=wallet.frozen_balance,
                        currency=wallet.currency,
                        is_active=wallet.is_active,
                        is_wallet_enabled=wallet.is_wallet_enabled,
                        created_at=wallet.created_at,
                        updated_at=wallet.updated_at,
                    )
                    for wallet in wallets
                ]
            )

            self.__logger.info(
                f"[gRPC]: Successfully fetched {len(wallets)} wallet records"
            )
            return response

        except Exception as exc:
            self.__logger.error(
                f"[gRPC]: Error fetching wallet details: {exc}"
            )
            raise GrpcException(
                details="Internal server error while fetching wallet details.",
                status_code=StatusCode.INTERNAL,
            )

    @inject
    async def WalletDebit(
        self,
        request: WalletDebitRequest,
        context,
        wallet_service: WalletService = Depends(
            Provide[Container.wallet_service]
        ),
    ):
        from uuid import UUID

        from src.components.common.rpc_uuid import parse_uuid
        from src.components.wallet.errors import (
            InsufficientBalanceError,
            WalletNotFoundError,
        )

        partner_id = parse_uuid(request.partner_id, "partner_id")
        try:
            result = await wallet_service.debit_call_charge(
                partner_id=partner_id,
                amount=request.amount,
                currency=request.currency or "INR",
                call_id=request.call_id,
                billed_minutes=request.billed_minutes,
            )
            return WalletDebitResponse(
                message="Success",
                transaction_id=uuid_str(result["transaction_id"]),
                amount=result["amount"],
                remaining_balance=result["remaining_balance"],
                already_charged=result["already_charged"],
            )
        except WalletNotFoundError:
            raise GrpcException(
                details="Wallet not found for partner.",
                status_code=StatusCode.NOT_FOUND,
            )
        except InsufficientBalanceError as exc:
            raise GrpcException(
                details=str(exc),
                status_code=StatusCode.FAILED_PRECONDITION,
            )
        except Exception as exc:
            self.__logger.error(f"[gRPC]: WalletDebit failed: {exc}")
            raise GrpcException(
                details="Internal server error during wallet debit.",
                status_code=StatusCode.INTERNAL,
            )