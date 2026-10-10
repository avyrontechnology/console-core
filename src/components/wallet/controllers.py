"""Wallet Controller module."""

import json
from typing import Any, Dict, Optional

from dependency_injector.wiring import Provide, inject
from fastapi import APIRouter, Depends, Header, Query, Request
from fastapi.responses import FileResponse

from src.components.api_key.schemas import ApiKeyResponse
from src.components.api_key.services import ApiKeyService
from src.components.auth.constant import TokenKeys
from src.components.common.constants import CurrentUserMap
from src.components.common.response import (
    BadRequestResponse,
    InternalServerErrorResponse,
    NotFoundResponse,
    SuccessResponse,
    UnauthorizedResponse,
)
from src.components.partner.models import Partner
from src.components.partner.services import PartnerService
from src.components.rbac.permission_dependency import PermissionDependency
from src.components.rbac.permission_injector import permission_check
from src.components.wallet.enum import ServiceName, TransactionType, PartnerTimeZone
from src.components.wallet.errors import (
    InsufficientBalanceError,
    WalletBalanceOverflowError,
    WalletNotFoundError,
)
from src.components.wallet.schema import (
    WalletResponse,
    WalletTransactionListResponse,
    WalletTransactionRequest,
)
from src.components.wallet.services import WalletService
from src.components.wallet.helper import WalletHelper
from src.core.container import Container
from src.exceptions import AuthException
from src.loggers.console_service_logger import ConsoleServiceLogger


class WalletController:
    """Controller for handling wallet operations."""

    wallet_router = APIRouter()

    @wallet_router.get("", summary="Get wallet details")
    @permission_check(PermissionDependency)
    @inject
    async def get_wallet(
        request: Request,
        api_key: Optional[str] = Header(None, alias="API-KEY"),
        partner_id: Optional[int] = None,
        wallet_service: WalletService = Depends(Provide[Container.wallet_service]),
        logger: ConsoleServiceLogger = Depends(
            Provide[Container.console_service_logger]
        ),
        api_key_service: ApiKeyService = Depends(Provide[Container.api_key_service]),
        partner_service: PartnerService = Depends(Provide[Container.partner_service]),
    ) -> SuccessResponse:
        """Retrieve wallet details for the current partner."""
        current_user: dict = request.state.user
        current_user_partner_id: int = current_user.get(CurrentUserMap.PARTNER_ID)
        try:
            effective_partner_id = await WalletHelper.resolve_partner_id_with_api_key(
                current_user,
                partner_id,
                api_key,
                api_key_service,
                partner_service,
                logger,
            )
        except AuthException as exec:
            logger.error("Authexception occured: {}".format(exec))
            return UnauthorizedResponse(detail=str(exec))

        if not effective_partner_id:
            logger.error("partner_id is required")
            return BadRequestResponse(detail="Partner id is required")

        logger.info(
            f"Received request to fetch wallet for partner_id={effective_partner_id}"
        )

        try:
            wallet_data: WalletResponse = await wallet_service.get_wallet(
                effective_partner_id
            )
            logger.info(
                f"Wallet successfully retrieved for partner_id={effective_partner_id}"
            )
            return SuccessResponse(wallet_data)

        except WalletNotFoundError as exc:
            logger.warning(
                f"Wallet not found for partner_id={effective_partner_id}: {exc}"
            )
            return NotFoundResponse(detail=str(exc))

        except Exception as exc:
            logger.error(
                f"Unhandled error in get_wallet for partner_id={effective_partner_id}: {exc}"
            )
            return InternalServerErrorResponse(detail=str(exc))

    @wallet_router.get("/transactions", summary="Get wallet transactions")
    @permission_check(PermissionDependency)
    @inject
    async def get_wallet_transactions(
        request: Request,
        partner_id: Optional[int] = None,
        api_key: Optional[str] = Header(None, alias="API-KEY"),
        limit: int = Query(..., ge=1, le=100),
        offset: int = Query(..., ge=1),
        start_date: Optional[int] = Query(None),
        end_date: Optional[int] = Query(None),
        service_name: ServiceName = Query(None),
        transaction_type: TransactionType = Query(None),
        attribute_filters: Optional[str] = Query(None),
        wallet_service: WalletService = Depends(Provide[Container.wallet_service]),
        logger: ConsoleServiceLogger = Depends(
            Provide[Container.console_service_logger]
        ),
        api_key_service: ApiKeyService = Depends(Provide[Container.api_key_service]),
        partner_service: PartnerService = Depends(Provide[Container.partner_service]),
    ) -> SuccessResponse:
        """Retrieve paginated wallet transaction history."""
        current_user: dict = request.state.user
        current_user_partner_id: int = current_user.get(CurrentUserMap.PARTNER_ID)
        try:
            effective_partner_id = await WalletHelper.resolve_partner_id_with_api_key(
                current_user,
                partner_id,
                api_key,
                api_key_service,
                partner_service,
                logger,
            )
        except AuthException as exec:
            logger.error("Authexception occured: {}".format(exec))
            return UnauthorizedResponse(detail=str(exec))
        if not effective_partner_id:
            logger.error("partner_id is required")
            return BadRequestResponse(detail="Partner id is required")
        logger.info(
            f"Fetching transactions for partner_id={effective_partner_id}, limit={limit}, offset={offset}, "
            f"service_name={service_name}, transaction_type={transaction_type}"
        )

        try:
            if start_date and end_date and start_date > end_date:
                logger.warning(
                    f"Invalid date range provided by partner_id={effective_partner_id}: start_date={start_date}, end_date={end_date}"
                )
                return BadRequestResponse(
                    detail="start_date should be less than end_date"
                )

            parsed_filters: Optional[Dict[str, Any]] = None
            if attribute_filters:
                try:
                    parsed_filters = json.loads(attribute_filters)
                    if not isinstance(parsed_filters, dict):
                        logger.warning(
                            "attribute_filters must be a JSON, {}".format(
                                attribute_filters
                            )
                        )
                        return BadRequestResponse(
                            detail="attribute_filters must be a JSON."
                        )
                except Exception as exc:
                    logger.warning(
                        "An error occured while parsing attribute_filters: {}".format(
                            str(exc)
                        )
                    )
                    return BadRequestResponse(
                        detail="Invalid JSON format for attribute_filters"
                    )

            data: WalletTransactionListResponse = (
                await wallet_service.get_wallet_transactions(
                    partner_id=effective_partner_id,
                    start_date=start_date,
                    end_date=end_date,
                    limit=limit,
                    offset=offset,
                    service_name=service_name,
                    transaction_type=transaction_type,
                    attribute_filters=parsed_filters,
                )
            )
            return SuccessResponse(data=data)

        except WalletNotFoundError as exc:
            logger.warning(
                f"Wallet not found for partner_id={effective_partner_id}: {exc}"
            )
            return NotFoundResponse(detail=str(exc))

        except Exception as exc:
            logger.error(
                f"Unhandled exception in get_wallet_transactions for partner_id={effective_partner_id}: {exc}"
            )
            return InternalServerErrorResponse(detail=str(exc))

    @wallet_router.get("/transaction-statement", response_class=FileResponse)
    @permission_check(PermissionDependency)
    @inject
    async def download_transaction_statement(
        request: Request,
        partner_id: Optional[int] = None,
        api_key: Optional[str] = Header(None, alias="API-KEY"),
        partner_timezone: Optional[str] = PartnerTimeZone.ASIA_KOLKATA,
        start_date: int = Query(...),
        end_date: int = Query(...),
        service_name: ServiceName = Query(None),
        transaction_type: TransactionType = Query(None),
        wallet_service: WalletService = Depends(Provide[Container.wallet_service]),
        logger: ConsoleServiceLogger = Depends(
            Provide[Container.console_service_logger]
        ),
        api_key_service: ApiKeyService = Depends(Provide[Container.api_key_service]),
        partner_service: PartnerService = Depends(Provide[Container.partner_service]),
    ):
        """Download wallet transaction statement as PDF."""
        current_user: dict = request.state.user
        current_user_partner_id: int = current_user.get(CurrentUserMap.PARTNER_ID)
        try:
            effective_partner_id = await WalletHelper.resolve_partner_id_with_api_key(
                current_user,
                partner_id,
                api_key,
                api_key_service,
                partner_service,
                logger,
            )
        except AuthException as exec:
            logger.error("Authexception occured: {}".format(exec))
            return UnauthorizedResponse(detail=str(exec))
        if not effective_partner_id:
            logger.error("partner_id is required")
            return BadRequestResponse(detail="Partner id is required")
        try:
            file_path: str = await wallet_service.generate_statement(
                partner_id=effective_partner_id,
                start_date=start_date,
                end_date=end_date,
                service_name=service_name,
                transaction_type=transaction_type,
                partner_timezone=partner_timezone,
            )
            return FileResponse(
                file_path,
                media_type="application/pdf",
                filename="wallet_transaction_statement.pdf",
            )
        except Exception as e:
            logger.error(
                "Failed to generate wallet statement for partner_id={} | Error: {}".format(
                    effective_partner_id, str(e)
                )
            )
            return InternalServerErrorResponse(detail=str(e))

    @wallet_router.post("/transaction", summary="Perform wallet transaction")
    @permission_check(PermissionDependency)
    @inject
    async def perform_wallet_transaction(
        request: Request,
        payload: WalletTransactionRequest,
        wallet_service: WalletService = Depends(Provide[Container.wallet_service]),
        logger: ConsoleServiceLogger = Depends(
            Provide[Container.console_service_logger]
        ),
    ):
        partner_id = payload.partner_id or request.state.user.get(TokenKeys.PARTNER_ID)
        if not partner_id:
            logger.error("partner_id is required")
            return BadRequestResponse(detail="Partner id is required")
        logger.info(
            "Transaction request: type={type}, amount={amount}, partner_id={pid}".format(
                type=payload.transaction_type.value,
                amount=payload.amount,
                pid=partner_id,
            )
        )
        current_user_id: int = request.state.user.get(CurrentUserMap.USER_ID)

        try:
            wallet: WalletResponse = await wallet_service.perform_transaction(
                current_user_id=current_user_id,
                partner_id=partner_id,
                transaction_type=payload.transaction_type,
                amount=payload.amount,
                service_name=payload.service_name,
                description=payload.description,
                attributes=payload.attributes,
                debit_from_wallet=payload.debit_from_wallet,
            )
            return SuccessResponse(data=wallet, message="Transaction successful")

        except WalletNotFoundError as e:
            logger.warning("Wallet not found: {e}".format(e=e))
            return NotFoundResponse(detail=str(e))

        except InsufficientBalanceError as e:
            logger.warning("Insufficient balance: {e}".format(e=e))
            return BadRequestResponse(detail=str(e))

        except WalletBalanceOverflowError as e:
            logger.warning(f"Wallet balance overflow: {e}")
            return BadRequestResponse(
                detail=str(e),
            )

        except Exception as e:
            logger.error("Unexpected error: {e}".format(e=e))
            return InternalServerErrorResponse(detail=str(e))
