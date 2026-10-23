from uuid import UUID
from unittest.mock import AsyncMock, MagicMock

import pytest
from grpc import StatusCode
from grpc_interceptor.exceptions import GrpcException

from src.components.partner_meta_data.rpc import PartnerMetaDataServiceGrpc
from src.components.partner_meta_data.schema import PartnerPlanDetailsResponse
from src.components.partner_meta_data.services import PartnerMetaDataServices
from src.pub.auth_pb2 import GetPartnerServiceDetailsResponse


@pytest.mark.asyncio
class TestPartnerMetaDataServiceGrpc:

    @pytest.fixture
    def mock_logger(self):
        """Fixture for logger"""
        return MagicMock()

    @pytest.fixture
    def grpc_service(self, mock_logger):
        """Fixture for the gRPC service under test"""
        return PartnerMetaDataServiceGrpc(logger=mock_logger)

    @pytest.fixture
    def mock_request(self):
        """Fixture for gRPC request"""

        class MockRequest:
            partner_id= UUID("12312312-3123-1231-2312-312312312312")

        return MockRequest()

    @pytest.fixture
    def mock_context(self):
        """Fixture for gRPC context (not really used but needed)"""
        return MagicMock()

    @pytest.mark.asyncio
    async def test_get_partner_services_details_failure(
        self, grpc_service, mock_request, mock_context, mock_logger
    ):
        # Arrange
        mock_service = AsyncMock(spec=PartnerMetaDataServices)
        mock_service.get_partner_plan_details.side_effect = Exception("DB error")

        # Act & Assert
        with pytest.raises(GrpcException) as exc_info:
            await grpc_service.GetPartnerServicesDetails(
                request=mock_request,
                context=mock_context,
                partner_meta_data_service=mock_service,
            )

        assert exc_info.value.status_code == StatusCode.INTERNAL
        assert "RPCExceptionMsg.ERROR_MSG" in exc_info.value.details
        mock_logger.error.assert_called_once()
