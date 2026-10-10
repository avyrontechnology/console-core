import pytest
from unittest.mock import AsyncMock, MagicMock
from grpc import StatusCode
from grpc_interceptor.exceptions import GrpcException

from src.pub.api_key_service_pb2 import PartnerApiKeyResponse, ValidateApiKeyResponse
from src.components.api_key.errors import ApiKeyNotFoundError
from src.components.api_key.rpc import ApiKeyServiceGRPC


@pytest.mark.asyncio
class TestApiKeyServiceGRPC:

    @pytest.fixture(autouse=True)
    def setup_method(self):
        """Setup mocks and initialize the gRPC service."""
        self.logger_mock = MagicMock()
        self.api_key_service_mock = AsyncMock()
        self.context_mock = MagicMock()

        self.grpc_service = ApiKeyServiceGRPC(logger=self.logger_mock)

    async def test_validate_api_key_success(self):
        """Test successful API key validation."""
        # Arrange
        request = MagicMock()
        request.key = "abc123456789xyz"

        # Mock valid key details returned by service
        mock_key_details = MagicMock(
            id=1,
            key="abc123456789xyz",
            partner_id=101,
            is_active=True,
            scopes=["maglo:get_leads"],
            user_context={"name": "Api Key User", "user_id": 7},
        )
        self.api_key_service_mock.validate_api_key.return_value = mock_key_details

        # Act
        response = await self.grpc_service.ValidateApiKey(
            request=request,
            context=self.context_mock,
            api_key_service=self.api_key_service_mock,
        )

        # Assert
        assert isinstance(response, ValidateApiKeyResponse)
        assert response.id == 1
        assert response.partner_id == 101
        assert response.is_active is True
        assert list(response.scopes) == ["maglo:get_leads"]
        assert response.user_context == '{"name": "Api Key User", "user_id": 7}'

        self.logger_mock.info.assert_any_call("[gRPC]: Validating API key: abc1234567")
        self.logger_mock.info.assert_any_call(
            "[gRPC]: Successfully validated API key for partner_id: 101"
        )

    async def test_validate_api_key_invalid_key(self):
        """Test handling of invalid or expired API key."""
        # Arrange
        request = MagicMock()
        request.key = "invalidkey123"
        self.api_key_service_mock.validate_api_key.return_value = None

        # Act & Assert
        with pytest.raises(GrpcException) as exc_info:
            await self.grpc_service.ValidateApiKey(
                request=request,
                context=self.context_mock,
                api_key_service=self.api_key_service_mock,
            )

        assert exc_info.value.status_code == StatusCode.UNAUTHENTICATED
        assert exc_info.value.details == "Invalid or expired API key."

        self.logger_mock.warning.assert_called_once_with(
            "[gRPC]: Invalid API key: invalidkey123"
        )

    async def test_validate_api_key_internal_error(self):
        """Test internal server error during validation."""
        # Arrange
        request = MagicMock()
        request.key = "errorKey987"
        self.api_key_service_mock.validate_api_key.side_effect = Exception(
            "Database failure"
        )

        # Act & Assert
        with pytest.raises(GrpcException) as exc_info:
            await self.grpc_service.ValidateApiKey(
                request=request,
                context=self.context_mock,
                api_key_service=self.api_key_service_mock,
            )

        assert exc_info.value.status_code == StatusCode.INTERNAL
        assert (
            exc_info.value.details
            == "Internal server error during API key validation."
        )

        self.logger_mock.error.assert_called_once_with(
            "[gRPC]: Error during API key validation: Database failure"
        )

    async def test_get_api_by_partner_id_success(self):
        """Test successful API key lookup by partner ID."""
        # Arrange
        request = MagicMock()
        request.partner_id = 101

        mock_key_details = MagicMock(
            id=1,
            key="abc123456789xyz",
            description="Primary API key",
            partner_id=101,
            is_active=True,
        )
        self.api_key_service_mock.get_api_key.return_value = mock_key_details

        # Act
        response = await self.grpc_service.GetApiByPartnerId(
            request=request,
            context=self.context_mock,
            api_key_service=self.api_key_service_mock,
        )

        # Assert
        assert isinstance(response, PartnerApiKeyResponse)
        assert response.id == 1
        assert response.key == "abc123456789xyz"
        assert response.description == "Primary API key"
        assert response.partner_id == 101
        assert response.is_active is True

        self.api_key_service_mock.get_api_key.assert_awaited_once_with(
            partner_id=101
        )
        self.logger_mock.info.assert_any_call(
            "[gRPC]: Fetching API key details for partner_id: 101"
        )
        self.logger_mock.info.assert_any_call(
            "[gRPC]: Retrieved API key for partner_id: 101"
        )

    async def test_get_api_by_partner_id_not_found(self):
        """Test API key lookup maps not found errors to gRPC NOT_FOUND."""
        # Arrange
        request = MagicMock()
        request.partner_id = 999
        self.api_key_service_mock.get_api_key.side_effect = ApiKeyNotFoundError(
            999
        )

        # Act & Assert
        with pytest.raises(GrpcException) as exc_info:
            await self.grpc_service.GetApiByPartnerId(
                request=request,
                context=self.context_mock,
                api_key_service=self.api_key_service_mock,
            )

        assert exc_info.value.status_code == StatusCode.NOT_FOUND
        assert exc_info.value.details == "API key not found."
        self.api_key_service_mock.get_api_key.assert_awaited_once_with(
            partner_id=999
        )

    async def test_get_api_by_partner_id_internal_error(self):
        """Test internal server error during API key lookup by partner ID."""
        # Arrange
        request = MagicMock()
        request.partner_id = 101
        self.api_key_service_mock.get_api_key.side_effect = Exception(
            "Database failure"
        )

        # Act & Assert
        with pytest.raises(GrpcException) as exc_info:
            await self.grpc_service.GetApiByPartnerId(
                request=request,
                context=self.context_mock,
                api_key_service=self.api_key_service_mock,
            )

        assert exc_info.value.status_code == StatusCode.INTERNAL
        assert (
            exc_info.value.details
            == "Internal server error while fetching API key."
        )
        self.api_key_service_mock.get_api_key.assert_awaited_once_with(
            partner_id=101
        )
        self.logger_mock.error.assert_called_once_with(
            "[gRPC]: Error fetching API key: Database failure"
        )
