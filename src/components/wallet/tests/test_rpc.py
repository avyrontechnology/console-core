import pytest
from unittest.mock import AsyncMock, MagicMock

from grpc import StatusCode
from grpc_interceptor.exceptions import GrpcException

from src.components.wallet.rpc import WalletServiceGRPC
from src.pub.partner_wallet_pb2 import (
    GetWalletsByPartnerIdsResponse,
)


@pytest.mark.asyncio
class TestWalletServiceGRPC:

    @pytest.fixture(autouse=True)
    def setup_method(self):
        self.logger_mock = MagicMock()
        self.wallet_service_mock = AsyncMock()
        self.context_mock = MagicMock()

        self.grpc_service = WalletServiceGRPC(
            logger=self.logger_mock
        )

    async def test_get_wallets_by_partner_ids_success(self):
        """Test successful wallet lookup."""

        request = MagicMock()
        request.partner_ids = [101, 102]

        wallet_1 = MagicMock(
            id=1,
            partner_id=101,
            balance=4502.06,
            frozen_balance=1924.42,
            currency="INR",
            is_active=True,
            is_wallet_enabled=False,
            created_at=12345523,
            updated_at=12345523,
        )

        wallet_2 = MagicMock(
            id=2,
            partner_id=102,
            balance=1000.00,
            frozen_balance=100.00,
            currency="INR",
            is_active=True,
            is_wallet_enabled=True,
            created_at=12345523,
            updated_at=13466341,
        )

        self.wallet_service_mock.get_wallets_by_partner_ids.return_value = [
            wallet_1,
            wallet_2,
        ]

        response = await self.grpc_service.GetWalletsByPartnerIds(
            request=request,
            context=self.context_mock,
            wallet_service=self.wallet_service_mock,
        )

        assert isinstance(
            response,
            GetWalletsByPartnerIdsResponse,
        )

        assert len(response.wallets) == 2

        assert response.wallets[0].partner_id == 101
        assert response.wallets[0].balance == 4502.06
        assert response.wallets[0].frozen_balance == 1924.42
        assert response.wallets[0].currency == "INR"
        assert response.wallets[0].is_wallet_enabled is False

        assert response.wallets[1].partner_id == 102
        assert response.wallets[1].balance == 1000.00
        assert response.wallets[1].frozen_balance == 100.00
        assert response.wallets[1].currency == "INR"
        assert response.wallets[1].is_wallet_enabled is True

        self.wallet_service_mock.get_wallets_by_partner_ids.assert_awaited_once_with(
            partner_ids=[101, 102]
        )

        self.logger_mock.info.assert_any_call(
            "[gRPC]: Fetching wallet details for partner_ids=[101, 102]"
        )

        self.logger_mock.info.assert_any_call(
            "[gRPC]: Successfully fetched 2 wallet records"
        )

    async def test_get_wallets_by_partner_ids_empty_response(self):
        """Test empty wallet response."""

        request = MagicMock()
        request.partner_ids = [101, 102]

        self.wallet_service_mock.get_wallets_by_partner_ids.return_value = []

        response = await self.grpc_service.GetWalletsByPartnerIds(
            request=request,
            context=self.context_mock,
            wallet_service=self.wallet_service_mock,
        )

        assert isinstance(
            response,
            GetWalletsByPartnerIdsResponse,
        )

        assert len(response.wallets) == 0

        self.wallet_service_mock.get_wallets_by_partner_ids.assert_awaited_once_with(
            partner_ids=[101, 102]
        )

        self.logger_mock.info.assert_any_call(
            "[gRPC]: Successfully fetched 0 wallet records"
        )

    async def test_get_wallets_by_partner_ids_internal_error(self):
        """Test internal error handling."""

        request = MagicMock()
        request.partner_ids = [101, 102]

        self.wallet_service_mock.get_wallets_by_partner_ids.side_effect = Exception(
            "Database failure"
        )

        with pytest.raises(GrpcException) as exc_info:
            await self.grpc_service.GetWalletsByPartnerIds(
                request=request,
                context=self.context_mock,
                wallet_service=self.wallet_service_mock,
            )

        assert exc_info.value.status_code == StatusCode.INTERNAL

        assert (
            exc_info.value.details
            == "Internal server error while fetching wallet details."
        )

        self.wallet_service_mock.get_wallets_by_partner_ids.assert_awaited_once_with(
            partner_ids=[101, 102]
        )

        self.logger_mock.error.assert_called_once_with(
            "[gRPC]: Error fetching wallet details: Database failure"
        )

    async def test_get_wallets_by_partner_ids_with_none_id(self):
        """Test wallet response when wallet.id is None."""

        request = MagicMock()
        request.partner_ids = [101]

        wallet = MagicMock(
            id=None,
            partner_id=101,
            balance=0.0,
            frozen_balance=0.0,
            currency="INR",
            is_active=False,
            is_wallet_enabled=False,
            created_at=None,
            updated_at=None,
        )

        self.wallet_service_mock.get_wallets_by_partner_ids.return_value = [
            wallet
        ]

        response = await self.grpc_service.GetWalletsByPartnerIds(
            request=request,
            context=self.context_mock,
            wallet_service=self.wallet_service_mock,
        )

        assert len(response.wallets) == 1
        assert response.wallets[0].id == 0
        assert response.wallets[0].partner_id == 101