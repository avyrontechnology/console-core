from uuid import UUID
from decimal import Decimal

import pytest
from pydantic import ValidationError

from src.components.wallet.enum import MAX_WALLET_NUMERIC, ServiceName, TransactionType
from src.components.wallet.schema import (
    WalletResponse,
    WalletTransactionListResponse,
    WalletTransactionRequest,
    WalletTransactionResponse,
)


class TestWalletSchemas:

    def test_wallet_transaction_request_valid(self):
        """Should create WalletTransactionRequest with valid data."""
        payload = WalletTransactionRequest(
            partner_id= UUID("12121212-1212-1212-1212-121212121212"),
            transaction_type=TransactionType.CREDIT,
            amount=1000.0,
            service_name=ServiceName.TALKO,
            description="Top-up",
            attributes={"campaign_id": "CMP123"},
        )

        assert payload.partner_id== UUID("12121212-1212-1212-1212-121212121212")
        assert payload.transaction_type == TransactionType.CREDIT
        assert payload.amount == 1000.0
        assert payload.service_name == ServiceName.TALKO
        assert payload.description == "Top-up"
        assert payload.attributes["campaign_id"] == "CMP123"

    def test_wallet_transaction_request_amount_zero_or_negative(self):
        """Should raise validation error if amount <= 0."""
        with pytest.raises(ValidationError):
            WalletTransactionRequest(
                transaction_type=TransactionType.CREDIT,
                amount=0,
                service_name=ServiceName.TALKO,
            )

        with pytest.raises(ValidationError):
            WalletTransactionRequest(
                transaction_type=TransactionType.DEBIT,
                amount=-100,
                service_name=ServiceName.TALKO,
            )

    def test_wallet_transaction_request_amount_exceeds_max(self):
        """Should raise validation error if amount > MAX_WALLET_NUMERIC."""
        with pytest.raises(ValidationError):
            WalletTransactionRequest(
                transaction_type=TransactionType.CREDIT,
                amount=MAX_WALLET_NUMERIC + 1,
                service_name=ServiceName.TALKO,
            )

    def test_wallet_response_instantiation(self):
        """Should create WalletResponse from attributes."""
        wallet = WalletResponse(
            partner_id= UUID("11111111-1111-1111-1111-111111111111"),
            balance=Decimal("5000.00"),
            frozen_balance=Decimal("1000.00"),
            currency="INR",
        )
        assert wallet.balance == Decimal("5000.00")
        assert wallet.frozen_balance == Decimal("1000.00")
        assert wallet.currency == "INR"

    def test_wallet_transaction_response_instantiation(self):
        """Should create WalletTransactionResponse from attributes."""
        tx = WalletTransactionResponse(
            id= UUID("11111111-1111-1111-1111-111111111111"),
            wallet_id= UUID("11111111-1111-1111-1111-111111111111"),
            transaction_type="CREDIT",
            service_name="Talko",
            previous_balance=Decimal("1000.00"),
            amount=Decimal("500.00"),
            remaining_balance=Decimal("1500.00"),
            description="Top-up",
            attributes={"campaign_id": "CMP1"},
            created_at=1234567890,
            additional_info={},
            status="SUCCESS"
        )

        assert tx.id == UUID("11111111-1111-1111-1111-111111111111")
        assert tx.wallet_id== UUID("11111111-1111-1111-1111-111111111111")
        assert tx.transaction_type == "CREDIT"
        assert tx.amount == Decimal("500.00")
        assert tx.remaining_balance == Decimal("1500.00")
        assert tx.attributes["campaign_id"] == "CMP1"

    def test_wallet_transaction_list_response_instantiation(self):
        """Should create WalletTransactionListResponse with multiple transactions."""
        tx1 = WalletTransactionResponse(
            id= UUID("11111111-1111-1111-1111-111111111111"),
            wallet_id= UUID("11111111-1111-1111-1111-111111111111"),
            transaction_type="CREDIT",
            service_name="Talko",
            previous_balance=Decimal("1000.00"),
            amount=Decimal("500.00"),
            remaining_balance=Decimal("1500.00"),
            description=None,
            attributes=None,
            created_at=1234567890,
            additional_info={},
            status="SUCCESS"
        )
        tx2 = WalletTransactionResponse(
            id= UUID("22222222-2222-2222-2222-222222222222"),
            wallet_id= UUID("11111111-1111-1111-1111-111111111111"),
            transaction_type="DEBIT",
            service_name="Talko",
            previous_balance=Decimal("1500.00"),
            amount=Decimal("200.00"),
            remaining_balance=Decimal("1300.00"),
            description=None,
            attributes=None,
            created_at=1234567891,
            additional_info={},
            status="SUCCESS"
        )

        tx_list = WalletTransactionListResponse(
            total_count=2, limit=10, offset=0, transactions=[tx1, tx2]
        )

        assert tx_list.total_count == 2
        assert len(tx_list.transactions) == 2
        assert tx_list.transactions[0].id == UUID("11111111-1111-1111-1111-111111111111")
        assert tx_list.transactions[1].transaction_type == "DEBIT"

    @pytest.mark.parametrize(
        "invalid_value",
        ["abc", None, "", {}, []],
    )
    def test_validate_amount_before_invalid(self, invalid_value):
        """Should raise ValueError if amount cannot be converted to float."""
        with pytest.raises(ValidationError) as exc_info:
            WalletTransactionRequest(
                transaction_type=TransactionType.CREDIT,
                amount=invalid_value,
                service_name=ServiceName.TALKO,
            )
        assert "Invalid amount: must be a number" in str(exc_info.value)

    @pytest.mark.parametrize(
        "invalid_value",
        [0, -1, -100.5],
    )
    def test_validate_amount_non_positive(self, invalid_value):
        """Should raise ValueError if amount <= 0 after parsing."""
        with pytest.raises(ValidationError) as exc_info:
            WalletTransactionRequest(
                transaction_type=TransactionType.CREDIT,
                amount=invalid_value,
                service_name=ServiceName.TALKO,
            )
        assert "Invalid amount: must be a positive number" in str(exc_info.value)

    def test_validate_amount_exceeds_max(self):
        """Should raise ValueError if amount > MAX_WALLET_NUMERIC."""
        with pytest.raises(ValidationError) as exc_info:
            WalletTransactionRequest(
                transaction_type=TransactionType.CREDIT,
                amount=MAX_WALLET_NUMERIC + 1,
                service_name=ServiceName.TALKO,
            )
        assert f"Invalid amount: must not exceed {MAX_WALLET_NUMERIC}" in str(
            exc_info.value
        )

    @pytest.mark.parametrize("invalid_service", ["InvalidService", 123, None, ""])
    def test_validate_service_name_before_invalid(self, invalid_service):
        """Should raise ValueError for invalid service_name."""
        with pytest.raises(ValidationError) as exc_info:
            WalletTransactionRequest(
                transaction_type=TransactionType.CREDIT,
                amount=100,
                service_name=invalid_service,
            )
        assert "Invalid Service Name: must be from existing Product" in str(
            exc_info.value
        )

    @pytest.mark.parametrize("invalid_type", ["InvalidType", 123, None, ""])
    def test_validate_transaction_type_before_invalid(self, invalid_type):
        """Should raise ValueError for invalid transaction_type."""
        with pytest.raises(ValidationError) as exc_info:
            WalletTransactionRequest(
                transaction_type=invalid_type,
                amount=100,
                service_name=ServiceName.TALKO,
            )
        assert "Invalid Transaction Type: must be from existing type" in str(
            exc_info.value
        )

    def test_validate_description_before_too_long(self):
        """Should raise ValueError if description exceeds 255 characters."""
        long_description = "a" * 256
        with pytest.raises(ValidationError) as exc_info:
            WalletTransactionRequest(
                transaction_type=TransactionType.CREDIT,
                amount=100,
                service_name=ServiceName.TALKO,
                description=long_description,
            )
        assert "Description should not exceed 255 characters" in str(exc_info.value)

    def test_validate_description_before_valid_length(self):
        """Should accept description <= 255 characters."""
        valid_description = "a" * 255
        payload = WalletTransactionRequest(
            transaction_type=TransactionType.CREDIT,
            amount=100,
            service_name=ServiceName.TALKO,
            description=valid_description,
        )
        assert payload.description == valid_description
