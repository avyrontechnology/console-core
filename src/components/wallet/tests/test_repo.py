from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy.exc import SQLAlchemyError

from src.components.wallet.enum import ServiceName, TransactionType
from src.components.wallet.errors import (
    InsufficientBalanceError,
    WalletBalanceOverflowError,
    WalletNotFoundError,
)
from src.components.wallet.models import Wallet, WalletTransaction
from src.components.wallet.repository import MAX_WALLET_NUMERIC, WalletRepository


@pytest.mark.asyncio
class TestWalletRepository:
    @pytest.fixture(autouse=True)
    def setup_class(self, mock_session_factory, mock_logger):
        """Setup WalletRepository with mock session and logger."""
        self.wallet_repository = WalletRepository(
            session_factory=mock_session_factory, logger=mock_logger
        )
        self.session = mock_session_factory.return_value.__aenter__.return_value
        self.mock_logger = mock_logger

        # Sample wallet and transaction
        self.wallet = Wallet(
            id=1,
            partner_id=1,
            balance=Decimal("100.00"),
            frozen_balance=Decimal("20.00"),
        )

        self.mock_transaction = WalletTransaction(
            id=1,
            wallet_id=1,
            service_name="Babbler",
            transaction_type="CREDIT",
            description="Test transaction",
            amount=100.0,
            remaining_balance=900.0,
            created_at=1234567890,
        )

    # ✅ Existing tests
    async def test_fetch_transactions_success(self):
        """Test successful fetch of wallet transactions."""
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = [self.mock_transaction]

        mock_execute = MagicMock()
        mock_execute.scalars.return_value = mock_scalars
        self.session.execute = AsyncMock(return_value=mock_execute)

        result = await self.wallet_repository.fetch_transactions(
            partner_id=1,
            start_date=0,
            end_date=9999999999,
            service_name=None,
            transaction_type=None,
        )

        assert isinstance(result, list)
        assert result[0]["service_name"] == "Babbler"
        assert result[0]["transaction_type"] == "CREDIT"
        assert result[0]["amount"] == 100.0
        assert result[0]["remaining_balance"] == 900.0

    async def test_fetch_transactions_with_filters(self):
        """Test fetch_transactions with service_name and transaction_type filters."""
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = [self.mock_transaction]

        mock_execute = MagicMock()
        mock_execute.scalars.return_value = mock_scalars
        self.session.execute = AsyncMock(return_value=mock_execute)

        result = await self.wallet_repository.fetch_transactions(
            partner_id=1,
            start_date=0,
            end_date=9999999999,
            service_name="Babbler",
            transaction_type="CREDIT",
        )

        assert len(result) == 1
        assert result[0]["service_name"] == "Babbler"
        assert result[0]["transaction_type"] == "CREDIT"

    async def test_fetch_transactions_no_transactions(self):
        """Test fetch_transactions when no transactions exist."""
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = []

        mock_execute = MagicMock()
        mock_execute.scalars.return_value = mock_scalars
        self.session.execute = AsyncMock(return_value=mock_execute)

        result = await self.wallet_repository.fetch_transactions(
            partner_id=1,
            start_date=0,
            end_date=9999999999,
            service_name=None,
            transaction_type=None,
        )

        assert result == []

    async def test_fetch_transactions_raises_exception(self):
        """Test fetch_transactions raises exception and logs error."""
        self.session.execute = AsyncMock(side_effect=Exception("Unexpected Error"))

        with pytest.raises(Exception) as exc_info:
            await self.wallet_repository.fetch_transactions(
                partner_id=1,
                start_date=0,
                end_date=9999999999,
                service_name=None,
                transaction_type=None,
            )

        assert str(exc_info.value) == "Unexpected Error"
        self.mock_logger.error.assert_called_with(
            "Error fetching transactions for partner_id=1 | Error: Unexpected Error"
        )

    async def test_perform_wallet_transaction_credit_success(self):
        """Should increase balance on CREDIT transaction."""
        # Mock wallet with currency to match WalletResponse schema
        self.wallet.currency = "INR"

        # Mock DB query result
        self.session.execute = AsyncMock(
            return_value=MagicMock(
                scalar_one_or_none=MagicMock(return_value=self.wallet)
            )
        )
        self.session.add = AsyncMock()
        self.session.flush = AsyncMock()
        self.session.commit = AsyncMock()
        self.session.refresh = AsyncMock()

        result = await self.wallet_repository.perform_wallet_transaction(
            current_user_id=1,
            partner_id=1,
            transaction_type=TransactionType.CREDIT,
            amount=Decimal("50.00"),
            service_name=ServiceName.BABBLER,
            description="Credit test",
        )

        assert result.balance == Decimal("150.00")
        assert result.frozen_balance == Decimal("20.00")
        assert result.currency == "INR"
        self.session.commit.assert_awaited_once()
        self.mock_logger.info.assert_any_call(
            "Transaction committed successfully for partner_id=1"
        )


    async def test_get_wallets_by_partner_ids_success(self):
        wallet_1 = Wallet(
            id=1,
            partner_id=101,
            balance=Decimal("100.00"),
            frozen_balance=Decimal("10.00"),
        )

        wallet_2 = Wallet(
            id=2,
            partner_id=102,
            balance=Decimal("200.00"),
            frozen_balance=Decimal("20.00"),
        )

        mock_scalars = MagicMock()
        mock_scalars.all.return_value = [wallet_1, wallet_2]

        mock_result = MagicMock()
        mock_result.scalars.return_value = mock_scalars

        self.session.execute = AsyncMock(return_value=mock_result)

        result = await self.wallet_repository.get_wallets_by_partner_ids(
            [101, 102]
        )

        assert len(result) == 2
        assert result[0].partner_id == 101
        assert result[1].partner_id == 102

        self.mock_logger.info.assert_called_with(
            "Fetching wallets for partner_ids=[101, 102]"
        )

    async def test_get_wallets_by_partner_ids_empty_result(self):
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = []

        mock_result = MagicMock()
        mock_result.scalars.return_value = mock_scalars

        self.session.execute = AsyncMock(return_value=mock_result)

        result = await self.wallet_repository.get_wallets_by_partner_ids(
            [999]
        )

        assert result == []

        self.mock_logger.info.assert_called_with(
            "Fetching wallets for partner_ids=[999]"
        )

    async def test_get_wallets_by_partner_ids_database_exception(self):
        self.session.execute = AsyncMock(
            side_effect=Exception("Database failure")
        )

        with pytest.raises(Exception, match="Database failure"):
            await self.wallet_repository.get_wallets_by_partner_ids(
                [1, 2, 3]
            )

        self.mock_logger.error.assert_called_with(
            "Database error: Database failure"
        )


    async def test_get_wallets_by_partner_ids_execute_called(self):
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = [self.wallet]

        mock_result = MagicMock()
        mock_result.scalars.return_value = mock_scalars

        self.session.execute = AsyncMock(return_value=mock_result)

        await self.wallet_repository.get_wallets_by_partner_ids([1])

        self.session.execute.assert_awaited_once()

        
    async def test_perform_wallet_transaction_debit_insufficient_balance(self):
        """Should raise InsufficientBalanceError if debit > available balance."""
        self.session.execute = AsyncMock(
            return_value=MagicMock(
                scalar_one_or_none=MagicMock(return_value=self.wallet)
            )
        )

        with pytest.raises(InsufficientBalanceError):
            await self.wallet_repository.perform_wallet_transaction(
                current_user_id=1,
                partner_id=1,
                transaction_type=TransactionType.DEBIT,
                amount=Decimal("1190.00"),
                service_name=ServiceName.BABBLER,
            )

    async def test_perform_wallet_transaction_wallet_not_found(self):
        """Should raise WalletNotFoundError if wallet not found."""
        self.session.execute = AsyncMock(
            return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=None))
        )

        with pytest.raises(WalletNotFoundError):
            await self.wallet_repository.perform_wallet_transaction(
                current_user_id=1,
                partner_id=99,
                transaction_type=TransactionType.CREDIT,
                amount=Decimal("10.00"),
                service_name=ServiceName.BABBLER,
            )

    async def test_perform_wallet_transaction_sqlalchemy_error(self):
        """Should handle SQLAlchemyError properly."""
        self.session.execute = AsyncMock(side_effect=SQLAlchemyError("DB error"))

        with pytest.raises(SQLAlchemyError):
            await self.wallet_repository.perform_wallet_transaction(
                current_user_id=1,
                partner_id=1,
                transaction_type=TransactionType.CREDIT,
                amount=Decimal("10.00"),
                service_name=ServiceName.BABBLER,
            )
        self.mock_logger.error.assert_called()

    @pytest.mark.asyncio
    async def test_perform_wallet_transaction_debit_success(self):
        """Should decrease balance correctly on DEBIT transaction."""
        wallet = MagicMock(
            balance=Decimal("100.00"), frozen_balance=Decimal("20.00"), currency="INR"
        )
        self.session.execute = AsyncMock(
            return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=wallet))
        )
        self.session.add = AsyncMock()
        self.session.flush = AsyncMock()
        self.session.commit = AsyncMock()
        self.session.refresh = AsyncMock()

        result = await self.wallet_repository.perform_wallet_transaction(
            current_user_id=1,
            partner_id=1,
            transaction_type=TransactionType.DEBIT,
            amount=Decimal("50.00"),
            service_name=ServiceName.BABBLER,
            description="Debit test",
            debit_from_wallet=True,
        )

        assert result.balance == Decimal("50.00")
        assert result.frozen_balance == Decimal("20.00")

    @pytest.mark.asyncio
    async def test_perform_wallet_transaction_freeze_success(self):
        """Should freeze amount and reduce available balance."""
        wallet = MagicMock(
            balance=Decimal("100.00"), frozen_balance=Decimal("10.00"), currency="INR"
        )
        self.session.execute = AsyncMock(
            return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=wallet))
        )
        self.session.add = AsyncMock()
        self.session.flush = AsyncMock()
        self.session.commit = AsyncMock()
        self.session.refresh = AsyncMock()

        result = await self.wallet_repository.perform_wallet_transaction(
            current_user_id=1,
            partner_id=1,
            transaction_type=TransactionType.FREEZE,
            amount=Decimal("30.00"),
            service_name=ServiceName.MAGLO,
            description="Freeze test",
        )

        assert result.balance == Decimal("70.00")
        assert result.frozen_balance == Decimal("40.00")

    @pytest.mark.asyncio
    async def test_perform_wallet_transaction_unfreeze_success(self):
        """Should unfreeze amount and increase available balance."""
        wallet = MagicMock(
            balance=Decimal("100.00"), frozen_balance=Decimal("50.00"), currency="INR"
        )
        self.session.execute = AsyncMock(
            return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=wallet))
        )
        self.session.add = AsyncMock()
        self.session.flush = AsyncMock()
        self.session.commit = AsyncMock()
        self.session.refresh = AsyncMock()

        result = await self.wallet_repository.perform_wallet_transaction(
            current_user_id=1,
            partner_id=1,
            transaction_type=TransactionType.UNFREEZE,
            amount=Decimal("20.00"),
            service_name=ServiceName.TALKO,
            description="Unfreeze test",
        )

        assert result.balance == Decimal("120.00")
        assert result.frozen_balance == Decimal("30.00")

    @pytest.mark.asyncio
    async def test_perform_wallet_transaction_insufficient_debit(self):
        """Should raise InsufficientBalanceError for DEBIT exceeding available."""
        wallet = MagicMock(
            balance=Decimal("100.00"), frozen_balance=Decimal("80.00"), currency="INR"
        )
        self.session.execute = AsyncMock(
            return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=wallet))
        )

        with pytest.raises(InsufficientBalanceError):
            await self.wallet_repository.perform_wallet_transaction(
                current_user_id=1,
                partner_id=1,
                transaction_type=TransactionType.DEBIT,
                amount=Decimal("150.00"),
                service_name=ServiceName.BABBLER,
            )

    @pytest.mark.asyncio
    async def test_perform_wallet_transaction_insufficient_freeze(self):
        """Should raise InsufficientBalanceError for FREEZE exceeding available."""
        wallet = MagicMock(
            balance=Decimal("100.00"), frozen_balance=Decimal("90.00"), currency="INR"
        )
        self.session.execute = AsyncMock(
            return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=wallet))
        )

        with pytest.raises(InsufficientBalanceError):
            await self.wallet_repository.perform_wallet_transaction(
                current_user_id=1,
                partner_id=1,
                transaction_type=TransactionType.FREEZE,
                amount=Decimal("110.00"),
                service_name=ServiceName.MAGLO,
            )

    @pytest.mark.asyncio
    async def test_perform_wallet_transaction_insufficient_unfreeze(self):
        """Should raise InsufficientBalanceError for UNFREEZE exceeding frozen balance."""
        wallet = MagicMock(
            balance=Decimal("100.00"), frozen_balance=Decimal("10.00"), currency="INR"
        )
        self.session.execute = AsyncMock(
            return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=wallet))
        )

        with pytest.raises(InsufficientBalanceError):
            await self.wallet_repository.perform_wallet_transaction(
                current_user_id=1,
                partner_id=1,
                transaction_type=TransactionType.UNFREEZE,
                amount=Decimal("50.00"),
                service_name=ServiceName.TALKO,
            )

    @pytest.mark.asyncio
    async def test_validate_post_operation_balance_overflow_balance(self):
        """Should raise WalletBalanceOverflowError when new_balance exceeds limit."""
        new_balance = MAX_WALLET_NUMERIC + Decimal("1.00")
        new_frozen = Decimal("0.00")

        with pytest.raises(WalletBalanceOverflowError):
            self.wallet_repository._validate_post_operation_balance(
                new_balance=new_balance,
                new_frozen=new_frozen,
            )

        self.mock_logger.error.assert_any_call(
            f"Wallet balance overflow detected: new_balance={new_balance}, limit={MAX_WALLET_NUMERIC}"
        )

    @pytest.mark.asyncio
    async def test_validate_post_operation_balance_overflow_frozen(self):
        """Should raise WalletBalanceOverflowError when new_frozen exceeds limit."""
        new_balance = Decimal("0.00")
        new_frozen = MAX_WALLET_NUMERIC + Decimal("1.00")

        with pytest.raises(WalletBalanceOverflowError):
            self.wallet_repository._validate_post_operation_balance(
                new_balance=new_balance,
                new_frozen=new_frozen,
            )

        self.mock_logger.error.assert_any_call(
            f"Frozen balance overflow detected: new_frozen={new_frozen}, limit={MAX_WALLET_NUMERIC}"
        )

    @pytest.mark.asyncio
    async def test_validate_post_operation_balance_valid(self):
        """Should NOT raise any exception when balances are within allowed limits."""
        try:
            self.wallet_repository._validate_post_operation_balance(
                new_balance=Decimal("5000.00"),
                new_frozen=Decimal("2000.00"),
            )
        except Exception:
            pytest.fail("Unexpected exception raised for valid balance/frozen values")

    
    @pytest.mark.asyncio
    async def test_fetch_wallet_transaction_report_success(self):
        expected = [
            {
                "partner_id": 1,
                "balance": Decimal("100.00"),
                "frozen_balance": Decimal("20.00"),
                "service": "Babbler",
                "amount": 100.0,
                "description": "Test transaction",
                "type": "CREDIT",
                "created_at": 1234567890,
            }
        ]

        execute_result = MagicMock()
        execute_result.mappings.return_value.all.return_value = expected

        self.session.execute = AsyncMock(
            return_value=execute_result
        )

        result = await self.wallet_repository.fetch_wallet_transaction_report(
            start_date=123,
            end_date=456,
        )

        assert result == expected

        self.session.execute.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_fetch_wallet_transaction_report_empty(self):
        execute_result = MagicMock()
        execute_result.mappings.return_value.all.return_value = []

        self.session.execute = AsyncMock(
            return_value=execute_result
        )

        result = await self.wallet_repository.fetch_wallet_transaction_report(
            start_date=123,
            end_date=456,
        )

        assert result == []

    @pytest.mark.asyncio
    async def test_fetch_wallet_transaction_report_with_service_filter(
        self
    ):
        execute_result = MagicMock()
        execute_result.mappings.return_value.all.return_value = []

        self.session.execute = AsyncMock(
            return_value=execute_result
        )

        await self.wallet_repository.fetch_wallet_transaction_report(
            start_date=123,
            end_date=456,
            service_name="Babbler",
        )

        self.session.execute.assert_awaited_once()

    
    @pytest.mark.asyncio
    async def test_fetch_wallet_transaction_report_with_transaction_type_filter(
        self
    ):
        execute_result = MagicMock()
        execute_result.mappings.return_value.all.return_value = []

        self.session.execute = AsyncMock(
            return_value=execute_result
        )

        await self.wallet_repository.fetch_wallet_transaction_report(
            start_date=123,
            end_date=456,
            transaction_type="CREDIT",
        )

        self.session.execute.assert_awaited_once()


    @pytest.mark.asyncio
    async def test_fetch_wallet_transaction_report_with_all_filters(
        self
    ):
        execute_result = MagicMock()
        execute_result.mappings.return_value.all.return_value = []

        self.session.execute = AsyncMock(
            return_value=execute_result
        )

        await self.wallet_repository.fetch_wallet_transaction_report(
            start_date=123,
            end_date=456,
            service_name="Babbler",
            transaction_type="CREDIT",
        )

        self.session.execute.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_fetch_wallet_transaction_report_service_filter_query(
        self
    ):
        execute_result = MagicMock()
        execute_result.mappings.return_value.all.return_value = []

        self.session.execute = AsyncMock(
            return_value=execute_result
        )

        await self.wallet_repository.fetch_wallet_transaction_report(
            start_date=123,
            end_date=456,
            service_name="Babbler",
        )

        query = self.session.execute.call_args.args[0]

        sql = str(
            query.compile(
                compile_kwargs={"literal_binds": True}
            )
        )

        assert "Babbler" in sql

    @pytest.mark.asyncio
    async def test_fetch_wallet_transaction_report_service_filter_query(self):
        execute_result = MagicMock()
        execute_result.mappings.return_value.all.return_value = []

        self.session.execute = AsyncMock(
            return_value=execute_result
        )

        await self.wallet_repository.fetch_wallet_transaction_report(
            start_date=123,
            end_date=456,
            service_name="Babbler",
        )

        query = self.session.execute.call_args.args[0]

        compiled = query.compile()

        assert "Babbler" in compiled.params.values()


    @pytest.mark.asyncio
    async def test_fetch_wallet_transaction_report_exception(self):
        self.mock_logger.reset_mock()

        self.session.execute = AsyncMock(
            side_effect=Exception("database error")
        )

        with pytest.raises(Exception, match="database error"):
            await self.wallet_repository.fetch_wallet_transaction_report(
                start_date=123,
                end_date=456,
            )

        self.mock_logger.error.assert_called()

        assert (
            "Error fetching wallet transaction report"
            in self.mock_logger.error.call_args[0][0]
        )