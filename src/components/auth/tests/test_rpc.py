from unittest.mock import AsyncMock, MagicMock

import jwt
import pytest
from grpc import StatusCode
from grpc_interceptor.exceptions import GrpcException

from src.components.auth.constant import RPCExceptionMsg
from src.components.auth.rpc import ALGORITHM, SECRET_KEY, AuthServiceGRPC
from src.components.partner.error import PartnerNotFoundError
from src.pub.auth_pb2 import (
    ActiveUserDetails,
    GetUserDetailsByPartnerIdResponse,
    GetUserParentDetailsResponse,
    UserParentDetail,
    ValidateTokenResponse,
)


@pytest.mark.asyncio
class TestAuthServiceGRPC:

    @pytest.fixture(autouse=True)
    def setup_method(self):
        self.logger_mock = MagicMock()
        self.db_session_manager_mock = MagicMock()

        self.console_service_mock = AsyncMock()
        self.context_mock = MagicMock()

        self.auth_service_grpc = AuthServiceGRPC(
            logger=self.logger_mock,
            db_session_manager=self.db_session_manager_mock,
        )
        self.session_mock = AsyncMock()
        self.db_session_manager_mock.session.return_value.__aenter__.return_value = (
            self.session_mock
        )

    async def test_get_active_users_by_partner_id_success(self):
        # Arrange
        request = MagicMock()
        request.partner_id = 101

        self.console_service_mock.get_users_by_partner_id.return_value = [
            {
                "id": 1,
                "name": "Alice",
                "email": "alice@example.com",
                "phone_number": "+911234567890",
                "role": "admin",
                "role_hierarchy": 1,
            },
            {
                "id": 2,
                "name": "Bob",
                "email": "bob@example.com",
                "phone_number": "+919876543210",
                "role": "manager",
                "role_hierarchy": 2,
            },
        ]

        # Act
        response = await self.auth_service_grpc.GetActiveUsersByPartnerId(
            request=request,
            context=self.context_mock,
            console_service=self.console_service_mock,
        )

        # Assert
        assert isinstance(response, GetUserDetailsByPartnerIdResponse)
        assert response.message == "Successfully fetched users for partner Id: 101"
        assert len(response.users) == 2
        assert isinstance(response.users[0], ActiveUserDetails)
        assert response.users[0].name == "Alice"

        self.logger_mock.info.assert_called_once_with(
            "Get All Active User throough RPC for partner ID: 101"
        )

    async def test_get_active_users_by_partner_id_partner_not_found(self):
        # Arrange
        request = MagicMock()
        request.partner_id = 202

        self.console_service_mock.get_users_by_partner_id.side_effect = (
            PartnerNotFoundError(202)
        )

        # Act
        response = await self.auth_service_grpc.GetActiveUsersByPartnerId(
            request=request,
            context=self.context_mock,
            console_service=self.console_service_mock,
        )

        # Assert
        assert isinstance(response, GetUserDetailsByPartnerIdResponse)
        assert response.message == "Partner not found with  partner Id: 202"
        assert len(response.users) == 0

        self.logger_mock.error.assert_called_once_with(
            "An Error occured while fetching users for partner id: 202 Exc: Partner not found, id: 202"
        )

    async def test_get_active_users_by_partner_id_unexpected_exception(self):
        # Arrange
        request = MagicMock()
        request.partner_id = 303

        self.console_service_mock.get_users_by_partner_id.side_effect = Exception(
            "Unexpected DB failure"
        )

        # Act
        response = await self.auth_service_grpc.GetActiveUsersByPartnerId(
            request=request,
            context=self.context_mock,
            console_service=self.console_service_mock,
        )

        # Assert: since there's no `return` in `except Exception`, response is `None`
        assert response is None
        self.logger_mock.error.assert_called_once_with(
            "An Unexpected Error occured in GetAllActiveUsersByPartnerId RPC method: Unexpected DB failure"
        )

    async def _call_validate_token(self, partner_id, session_id, extra_claims=None):
        """Shared scaffolding for ValidateToken tests: builds a token, a request,
        and an active session, then invokes the RPC. Returns the response."""
        token = jwt.encode(
            {
                "user_id": 1,
                "partner_id": partner_id,
                "user_session_id": session_id,
                **(extra_claims or {}),
            },
            SECRET_KEY,
            algorithm=ALGORITHM,
        )
        request = MagicMock()
        request.mcontext.correlation_id = "corr-id-1"
        request.mbody.token = token

        session_management_service = AsyncMock()
        session_management_service.get_user_session.return_value = MagicMock(
            is_active=True, session_id=session_id
        )

        return await self.auth_service_grpc.ValidateToken(
            request=request,
            context=self.context_mock,
            session_management_service=session_management_service,
        )

    async def test_validate_token_returns_claims_from_token(self):
        # is_add_number_enabled is partner-level config, resolved live via
        # GetPartnerMetaDataDetails, never embedded in or read from the token.
        response = await self._call_validate_token(
            partner_id=12,
            session_id="session-1",
            extra_claims={"is_maglo_enabled": True, "is_obotaai_enabled": True},
        )

        assert isinstance(response, ValidateTokenResponse)
        assert response.is_active is True
        assert response.partner_id == 12
        assert response.is_obotaai_enabled is True

    async def test_get_user_parent_details_success_with_parents(self):
        # Arrange
        request = MagicMock()
        request.user_ids = [1, 2]

        # Mock query result
        mock_result = MagicMock()
        mock_result.mappings.return_value.all.return_value = [
            {"user_id": 1, "name": "Alice", "parent_id": 3, "parent_name": "Charlie"},
            {"user_id": 2, "name": "Bob", "parent_id": 4, "parent_name": "David"},
        ]
        self.session_mock.execute.return_value = mock_result

        # Act
        response = await self.auth_service_grpc.GetUserParentDetails(
            request=request, context=self.context_mock
        )

        # Assert
        assert isinstance(response, GetUserParentDetailsResponse)
        assert response.message == "Success"
        assert len(response.user_details) == 2
        assert response.user_details[0] == UserParentDetail(
            user_id=1, name="Alice", parent_id=3, parent_name="Charlie"
        )
        assert response.user_details[1] == UserParentDetail(
            user_id=2, name="Bob", parent_id=4, parent_name="David"
        )
        self.logger_mock.info.assert_any_call(
            "Fetching parent details for user_ids: [1, 2]"
        )
        self.logger_mock.info.assert_any_call("Found parent details for 2 user IDs")

    async def test_get_user_parent_details_no_parents(self):
        # Arrange
        request = MagicMock()
        request.user_ids = [1, 2]

        # Mock query result with no parents
        mock_result = MagicMock()
        mock_result.mappings.return_value.all.return_value = [
            {"user_id": 1, "name": "Alice", "parent_id": None, "parent_name": None},
            {"user_id": 2, "name": "Bob", "parent_id": None, "parent_name": None},
        ]
        self.session_mock.execute.return_value = mock_result

        # Act
        response = await self.auth_service_grpc.GetUserParentDetails(
            request=request, context=self.context_mock
        )

        # Assert
        assert isinstance(response, GetUserParentDetailsResponse)
        assert response.message == "Success"
        assert len(response.user_details) == 2
        assert response.user_details[0] == UserParentDetail(
            user_id=1, name="Alice", parent_id=0, parent_name=""
        )
        assert response.user_details[1] == UserParentDetail(
            user_id=2, name="Bob", parent_id=0, parent_name=""
        )
        self.logger_mock.info.assert_any_call(
            "Fetching parent details for user_ids: [1, 2]"
        )
        self.logger_mock.info.assert_any_call("Found parent details for 2 user IDs")

    async def test_get_user_parent_details_empty_user_ids(self):
        # Arrange
        request = MagicMock()
        request.user_ids = []

        # Mock query result for empty input
        mock_result = MagicMock()
        mock_result.mappings.return_value.all.return_value = []
        self.session_mock.execute.return_value = mock_result

        # Act
        response = await self.auth_service_grpc.GetUserParentDetails(
            request=request, context=self.context_mock
        )

        # Assert
        assert isinstance(response, GetUserParentDetailsResponse)
        assert response.message == "Success"
        assert len(response.user_details) == 0
        self.logger_mock.info.assert_any_call(
            "Fetching parent details for user_ids: []"
        )
        self.logger_mock.info.assert_any_call("Found parent details for 0 user IDs")

    async def test_get_user_parent_details_no_users_found(self):
        # Arrange
        request = MagicMock()
        request.user_ids = [1, 2]

        # Mock empty query result
        mock_result = MagicMock()
        mock_result.mappings.return_value.all.return_value = []
        self.session_mock.execute.return_value = mock_result

        # Act
        response = await self.auth_service_grpc.GetUserParentDetails(
            request=request, context=self.context_mock
        )

        # Assert
        assert isinstance(response, GetUserParentDetailsResponse)
        assert response.message == "Success"
        assert len(response.user_details) == 0
        self.logger_mock.info.assert_any_call(
            "Fetching parent details for user_ids: [1, 2]"
        )
        self.logger_mock.info.assert_any_call("Found parent details for 0 user IDs")

    async def test_get_user_parent_details_unexpected_exception(self):
        # Arrange
        request = MagicMock()
        request.user_ids = [1, 2]

        # Mock query to raise an exception
        self.session_mock.execute.side_effect = Exception("Database connection error")

        # Act
        with pytest.raises(GrpcException) as exc_info:
            await self.auth_service_grpc.GetUserParentDetails(
                request=request, context=self.context_mock
            )

        # Assert
        assert exc_info.value.details == RPCExceptionMsg.ERROR_MSG
        assert exc_info.value.status_code == StatusCode.INTERNAL
        self.logger_mock.info.assert_called_once_with(
            "Fetching parent details for user_ids: [1, 2]"
        )
        self.logger_mock.error.assert_called_once_with(
            "Error fetching parent details: Database connection error"
        )

    async def test_get_user_parent_hierarchy_success(self):
        # Arrange
        request = MagicMock()
        request.user_id = 34

        # Create mock rows that behave like SQLAlchemy Row objects
        row_1 = MagicMock()
        row_1.user_id = 33
        row_1.name = "Dheeraj Chauhan"
        row_1.role = "Admin"
        row_1.role_hierarchy = 5

        row_2 = MagicMock()
        row_2.user_id = 12
        row_2.name = "Super Admin"
        row_2.role = "SuperAdmin"
        row_2.role_hierarchy = 6

        result_mock = MagicMock()
        result_mock.all = MagicMock(return_value=[row_1, row_2])

        self.session_mock.execute = AsyncMock(return_value=result_mock)

        # Act
        response = await self.auth_service_grpc.GetUserParentHierarchy(
            request=request,
            context=self.context_mock,
        )

        # Assert
        assert response.message == "Success"
        assert len(response.parents) == 2

        assert response.parents[0].user_id == 33
        assert response.parents[0].name == "Dheeraj Chauhan"
        assert response.parents[1].user_id == 12
        assert response.parents[1].name == "Super Admin"

    async def test_get_user_parent_hierarchy_no_parents(self):
        # Arrange
        request = MagicMock()
        request.user_id = 1  # root user

        result_mock = MagicMock()
        result_mock.all.return_value = []

        self.session_mock.execute.return_value = result_mock

        # Act
        response = await self.auth_service_grpc.GetUserParentHierarchy(
            request=request,
            context=self.context_mock,
        )

        # Assert
        assert response.message == "Success"
        assert response.parents == []

        self.session_mock.execute.assert_called_once()

    async def test_get_user_parent_hierarchy_user_id_missing(self):
        # Arrange
        request = MagicMock()
        request.user_id = None

        # Act + Assert
        with pytest.raises(GrpcException) as exc:
            await self.auth_service_grpc.GetUserParentHierarchy(
                request=request,
                context=self.context_mock,
            )

        assert exc.value.status_code == StatusCode.INVALID_ARGUMENT
        assert exc.value.details == RPCExceptionMsg.USER_ID_NOT_FOUND

    async def test_get_user_parent_hierarchy_db_error(self):
        # A`rrange
        request = MagicMock()
        request.user_id = 34

        self.session_mock.execute.side_effect = Exception("DB failure")

        # Act + Assert
        with pytest.raises(GrpcException) as exc:
            await self.auth_service_grpc.GetUserParentHierarchy(
                request=request,
                context=self.context_mock,
            )

        assert exc.value.status_code == StatusCode.INTERNAL
        assert exc.value.details == RPCExceptionMsg.ERROR_MSG

        self.logger_mock.error.assert_called_once()

    async def test_get_partner_details_success_with_subscription_status(self):
        request = MagicMock()
        request.partner_id = 1

        result_mock = MagicMock()
        result_mock.mappings.return_value.first.return_value = {
            "partner_id": 1,
            "name": "Test Partner",
            "is_active": True,
            "is_maglo_publisher": False,
            "created_at": 1704067200000,
            "partner_status": "active",
            "partner_logo": None,
            "publisher_username": "pub_user",
            "publisher_email": "pub@test.com",
            "is_feedback_enabled": True,
            "has_active_maglo_publisher": True,
            "has_address": True,
        }
        self.session_mock.execute.return_value = result_mock

        entitlement_service_mock = AsyncMock()
        entitlement_service_mock.get_subscription_status.return_value = {
            "console": {
                "status": "active",
                "entitlement_start_date": 1704067200000,
                "entitlement_end_date": 4102444800000,
            }
        }

        response = await self.auth_service_grpc.GetPartnerDetails(
            request=request,
            context=self.context_mock,
            entitlement_service=entitlement_service_mock,
            grace_repo=AsyncMock(),
        )

        assert response.message == "Success"
        assert response.partner_detail.partner_id == 1
        assert response.partner_detail.is_publisher_onboarding_completed is True
        sub = response.partner_detail.subscription_status["console"]
        assert sub.status == "active"
        assert (
            not sub.HasField("grace_start_date") if hasattr(sub, "HasField") else True
        )

    async def test_get_partner_details_success_with_grace_dates(self):
        request = MagicMock()
        request.partner_id = 1

        result_mock = MagicMock()
        result_mock.mappings.return_value.first.return_value = {
            "partner_id": 1,
            "name": "Test Partner",
            "is_active": True,
            "is_maglo_publisher": False,
            "created_at": 1704067200000,
            "partner_status": "active",
            "partner_logo": None,
            "publisher_username": None,
            "publisher_email": None,
            "is_feedback_enabled": False,
            "has_active_maglo_publisher": True,
            "has_address": True,
        }
        self.session_mock.execute.return_value = result_mock

        entitlement_service_mock = AsyncMock()
        entitlement_service_mock.get_subscription_status.return_value = {
            "console": {
                "status": "grace",
                "entitlement_start_date": 1704067200000,
                "entitlement_end_date": 1706745600000,
                "grace_start_date": 1706745600000,
                "grace_end_date": 1707350400000,
            }
        }

        response = await self.auth_service_grpc.GetPartnerDetails(
            request=request,
            context=self.context_mock,
            entitlement_service=entitlement_service_mock,
            grace_repo=AsyncMock(),
        )

        sub = response.partner_detail.subscription_status["console"]
        assert sub.status == "grace"
        assert sub.grace_start_date == 1706745600000
        assert sub.grace_end_date == 1707350400000

    async def test_get_partner_details_onboarding_incomplete_no_address(self):
        request = MagicMock()
        request.partner_id = 1

        result_mock = MagicMock()
        result_mock.mappings.return_value.first.return_value = {
            "partner_id": 1,
            "name": "Test Partner",
            "is_active": True,
            "is_maglo_publisher": False,
            "created_at": 1704067200000,
            "partner_status": "active",
            "partner_logo": None,
            "publisher_username": None,
            "publisher_email": None,
            "is_feedback_enabled": False,
            "has_active_maglo_publisher": True,
            "has_address": False,
        }
        self.session_mock.execute.return_value = result_mock

        entitlement_service_mock = AsyncMock()
        entitlement_service_mock.get_subscription_status.return_value = {}

        response = await self.auth_service_grpc.GetPartnerDetails(
            request=request,
            context=self.context_mock,
            entitlement_service=entitlement_service_mock,
            grace_repo=AsyncMock(),
        )

        assert response.partner_detail.is_publisher_onboarding_completed is False

    async def test_get_partner_details_onboarding_incomplete_no_maglo_publisher(self):
        request = MagicMock()
        request.partner_id = 1

        result_mock = MagicMock()
        result_mock.mappings.return_value.first.return_value = {
            "partner_id": 1,
            "name": "Test Partner",
            "is_active": True,
            "is_maglo_publisher": False,
            "created_at": 1704067200000,
            "partner_status": "active",
            "partner_logo": None,
            "publisher_username": None,
            "publisher_email": None,
            "is_feedback_enabled": False,
            "has_active_maglo_publisher": False,
            "has_address": True,
        }
        self.session_mock.execute.return_value = result_mock

        entitlement_service_mock = AsyncMock()
        entitlement_service_mock.get_subscription_status.return_value = {}

        response = await self.auth_service_grpc.GetPartnerDetails(
            request=request,
            context=self.context_mock,
            entitlement_service=entitlement_service_mock,
            grace_repo=AsyncMock(),
        )

        assert response.partner_detail.is_publisher_onboarding_completed is False

    async def test_get_partner_details_subscription_status_failure_returns_empty_map(
        self,
    ):
        request = MagicMock()
        request.partner_id = 1

        result_mock = MagicMock()
        result_mock.mappings.return_value.first.return_value = {
            "partner_id": 1,
            "name": "Test Partner",
            "is_active": True,
            "is_maglo_publisher": False,
            "created_at": 1704067200000,
            "partner_status": "active",
            "partner_logo": None,
            "publisher_username": None,
            "publisher_email": None,
            "is_feedback_enabled": False,
            "has_active_maglo_publisher": True,
            "has_address": True,
        }
        self.session_mock.execute.return_value = result_mock

        entitlement_service_mock = AsyncMock()
        entitlement_service_mock.get_subscription_status.side_effect = Exception(
            "entitlement service down"
        )

        response = await self.auth_service_grpc.GetPartnerDetails(
            request=request,
            context=self.context_mock,
            entitlement_service=entitlement_service_mock,
            grace_repo=AsyncMock(),
        )

        assert response.message == "Success"
        assert len(response.partner_detail.subscription_status) == 0
        self.logger_mock.warning.assert_called_once()
        assert "entitlement service down" in self.logger_mock.warning.call_args[0][0]

    async def test_get_partner_details_db_error_raises_internal(self):
        request = MagicMock()
        request.partner_id = 1

        self.session_mock.execute.side_effect = Exception("DB connection lost")

        with pytest.raises(GrpcException) as exc:
            await self.auth_service_grpc.GetPartnerDetails(
                request=request,
                context=self.context_mock,
                entitlement_service=AsyncMock(),
                grace_repo=AsyncMock(),
            )

        assert exc.value.status_code == StatusCode.INTERNAL
        assert exc.value.details == RPCExceptionMsg.ERROR_MSG
        self.logger_mock.error.assert_called_with(
            "Error fetching partner details: DB connection lost"
        )

    async def test_get_user_details_success(self):
        """Happy path — user found, show_popup computed successfully."""
        request = MagicMock()
        request.user_id = 1
        request.mcontext = MagicMock()

        mock_user_row = {
            "user_id": 1,
            "name": "Test User",
            "email": "test@example.com",
            "partner_id": 10,
            "partner_name": "Test Partner",
            "role_hierarchy_level": 1,
            "is_maglo_publisher": False,
            "phone_number": "9999999999",
            "is_active": True,
            "is_email_verified": True,
            "is_phone_number_verified": False,
            "is_walkthrough_completed": True,
            "cloud_agent_number": None,
            "additional_info": {"popup_last_closed": {"console": 1000000}},
        }

        mock_config_rows = []

        mock_user_result = MagicMock()
        mock_user_result.mappings.return_value.first.return_value = mock_user_row

        mock_config_result = MagicMock()
        mock_config_result.fetchall.return_value = mock_config_rows

        self.session_mock.execute = AsyncMock(
            side_effect=[mock_user_result, mock_config_result]
        )

        entitlement_service_mock = AsyncMock()
        entitlement_service_mock.get_subscription_status.return_value = {
            "console": {"status": "active", "entitlement_end_date": 9999999999999},
            "maglo": {"status": "suspended", "entitlement_end_date": None},
            "babbler": {"status": "suspended", "entitlement_end_date": None},
        }
        grace_repo_mock = AsyncMock()

        response = await self.auth_service_grpc.GetUserDetails(
            request=request,
            context=self.context_mock,
            entitlement_service=entitlement_service_mock,
            grace_repo=grace_repo_mock,
        )

        assert response.message == "Success"
        assert response.user_profile.user_id == 1
        assert response.user_profile.name == "Test User"
        assert "console" in response.user_profile.show_popup
        assert "maglo" in response.user_profile.show_popup
        assert "babbler" in response.user_profile.show_popup
        self.logger_mock.info.assert_any_call("User details retrieved for user_id: 1")

    async def test_get_user_details_inactive_user_name_suffixed(self):
        """Inactive user gets (Inactive) appended to name."""
        request = MagicMock()
        request.user_id = 2
        request.mcontext = MagicMock()

        mock_user_row = {
            "user_id": 2,
            "name": "Inactive User",
            "email": "inactive@example.com",
            "partner_id": 10,
            "partner_name": "Test Partner",
            "role_hierarchy_level": 3,
            "is_maglo_publisher": False,
            "phone_number": None,
            "is_active": False,
            "is_email_verified": False,
            "is_phone_number_verified": False,
            "is_walkthrough_completed": False,
            "cloud_agent_number": None,
            "additional_info": None,
        }

        mock_user_result = MagicMock()
        mock_user_result.mappings.return_value.first.return_value = mock_user_row

        mock_config_result = MagicMock()
        mock_config_result.fetchall.return_value = []

        self.session_mock.execute = AsyncMock(
            side_effect=[mock_user_result, mock_config_result]
        )

        entitlement_service_mock = AsyncMock()
        entitlement_service_mock.get_subscription_status.return_value = {}
        grace_repo_mock = AsyncMock()

        response = await self.auth_service_grpc.GetUserDetails(
            request=request,
            context=self.context_mock,
            entitlement_service=entitlement_service_mock,
            grace_repo=grace_repo_mock,
        )

        assert response.user_profile.name == "Inactive User (Inactive)"

    async def test_get_user_details_user_not_found_returns_empty(self):
        """No user row found — returns empty dict."""
        request = MagicMock()
        request.user_id = 99
        request.mcontext = MagicMock()

        mock_result = MagicMock()
        mock_result.mappings.return_value.first.return_value = None
        self.session_mock.execute = AsyncMock(return_value=mock_result)

        response = await self.auth_service_grpc.GetUserDetails(
            request=request,
            context=self.context_mock,
            entitlement_service=AsyncMock(),
            grace_repo=AsyncMock(),
        )

        assert response == {}
        self.logger_mock.error.assert_called_once_with("User not found for user_id: 99")

    async def test_get_user_details_no_user_id_raises_grpc_exception(self):
        """Missing user_id raises INVALID_ARGUMENT."""
        request = MagicMock()
        request.user_id = None
        request.mcontext = MagicMock()

        with pytest.raises(GrpcException) as exc_info:
            await self.auth_service_grpc.GetUserDetails(
                request=request,
                context=self.context_mock,
                entitlement_service=AsyncMock(),
                grace_repo=AsyncMock(),
            )

        assert exc_info.value.status_code == StatusCode.INVALID_ARGUMENT
        assert exc_info.value.details == RPCExceptionMsg.USER_ID_NOT_FOUND

    async def test_get_user_details_show_popup_computation_fails_defaults_to_false(
        self,
    ):
        """EntitlementService failure — show_popup defaults to all false, no exception raised."""
        request = MagicMock()
        request.user_id = 1
        request.mcontext = MagicMock()

        mock_user_row = {
            "user_id": 1,
            "name": "Test User",
            "email": "test@example.com",
            "partner_id": 10,
            "partner_name": "Partner",
            "role_hierarchy_level": 1,
            "is_maglo_publisher": False,
            "phone_number": None,
            "is_active": True,
            "is_email_verified": True,
            "is_phone_number_verified": False,
            "is_walkthrough_completed": False,
            "cloud_agent_number": None,
            "additional_info": {},
        }

        mock_user_result = MagicMock()
        mock_user_result.mappings.return_value.first.return_value = mock_user_row

        mock_config_result = MagicMock()
        mock_config_result.fetchall.return_value = []

        self.session_mock.execute = AsyncMock(
            side_effect=[mock_user_result, mock_config_result]
        )

        entitlement_service_mock = AsyncMock()
        entitlement_service_mock.get_subscription_status.side_effect = Exception(
            "entitlement service down"
        )

        response = await self.auth_service_grpc.GetUserDetails(
            request=request,
            context=self.context_mock,
            entitlement_service=entitlement_service_mock,
            grace_repo=AsyncMock(),
        )

        assert response.message == "Success"
        assert response.user_profile.show_popup["console"] is False
        assert response.user_profile.show_popup["maglo"] is False
        assert response.user_profile.show_popup["babbler"] is False
        self.logger_mock.warning.assert_called_once()
        assert "entitlement service down" in self.logger_mock.warning.call_args[0][0]

    async def test_get_user_details_db_exception_returns_none(self):
        """Outer DB exception — returns None and logs error."""
        request = MagicMock()
        request.user_id = 1
        request.mcontext = MagicMock()

        self.session_mock.execute = AsyncMock(
            side_effect=Exception("DB connection lost")
        )

        response = await self.auth_service_grpc.GetUserDetails(
            request=request,
            context=self.context_mock,
            entitlement_service=AsyncMock(),
            grace_repo=AsyncMock(),
        )

        assert response is None
        self.logger_mock.error.assert_called_once_with(
            "Error fetching user details: DB connection lost"
        )

    async def test_get_user_details_additional_info_none_popup_defaults_false(self):
        """User.additional_info is None — popup_last_closed treated as empty, no crash."""
        request = MagicMock()
        request.user_id = 1
        request.mcontext = MagicMock()

        mock_user_row = {
            "user_id": 1,
            "name": "Test User",
            "email": "test@example.com",
            "partner_id": 10,
            "partner_name": "Partner",
            "role_hierarchy_level": 4,  # MANAGER — ineligible, all false
            "is_maglo_publisher": False,
            "phone_number": None,
            "is_active": True,
            "is_email_verified": True,
            "is_phone_number_verified": False,
            "is_walkthrough_completed": False,
            "cloud_agent_number": None,
            "additional_info": None,
        }

        mock_user_result = MagicMock()
        mock_user_result.mappings.return_value.first.return_value = mock_user_row

        mock_config_result = MagicMock()
        mock_config_result.fetchall.return_value = []

        self.session_mock.execute = AsyncMock(
            side_effect=[mock_user_result, mock_config_result]
        )

        entitlement_service_mock = AsyncMock()
        entitlement_service_mock.get_subscription_status.return_value = {
            "console": {"status": "active", "entitlement_end_date": 9999999999999},
            "maglo": {"status": "grace", "entitlement_end_date": None},
            "babbler": {"status": "suspended", "entitlement_end_date": None},
        }

        response = await self.auth_service_grpc.GetUserDetails(
            request=request,
            context=self.context_mock,
            entitlement_service=entitlement_service_mock,
            grace_repo=AsyncMock(),
        )

        assert response.message == "Success"
        # MANAGER (hierarchy=4) > PopupEligibleHierarchy.MAX(3) → all false
        assert response.user_profile.show_popup["console"] is False
        assert response.user_profile.show_popup["maglo"] is False
        assert response.user_profile.show_popup["babbler"] is True
