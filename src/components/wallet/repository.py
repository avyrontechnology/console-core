"""Wallet Repository module."""

from decimal import Decimal
from typing import Any, Dict, List, Optional, Set, Tuple

from sqlalchemy import and_, func, select, text
from sqlalchemy.exc import SQLAlchemyError

from src.components.order.models import Order
from src.components.wallet.enum import MAX_WALLET_NUMERIC, ServiceName, TransactionType
from src.components.wallet.errors import (
    InsufficientBalanceError,
    WalletAlreadyExistsError,
    WalletBalanceOverflowError,
    WalletNotFoundError,
)
from src.components.wallet.models import Wallet, WalletTransaction
from src.components.wallet.schema import WalletTransactionResponse
from src.loggers.console_service_logger import ConsoleServiceLogger


class WalletRepository:
    """Handles database operations for wallet and wallet transactions."""

    def __init__(self, session_factory, logger: ConsoleServiceLogger):
        self.__session_factory = session_factory
        self.__logger = logger

    async def get_wallet_by_partner_id(self, partner_id: int) -> Optional[Wallet]:
        """
        Fetch wallet record for a given partner.
        """
        try:
            async with self.__session_factory() as session:
                self.__logger.info(f"Fetching wallet for partner_id={partner_id}")
                result = await session.execute(
                    select(Wallet).where(Wallet.partner_id == partner_id)
                )
                wallet = result.scalars().first()

                if not wallet:
                    self.__logger.warning(
                        f"No wallet found for partner_id={partner_id}"
                    )
                    return None

                return wallet
        except Exception as exc:
            self.__logger.error(f"Database error in get_wallet_by_partner_id: {exc}")
            raise exc

    async def get_wallets_by_partner_ids(
        self, partner_ids: list[int]
    ) -> List[Wallet]:
        try:
            self.__logger.info(f"Fetching wallets for partner_ids={partner_ids}")
            async with self.__session_factory() as session:
                result = await session.execute(
                    select(Wallet).where(Wallet.partner_id.in_(partner_ids))
                )

                return result.scalars().all()
        except Exception as exc:
            self.__logger.error(f"Database error: {exc}")
            raise
        
    async def get_wallet_transactions(
        self,
        wallet_id: int,
        start_date: Optional[int] = None,
        end_date: Optional[int] = None,
        limit: int = 10,
        offset: int = 1,
        service_name: Optional[str] = None,
        transaction_type: Optional[str] = None,
        attribute_filters: Optional[Dict[str, Any]] = None,
    ) -> Tuple[List[WalletTransactionResponse], int]:
        """
        Fetch wallet transactions with pagination and filters.
        """
        try:
            async with self.__session_factory() as session:
                filters = [WalletTransaction.wallet_id == wallet_id]

                if start_date and end_date:
                    filters.append(
                        and_(
                            WalletTransaction.created_at >= start_date,
                            WalletTransaction.created_at <= end_date,
                        )
                    )

                if service_name:
                    filters.append(WalletTransaction.service_name == service_name)

                if transaction_type:
                    filters.append(
                        WalletTransaction.transaction_type == transaction_type
                    )
                if attribute_filters:
                    for key, value in attribute_filters.items():
                        filters.append(text(f"attributes ->> '{key}' = '{value}'"))

                total_count: int = (
                    await session.execute(
                        select(func.count())
                        .select_from(WalletTransaction)
                        .where(and_(*filters))
                    )
                ).scalar() or 0

                transactions: List[WalletTransaction] = (
                    await session.execute(
                        select(WalletTransaction)
                        .where(and_(*filters))
                        .order_by(WalletTransaction.created_at.desc())
                        .limit(limit)
                        .offset((offset - 1) * limit)
                    )
                ).scalars().all()

                order_ids: Set[int] = {
                    int(txn.additional_info.get("order_id"))
                    for txn in transactions
                    if isinstance(txn.additional_info, dict)
                    and txn.additional_info.get("order_id")
                }

                order_status_map: Dict[int, str] = {}
                if order_ids:
                    rows: List[tuple[int, str]] = await session.execute(
                        select(Order.id, Order.status).where(Order.id.in_(order_ids))
                    )
                    order_status_map = dict(rows.all())

                return (
                    [
                        WalletTransactionResponse(
                            id=txn.id,
                            wallet_id=txn.wallet_id,
                            transaction_type=txn.transaction_type,
                            service_name=txn.service_name,
                            previous_balance=txn.previous_balance,
                            amount=txn.amount,
                            remaining_balance=txn.remaining_balance,
                            description=txn.description,
                            attributes=txn.attributes,
                            additional_info=txn.additional_info,
                            created_at=txn.created_at,
                            status=(
                                order_status_map.get(
                                    int(txn.additional_info.get("order_id")), "SUCCESS"
                                )
                                if isinstance(txn.additional_info, dict)
                                and txn.additional_info.get("order_id")
                                else "SUCCESS"
                            ),
                        )
                        for txn in transactions
                    ],
                    total_count,
                )

        except Exception as exc:
            self.__logger.error(f"Database error in get_wallet_transactions: {exc}")
            raise exc

    async def create_wallet(self, partner_id: int) -> Wallet:
        """
        Create a wallet for the given partner if not already exists.

        Args:
            partner_id (int): ID of the partner for whom the wallet should be created.

        Returns:
            Wallet: The newly created Wallet instance.

        Raises:
            WalletAlreadyExistsError: If a wallet already exists for the given partner.
        """
        try:
            async with self.__session_factory() as session:
                self.__logger.info(
                    "Checking if wallet exists for partner_id={}".format(partner_id)
                )
                result = await session.execute(
                    select(Wallet).where(Wallet.partner_id == partner_id)
                )
                existing_wallet = result.scalars().first()

                if existing_wallet:
                    self.__logger.warning(
                        "Wallet already exists for partner_id={}".format(partner_id)
                    )
                    raise WalletAlreadyExistsError(partner_id)

                wallet = Wallet(partner_id=partner_id)
                session.add(wallet)
                await session.commit()
                await session.refresh(wallet)

                self.__logger.info(
                    "Wallet created for partner_id={} with wallet_id={}".format(
                        partner_id, wallet.id
                    )
                )

                return wallet

        except WalletAlreadyExistsError:
            self.__logger.warning(
                "Wallet already exists for partner_id: {}".format(partner_id)
            )
            raise

        except Exception as exc:
            self.__logger.error(
                "Unexpected error while creating wallet for partner_id={}: {}".format(
                    partner_id, exc
                )
            )
            raise

    async def fetch_transactions(
        self,
        partner_id: int,
        start_date: int,
        end_date: int,
        service_name: str | None,
        transaction_type: str | None,
    ):
        """Fetch wallet transactions for a partner."""
        try:
            async with self.__session_factory() as session:
                query = (
                    select(WalletTransaction)
                    .join(Wallet)
                    .where(
                        (Wallet.partner_id == partner_id)
                        & (WalletTransaction.created_at >= start_date)
                        & (WalletTransaction.created_at <= end_date)
                    )
                )

                if service_name:
                    query = query.where(WalletTransaction.service_name == service_name)
                if transaction_type:
                    query = query.where(
                        WalletTransaction.transaction_type == transaction_type
                    )

                transactions: List[WalletTransaction] = (
                    await session.execute(
                        query.order_by(WalletTransaction.created_at.desc())
                    )
                ).scalars().all()

                order_ids: Set[int] = {
                    int(tx.additional_info["order_id"])
                    for tx in transactions
                    if isinstance(tx.additional_info, dict)
                    and tx.additional_info.get("order_id")
                }

                order_status_map: Dict[int, str] = {}
                if order_ids:
                    rows: List[tuple[int, str]] = await session.execute(
                        select(Order.id, Order.status).where(Order.id.in_(order_ids))
                    )
                    order_status_map = dict(rows.all())

                return [
                    {
                        "created_at": tx.created_at,
                        "service_name": getattr(tx.service_name, "name", tx.service_name),
                        "transaction_type": getattr(
                            tx.transaction_type, "name", tx.transaction_type
                        ),
                        "description": tx.description or "-",
                        "amount": float(tx.amount),
                        "remaining_balance": float(tx.remaining_balance),
                        "status": (
                            order_status_map.get(
                                int(tx.additional_info["order_id"]), "SUCCESS"
                            )
                            if isinstance(tx.additional_info, dict)
                            and tx.additional_info.get("order_id")
                            else "SUCCESS"
                        ),
                    }
                    for tx in transactions
                ]

        except Exception as e:
            self.__logger.error(
                "Error fetching transactions for partner_id={} | Error: {}".format(
                    partner_id, str(e)
                )
            )
            raise

    async def perform_wallet_transaction(
        self,
        current_user_id: int,
        partner_id: int,
        transaction_type: TransactionType,
        amount: Decimal,
        service_name: ServiceName,
        description: Optional[str] = None,
        attributes: Optional[Dict[str, Any]] = None,
        debit_from_wallet: Optional[bool] = False,
        additional_info: Optional[Dict[str, Any]] = None,
        create_transaction: bool = True,
        update_wallet: bool = True
    ) -> Wallet:
        """Atomically handle wallet transaction and log entry."""
        self.__logger.info(
            "Starting wallet transaction: partner_id={pid}, type={type}, amount={amt}".format(
                pid=partner_id, type=transaction_type.value, amt=amount
            )
        )

        try:
            async with self.__session_factory() as session:
                async with session.begin():
                    # Lock wallet row
                    result = await session.execute(
                        select(Wallet)
                        .where(Wallet.partner_id == partner_id)
                        .with_for_update()
                    )
                    wallet = result.scalar_one_or_none()

                    if not wallet:
                        self.__logger.warning(
                            "No wallet found for partner_id={pid} during locked transaction.".format(
                                pid=partner_id
                            )
                        )
                        raise WalletNotFoundError(partner_id)

                    prev_balance = wallet.balance
                    prev_frozen = wallet.frozen_balance

                    self.__logger.info(
                        "Fetched locked wallet for partner_id={pid}: balance={bal}, frozen={frozen}".format(
                            pid=partner_id, bal=prev_balance, frozen=prev_frozen
                        )
                    )

                    # Determine new balances
                    new_balance, new_frozen = self.__calculate_new_balances(
                        transaction_type, prev_balance, prev_frozen, amount, partner_id, debit_from_wallet
                    )

                    self._validate_post_operation_balance(new_balance, new_frozen)

                    # Update wallet
                    if update_wallet:
                        wallet.balance = new_balance
                        wallet.frozen_balance = new_frozen
                        wallet.updated_by = current_user_id
                        session.add(wallet)

                        self.__logger.info(
                            "Wallet updated for partner_id={pid}: new_balance={bal}, new_frozen={frozen}".format(
                                pid=partner_id, bal=new_balance, frozen=new_frozen
                            )
                        )

                    # Create transaction log
                    if create_transaction:
                        transaction = WalletTransaction(
                            wallet_id=wallet.id,
                            transaction_type=transaction_type,
                            service_name=service_name,
                            amount=amount,
                            previous_balance=prev_balance,
                            remaining_balance=new_balance,
                            description=description,
                            attributes=attributes,
                            additional_info=additional_info,
                            created_by=current_user_id,
                            updated_by=current_user_id,
                        )
                        session.add(transaction)

                    await session.flush()

                    self.__logger.info(
                        "Transaction log created: wallet_id={wid}, type={type}, amount={amt}".format(
                            wid=wallet.id, type=transaction_type.value, amt=amount
                        )
                    )

                    await session.commit()
                    self.__logger.info(
                        "Transaction staged for partner_id={pid}".format(pid=partner_id)
                    )
                await session.refresh(wallet)

                self.__logger.info(
                    "Transaction committed successfully for partner_id={pid}".format(
                        pid=partner_id
                    )
                )

                return wallet

        except WalletNotFoundError as exc:
            self.__logger.warning(
                "WalletNotFoundError in perform_wallet_transaction: partner_id={pid}, error={err}".format(
                    pid=partner_id, err=exc
                )
            )
            raise

        except InsufficientBalanceError as exc:
            self.__logger.warning(
                "InsufficientBalanceError in perform_wallet_transaction: partner_id={pid}, error={err}".format(
                    pid=partner_id, err=exc
                )
            )
            raise

        except SQLAlchemyError as exc:
            self.__logger.error(
                "SQLAlchemyError while performing wallet transaction for partner_id={pid}: {err}".format(
                    pid=partner_id, err=exc
                )
            )
            raise

        except Exception as exc:
            self.__logger.error(
                "Unexpected error in perform_wallet_transaction for partner_id={pid}: {err}".format(
                    pid=partner_id, err=exc
                )
            )
            raise

    def __calculate_new_balances(
        self,
        transaction_type: TransactionType,
        prev_balance: Decimal,
        prev_frozen: Decimal,
        amount: Decimal,
        partner_id: int,
        debit_from_wallet: Optional[bool]=False,
    ) -> Tuple[Decimal, Decimal]:
        """Route to correct balance calculator based on transaction type."""
        if transaction_type == TransactionType.CREDIT:
            return self.__handle_credit(prev_balance, prev_frozen, amount)

        elif transaction_type == TransactionType.DEBIT:
            if debit_from_wallet:
                return self.__handle_debit(prev_balance, prev_frozen, amount, partner_id)
            else:
                return self.__handle_frozen_debit(prev_balance, prev_frozen, amount, partner_id)

        elif transaction_type == TransactionType.FREEZE:
            return self.__handle_freeze(prev_balance, prev_frozen, amount, partner_id)

        elif transaction_type == TransactionType.UNFREEZE:
            return self.__handle_unfreeze(prev_balance, prev_frozen, amount, partner_id)
        

        self.__logger.error(
            f"Invalid transaction type '{transaction_type}' for partner_id={partner_id}"
        )
        raise ValueError(f"Unsupported transaction type: {transaction_type}")

    def __handle_credit(
        self, prev_balance: Decimal, prev_frozen: Decimal, amount: Decimal
    ) -> Tuple[Decimal, Decimal]:
        new_balance = prev_balance + amount
        self.__logger.info(
            f"CREDIT transaction: old_balance={prev_balance}, new_balance={new_balance}"
        )
        return new_balance, prev_frozen

    def __handle_debit(
        self,
        prev_balance: Decimal,
        prev_frozen: Decimal,
        amount: Decimal,
        partner_id: int,
    ) -> Tuple[Decimal, Decimal]:
        if amount > prev_balance:
            self.__logger.warning(
                f"Insufficient funds for DEBIT: partner_id={partner_id}, "
                f"available={prev_balance}, requested={amount}"
            )
            raise InsufficientBalanceError("Insufficient available balance.")
        return prev_balance - amount, prev_frozen

    def __handle_freeze(
        self,
        prev_balance: Decimal,
        prev_frozen: Decimal,
        amount: Decimal,
        partner_id: int,
    ) -> Tuple[Decimal, Decimal]:
        if amount > prev_balance:
            self.__logger.warning(
                f"Insufficient balance to FREEZE: partner_id={partner_id}, "
                f"available={prev_balance}, requested={amount}"
            )
            raise InsufficientBalanceError("Insufficient balance to freeze.")
        return prev_balance - amount, prev_frozen + amount

    def __handle_unfreeze(
        self,
        prev_balance: Decimal,
        prev_frozen: Decimal,
        amount: Decimal,
        partner_id: int,
    ) -> Tuple[Decimal, Decimal]:
        if amount > prev_frozen:
            self.__logger.warning(
                f"Insufficient frozen balance to UNFREEZE: partner_id={partner_id}, "
                f"frozen={prev_frozen}, requested={amount}"
            )
            raise InsufficientBalanceError("Insufficient frozen balance.")
        return prev_balance + amount, prev_frozen - amount

    def _validate_post_operation_balance(
        self, new_balance: Decimal, new_frozen: Decimal
    ):
        if abs(new_balance) > MAX_WALLET_NUMERIC:
            self.__logger.error(
                f"Wallet balance overflow detected: new_balance={new_balance}, "
                f"limit={MAX_WALLET_NUMERIC}"
            )
            raise WalletBalanceOverflowError(
                f"Operation would exceed maximum wallet balance limit ({MAX_WALLET_NUMERIC})."
            )

        if abs(new_frozen) > MAX_WALLET_NUMERIC:
            self.__logger.error(
                f"Frozen balance overflow detected: new_frozen={new_frozen}, "
                f"limit={MAX_WALLET_NUMERIC}"
            )
            raise WalletBalanceOverflowError(
                f"Operation would exceed maximum frozen balance limit ({MAX_WALLET_NUMERIC})."
            )
        
    def __handle_frozen_debit(
        self,
        prev_balance: Decimal,
        prev_frozen: Decimal,
        amount: Decimal,
        partner_id: int,
    ) -> Tuple[Decimal, Decimal]:
        if amount > prev_frozen:
            self.__logger.warning(
                f"Insufficient funds for DEBIT: partner_id={partner_id}, "
                f"available={prev_frozen}, requested={amount}"
            )
            raise InsufficientBalanceError("Insufficient available balance.")
        return prev_balance , prev_frozen - amount


    async def fetch_wallet_transaction_report(
        self,
        start_date: int,
        end_date: int,
        service_name: str | None = None,
        transaction_type: str | None = None,
    ) -> list[dict]:
        try:
            async with self.__session_factory() as session:

                query = (
                    select(
                        Wallet.partner_id.label("partner_id"),
                        Wallet.balance.label("balance"),
                        Wallet.frozen_balance.label("frozen_balance"),
                        WalletTransaction.service_name.label("service"),
                        WalletTransaction.amount.label("amount"),
                        WalletTransaction.description.label("description"),
                        WalletTransaction.transaction_type.label("type"),
                        WalletTransaction.created_at.label("created_at"),
                    )
                    .join(
                        Wallet,
                        Wallet.id == WalletTransaction.wallet_id,
                    )
                    .where(
                        WalletTransaction.created_at >= start_date,
                        WalletTransaction.created_at <= end_date,
                    )
                )

                if service_name:
                    query = query.where(
                        WalletTransaction.service_name == service_name
                    )

                if transaction_type:
                    query = query.where(
                        WalletTransaction.transaction_type == transaction_type
                    )

                result = await session.execute(
                    query.order_by(
                        Wallet.partner_id,
                        WalletTransaction.created_at.desc()
                    )
                )

                return result.mappings().all()

        except Exception as exp:
            self.__logger.error(
                f"Error fetching wallet transaction report: {exp}"
            )
            raise