import pytest
from unittest.mock import AsyncMock, MagicMock
from grpc import StatusCode
from grpc_interceptor.exceptions import GrpcException

from src.pub.user_pb2 import (
    UserDetail,
    GetPartnerUserDetailsByHierarchyResponse,
    UserAvailabilityStatus,
    GetUsersAvailabilityStatusResponse,
)
from src.components.user.rpc import UserServiceGRPC  # adjust import path
from types import SimpleNamespace

@pytest.mark.asyncio
class TestUserServiceGRPC:

    @pytest.fixture(autouse=True)
    def setup_method(self):
        self.logger_mock = MagicMock()
        self.user_service_mock = AsyncMock()
        self.context_mock = MagicMock()

        self.grpc_service = UserServiceGRPC(logger=self.logger_mock)

    async def test_get_partner_user_details_by_hierarchy_success(self):
        # Arrange
        request = MagicMock()
        request.partner_id = 101
        request.role_hierarchy_level = 1

        # Fake user objects with attributes like Pydantic/ORM models
        fake_users = [
            SimpleNamespace(user_id=1, email="alice@example.com", name="Alice", role="admin"),
            SimpleNamespace(user_id=2, email="bob@example.com", name="Bob", role="manager"),
        ]
        self.user_service_mock.get_admin_credentials_by_hierarchy.return_value = fake_users

        # Act
        response: GetPartnerUserDetailsByHierarchyResponse = await self.grpc_service.GetPartnerUserDetailsByHierarchy(
            request=request,
            context=self.context_mock,
            user_service=self.user_service_mock,
        )

        # Assert
        assert isinstance(response, GetPartnerUserDetailsByHierarchyResponse)
        assert len(response.users_details) == 2
        assert isinstance(response.users_details[0], UserDetail)
        assert response.users_details[0].name == "Alice"
        assert response.users_details[1].role == "manager"

        self.logger_mock.info.assert_called_once_with(
            "[gRPC]: Attempting to get user details by hierarchy: 1, for partner: 101"
        )
        self.user_service_mock.get_admin_credentials_by_hierarchy.assert_awaited_once_with(
            user_hierarchy=1, partner_id=101
        )

    async def test_get_partner_user_details_by_hierarchy_empty_result(self):
        # Arrange
        request = MagicMock()
        request.partner_id = 202
        request.role_hierarchy_level = 3

        self.user_service_mock.get_admin_credentials_by_hierarchy.return_value = []

        # Act
        response: GetPartnerUserDetailsByHierarchyResponse = await self.grpc_service.GetPartnerUserDetailsByHierarchy(
            request=request,
            context=self.context_mock,
            user_service=self.user_service_mock,
        )

        # Assert
        assert isinstance(response, GetPartnerUserDetailsByHierarchyResponse)
        assert len(response.users_details) == 0
        self.logger_mock.info.assert_called_once_with(
            "[gRPC]: Attempting to get user details by hierarchy: 3, for partner: 202"
        )

    async def test_get_partner_user_details_by_hierarchy_exception(self):
        # Arrange
        request = MagicMock()
        request.partner_id = 303
        request.role_hierarchy_level = 2

        self.user_service_mock.get_admin_credentials_by_hierarchy.side_effect = Exception(
            "Database failure"
        )

        # Act & Assert
        with pytest.raises(GrpcException) as exc_info:
            await self.grpc_service.GetPartnerUserDetailsByHierarchy(
                request=request,
                context=self.context_mock,
                user_service=self.user_service_mock,
            )
            
        assert exc_info.value.status_code == StatusCode.INTERNAL

        self.logger_mock.error.assert_called_once_with(
            "[gRPC]: Error occurred while get users details by hierarchy: 2 for partner: 303. error: Database failure"
        )

    async def test_get_users_availability_status_success(self):
        # Arrange
        request = MagicMock()
        request.user_ids = [1, 2]

        fake_users_status = [
            SimpleNamespace(user_id=1, current_status="Active"),
            SimpleNamespace(user_id=2, current_status="Offline"),
        ]
        self.user_service_mock.get_users_availability_status.return_value = fake_users_status

        # Act
        response: GetUsersAvailabilityStatusResponse = await self.grpc_service.GetUsersAvailabilityStatus(
            request=request,
            context=self.context_mock,
            user_service=self.user_service_mock,
        )

        # Assert
        assert isinstance(response, GetUsersAvailabilityStatusResponse)
        assert len(response.users_availability_status) == 2
        assert isinstance(response.users_availability_status[0], UserAvailabilityStatus)
        assert response.users_availability_status[0].user_id == 1
        assert response.users_availability_status[0].current_status == "Active"
        assert response.users_availability_status[1].user_id == 2
        assert response.users_availability_status[1].current_status == "Offline"

        self.logger_mock.info.assert_called_once_with(
            "[gRPC]: Attempting to get current status for user_ids: [1, 2]"
        )
        self.user_service_mock.get_users_availability_status.assert_awaited_once_with([1, 2])

    async def test_get_users_availability_status_empty_result(self):
        # Arrange
        request = MagicMock()
        request.user_ids = [3]

        self.user_service_mock.get_users_availability_status.return_value = []

        # Act
        response: GetUsersAvailabilityStatusResponse = await self.grpc_service.GetUsersAvailabilityStatus(
            request=request,
            context=self.context_mock,
            user_service=self.user_service_mock,
        )

        # Assert
        assert isinstance(response, GetUsersAvailabilityStatusResponse)
        assert len(response.users_availability_status) == 0

    async def test_get_users_availability_status_exception(self):
        # Arrange
        request = MagicMock()
        request.user_ids = [4]

        self.user_service_mock.get_users_availability_status.side_effect = Exception(
            "Database failure"
        )

        # Act & Assert
        with pytest.raises(GrpcException) as exc_info:
            await self.grpc_service.GetUsersAvailabilityStatus(
                request=request,
                context=self.context_mock,
                user_service=self.user_service_mock,
            )

        assert exc_info.value.status_code == StatusCode.INTERNAL

        self.logger_mock.error.assert_called_once_with(
            "[gRPC]: Error occurred while getting current status for user_ids: [4]. error: Database failure"
        )
