import base64
import os
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.components.wallet.constants import WalletEmailConstants
from src.components.wallet.enum import TABLE_HEADERS, ServiceName, TransactionType
from src.components.wallet.errors import InsufficientBalanceError, WalletNotFoundError
from src.components.wallet.repository import WalletRepository
from src.components.wallet.services import WalletService
from src.loggers.console_service_logger import ConsoleServiceLogger
from src.components.services.email_service import EmailService


@pytest.mark.asyncio
class TestWalletService:
    @pytest.fixture(autouse=True)
    def setup_class(self, tmp_path):
        self.mock_wallet_repo = AsyncMock(spec=WalletRepository)
        self.mock_logger = MagicMock(spec=ConsoleServiceLogger)
        self.wallet_service = WalletService(
            wallet_repository=self.mock_wallet_repo, logger=self.mock_logger
        )

        # Sample transactions
        self.transactions = [
            {
                "created_at": 1700000000,
                "service_name": "Babbler",
                "transaction_type": TransactionType.CREDIT.value,
                "description": "Test credit",
                "amount": 100.0,
                "remaining_balance": 500.0,
            },
            {
                "created_at": 1700000500,
                "service_name": "Talko",
                "transaction_type": TransactionType.DEBIT.value,
                "description": None,
                "amount": 50.0,
                "remaining_balance": 450.0,
            },
        ]

    async def test_generate_statement_success(self):
        self.mock_wallet_repo.fetch_transactions.return_value = self.transactions

        with patch.object(
            self.wallet_service, "_build_pdf", return_value=None
        ) as mock_build_pdf:
            file_path = await self.wallet_service.generate_statement(
                partner_id=1,
                start_date=0,
                end_date=9999999999,
                service_name=None,
                transaction_type=None,
            )

            assert file_path.endswith(".pdf")

            mock_build_pdf.assert_called_once()

            call_args = mock_build_pdf.call_args[0]

            assert call_args[0] == file_path

            assert call_args[1] == self.transactions

            assert call_args[2] == "Asia/Kolkata"

            self.mock_logger.info.assert_called_with(
                "Wallet statement generated successfully for partner_id=1"
            )

            if os.path.exists(file_path):
                os.remove(file_path)


    async def test_generate_statement_no_transactions(self):
        self.mock_wallet_repo.fetch_transactions.return_value = []

        with patch.object(
            self.wallet_service, "_build_pdf", return_value=None
        ) as mock_build_pdf:
            await self.wallet_service.generate_statement(
                partner_id=2,
                start_date=0,
                end_date=9999999999,
                service_name=None,
                transaction_type=None,
            )

            mock_build_pdf.assert_called_once()

            call_args = mock_build_pdf.call_args[0]

            assert call_args[0].endswith(".pdf")

            assert call_args[1] == []

            assert call_args[2] == "Asia/Kolkata"


    def test_safe_str(self):
        assert self.wallet_service.safe_str(None) == "-"
        assert self.wallet_service.safe_str(123) == "123"
        assert self.wallet_service.safe_str("hello") == "hello"
        assert self.wallet_service.safe_str("hello\udc80") == "hello"

    def test_build_wallet_table_structure(self):
        table = self.wallet_service._build_wallet_table(self.transactions)
        assert len(table._cellvalues) == 3
        assert [c for c in table._cellvalues[0]] == TABLE_HEADERS

    async def test_perform_transaction_success(self):
        """Should successfully perform transaction."""
        # Mock wallet object consistent with WalletResponse schema
        mock_wallet = MagicMock(
            partner_id=1,
            balance=Decimal("100.00"),
            frozen_balance=Decimal("0.00"),
            currency="INR",
        )

        self.mock_wallet_repo.get_wallet_by_partner_id.return_value = mock_wallet
        self.mock_wallet_repo.perform_wallet_transaction.return_value = mock_wallet

        result = await self.wallet_service.perform_transaction(
            current_user_id=1,
            partner_id=1,
            transaction_type=TransactionType.CREDIT,
            amount=50.0,
            service_name=ServiceName.BABBLER,
        )

        self.mock_wallet_repo.perform_wallet_transaction.assert_awaited_once()
        assert result.partner_id == 1
        assert result.currency == "INR"
        assert isinstance(result.balance, Decimal)
        assert result.balance == Decimal("100.00")

    async def test_perform_transaction_wallet_not_found(self):
        """Should raise WalletNotFoundError if wallet does not exist."""
        self.mock_wallet_repo.get_wallet_by_partner_id.return_value = None

        with pytest.raises(WalletNotFoundError):
            await self.wallet_service.perform_transaction(
                current_user_id=1,
                partner_id=999,
                transaction_type=TransactionType.CREDIT,
                amount=10.0,
                service_name=ServiceName.BABBLER,
            )

    async def test_perform_transaction_insufficient_balance(self):
        """Should raise InsufficientBalanceError from repository."""
        mock_wallet = MagicMock(balance=Decimal("100.00"), frozen_balance=Decimal("0"))
        self.mock_wallet_repo.get_wallet_by_partner_id.return_value = mock_wallet
        self.mock_wallet_repo.perform_wallet_transaction.side_effect = (
            InsufficientBalanceError("Not enough funds")
        )

        with pytest.raises(InsufficientBalanceError):
            await self.wallet_service.perform_transaction(
                current_user_id=1,
                partner_id=1,
                transaction_type=TransactionType.DEBIT,
                amount=200.0,
                service_name=ServiceName.BABBLER,
            )

    async def test_perform_transaction_unexpected_error(self):
        """Should handle unexpected errors gracefully."""
        mock_wallet = MagicMock(balance=Decimal("100.00"), frozen_balance=Decimal("0"))
        self.mock_wallet_repo.get_wallet_by_partner_id.return_value = mock_wallet
        self.mock_wallet_repo.perform_wallet_transaction.side_effect = Exception(
            "DB fail"
        )

        with pytest.raises(Exception):
            await self.wallet_service.perform_transaction(
                current_user_id=1,
                partner_id=1,
                transaction_type=TransactionType.CREDIT,
                amount=50.0,
                service_name=ServiceName.BABBLER,
            )

        self.mock_logger.error.assert_called()

    async def test_generate_statement_passes_default_timezone(self):
        self.mock_wallet_repo.fetch_transactions.return_value = self.transactions

        with patch.object(
            self.wallet_service, "_build_pdf", return_value=None
        ) as mock_build_pdf:
            await self.wallet_service.generate_statement(
                partner_id=1,
                start_date=0,
                end_date=9999999999,
                service_name=None,
                transaction_type=None,
            )

            mock_build_pdf.assert_called_once()
            args = mock_build_pdf.call_args[0]

            assert args[2] == "Asia/Kolkata"


    async def test_get_wallets_by_partner_ids_success(self):
        mock_partner_config_service = AsyncMock()

        mock_wallet = MagicMock(
            id=1,
            partner_id=100,
            balance=Decimal("500.00"),
            frozen_balance=Decimal("50.00"),
            currency="INR",
        )

        mock_config = MagicMock(
            partner_id=100,
            value=True,
        )

        self.mock_wallet_repo.get_wallets_by_partner_ids.return_value = [mock_wallet]

        mock_partner_config_service.get_partner_config_by_key.return_value = [
            mock_config
        ]

        result = await self.wallet_service.get_wallets_by_partner_ids(
            partner_ids=[100],
            partner_config_service=mock_partner_config_service,
        )

        assert len(result) == 1

        assert result[0].partner_id == 100
        assert result[0].balance == Decimal("500.00")
        assert result[0].frozen_balance == Decimal("50.00")
        assert result[0].currency == "INR"
        assert result[0].is_wallet_enabled is True

        self.mock_wallet_repo.get_wallets_by_partner_ids.assert_awaited_once_with(
            [100]
        )

        mock_partner_config_service.get_partner_config_by_key.assert_awaited_once_with(
            [100],
            "is_wallet_enabled",
        )

    async def test_get_wallets_by_partner_ids_wallet_not_found(self):
        mock_partner_config_service = AsyncMock()

        self.mock_wallet_repo.get_wallets_by_partner_ids.return_value = []

        mock_partner_config_service.get_partner_config_by_key.return_value = [
            MagicMock(
                partner_id=200,
                value=True,
            )
        ]

        result = await self.wallet_service.get_wallets_by_partner_ids(
            partner_ids=[200],
            partner_config_service=mock_partner_config_service,
        )

        assert len(result) == 1

        assert result[0].partner_id == 200
        assert result[0].balance == Decimal("0.00")
        assert result[0].frozen_balance == Decimal("0.00")
        assert result[0].currency == "INR"
        assert result[0].is_wallet_enabled is True


    async def test_get_wallets_by_partner_ids_wallet_disabled(self):
        mock_partner_config_service = AsyncMock()

        mock_wallet = MagicMock(
            id=1,
            partner_id=300,
            balance=Decimal("100.00"),
            frozen_balance=Decimal("10.00"),
            currency="INR",
        )

        self.mock_wallet_repo.get_wallets_by_partner_ids.return_value = [mock_wallet]

        mock_partner_config_service.get_partner_config_by_key.return_value = [
            MagicMock(
                partner_id=300,
                value=False,
            )
        ]

        result = await self.wallet_service.get_wallets_by_partner_ids(
            partner_ids=[300],
            partner_config_service=mock_partner_config_service,
        )

        assert len(result) == 1
        assert result[0].is_wallet_enabled is False


    async def test_get_wallets_by_partner_ids_multiple_partners(self):
        mock_partner_config_service = AsyncMock()

        wallet_1 = MagicMock(
            id=1,
            partner_id=101,
            balance=Decimal("100.00"),
            frozen_balance=Decimal("5.00"),
            currency="INR",
        )

        wallet_2 = MagicMock(
            id=2,
            partner_id=103,
            balance=Decimal("300.00"),
            frozen_balance=Decimal("15.00"),
            currency="INR",
        )

        self.mock_wallet_repo.get_wallets_by_partner_ids.return_value = [
            wallet_1,
            wallet_2,
        ]

        mock_partner_config_service.get_partner_config_by_key.return_value = [
            MagicMock(partner_id=101, value=True),
            MagicMock(partner_id=102, value=False),
            MagicMock(partner_id=103, value=True),
        ]

        result = await self.wallet_service.get_wallets_by_partner_ids(
            partner_ids=[101, 102, 103],
            partner_config_service=mock_partner_config_service,
        )

        assert len(result) == 3

        assert result[0].partner_id == 101
        assert result[0].balance == Decimal("100.00")

        assert result[1].partner_id == 102
        assert result[1].balance == Decimal("0.00")
        assert result[1].is_wallet_enabled is False

        assert result[2].partner_id == 103
        assert result[2].balance == Decimal("300.00")
        assert result[2].is_wallet_enabled is True


    async def test_get_wallets_by_partner_ids_repository_exception(self):
        mock_partner_config_service = AsyncMock()

        self.mock_wallet_repo.get_wallets_by_partner_ids.side_effect = Exception(
            "Database error"
        )

        with pytest.raises(Exception, match="Database error"):
            await self.wallet_service.get_wallets_by_partner_ids(
                partner_ids=[1, 2],
                partner_config_service=mock_partner_config_service,
            )

        self.mock_logger.error.assert_called_once()


    async def test_get_wallets_by_partner_ids_partner_config_exception(self):
        mock_partner_config_service = AsyncMock()

        self.mock_wallet_repo.get_wallets_by_partner_ids.return_value = []

        mock_partner_config_service.get_partner_config_by_key.side_effect = Exception(
            "Config service error"
        )

        with pytest.raises(Exception, match="Config service error"):
            await self.wallet_service.get_wallets_by_partner_ids(
                partner_ids=[1],
                partner_config_service=mock_partner_config_service,
            )

        self.mock_logger.error.assert_called_once()




    async def test_get_wallets_by_partner_ids_success(self):
        mock_partner_config_service = AsyncMock()

        mock_wallet = MagicMock(
            id=1,
            partner_id=100,
            balance=Decimal("500.00"),
            frozen_balance=Decimal("50.00"),
            currency="INR",
        )

        mock_config = MagicMock(
            partner_id=100,
            value=True,
        )

        self.mock_wallet_repo.get_wallets_by_partner_ids.return_value = [mock_wallet]

        mock_partner_config_service.get_partner_config_by_key.return_value = [
            mock_config
        ]

        result = await self.wallet_service.get_wallets_by_partner_ids(
            partner_ids=[100],
            partner_config_service=mock_partner_config_service,
        )

        assert len(result) == 1

        assert result[0].partner_id == 100
        assert result[0].balance == Decimal("500.00")
        assert result[0].frozen_balance == Decimal("50.00")
        assert result[0].currency == "INR"
        assert result[0].is_wallet_enabled is True

        self.mock_wallet_repo.get_wallets_by_partner_ids.assert_awaited_once_with(
            [100]
        )

        mock_partner_config_service.get_partner_config_by_key.assert_awaited_once_with(
            [100],
            "is_wallet_enabled",
        )

    async def test_get_wallets_by_partner_ids_wallet_not_found(self):
        mock_partner_config_service = AsyncMock()

        self.mock_wallet_repo.get_wallets_by_partner_ids.return_value = []

        mock_partner_config_service.get_partner_config_by_key.return_value = [
            MagicMock(
                partner_id=200,
                value=True,
            )
        ]

        result = await self.wallet_service.get_wallets_by_partner_ids(
            partner_ids=[200],
            partner_config_service=mock_partner_config_service,
        )

        assert len(result) == 1

        assert result[0].partner_id == 200
        assert result[0].balance == Decimal("0.00")
        assert result[0].frozen_balance == Decimal("0.00")
        assert result[0].currency == "INR"
        assert result[0].is_wallet_enabled is True


    async def test_get_wallets_by_partner_ids_wallet_disabled(self):
        mock_partner_config_service = AsyncMock()

        mock_wallet = MagicMock(
            id=1,
            partner_id=300,
            balance=Decimal("100.00"),
            frozen_balance=Decimal("10.00"),
            currency="INR",
        )

        self.mock_wallet_repo.get_wallets_by_partner_ids.return_value = [mock_wallet]

        mock_partner_config_service.get_partner_config_by_key.return_value = [
            MagicMock(
                partner_id=300,
                value=False,
            )
        ]

        result = await self.wallet_service.get_wallets_by_partner_ids(
            partner_ids=[300],
            partner_config_service=mock_partner_config_service,
        )

        assert len(result) == 1
        assert result[0].is_wallet_enabled is False


    async def test_get_wallets_by_partner_ids_multiple_partners(self):
        mock_partner_config_service = AsyncMock()

        wallet_1 = MagicMock(
            id=1,
            partner_id=101,
            balance=Decimal("100.00"),
            frozen_balance=Decimal("5.00"),
            currency="INR",
        )

        wallet_2 = MagicMock(
            id=2,
            partner_id=103,
            balance=Decimal("300.00"),
            frozen_balance=Decimal("15.00"),
            currency="INR",
        )

        self.mock_wallet_repo.get_wallets_by_partner_ids.return_value = [
            wallet_1,
            wallet_2,
        ]

        mock_partner_config_service.get_partner_config_by_key.return_value = [
            MagicMock(partner_id=101, value=True),
            MagicMock(partner_id=102, value=False),
            MagicMock(partner_id=103, value=True),
        ]

        result = await self.wallet_service.get_wallets_by_partner_ids(
            partner_ids=[101, 102, 103],
            partner_config_service=mock_partner_config_service,
        )

        assert len(result) == 3

        assert result[0].partner_id == 101
        assert result[0].balance == Decimal("100.00")

        assert result[1].partner_id == 102
        assert result[1].balance == Decimal("0.00")
        assert result[1].is_wallet_enabled is False

        assert result[2].partner_id == 103
        assert result[2].balance == Decimal("300.00")
        assert result[2].is_wallet_enabled is True


    async def test_get_wallets_by_partner_ids_repository_exception(self):
        mock_partner_config_service = AsyncMock()

        self.mock_wallet_repo.get_wallets_by_partner_ids.side_effect = Exception(
            "Database error"
        )

        with pytest.raises(Exception, match="Database error"):
            await self.wallet_service.get_wallets_by_partner_ids(
                partner_ids=[1, 2],
                partner_config_service=mock_partner_config_service,
            )

        self.mock_logger.error.assert_called_once()


    async def test_get_wallets_by_partner_ids_partner_config_exception(self):
        mock_partner_config_service = AsyncMock()

        self.mock_wallet_repo.get_wallets_by_partner_ids.return_value = []

        mock_partner_config_service.get_partner_config_by_key.side_effect = Exception(
            "Config service error"
        )

        with pytest.raises(Exception, match="Config service error"):
            await self.wallet_service.get_wallets_by_partner_ids(
                partner_ids=[1],
                partner_config_service=mock_partner_config_service,
            )

        self.mock_logger.error.assert_called_once()



    @pytest.mark.asyncio
    async def test_create_transaction_csv_success(self):
        result = await self.wallet_service.create_tranaction_csv(
            self.transactions
        )

        assert result is not None

        decoded_csv = base64.b64decode(result).decode("utf-8")

        assert "created_at" in decoded_csv
        assert "service_name" in decoded_csv
        assert "Babbler" in decoded_csv
        assert "Talko" in decoded_csv

    
    @pytest.mark.asyncio
    async def test_create_transaction_csv_empty(self):
        result = await self.wallet_service.create_tranaction_csv(
            []
        )

        assert result is None

    
    @pytest.mark.asyncio
    @patch("csv.DictWriter")
    async def test_create_transaction_csv_exception(
        self,
        mock_writer
    ):
        mock_writer.side_effect = Exception("csv failed")

        result = await self.wallet_service.create_tranaction_csv(
            self.transactions
        )

        assert result is None

        self.mock_logger.error.assert_called_once()

    
    def test_send_wallet_report_success(self):
        mock_email = MagicMock(spec=EmailService)

        self.wallet_service._WalletService__send_wallet_report_to_internal_partner(
            csv_url="encoded_csv",
            timestamp=1700000000000,
            email=mock_email,
        )

        mock_email.send_email.assert_called_once()

        kwargs = mock_email.send_email.call_args.kwargs

        assert kwargs["attachments"][0]["content"] == "encoded_csv"

        assert kwargs["html_template"] == "wallet_report.html"

        assert kwargs["subject"] == WalletEmailConstants.SUBJECT

        self.mock_logger.info.assert_called_with("email sent")

    
    def test_send_wallet_report_exception(self):
        mock_email = MagicMock(spec=EmailService)

        mock_email.send_email.side_effect = Exception("email failed")

        with pytest.raises(Exception):
            self.wallet_service._WalletService__send_wallet_report_to_internal_partner(
                csv_url="encoded_csv",
                timestamp=1700000000000,
                email=mock_email,
            )

        self.mock_logger.info.assert_called()

    
    @pytest.mark.asyncio
    async def test_send_partner_wallet_balance_email_success(self):
        self.mock_wallet_repo.fetch_wallet_transaction_report.return_value = (
            self.transactions
        )

        with patch.object(
            self.wallet_service,
            "_WalletService__send_wallet_report_to_internal_partner"
        ) as mock_send_email:

            await self.wallet_service.send_partner_wallet_balance_email()

            self.mock_wallet_repo.fetch_wallet_transaction_report.assert_awaited_once()

            mock_send_email.assert_called_once()

    @pytest.mark.asyncio
    async def test_send_partner_wallet_balance_email_no_transactions(self):
        self.mock_wallet_repo.fetch_wallet_transaction_report.return_value = []

        with patch.object(
            self.wallet_service,
            "_WalletService__send_wallet_report_to_internal_partner"
        ) as mock_send_email:

            await self.wallet_service.send_partner_wallet_balance_email()

            mock_send_email.assert_not_called()

            self.mock_logger.info.assert_called()

    
    @pytest.mark.asyncio
    async def test_send_partner_wallet_balance_email_repository_exception(
        self,
    ):
        self.mock_wallet_repo.fetch_wallet_transaction_report.side_effect = (
            Exception("db failed")
        )

        with pytest.raises(Exception):
            await self.wallet_service.send_partner_wallet_balance_email()

        self.mock_logger.info.assert_called()

    
    @pytest.mark.asyncio
    async def test_send_partner_wallet_balance_email_email_exception(
        self,
    ):
        self.mock_wallet_repo.fetch_wallet_transaction_report.return_value = (
            self.transactions
        )

        with patch.object(
            self.wallet_service,
            "_WalletService__send_wallet_report_to_internal_partner",
            side_effect=Exception("mail failed")
        ):
            with pytest.raises(Exception):
                await self.wallet_service.send_partner_wallet_balance_email()

        self.mock_logger.info.assert_called()