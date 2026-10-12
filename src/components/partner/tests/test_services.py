from uuid import UUID
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import Request, UploadFile
from sqlalchemy.exc import IntegrityError

from src.components.auth.models import Role
from src.components.common.constants import CurrentUserMap
from src.components.partner.constant import PartnerResponseData, PartnerStatus
from src.components.partner.error import PartnerNotFoundError
from src.components.partner.models import Partner
from src.components.partner.schema import (
    BasePartnerData,
    ChangePartnerStatusResponse,
    PaginatedPartnerResponse,
    PartnerDetails,
    PartnerFilterRequest,
    PartnerMetaDataDetails,
    PartnerOnboardingDetails,
    PartnerOnboardingResponse,
    TogglePartnerActivation,
    TogglePartnerActivationResponse,
    UserDetails,
)
from src.components.partner.services import PartnerService
from src.exceptions import (
    AuthException,
    PartnerException,
    PartnerStatusUnchangedException,
)


@pytest.mark.asyncio
class TestPartnerService:

    @pytest.fixture(autouse=True)
    def setup_class(self, mock_logger, redis_mock):
        self.mock_logger = mock_logger
        self.redis_mock = redis_mock
        self.user_repository_mock = AsyncMock()
        self.partner_repository_mock = AsyncMock()
        self.audit_log_mock = AsyncMock()

        self.partner_service = PartnerService(
            partner_repository=self.partner_repository_mock,
            console_service_logger=self.mock_logger,
            partner_service_cache=self.redis_mock,
            audit_service=self.audit_log_mock,
        )

        # Test data
        self.partner_data = BasePartnerData(
            name="Tech Solutions",
            company_legal_name="Tech Solutions Pvt Ltd",
            gst_no="12ABCDE1234F1Z5",
            cin_no="U12345DL2024PTC123456",
            active_license=1,
            description="Tech Solutions is a leading IT company.",
        )

        self.partner_response = SimpleNamespace(
            id= UUID("11111111-1111-1111-1111-111111111111"),
            name="Tech Solutions",
            company_legal_name="Tech Solutions Pvt Ltd",
            gst_no="12ABCDE1234F1Z5",
            cin_no="U12345DL2024PTC123456",
            active_license=1,
            description="Tech Solutions is a leading IT company.",
        )

        self.current_user_mock = {"user_id": UUID("11111111-1111-1111-1111-111111111111")}

    async def test_create_partner_success(self):
        """Test successful creation of a partner."""
        # Arrange
        partner_data = BasePartnerData(
            name="Tech Solutions",
            company_legal_name="Tech Solutions Pvt Ltd",
            gst_no="12ABCDE1234F1Z5",
            cin_no="U12345DL2024PTC123456",
            active_license=10,
        )

        created_partner = Partner(
            id= UUID("11111111-1111-1111-1111-111111111111"),
            name="Tech Solutions",
            company_legal_name="Tech Solutions Pvt Ltd",
            gst_no="12ABCDE1234F1Z5",
            cin_no="U12345DL2024PTC123456",
            active_license=10,
        )

        repository_mock = AsyncMock()
        repository_mock.add_partner.return_value = created_partner

        audit_service_mock = AsyncMock()
        logger_mock = MagicMock()
        wallet_service_mock = AsyncMock()  # ✅ mock wallet service

        partner_service = PartnerService(
            partner_repository=repository_mock,
            audit_service=audit_service_mock,
            console_service_logger=logger_mock,
            partner_service_cache=None,
        )

        # Act
        result = await partner_service.create_partner(
            partner_data, wallet_service=wallet_service_mock
        )

        # Assert
        repository_mock.add_partner.assert_called_once_with(partner_data=partner_data)
        audit_service_mock.log_action.assert_called_once()
        wallet_service_mock.create_wallet.assert_called_once_with(
            created_partner.id
        )  # ✅ check call
        assert result.name == "Tech Solutions"
        logger_mock.info.assert_any_call(
            "Partner created successfully : {}".format(created_partner)
        )

    async def test_get_partner_by_id_success(self):
        """Test successful retrieval of partner by ID."""

        # Mock the repository's method to return a partner by ID
        self.partner_repository_mock.get_by_id.return_value = self.partner_response

        # Call the get_partner_by_id method
        partner = await self.partner_service.get_partner_by_id(UUID("11111111-1111-1111-1111-111111111111"))

        # Assert the partner's details
        assert partner.name == "Tech Solutions"
        assert partner.gst_no == "12ABCDE1234F1Z5"

        # Check if the log for fetching partner by ID is called
        self.mock_logger.info.assert_called_with(
            "Fetched partner successfully : {} ".format(self.partner_response)
        )

    async def test_update_partner_success(self):
        """Test successful partner update."""

        # Mock the repository's update method to return the updated partner response
        self.partner_repository_mock.update.return_value = self.partner_response

        # Call the update_partner method
        updated_partner = await self.partner_service.update_partner(
            1, self.partner_data, self.current_user_mock
        )

        # Assert the updated partner's attributes
        # assert updated_partner.name == "Tech Solutions"
        # assert updated_partner.gst_no == "12ABCDE1234F1Z5"

    async def test_update_partner_partner_not_found(self):
        """Test partner update when partner is not found."""

        # Mock the repository's update method to raise PartnerNotFoundError
        self.partner_repository_mock.get_by_id.side_effect = PartnerNotFoundError(
            "Partner not found"
        )

        with pytest.raises(PartnerNotFoundError):
            await self.partner_service.update_partner(
                1, self.partner_data, self.current_user_mock
            )

        # Check that the error is logged
        self.mock_logger.error.assert_called_with(
            "duplicate partner: Partner not found, id: Partner not found"
        )

    async def test_delete_partner_success(self):
        """Test successful partner deletion."""

        # Mock the repository's delete method to return the deleted partner response
        self.partner_repository_mock.delete_by_id.return_value = self.partner_response

        # Call the delete_partner_by_id method
        deleted_partner = await self.partner_service.delete_partner_by_id(
            1, self.current_user_mock
        )

        # Assert that the partner was deleted successfully
        assert deleted_partner.name == "Tech Solutions"

        # Ensure the deletion action is logged
        self.audit_log_mock.log_action.assert_called()

    async def test_delete_partner_partner_not_found(self):
        """Test partner deletion when partner is not found."""

        # Mock the repository's delete method to raise PartnerNotFoundError
        self.partner_repository_mock.delete_by_id.side_effect = PartnerNotFoundError(
            "Partner not found"
        )

        with pytest.raises(PartnerException):
            await self.partner_service.delete_partner_by_id(UUID("11111111-1111-1111-1111-111111111111"), self.current_user_mock)

        # Check that the error is logged
        self.mock_logger.error.assert_called_with(
            "Error while delete Partner: Partner not found, id: {}".format(
                self.partner_response.id
            )
        )

    async def test_get_partner_by_id_not_found(self):
        """Test partner not found during fetch by ID."""

        # Simulate partner not found by making `get_by_id` raise `PartnerNotFoundError`
        self.partner_repository_mock.get_by_id.side_effect = PartnerNotFoundError(
            "Partner not found"
        )

        # Call the service method to get partner by ID
        with pytest.raises(PartnerException):
            await self.partner_service.get_partner_by_id(partner_id= UUID("11111111-1111-1111-1111-111111111111"))

        # Ensure the repository method was called with the correct ID
        self.partner_repository_mock.get_by_id.assert_called_with(UUID("11111111-1111-1111-1111-111111111111"))

        # Ensure error logging was performed
        self.mock_logger.error.assert_called_with(
            "Error while getting Partner: Partner not found, id: {}".format(
                self.partner_response.id
            )
        )

    async def test_get_partner_by_id_generic_exception(self):
        """Test generic exception during fetching partner by ID."""

        # Simulate a generic exception by making `get_by_id` raise a generic exception
        self.partner_repository_mock.get_by_id.side_effect = Exception(
            "Generic error occurred"
        )

        # Call the service method to get partner by ID
        with pytest.raises(Exception):
            await self.partner_service.get_partner_by_id(partner_id= UUID("99999999-9999-9999-9999-999999999999"))

        # Ensure the repository method was called with the correct ID
        self.partner_repository_mock.get_by_id.assert_called_with(UUID("99999999-9999-9999-9999-999999999999"))

        # Ensure error logging was performed for the generic exception
        self.mock_logger.error.assert_called_with(
            "Error while getting Partner: Generic error occurred"
        )

    async def test_delete_partner_by_id_generic_exception(self):
        """Test generic exception during partner deletion by ID."""

        # Simulate a generic exception by making `delete_by_id` raise a generic exception
        self.partner_repository_mock.delete_by_id.side_effect = Exception(
            "Generic error occurred during deletion"
        )

        # Call the service method to delete the partner by ID
        with pytest.raises(Exception):
            await self.partner_service.delete_partner_by_id(
                partner_id= UUID("99999999-9999-9999-9999-999999999999"), current_user={"user_id": UUID("11111111-1111-1111-1111-111111111111")}
            )

    async def test_update_partner_integrity_error(self):
        """Test IntegrityError during partner update."""

        # Prepare mock partner data
        partner_data = BasePartnerData(
            name="Updated Tech Solutions",
            company_legal_name="Updated Tech Solutions Pvt Ltd",
            gst_no="12ABCDE1234F1Z5",
            cin_no="U12345TG2024PTC000123",
            active_license=1,
            description="Updated description",
        )

        # Simulate IntegrityError by making `update` raise an IntegrityError
        self.partner_repository_mock.update.side_effect = IntegrityError(
            "mock", "mock", "mock"
        )

        # Call the service method to update a partner
        with pytest.raises(PartnerException):
            await self.partner_service.update_partner(
                partner_id= UUID("11111111-1111-1111-1111-111111111111"), partner_data=partner_data, current_user={"id": UUID("11111111-1111-1111-1111-111111111111")}
            )

        # Ensure error logging was performed for the integrity error
        self.mock_logger.error.assert_called_with(
            "IntegrityError while creating partner: (builtins.str) mock\n[SQL: mock]\n[parameters: 'mock']\n(Background on this error at: https://sqlalche.me/e/20/gkpj)"
        )

    async def test_update_partner_generic_exception(self):
        """Test generic exception during partner update."""

        # Prepare mock partner data
        partner_data = BasePartnerData(
            name="Updated Tech Solutions",
            company_legal_name="Updated Tech Solutions Pvt Ltd",
            gst_no="12ABCDE1234F1Z5",
            cin_no="U12345TG2024PTC000123",
            active_license=1,
            description="Updated description",
        )

        # Simulate a generic exception by making `update` raise a generic exception
        self.partner_repository_mock.update.side_effect = Exception(
            "Generic error occurred during update"
        )

        # Call the service method to update a partner
        with pytest.raises(Exception):
            await self.partner_service.update_partner(
                partner_id= UUID("11111111-1111-1111-1111-111111111111"), partner_data=partner_data, current_user={"id": UUID("11111111-1111-1111-1111-111111111111")}
            )

        # Ensure error logging was performed for the generic exception
        self.mock_logger.error.assert_called_with(
            "Error while update Partner: Generic error occurred during update"
        )


    def test_get_partner_statuses_success(self):
        """Test successful retrieval of all partner statuses."""
        # Arrange
        mock_statuses = ["ACTIVE", "INACTIVE", "PENDING"]
        PartnerStatus.choices = MagicMock(return_value=mock_statuses)

        # Act
        result = self.partner_service.get_partner_statuses()

        # Assert
        assert result == mock_statuses
        self.mock_logger.info.assert_any_call("Fetching partner statuses")
        self.mock_logger.info.assert_any_call(
            f"Retrieved {len(mock_statuses)} partner statuses"
        )

    async def test_change_partner_status_success(self):
        """Test successful change of partner status and feedback flag."""
        # Arrange
        partner_id= UUID("11111111-1111-1111-1111-111111111111")
        new_status = "ACTIVE"
        is_feedback_enabled = True
        current_partner = Partner(
            id=partner_id,
            name="Tech Solutions",
            partner_status="PENDING",
            is_feedback_enabled=False,
        )
        updated_partner = Partner(
            id=partner_id,
            name="Tech Solutions",
            partner_status=new_status,
            is_feedback_enabled=is_feedback_enabled,
        )
        self.partner_repository_mock.get_by_id.return_value = current_partner
        self.partner_repository_mock.change_partner_status.return_value = (
            updated_partner
        )

        # Act
        result = await self.partner_service.change_partner_status(
            partner_id=partner_id,
            status=new_status,
            is_feedback_enabled=is_feedback_enabled,
        )

        # Assert
        self.partner_repository_mock.get_by_id.assert_called_once_with(partner_id)
        self.partner_repository_mock.change_partner_status.assert_called_once_with(
            partner_id, new_status, is_feedback_enabled
        )
        assert isinstance(result, ChangePartnerStatusResponse)
        assert result.id == partner_id
        assert result.name == "Tech Solutions"
        assert result.partner_status == new_status
        assert result.is_feedback_enabled == is_feedback_enabled
        self.mock_logger.info.assert_any_call(
            f"Processing status change for partner_id={partner_id}, status={new_status}, is_feedback_enabled={is_feedback_enabled}"
        )
        self.mock_logger.info.assert_any_call(
            f"Successfully updated partner_id={partner_id}"
        )

    async def test_get_partner_statuses_exception(self):
        """Test retrieval of partner statuses with an exception."""
        # Arrange
        PartnerStatus.choices = MagicMock(side_effect=Exception("Database error"))
        self.mock_logger.error.reset_mock()

        # Act & Assert
        with pytest.raises(Exception, match="Database error"):
            await self.partner_service.get_partner_statuses()
        self.mock_logger.error.assert_called_once_with(
            "Error fetching partner statuses: Database error"
        )

    async def test_change_partner_status_no_update_needed(self):
        """Test change partner status when no update is needed."""
        # Arrange
        partner_id= UUID("11111111-1111-1111-1111-111111111111")
        current_status = "ACTIVE"
        current_feedback_enabled = True
        current_partner = Partner(
            id=partner_id,
            name="Tech Solutions",
            partner_status=current_status,
            is_feedback_enabled=current_feedback_enabled,
        )
        self.partner_repository_mock.get_by_id.return_value = current_partner
        self.mock_logger.error.reset_mock()

        # Act & Assert
        with pytest.raises(PartnerStatusUnchangedException):
            await self.partner_service.change_partner_status(
                partner_id=partner_id,
                status=current_status,
                is_feedback_enabled=current_feedback_enabled,
            )
        self.mock_logger.info.assert_any_call(
            f"Processing status change for partner_id={partner_id}, status={current_status}, is_feedback_enabled={current_feedback_enabled}"
        )
        self.mock_logger.info.assert_any_call(
            f"No update needed for partner_id={partner_id}: status and is_feedback_enabled unchanged"
        )
        self.mock_logger.error.assert_called_once_with(
            f"Partner: {partner_id} remians unchanged"
        )

    async def test_change_partner_status_partner_not_found(self):
        """Test change partner status when partner is not found."""
        # Arrange
        partner_id= UUID("11111111-1111-1111-1111-111111111111")
        self.partner_repository_mock.get_by_id.return_value = None
        self.mock_logger.error.reset_mock()

        # Act & Assert
        with pytest.raises(PartnerException):
            await self.partner_service.change_partner_status(
                partner_id=partner_id, status="ACTIVE", is_feedback_enabled=True
            )
        self.mock_logger.error.assert_called_once_with(
            "Error while changing status of Partner: Partner not found, id: {}".format(
                partner_id
            )
        )

    async def test_change_partner_status_repository_failure(self):
        """Test change partner status when repository update fails."""
        # Arrange
        partner_id= UUID("11111111-1111-1111-1111-111111111111")
        current_partner = Partner(
            id=partner_id,
            name="Tech Solutions",
            partner_status="PENDING",
            is_feedback_enabled=False,
        )
        self.partner_repository_mock.get_by_id.return_value = current_partner
        self.partner_repository_mock.change_partner_status.return_value = None
        self.mock_logger.error.reset_mock()

        # Act & Assert
        with pytest.raises(
            ValueError, match=f"Partner with id={partner_id} not found or inactive"
        ):
            await self.partner_service.change_partner_status(
                partner_id=partner_id, status="ACTIVE", is_feedback_enabled=True
            )
        self.mock_logger.error.assert_called_once_with(
            f"Error changing partner status for partner_id={partner_id}: Partner with id={partner_id} not found or inactive"
        )

    async def test_change_partner_status_unexpected_exception(self):
        """Test change partner status with an unexpected exception."""
        # Arrange
        partner_id= UUID("11111111-1111-1111-1111-111111111111")
        current_partner = Partner(
            id=partner_id,
            name="Tech Solutions",
            partner_status="PENDING",
            is_feedback_enabled=False,
        )
        self.partner_repository_mock.get_by_id.return_value = current_partner
        self.partner_repository_mock.change_partner_status.side_effect = Exception(
            "Unexpected error"
        )
        self.mock_logger.error.reset_mock()

        # Act & Assert
        with pytest.raises(Exception, match="Unexpected error"):
            await self.partner_service.change_partner_status(
                partner_id=partner_id, status="ACTIVE", is_feedback_enabled=True
            )
        self.mock_logger.error.assert_called_once_with(
            f"Error changing partner status for partner_id={partner_id}: Unexpected error"
        )

    @pytest.mark.asyncio
    async def test_create_partner_with_existing_gst(self):
        """Test creating a partner with an existing GST number."""
        # Simulate IntegrityError for existing GST number
        self.partner_repository_mock.add_partner.side_effect = IntegrityError(
            statement="INSERT INTO partners ...",
            params=None,
            orig=Exception("console_partners_gst_no_key"),
        )

        # Act & Assert
        with pytest.raises(PartnerException, match="GST number already exists."):
            await self.partner_service.create_partner(partner_data=self.partner_data)

        # Ensure the error is logged
        self.mock_logger.error.assert_called_with(
            "Error changing partner status for partner_id=11111111-1111-1111-1111-111111111111: Unexpected error"
        )

    @pytest.mark.asyncio
    async def test_create_partner_with_existing_cin(self):
        """Test creating a partner with an existing CIN number."""
        # Simulate IntegrityError for existing CIN number
        self.partner_repository_mock.add_partner.side_effect = IntegrityError(
            statement="INSERT INTO partners ...",
            params=None,
            orig=Exception("console_partners_cin_no_key"),
        )

        # Act & Assert
        with pytest.raises(PartnerException, match="cin number already exists."):
            await self.partner_service.create_partner(partner_data=self.partner_data)

        # Ensure the error is logged
        self.mock_logger.error.assert_called_with(
            "Error changing partner status for partner_id=11111111-1111-1111-1111-111111111111: Unexpected error"
        )

    async def test_onboard_partner_success(self):
        """Should successfully onboard a partner and return response with login token."""
        request = MagicMock(spec=Request)

        # Test data
        user_details = UserDetails(
            email="test@example.com",
            password="Password@123",
            name="Test User",
            phone_number="+919595903456",
        )
        partner_meta_data = PartnerMetaDataDetails(is_talko_free_trial__enabled=True)
        partner_details = PartnerDetails(
            id= UUID("11111111-1111-1111-1111-111111111111"),
            name="Test Partner",
            company_legal_name="Test Partner",
            description="Sample Partner",
        )
        partner_data = PartnerOnboardingDetails(
            user_details=user_details,
            partner_meta_data=partner_meta_data,
            partner_details=partner_details,
        )

        # Mock dependencies
        auth_service_utility_mock = AsyncMock()
        auth_service_mock = AsyncMock()

        self.partner_service.check_partner_free_trial_eligible = AsyncMock(
            return_value=True
        )
        auth_service_utility_mock.get_password_hash.return_value = "hashed_pwd"
        auth_service_mock.get_role_by_hierarchy.return_value = Role(id= UUID("11111111-1111-1111-1111-111111111111"), name="Admin")
        self.partner_repository_mock.onboard_partner = AsyncMock(
            return_value=partner_details
        )
        auth_service_mock.get_token.return_value = "mock_token"
        wallet_service_mock = AsyncMock()

        result = await self.partner_service.onboard_partner(
            request,
            partner_data,
            auth_service=auth_service_mock,
            auth_service_utility=auth_service_utility_mock,
            wallet_service=wallet_service_mock,
        )

        assert isinstance(result, PartnerOnboardingResponse)
        assert result.user_login_token == "mock_token"
        wallet_service_mock.create_wallet.assert_called_once_with(partner_details.id)

    async def test_onboard_partner_partner_exception(self):
        """Should log and re-raise PartnerException."""
        # Test data
        user_details = UserDetails(
            email="test@example.com",
            password="Password@123",
            name="Test User",
            phone_number="+919595903456",
        )
        partner_meta_data = PartnerMetaDataDetails(is_talko_free_trial__enabled=True)
        partner_details = PartnerDetails(
            id= UUID("11111111-1111-1111-1111-111111111111"),
            name="Test Partner",
            company_legal_name="Test Partner",
            description="Sample Partner",
        )
        partner_data = PartnerOnboardingDetails(
            user_details=user_details,
            partner_meta_data=partner_meta_data,
            partner_details=partner_details,
        )

        request = MagicMock(spec=Request)

        auth_service_utility_mock = AsyncMock()
        auth_service_mock = AsyncMock()

        self.partner_service.check_partner_free_trial_eligible = AsyncMock(
            side_effect=PartnerException("Invalid partner")
        )

        with pytest.raises(PartnerException):
            await self.partner_service.onboard_partner(
                request,
                partner_data,
                auth_service=auth_service_mock,
                auth_service_utility=auth_service_utility_mock,
            )

        self.mock_logger.error.assert_called_with(
            "Error occurred onboarding free trial partner, error: Invalid partner"
        )

    async def test_onboard_partner_generic_exception(self):
        """Should log and re-raise generic exceptions."""

        auth_service_utility_mock = AsyncMock()
        auth_service_mock = AsyncMock()

        request = MagicMock(spec=Request)

        self.partner_service.check_partner_free_trial_eligible = AsyncMock(
            side_effect=Exception("DB error")
        )

        # Test data
        user_details = UserDetails(
            email="test@example.com",
            password="Password@123",
            name="Test User",
            phone_number="+919595903456",
        )
        partner_meta_data = PartnerMetaDataDetails(is_talko_free_trial__enabled=True)
        partner_details = PartnerDetails(
            id= UUID("11111111-1111-1111-1111-111111111111"),
            name="Test Partner",
            company_legal_name="Test Partner",
            description="Sample Partner",
        )
        partner_data = PartnerOnboardingDetails(
            user_details=user_details,
            partner_meta_data=partner_meta_data,
            partner_details=partner_details,
        )

        with pytest.raises(Exception):
            await self.partner_service.onboard_partner(
                request,
                partner_data,
                auth_service=auth_service_mock,
                auth_service_utility=auth_service_utility_mock,
            )

        self.mock_logger.error.assert_called_with(
            "Error while creating Partner: DB error"
        )

    async def test_set_trial_expiry_time_talko_enabled(self):
        """Should set talko expiry time and enable talko when free trial enabled."""
        user_details = UserDetails(
            email="t@e.com",
            password="Test@123",
            phone_number="+919595903445",
            name="test name",
            is_talko_enabled=True,
        )
        partner_meta_data = PartnerMetaDataDetails(is_talko_free_trial__enabled=True)

        self.partner_service.set_trial_expiry_time_and_allow_services(
            partner_meta_data, user_details
        )

        assert partner_meta_data.talko_trail_expiry_time is not None
        assert user_details.is_talko_enabled is True

    async def test_check_partner_free_trial_eligible_success(self):
        """Should return True if partner is eligible."""
        self.partner_service._PartnerService__repository.check_partner_free_trial_eligible = AsyncMock(
            return_value=True
        )

        result = await self.partner_service.check_partner_free_trial_eligible(
            self.partner_data
        )
        assert result is True
        self.mock_logger.info.assert_called_with(
            "Attempting to check partner is eligible"
        )

    async def test_check_partner_free_trial_eligible_partner_exception(self):
        """Should log and re-raise PartnerException."""
        self.partner_service._PartnerService__repository.check_partner_free_trial_eligible = AsyncMock(
            side_effect=PartnerException("Eligibility check failed")
        )

        with pytest.raises(PartnerException):
            await self.partner_service.check_partner_free_trial_eligible(
                self.partner_data
            )

        self.mock_logger.error.assert_called_with(
            "Error occurred while checking partner eligibility, error: Eligibility check failed"
        )

    async def test_check_partner_free_trial_eligible_generic_exception(self):
        """Should log and re-raise generic exception."""
        self.partner_service._PartnerService__repository.check_partner_free_trial_eligible = AsyncMock(
            side_effect=Exception("Unexpected DB error")
        )

        with pytest.raises(Exception):
            await self.partner_service.check_partner_free_trial_eligible(
                self.partner_data
            )

        self.mock_logger.error.assert_called_with(
            "Unexpected error occurred while checking partner eligibility, error: Unexpected DB error"
        )

    @pytest.mark.asyncio
    async def test_enlist_partners_dynamically_success(self):
        # Arrange
        filter_request = PartnerFilterRequest(
            filters=[],
            order_by=[],
            limit=10,
            offset=0,
            dashboard_filters=None,
            is_custom_role_permission_enabled=False,
        )

        # Mocks
        user_service_mock = AsyncMock()
        user_service_mock.is_user_internal.return_value = True

        partner_filter_service_mock = AsyncMock()
        fake_response = PaginatedPartnerResponse(
            total_count=1, limit=10, offset=0, partners_data=[]
        )
        partner_filter_service_mock.enlist_partners_dynamically.return_value = (
            fake_response
        )

        # Act
        response = await self.partner_service.enlist_partners_dynamically(
            current_user=self.current_user_mock,
            filter_request=filter_request,
            user_service=user_service_mock,
            partner_filter_service=partner_filter_service_mock,
        )

        # Assert
        assert response == fake_response
        user_service_mock.is_user_internal.assert_awaited_once_with(
            self.current_user_mock["user_id"]
        )
        partner_filter_service_mock.enlist_partners_dynamically.assert_awaited_once_with(
            filter_request=filter_request
        )

    @pytest.mark.asyncio
    async def test_enlist_partners_dynamically_not_internal_user_raises_auth(self):
        # Arrange
        filter_request = PartnerFilterRequest(
            filters=[],
            order_by=[],
            limit=10,
            offset=0,
            dashboard_filters=None,
            is_custom_role_permission_enabled=False,
        )

        user_service_mock = AsyncMock()
        user_service_mock.is_user_internal.return_value = False

        partner_filter_service_mock = AsyncMock()

        # Act & Assert
        with pytest.raises(AuthException):
            await self.partner_service.enlist_partners_dynamically(
                current_user=self.current_user_mock,
                filter_request=filter_request,
                user_service=user_service_mock,
                partner_filter_service=partner_filter_service_mock,
            )

        user_service_mock.is_user_internal.assert_awaited_once_with(
            self.current_user_mock["user_id"]
        )
        partner_filter_service_mock.enlist_partners_dynamically.assert_not_awaited()

    @pytest.fixture
    def toggle_partner_activation_setup(self):
        # Mocks for dependencies
        user_service = AsyncMock()
        user_session_service = AsyncMock()
        partner_service_cache = AsyncMock()
        repository = AsyncMock()
        logger = MagicMock()
        service = PartnerService(
            partner_repository=repository,
            console_service_logger=logger,
            partner_service_cache=partner_service_cache,
            audit_service=AsyncMock(),
        )
        return (
            service,
            repository,
            logger,
            partner_service_cache,
            user_service,
            user_session_service,
        )

    @pytest.mark.asyncio
    async def test_toggle_partner_activation_success_active(
        self, toggle_partner_activation_setup
    ):
        (
            service,
            repository,
            logger,
            partner_service_cache,
            user_service,
            user_session_service,
        ) = toggle_partner_activation_setup
        current_user = {CurrentUserMap.USER_ID: UUID("11111111-1111-1111-1111-111111111111")}
        partner_id= UUID("42424242-4242-4242-4242-424242424242")
        partner_data = TogglePartnerActivation(is_active=True)
        repository.toggle_partner_activation.return_value = (
            True,
            [{"id": 101}, {"id": 102}],
        )
        user_service.is_user_internal.return_value = True

        # Act
        response = await service.toggle_partner_activation(
            current_user=current_user,
            partner_id=partner_id,
            partner_data=partner_data,
            user_service=user_service,
            user_session_service=user_session_service,
        )

        # Assert
        repository.toggle_partner_activation.assert_awaited_once_with(
            partner_id=partner_id, partner_data=partner_data
        )
        user_service.is_user_internal.assert_awaited_once_with(UUID("11111111-1111-1111-1111-111111111111"))

        assert isinstance(response, TogglePartnerActivationResponse)
        assert response.is_active is True
        logger.info.assert_any_call(
            f"Trying to update the partner active status for id: {partner_id}"
        )

    @pytest.mark.asyncio
    async def test_toggle_partner_activation_success_deactivated(
        self, toggle_partner_activation_setup
    ):
        (
            service,
            repository,
            logger,
            partner_service_cache,
            user_service,
            user_session_service,
        ) = toggle_partner_activation_setup
        current_user = {CurrentUserMap.USER_ID: UUID("11111111-1111-1111-1111-111111111111")}
        partner_id= UUID("42424242-4242-4242-4242-424242424242")
        partner_data = TogglePartnerActivation(is_active=False)
        repository.toggle_partner_activation.return_value = (
            False,
            [{"id": 101}, {"id": 102}],
        )
        user_service.is_user_internal.return_value = True

        # Act
        response = await service.toggle_partner_activation(
            current_user=current_user,
            partner_id=partner_id,
            partner_data=partner_data,
            user_service=user_service,
            user_session_service=user_session_service,
        )

        # Assert
        user_session_service.deactivate_user_sessions.assert_awaited_once_with(
            [101, 102]
        )
        logger.info.assert_any_call(
            f"partner is deactivated, making all user's session false for partner id: {partner_id}"
        )
        logger.info.assert_any_call(
            f"All the user's session associated with current partner id: {partner_id} is deactivated successfully"
        )
        assert isinstance(response, TogglePartnerActivationResponse)
        assert response.is_active is False

    @pytest.mark.asyncio
    async def test_toggle_partner_activation_not_internal_user(
        self, toggle_partner_activation_setup
    ):
        (
            service,
            repository,
            logger,
            partner_service_cache,
            user_service,
            user_session_service,
        ) = toggle_partner_activation_setup
        current_user = {CurrentUserMap.USER_ID: UUID("11111111-1111-1111-1111-111111111111")}
        partner_id= UUID("42424242-4242-4242-4242-424242424242")
        partner_data = TogglePartnerActivation(is_active=True)
        user_service.is_user_internal.return_value = False

        with pytest.raises(PartnerException) as exc_info:
            await service.toggle_partner_activation(
                current_user=current_user,
                partner_id=partner_id,
                partner_data=partner_data,
                user_service=user_service,
                user_session_service=user_session_service,
            )
        assert PartnerResponseData.CHANGE_PARTNER_STATUS_VALIDATION in str(
            exc_info.value
        )

    @pytest.mark.asyncio
    async def test_toggle_partner_activation_partner_not_found(
        self, toggle_partner_activation_setup
    ):
        (
            service,
            repository,
            logger,
            partner_service_cache,
            user_service,
            user_session_service,
        ) = toggle_partner_activation_setup
        current_user = {CurrentUserMap.USER_ID: UUID("11111111-1111-1111-1111-111111111111")}
        partner_id= UUID("42424242-4242-4242-4242-424242424242")
        partner_data = TogglePartnerActivation(is_active=True)
        user_service.is_user_internal.return_value = True
        repository.toggle_partner_activation.side_effect = PartnerNotFoundError(
            "not found"
        )

        with pytest.raises(PartnerNotFoundError):
            await service.toggle_partner_activation(
                current_user=current_user,
                partner_id=partner_id,
                partner_data=partner_data,
                user_service=user_service,
                user_session_service=user_session_service,
            )
        logger.error.assert_called_with(
            "Partner not found error: Partner not found, id: not found"
        )

    @pytest.mark.asyncio
    async def test_toggle_partner_activation_partner_exception(
        self, toggle_partner_activation_setup
    ):
        (
            service,
            repository,
            logger,
            partner_service_cache,
            user_service,
            user_session_service,
        ) = toggle_partner_activation_setup
        current_user = {CurrentUserMap.USER_ID: UUID("11111111-1111-1111-1111-111111111111")}
        partner_id= UUID("42424242-4242-4242-4242-424242424242")
        partner_data = TogglePartnerActivation(is_active=True)
        user_service.is_user_internal.return_value = True
        repository.toggle_partner_activation.side_effect = PartnerException(
            "custom error"
        )

        with pytest.raises(PartnerException):
            await service.toggle_partner_activation(
                current_user=current_user,
                partner_id=partner_id,
                partner_data=partner_data,
                user_service=user_service,
                user_session_service=user_session_service,
            )
        logger.error.assert_called_with("Partner exception occured: custom error")

    @pytest.mark.asyncio
    async def test_toggle_partner_activation_generic_exception(
        self, toggle_partner_activation_setup
    ):
        (
            service,
            repository,
            logger,
            partner_service_cache,
            user_service,
            user_session_service,
        ) = toggle_partner_activation_setup
        current_user = {CurrentUserMap.USER_ID: UUID("11111111-1111-1111-1111-111111111111")}
        partner_id= UUID("42424242-4242-4242-4242-424242424242")
        partner_data = TogglePartnerActivation(is_active=True)
        user_service.is_user_internal.return_value = True
        repository.toggle_partner_activation.side_effect = Exception("unexpected")

        with pytest.raises(Exception):
            await service.toggle_partner_activation(
                current_user=current_user,
                partner_id=partner_id,
                partner_data=partner_data,
                user_service=user_service,
                user_session_service=user_session_service,
            )
        logger.error.assert_called_with(
            "An unexpected error occured while updating the partner active status: unexpected"
        )