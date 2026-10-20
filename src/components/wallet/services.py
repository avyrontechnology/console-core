"""Wallet Service module."""
from uuid import UUID
from fastapi import Depends
import asyncio
import base64
import os
import tempfile
import csv
import io
from zoneinfo import ZoneInfo
from datetime import datetime, timezone, timedelta
from decimal import Decimal
from typing import Any, Dict, Optional
from dependency_injector.wiring import Provide
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table

from src.components.wallet.enum import (
    GRID_COLOR,
    HEADER_BG_COLOR,
    HEADER_TEXT_COLOR,
    STATEMENT_TITLE,
    TABLE_COLUMN_WIDTHS,
    TABLE_HEADERS,
    ServiceName,
    TransactionType,
    PartnerTimeZone
)
from src.components.wallet.errors import (
    InsufficientBalanceError,
    WalletAlreadyExistsError,
    WalletNotFoundError,
)
from src.components.wallet.models import Wallet
from src.components.wallet.repository import WalletRepository
from src.components.wallet.schema import WalletRPCResponse, WalletResponse, WalletTransactionListResponse
from src.loggers.console_service_logger import ConsoleServiceLogger
from dependency_injector.wiring import Provide
from fastapi import Depends

class WalletService:
    """Service layer for wallet operations."""

    def __init__(
        self, wallet_repository: WalletRepository, logger: ConsoleServiceLogger
    ) -> None:
        self.__wallet_repository: WalletRepository = wallet_repository
        self.__logger: ConsoleServiceLogger = logger

    async def get_wallet(self, partner_id: UUID) -> Wallet:
        """Retrieve wallet details for the given partner."""
        try:
            wallet: Optional[Wallet] = (
                await self.__wallet_repository.get_wallet_by_partner_id(partner_id)
            )
            if not wallet:
                self.__logger.warning(f"Wallet not found for partner_id={partner_id}")
                raise WalletNotFoundError(partner_id)

            self.__logger.info(f"Fetched wallet for partner_id={partner_id}")
            return WalletResponse.model_validate(wallet)

        except WalletNotFoundError as exc:
            self.__logger.warning(f"Wallet retrieval failed: {exc}")
            raise
        except Exception as exc:
            self.__logger.error(f"Unexpected error in get_wallet: {exc}")
            raise

    async def debit_call_charge(
        self,
        partner_id: UUID,
        amount: float,
        currency: str,
        call_id: str,
        billed_minutes: float,
        actor_id: UUID | None = None,
    ) -> dict:
        """Idempotent per-call debit for Talko ledger unification.

        Find-or-debit on attributes.call_id: a retry returns the original
        transaction instead of double-charging. Raises WalletNotFoundError
        (no wallet = partner not provisioned) and InsufficientBalanceError.
        Returns {transaction_id, amount, remaining_balance, already_charged}.
        """
        try:
            wallet: Optional[Wallet] = (
                await self.__wallet_repository.get_wallet_by_partner_id(partner_id)
            )
            if not wallet:
                raise WalletNotFoundError(partner_id)
            existing = await self.__wallet_repository.find_transaction_by_attribute(
                wallet.id, "call_id", call_id
            )
            if existing is not None:
                self.__logger.info(
                    "Call {} already charged, returning original transaction {}".format(
                        call_id, existing.id
                    )
                )
                return {
                    "transaction_id": existing.id,
                    "amount": float(existing.amount),
                    "remaining_balance": float(existing.remaining_balance),
                    "already_charged": True,
                }
            updated = await self.__wallet_repository.perform_wallet_transaction(
                current_user_id=actor_id or partner_id,
                partner_id=partner_id,
                transaction_type=TransactionType.DEBIT,
                amount=Decimal(str(amount)),
                service_name=ServiceName.TALKO,
                description="call {} ({} min)".format(call_id, billed_minutes),
                attributes={"call_id": call_id, "billed_minutes": billed_minutes},
                # A call charge spends available balance, not frozen funds.
                debit_from_wallet=True,
            )
            self.__logger.info(
                "Charged call {} amount={} partner={}".format(
                    call_id, amount, partner_id
                )
            )
            return {
                "transaction_id": updated.id,
                "amount": float(amount),
                "remaining_balance": float(updated.balance),
                "already_charged": False,
            }
        except (WalletNotFoundError, InsufficientBalanceError) as exc:
            raise
        except Exception as exc:
            self.__logger.error(
                "Unexpected error in debit_call_charge call_id={}: {}".format(
                    call_id, exc
                )
            )
            raise


    async def get_wallets_by_partner_ids(
        self,
        partner_ids: list[int],
        partner_config_service = Depends(Provide["partner_config_service"]),
    ) -> list[WalletRPCResponse]:
        try:
            self.__logger.info(f"Attempting to get wallet details of partner_ids: {partner_ids}")
            wallets = await self.__wallet_repository.get_wallets_by_partner_ids(
                partner_ids
            )

            wallets_by_partner_id = {
                wallet.partner_id: wallet
                for wallet in wallets
            }

            partner_configs = await partner_config_service.get_partner_config_by_key(
                partner_ids,
                "is_wallet_enabled",
            )

            wallet_enabled_by_partner_id = {
                config.partner_id: bool(config.value)
                for config in partner_configs
            }

            response = []

            for partner_id in partner_ids:
                wallet = wallets_by_partner_id.get(partner_id)

                if wallet:
                    response.append(
                        WalletRPCResponse(
                            id=wallet.id or 0,
                            partner_id=wallet.partner_id,
                            balance=wallet.balance,
                            frozen_balance=wallet.frozen_balance,
                            currency=wallet.currency,
                            is_wallet_enabled=wallet_enabled_by_partner_id.get(
                                partner_id,
                                False,
                            ),
                        )
                    )
                else:
                    response.append(
                        WalletRPCResponse(
                            partner_id=partner_id,
                            balance=Decimal("0.00"),
                            frozen_balance=Decimal("0.00"),
                            currency="INR",
                            is_wallet_enabled=wallet_enabled_by_partner_id.get(
                                partner_id,
                                False,
                            ),
                        )
                    )
            return response

        except Exception as exc:
            self.__logger.error(
                f"Error in get_wallets_by_partner_ids: {exc}",
            )
            raise exc


    async def get_wallet_transactions(
        self,
        partner_id: UUID,
        start_date: Optional[int],
        end_date: Optional[int],
        limit: int,
        offset: int,
        service_name: Optional[str] = None,
        transaction_type: Optional[str] = None,
        attribute_filters: Optional[Dict[str, Any]] = None,
    ) -> WalletTransactionListResponse:
        """Fetch paginated transaction history for a partner with optional filters."""
        try:
            self.__logger.info(
                f"Fetching wallet for partner_id={partner_id} before transaction lookup"
            )
            wallet: Optional[Wallet] = (
                await self.__wallet_repository.get_wallet_by_partner_id(partner_id)
            )

            if not wallet:
                self.__logger.warning(f"No wallet found for partner_id={partner_id}")
                raise WalletNotFoundError(partner_id)

            self.__logger.info(
                f"Fetching transactions for wallet_id={wallet.id}, "
                f"filters: start_date={start_date}, end_date={end_date}, "
                f"service_name={service_name}, transaction_type={transaction_type}"
            )

            transactions, total_count = (
                await self.__wallet_repository.get_wallet_transactions(
                    wallet_id=wallet.id,
                    start_date=start_date,
                    end_date=end_date,
                    limit=limit,
                    offset=offset,
                    service_name=service_name,
                    transaction_type=transaction_type,
                    attribute_filters=attribute_filters,
                )
            )

            self.__logger.info(
                f"Fetched {len(transactions)} transactions (of {total_count}) for partner_id={partner_id}"
            )

            return WalletTransactionListResponse(
                total_count=total_count,
                limit=limit,
                offset=offset,
                transactions=transactions,
            )

        except WalletNotFoundError as exc:
            self.__logger.warning(
                f"Wallet retrieval failed for partner_id={partner_id}: {exc}"
            )
            raise

        except Exception as exc:
            self.__logger.error(
                f"Unexpected error fetching wallet transactions for partner_id={partner_id}: {exc}"
            )
            raise

    async def create_wallet(self, partner_id: UUID) -> Wallet:
        """
        Create a wallet for a given partner.

        Args:
            partner_id (int): ID of the partner for whom the wallet should be created.

        Returns:
            Optional[Wallet]: The newly created Wallet instance.

        Raises:
            WalletAlreadyExistsError: If a wallet already exists for the given partner.
        """
        try:
            self.__logger.info(
                "Attempting to create wallet for partner_id={}".format(partner_id)
            )

            wallet: Wallet = await self.__wallet_repository.create_wallet(partner_id)

            self.__logger.info(
                "Wallet successfully created for partner_id={} with wallet_id={}".format(
                    partner_id, wallet.id
                )
            )

            return wallet

        except WalletAlreadyExistsError as exc:
            self.__logger.warning(
                "Wallet creation failed for partner_id={} — wallet already exists".format(
                    partner_id
                )
            )
            raise exc

        except Exception as exc:
            self.__logger.error(
                "Unexpected error while creating wallet for partner_id={}: {}".format(
                    partner_id, exc
                )
            )
            raise

    async def generate_statement(
        self,
        partner_id: UUID,
        start_date: int,
        end_date: int,
        service_name: str | None,
        transaction_type: str | None,
        partner_timezone: Optional[str] = PartnerTimeZone.ASIA_KOLKATA,
    ) -> str:
        """Generate PDF wallet statement asynchronously and safely."""

        transactions = await self.__wallet_repository.fetch_transactions(
            partner_id=partner_id,
            start_date=start_date,
            end_date=end_date,
            service_name=service_name,
            transaction_type=transaction_type,
        )

        # Async-safe temporary file path
        fd, file_path = tempfile.mkstemp(
            prefix=f"wallet_statement_{partner_id}_{int(datetime.now().timestamp())}_",
            suffix=".pdf",
        )
        os.close(fd)  # Close immediately — ReportLab will reopen this path

        # Offload PDF generation to a background thread (since ReportLab is sync)
        await asyncio.to_thread(self._build_pdf, file_path, transactions, partner_timezone)

        self.__logger.info(
            f"Wallet statement generated successfully for partner_id={partner_id}"
        )
        return file_path

    def _build_pdf(self, file_path: str, transactions, partner_timezone: Optional[str] = PartnerTimeZone.ASIA_KOLKATA,):
        """Build PDF file synchronously using ReportLab."""
        doc = SimpleDocTemplate(
            file_path,
            pagesize=landscape(A4),
            leftMargin=30,
            rightMargin=30,
            topMargin=30,
            bottomMargin=30,
        )

        styles = getSampleStyleSheet()
        centered_title = ParagraphStyle(
            name="CenteredTitle",
            parent=styles["Heading1"],
            alignment=1,
            fontSize=18,
            spaceAfter=20,
        )

        elements = [Paragraph(STATEMENT_TITLE, centered_title), Spacer(1, 0.2 * 72)]

        wallet_table = self._build_wallet_table(transactions, partner_timezone)
        elements.append(wallet_table)

        doc.build(elements)

    def _build_wallet_table(self, transactions, partner_timezone: Optional[str] = PartnerTimeZone.ASIA_KOLKATA,):
        """Construct wallet statement table with wrapped text and colors."""
        styles = getSampleStyleSheet()
        body_style = ParagraphStyle(
            name="Body",
            parent=styles["BodyText"],
            fontSize=9,
            leading=11,
            wordWrap="CJK",
        )

        data = [TABLE_HEADERS]

        for tx in transactions:
            debit, credit = "-", "-"
            tx_type = tx.get("transaction_type")

            if tx_type in {TransactionType.DEBIT.value, TransactionType.FREEZE.value}:
                debit = f"{tx['amount']:.2f}"
            elif tx_type in {
                TransactionType.CREDIT.value,
                TransactionType.UNFREEZE.value,
            }:
                credit = f"{tx['amount']:.2f}"

            tz = ZoneInfo(partner_timezone)
            created_at = tx.get("created_at")
            if isinstance(created_at, (int, float)):
                try:
                    utc_dt = datetime.fromtimestamp(
                        created_at / 1000 if created_at > 1e12 else created_at,
                        tz=timezone.utc,
                    )

                    created_at = utc_dt.astimezone(tz)
                except Exception:
                    created_at = datetime.now(tz)

            row = [
                Paragraph(created_at.strftime("%d-%m-%Y %H:%M:%S"), body_style),
                Paragraph(self.safe_str(tx.get("service_name")), body_style),
                Paragraph(self.safe_str(tx.get("transaction_type")), body_style),
                Paragraph(self.safe_str(tx.get("description")), body_style),
                Paragraph(debit, body_style),
                Paragraph(credit, body_style),
                Paragraph(f"{tx['remaining_balance']:.2f}", body_style),
                Paragraph(self.safe_str(tx.get("status", "SUCCESS")), body_style),
            ]
            data.append(row)

        table = Table(data, repeatRows=1, colWidths=TABLE_COLUMN_WIDTHS)
        table.setStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), HEADER_BG_COLOR),
                ("TEXTCOLOR", (0, 0), (-1, 0), HEADER_TEXT_COLOR),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("ALIGN", (0, 0), (-1, 0), "CENTER"),
                ("BOTTOMPADDING", (0, 0), (-1, 0), 8),
                ("TOPPADDING", (0, 0), (-1, 0), 8),
                ("ALIGN", (0, 1), (-1, -1), "CENTER"),
                ("ALIGN", (3, 1), (3, -1), "LEFT"),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("GRID", (0, 0), (-1, -1), 0.25, GRID_COLOR),
                ("FONTSIZE", (0, 1), (-1, -1), 9),
            ]
        )

        return table

    @staticmethod
    def safe_str(value):
        """Ensure UTF-8 safe string for ReportLab Paragraphs."""
        if value is None:
            return "-"
        if not isinstance(value, str):
            value = str(value)
        return value.encode("utf-8", "ignore").decode("utf-8", "ignore")

    async def perform_transaction(
        self,
        current_user_id: UUID,
        partner_id: UUID,
        transaction_type: TransactionType,
        amount: float,
        service_name: ServiceName,
        description: Optional[str] = None,
        attributes: Optional[Dict[str, Any]] = None,
        debit_from_wallet: Optional[bool] = False,
        additional_info: Optional[Dict[str, Any]] = None,
        create_transaction: bool = True,
        update_wallet: bool = True
    ) -> WalletResponse:
        """Handles wallet transactions with validation, logs, and repo delegation."""

        self.__logger.info(
            "Initiating transaction: partner_id={pid}, type={type}, amount={amt}".format(
                pid=partner_id, type=transaction_type.value, amt=amount
            )
        )

        try:
            # Check wallet existence first (non-locking)
            wallet: Optional[Wallet] = (
                await self.__wallet_repository.get_wallet_by_partner_id(partner_id)
            )
            if not wallet:
                self.__logger.warning(
                    "Wallet not found for partner_id={pid}".format(pid=partner_id)
                )
                raise WalletNotFoundError(partner_id)

            self.__logger.info(
                "Wallet found for partner_id={pid}: balance={bal}, frozen={frozen}".format(
                    pid=partner_id,
                    bal=wallet.balance,
                    frozen=wallet.frozen_balance,
                )
            )

            amount_dec: Decimal = Decimal(str(amount))

            self.__logger.info(
                "Delegating transaction to repository: partner_id={pid}, type={type}".format(
                    pid=partner_id, type=transaction_type.value
                )
            )

            updated_wallet: Wallet = (
                await self.__wallet_repository.perform_wallet_transaction(
                    current_user_id=current_user_id,
                    partner_id=partner_id,
                    transaction_type=transaction_type,
                    amount=amount_dec,
                    service_name=service_name,
                    description=description,
                    attributes=attributes,
                    debit_from_wallet=debit_from_wallet,
                    additional_info=additional_info,
                    create_transaction=create_transaction,
                    update_wallet=update_wallet,
                )
            )

            self.__logger.info(
                "Transaction completed successfully for partner_id={pid}, type={type}".format(
                    pid=partner_id, type=transaction_type.value
                )
            )

            return WalletResponse.model_validate(updated_wallet)

        except WalletNotFoundError as exc:
            self.__logger.warning(
                "WalletNotFoundError in perform_transaction: partner_id={pid}, error={err}".format(
                    pid=partner_id, err=exc
                )
            )
            raise

        except InsufficientBalanceError as exc:
            self.__logger.warning(
                "InsufficientBalanceError in perform_transaction: partner_id={pid}, error={err}".format(
                    pid=partner_id, err=exc
                )
            )
            raise

        except ValueError as exc:
            self.__logger.warning(
                "Validation error during transaction for partner_id={pid}: {err}".format(
                    pid=partner_id, err=exc
                )
            )
            raise

        except Exception as exc:
            self.__logger.error(
                "Unexpected error during transaction for partner_id={pid}: {err}".format(
                    pid=partner_id, err=exc
                )
            )
            raise

    
    async def create_tranaction_csv(
        self,
        list_of_transactions:list[dict],
    ):
        try:
            self.__logger.info("inside in here!!")
            transactions_csv_file = io.StringIO()
            if not list_of_transactions:
                return None
            writer = csv.DictWriter(transactions_csv_file, fieldnames=list_of_transactions[0].keys())
            writer.writeheader()
            writer.writerows(list_of_transactions)
            transactions_csv_file.seek(0)
            csv_content = transactions_csv_file.getvalue()
            csv_base64 = base64.b64encode(
                csv_content.encode("utf-8")
            ).decode("utf-8")

            return csv_base64
        except Exception as exp:
            self.__logger.error(f"Got an exception while creating CSV : {exp}")
    

    def __send_wallet_report_to_internal_partner(self, csv_url: str, timestamp: int):
        formatted_date = datetime.fromtimestamp(int(timestamp / 1000)).strftime("%d-%B-%Y")
        self.__logger.info(
            f"Wallet report email retired with the mailer; CSV ready (not sent): "
            f"wallet_status_{formatted_date}.csv"
        )
        
    
    async def send_partner_wallet_balance_email(self) -> None:
        try:
            # Calulating the time range : 1 Day before the current date
            yesterday = datetime.now().date() - timedelta(days=1)
            start_ts:int = int(datetime.combine(yesterday, datetime.min.time()).timestamp())*1000
            end_ts:int = int(datetime.combine(yesterday, datetime.max.time()).timestamp())*1000
            self.__logger.info(f"Got the dates as {start_ts}, {end_ts}")


            # Getting the CREDIT transactions form the Database for that Date
            list_of_transactions:list[dict] = await self.__wallet_repository.fetch_wallet_transaction_report(
                start_date=start_ts, end_date=end_ts, transaction_type='CREDIT'
            )
            self.__logger.info(f"Got {len(list_of_transactions)} transactions")


            # Creating a CSV out of the transaction
            csv_file = await self.create_tranaction_csv(list_of_transactions)
            self.__logger.info("Got the CSV file")


            # send an email and add transaction CSV as attachment
            if csv_file:
                self.__send_wallet_report_to_internal_partner(csv_url=csv_file, timestamp=start_ts)
            else:
                self.__logger.info(
                    f"Could not any transactions for {datetime.fromtimestamp(int(start_ts/1000)).strftime('%d-%B-%Y')}"
                )
            
        except Exception as exp:
            self.__logger.info(f"Got an excpetion while sending report mail : {exp}")
            raise