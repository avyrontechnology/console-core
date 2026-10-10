from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from src.components.partner.constant import TrialPartnerExceptionMessage
from src.components.partner.error import PartnerNotFoundError
from src.components.partner.models import Partner
from src.components.partner.repositories import PartnerRepository
from src.components.partner.schema import (
    BasePartnerData,
    PartnerDetails,
    PartnerMetaDataDetails,
    PartnerOnboardingDetails,
    UserDetails,
)
from src.components.partner_config.constants import (
    PartnerConfigEnum,
    SubscriptionModeEnum,
)
from src.exceptions import PartnerException


@pytest.mark.asyncio
class TestPartnerRepository:

    @pytest.fixture(autouse=True)
    def setup_class(self, mock_session_factory, mock_logger):
        """Set up the auth repository using fixtures for mock session and logger."""
        self.partner_repository = PartnerRepository(
            session_factory=mock_session_factory, console_service_logger=mock_logger
        )
        self.session = mock_session_factory.return_value.__aenter__.return_value
        self.mock_logger = mock_logger

        self.mock_partner = Partner(
            id=1, name="Tech Solutions", is_active=True, gst_no="1234567890GST"
        )

    async def test_get_partner_by_id(self):
        """Test for getting partner by id."""
        partner_id = 1
        mock_partner_data = Partner(
            name="Tech Solutions",
            company_legal_name="Tech Solutions Pvt Ltd",
            gst_no="12ABCDE1234F1Z5",
            cin_no="U12345TG2024PTC000123",
            active_license=1,
            description="A leading tech partner",
            is_active=True,
        )

        # Mock the database execution and response
        mock_scalars = MagicMock()
        mock_scalars.first.return_value = mock_partner_data
        mock_execute = MagicMock()
        mock_execute.scalars.return_value = mock_scalars
        self.session.execute = AsyncMock(return_value=mock_execute)

        # calling get partner by id method
        result = await self.partner_repository.get_by_id(partner_id)

        # Asserting the results
        assert result == mock_partner_data

    async def test_get_partner_by_id_not_found(self):
        """ "Test for get partner by by id when the partner with the perticular id is not found"""
        partner_id = 1
        mock_scalars = MagicMock()
        mock_scalars.first.return_value = None
        mock_execute = MagicMock()
        mock_execute.scalars.return_value = mock_scalars
        self.session.execute = AsyncMock(return_value=mock_execute)

        # Simulate the behavior where no partner is found
        # self.session.get.return_value = None

        # Checking that the PartnerNotFoundError is raised when the partner with the perticular partner id is not available
        with pytest.raises(PartnerNotFoundError) as exc_info:
            await self.partner_repository.get_by_id(partner_id)

        # Asserting the exception message containing partner id
        assert str(partner_id) in str(exc_info.value)

    async def test_get_partner_by_id_generic_exception(self):
        """Test for the generic exception when partner with perticular id is not found"""
        self.session.execute = AsyncMock(side_effect=Exception("Unexpected Error"))
        with pytest.raises(Exception) as exc_info:
            await self.partner_repository.get_by_id(partner_id=1)
        assert str(exc_info.value) == "Unexpected Error"
        self.mock_logger.error.assert_called_with(
            "Error while get Partner by id: Unexpected Error"
        )

    async def test_delete_partner_by_id(self):
        """Test for delete partner by id."""
        partner_id = 1
        # Mocking the return value of scalars().first and session.execute()
        mock_scalars = MagicMock()
        mock_scalars.first.return_value = self.mock_partner

        mock_execute = MagicMock()
        mock_execute.scalars.return_value = mock_scalars
        self.session.execute = AsyncMock(return_value=mock_execute)

        # Mock commit and refresh to avoid real DB calls
        self.session.commit = AsyncMock()
        self.session.refresh = AsyncMock()

        result = await self.partner_repository.delete_by_id(partner_id, user_id=1)

        # Asserting the result
        assert result.id == partner_id
        assert result.is_deleted is True

    async def test_delete_partner_partner_not_found(self):
        """Test for delete partner by id when partner is not found."""
        partner_id = 1

        # Mock the session's execute method to return None for the partner
        mock_scalars = MagicMock()
        mock_scalars.first.return_value = None
        self.session.execute.return_value.scalars.return_value = mock_scalars

        # Test: Check that PartnerNotFoundError is raised when partner is not found
        with pytest.raises(PartnerNotFoundError):
            await self.partner_repository.delete_by_id(partner_id=partner_id, user_id=1)

        # Ensure that the logger's error method was called with the correct message
        self.mock_logger.error.assert_called_with(
            "Error while deleting Partner: Partner not found, id: {}".format(partner_id)
        )

    async def test_delete_partner_generic_exception(self):
        # Mock generic Exception
        self.session.execute = AsyncMock(side_effect=Exception("Unexpected Error"))

        with pytest.raises(Exception) as exc_info:
            await self.partner_repository.delete_by_id(partner_id=1, user_id=1)

        assert str(exc_info.value) == "Unexpected Error"
        self.mock_logger.error.assert_called_with(
            "Error while deleting Partner: Unexpected Error"
        )

    async def test_update_partner_success(self):
        """Test for successful partner update."""

        partner_id = 1
        user_id = 1
        partner_data = BasePartnerData(
            name="Updated Tech Solutions",
            company_legal_name="Updated Tech Solutions Pvt Ltd",
            gst_no="12ABCDE1234F1Z5",
            cin_no="U12345TG2024PTC000123",
            active_license=1,
            description="Updated description",
        )

        # Mock the session's execute method to return the mock_partner when queried
        mock_execute_result = MagicMock()
        mock_execute_result.scalars.first.return_value = AsyncMock(
            return_value=self.mock_partner
        )

        # Mock session.execute to return the mock_execute_result
        self.session.execute = AsyncMock(return_value=mock_execute_result)

        # Mock the commit and refresh methods
        self.session.commit = AsyncMock()
        self.session.refresh = AsyncMock()

        # Call the method to update the partner
        updated_partner = await self.partner_repository.update(
            user_id, partner_id, partner_data
        )

        # Assertions to ensure that the partner was updated correctly
        assert updated_partner.name == partner_data.name
        assert updated_partner.gst_no == partner_data.gst_no
        assert updated_partner.name == "Updated Tech Solutions"
        assert updated_partner.gst_no == "12ABCDE1234F1Z5"

        # Ensure the mock session methods were called
        self.session.commit.assert_called_once()
        self.session.refresh.assert_called_once()
        self.mock_logger.info.assert_called()

    async def test_update_partner_integrity_error(self):
        """Test for integrity error during partner update."""

        partner_id = 1
        user_id = 1
        partner_data = BasePartnerData(
            name="Updated Tech Solutions",
            company_legal_name="Updated Tech Solutions Pvt Ltd",
            gst_no="12ABCDE1234F1Z5",
            cin_no="U12345TG2024PTC000123",
            active_license=1,
            description="Updated description",
        )

        # Mock the session's execute method to return the mock_partner when queried
        mock_execute_result = MagicMock()
        mock_execute_result.scalars.first.return_value = AsyncMock(
            return_value=self.mock_partner
        )

        # Mock session.execute to return the mock_execute_result
        self.session.execute = AsyncMock(return_value=mock_execute_result)

        # Create a more detailed mock of the IntegrityError to simulate the actual exception
        integrity_error = IntegrityError("mock", "mock", "mock")
        integrity_error.orig = Exception(
            'duplicate key value violates unique constraint "ix_console_partners_name"'
        )

        # Mock the commit method to raise the mocked IntegrityError with the correct message
        self.session.commit = AsyncMock(side_effect=integrity_error)

        # Mock the rollback method to ensure it is called
        self.session.rollback = AsyncMock()

        with pytest.raises(IntegrityError) as context:
            await self.partner_repository.update(user_id, partner_id, partner_data)

        # Assert that rollback was called
        self.session.rollback.assert_called_once()

        # Assert that the exception message is as expected
        assert (
            str(context.value.orig)
            == 'duplicate key value violates unique constraint "ix_console_partners_name"'
        )

        # Ensure the mock session methods were called
        self.session.execute.assert_called_once()
        self.session.commit.assert_called_once()
        self.mock_logger.error.assert_called()

        # Print the rollback call count for debugging
        print(f"Rollback call count: {self.session.rollback.call_count}")

    async def test_update_partner_generic_exception(self):
        """Test for a generic exception during partner update."""

        partner_id = 1
        user_id = 1
        partner_data = BasePartnerData(
            name="Updated Tech Solutions",
            company_legal_name="Updated Tech Solutions Pvt Ltd",
            gst_no="12ABCDE1234F1Z5",
            cin_no="U12345TG2024PTC000123",
            active_license=1,
            description="Updated description",
        )

        # Mock the session's execute method to return the mock_partner when queried
        mock_execute_result = MagicMock()
        mock_execute_result.scalars.first.return_value = AsyncMock(
            return_value=self.mock_partner
        )

        # Mock session.execute to return the mock_execute_result
        self.session.execute = AsyncMock(return_value=mock_execute_result)

        # Mock the commit method to raise a generic exception (e.g., ValueError)
        self.session.commit = AsyncMock(
            side_effect=ValueError("A generic error occurred")
        )

        # Mock the rollback method to ensure it is not called (since this isn't an IntegrityError)
        self.session.rollback = AsyncMock()

        with pytest.raises(ValueError) as context:
            await self.partner_repository.update(user_id, partner_id, partner_data)

        # Assert that rollback was not called for a generic exception
        self.session.rollback.assert_not_called()

        # Assert that the exception message is as expected
        assert str(context.value) == "A generic error occurred"

        # Ensure the mock session methods were called
        self.session.execute.assert_called_once()
        self.session.commit.assert_called_once()
        self.mock_logger.error.assert_called()  # Check that error logging occurred

        # Print the error call count for debugging
        print(f"Error call count: {self.mock_logger.error.call_count}")

    async def test_update_partner_logo_success(self):
        """Test successful update of partner logo."""
        # Arrange
        partner_id = 1
        partner_logo_id = 123
        user_id = 1
        mock_partner = MagicMock(id=partner_id, partner_logo_id=None)

        # Mock the database execution and response
        mock_scalars = MagicMock()
        mock_scalars.first.return_value = mock_partner
        mock_execute = MagicMock()
        mock_execute.scalars.return_value = mock_scalars
        self.session.execute = AsyncMock(return_value=mock_execute)

        # Mock commit and refresh
        self.session.commit = AsyncMock()
        self.session.refresh = AsyncMock()

        # Act
        result = await self.partner_repository.update_partner_logo(
            partner_id=partner_id,
            partner_logo_id=partner_logo_id,
            user_id=user_id,
        )

        # Assert
        assert result == mock_partner
        assert result.partner_logo_id == partner_logo_id
        assert result.updated_by == user_id
        self.session.execute.assert_called_once()
        self.session.commit.assert_called_once()
        self.session.refresh.assert_called_once_with(mock_partner)
        self.mock_logger.info.assert_called_with(
            f"Updating logo for partner_id: {partner_id}"
        )

    async def test_add_partner_success(self):
        partner_data = BasePartnerData(
            name="New Partner Co.",
            company_legal_name="New Partner Pvt Ltd",
            gst_no="12ABCDE1234F1Z5",
            cin_no="U12345TG2024PTC000999",
            active_license=1,
            description="A new partner",
            is_maglo_publisher=False,
        )

        self.session.scalar = AsyncMock(return_value=None)
        self.session.add = MagicMock()
        self.session.commit = AsyncMock()
        self.session.refresh = AsyncMock()
        self.session.flush = AsyncMock()

        result = await self.partner_repository.add_partner(partner_data)

        # ✅ Assert Partner + 2 PartnerConfig objects were added (3 total)
        assert self.session.add.call_count == 3
        added_objs = [call_args[0][0] for call_args in self.session.add.call_args_list]
        assert any(isinstance(obj, Partner) for obj in added_objs)
        partner_configs = [
            obj for obj in added_objs if obj.__class__.__name__ == "PartnerConfig"
        ]
        assert len(partner_configs) == 2

        config_keys = {cfg.key for cfg in partner_configs}
        assert PartnerConfigEnum.IS_EMAIL_VERIFICATION_ENABLED.value in config_keys
        assert PartnerConfigEnum.SUBSCRIPTION_MODE.value in config_keys

        self.session.commit.assert_awaited()
        self.session.refresh.assert_awaited()
        assert isinstance(result, Partner)
        assert result.name == partner_data.name

    async def test_add_partner_raises_if_existing_maglo_publisher(self):
        # Arrange
        existing_partner = Partner(
            id=42,
            name="Tech Solutions",
            is_maglo_publisher=True,
        )

        partner_data = BasePartnerData(
            name="Tech Solutions",
            company_legal_name="Tech Solutions Pvt Ltd",
            is_maglo_publisher=True,
        )

        self.session.scalar = AsyncMock(return_value=existing_partner)
        self.session.commit = AsyncMock()
        self.session.refresh = AsyncMock()

        # Act & Assert
        with pytest.raises(PartnerException) as exc_info:
            await self.partner_repository.add_partner(partner_data)

        # Important: commit and refresh should NOT be called
        self.session.commit.assert_not_awaited()
        self.session.refresh.assert_not_awaited()

    async def test_add_partner_generic_exception(self):
        # Arrange: Raise RuntimeError when scalar is called
        partner_data = BasePartnerData(
            name="Unexpected Partner",
            company_legal_name="Oops Ltd",
            is_maglo_publisher=False,
        )

        self.session.scalar = AsyncMock(side_effect=RuntimeError("Database down"))

        # Act & Assert
        with pytest.raises(RuntimeError) as exc_info:
            await self.partner_repository.add_partner(partner_data)

        assert "Database down" in str(exc_info.value)

        # Verify error was logged
        self.mock_logger.error.assert_any_call(
            "Error while creating Partner: Database down"
        )

    async def test_change_partner_status_success(self):
        """Test successful update of partner status and feedback flag."""
        # Arrange
        partner_id = 1
        new_status = "ACTIVE"
        is_feedback_enabled = True
        mock_partner = Partner(
            id=partner_id,
            name="Tech Solutions",
            partner_status="PENDING",
            is_feedback_enabled=False,
            is_active=True,
        )

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_partner
        self.session.execute = AsyncMock(return_value=mock_result)
        self.session.commit = AsyncMock()
        self.session.refresh = AsyncMock()
        self.mock_logger.error.reset_mock()

        # Act
        result = await self.partner_repository.change_partner_status(
            partner_id=partner_id,
            status=new_status,
            is_feedback_enabled=is_feedback_enabled,
        )

        # Assert
        assert result == mock_partner
        assert mock_partner.partner_status == new_status
        assert mock_partner.is_feedback_enabled == is_feedback_enabled
        self.session.execute.assert_called_once()
        self.session.commit.assert_called_once()
        self.session.refresh.assert_called_once_with(mock_partner)
        self.mock_logger.info.assert_any_call(
            f"Updating partner_id={partner_id} with status={new_status}, is_feedback_enabled={is_feedback_enabled}"
        )
        self.mock_logger.info.assert_any_call(
            f"Partner_id={partner_id} updated successfully"
        )

    async def test_change_partner_status_exception(self):
        """Test change partner status with an unexpected exception."""
        # Arrange
        partner_id = 1
        new_status = "ACTIVE"
        is_feedback_enabled = True
        self.session.execute = AsyncMock(side_effect=Exception("Database error"))
        self.session.rollback = AsyncMock()
        self.mock_logger.error.reset_mock()

        # Act & Assert
        with pytest.raises(Exception, match="Database error"):
            await self.partner_repository.change_partner_status(
                partner_id=partner_id,
                status=new_status,
                is_feedback_enabled=is_feedback_enabled,
            )
        self.session.execute.assert_called_once()
        self.session.rollback.assert_called_once()
        self.mock_logger.info.assert_any_call(
            f"Updating partner_id={partner_id} with status={new_status}, is_feedback_enabled={is_feedback_enabled}"
        )
        self.mock_logger.error.assert_called_once_with(
            f"Error updating partner_id={partner_id}: Database error"
        )

    async def test_onboard_partner_success(self):
        """Test successful partner onboarding with commit & refresh."""
        # Test data
        user_details = UserDetails(
            email="test@example.com",
            password="Password@123",
            name="Test User",
            phone_number="+919595903456",
        )
        partner_meta_data = PartnerMetaDataDetails(is_maglo_free_trial_enabled=True)
        partner_details = PartnerDetails(
            id=1,
            name="Test Partner",
            company_legal_name="Test Partner",
            description="Sample Partner",
        )
        partner_data = PartnerOnboardingDetails(
            user_details=user_details,
            partner_meta_data=partner_meta_data,
            partner_details=partner_details,
        )
        # Mock flush and refresh to set partner.id
        self.session.flush = AsyncMock(
            side_effect=lambda: setattr(self.partner_repository, "id", 1)
        )
        self.session.commit = AsyncMock()
        self.session.refresh = AsyncMock()

        partner = await self.partner_repository.onboard_partner(partner_data)

        assert isinstance(partner, Partner)
        self.session.add.assert_any_call(partner)
        self.session.commit.assert_awaited()
        self.session.refresh.assert_awaited_with(partner)
        self.mock_logger.info.assert_any_call(
            f"Partner with ID {partner.id} successfully onboarded and PartnerConfig 'is_email_verification_enabled' created"
        )

    async def test_onboard_partner_rollback_on_error(self):
        """Test onboarding rollback when exception occurs."""
        # Test data
        user_details = UserDetails(
            email="test@example.com",
            password="Password@123",
            name="Test User",
            phone_number="+919595903456",
        )
        partner_meta_data = PartnerMetaDataDetails(is_maglo_free_trial_enabled=True)
        partner_details = PartnerDetails(
            id=1,
            name="Test Partner",
            company_legal_name="Test Partner",
            description="Sample Partner",
        )
        partner_data = PartnerOnboardingDetails(
            user_details=user_details,
            partner_meta_data=partner_meta_data,
            partner_details=partner_details,
        )

        self.session.flush = AsyncMock(side_effect=SQLAlchemyError("DB Error"))
        self.session.rollback = AsyncMock()

        with pytest.raises(SQLAlchemyError):
            await self.partner_repository.onboard_partner(partner_data)

        self.session.rollback.assert_awaited()
        self.mock_logger.error.assert_called_with(
            "Error while creating Partner: DB Error"
        )

    async def test_check_partner_free_trial_eligible_success(self):
        """Test eligibility when no partner or user exists."""
        # Test data
        user_details = UserDetails(
            email="test@example.com",
            password="Password@123",
            name="Test User",
            phone_number="+919595903456",
        )
        partner_meta_data = PartnerMetaDataDetails(is_maglo_free_trial_enabled=True)
        partner_details = PartnerDetails(
            id=1,
            name="Test Partner",
            company_legal_name="Test Partner",
            description="Sample Partner",
        )
        partner_data = PartnerOnboardingDetails(
            user_details=user_details,
            partner_meta_data=partner_meta_data,
            partner_details=partner_details,
        )

        # Mock partner query
        partner_scalars_mock = MagicMock()
        partner_scalars_mock.first.return_value = None

        partner_execute_mock = MagicMock()
        partner_execute_mock.scalars.return_value = partner_scalars_mock

        # Mock user query
        user_scalars_mock = MagicMock()
        user_scalars_mock.first.return_value = None

        user_execute_mock = MagicMock()
        user_execute_mock.scalars.return_value = user_scalars_mock

        # Patch session.execute to return partner first, then user
        self.session.execute = AsyncMock(
            side_effect=[partner_execute_mock, user_execute_mock]
        )

        # Run
        result = await self.partner_repository.check_partner_free_trial_eligible(
            partner_data
        )

        # Assert
        assert result is True
        self.mock_logger.info.assert_called_with(
            "Checking partner and user are eligable"
        )

    async def test_check_partner_free_trial_partner_exists(self):
        """Test eligibility fails when partner already exists."""
        # Test data
        user_details = UserDetails(
            email="test@example.com",
            password="Password@123",
            name="Test User",
            phone_number="+919595903456",
        )
        partner_meta_data = PartnerMetaDataDetails(is_maglo_free_trial_enabled=True)
        partner_details = PartnerDetails(
            id=1,
            name="Test Partner",
            company_legal_name="Test Partner",
            description="Sample Partner",
        )
        partner_data = PartnerOnboardingDetails(
            user_details=user_details,
            partner_meta_data=partner_meta_data,
            partner_details=partner_details,
        )

        # Correct mock setup
        partner_result_mock = MagicMock()
        partner_result_mock.scalars.return_value.first.return_value = Partner(
            id=1, name="Tech Solutions"
        )

        self.session.execute = AsyncMock(return_value=partner_result_mock)

        with pytest.raises(PartnerException) as exc_info:
            await self.partner_repository.check_partner_free_trial_eligible(
                partner_data
            )

        assert "Partner already exists" in str(
            exc_info.value
        ) or TrialPartnerExceptionMessage.PARTNER_EXISTS in str(exc_info.value)
        self.mock_logger.error.assert_called()

    async def test_toggle_partner_activation_success(self):
        """Test toggling partner activation successfully updates status and returns users."""
        partner_id = 1
        partner_data = MagicMock(is_active=False)
        partner_data.dict.return_value = {"is_active": False}
        mock_partner = MagicMock(id=partner_id, is_active=True)
        mock_users = [MagicMock(id=101), MagicMock(id=102)]

        # Mock partner query
        partner_scalars = MagicMock()
        partner_scalars.first.return_value = mock_partner
        partner_execute = MagicMock()
        partner_execute.scalars.return_value = partner_scalars

        # Mock users query
        users_scalars = MagicMock()
        users_scalars.all.return_value = mock_users
        users_execute = MagicMock()
        users_execute.scalars.return_value = users_scalars

        # Patch session.execute to return partner, then users
        self.session.execute = AsyncMock(side_effect=[partner_execute, users_execute])
        self.session.commit = AsyncMock()
        self.session.refresh = AsyncMock()

        # Act
        result_is_active, result_users = (
            await self.partner_repository.toggle_partner_activation(
                partner_id=partner_id, partner_data=partner_data
            )
        )

        # Assert
        assert result_is_active == partner_data.is_active
        assert result_users == [{"id": 101}, {"id": 102}]
        self.session.commit.assert_awaited_once()
        self.session.refresh.assert_awaited_once_with(mock_partner)
        self.mock_logger.info.assert_any_call(
            "Updating the partner active status to: {}".format(partner_data.is_active)
        )

    async def test_toggle_partner_activation_partner_not_found(self):
        """Test toggling activation when partner does not exist raises error."""
        partner_id = 999
        partner_data = MagicMock(is_active=True)
        partner_data.dict.return_value = {"is_active": True}

        # Partner query returns None
        partner_scalars = MagicMock()
        partner_scalars.first.return_value = None
        partner_execute = MagicMock()
        partner_execute.scalars.return_value = partner_scalars

        self.session.execute = AsyncMock(return_value=partner_execute)

        with pytest.raises(PartnerNotFoundError):
            await self.partner_repository.toggle_partner_activation(
                partner_id=partner_id, partner_data=partner_data
            )

        self.mock_logger.error.assert_any_call(
            "Partner not found with id: {}".format(partner_id)
        )
        self.mock_logger.error.assert_any_call(
            "Partner not found error occured while updating the active status of partner id: {}".format(
                partner_id
            )
        )

    async def test_toggle_partner_activation_generic_exception(self):
        """Test toggling activation raises generic exception and logs error."""
        partner_id = 1
        partner_data = MagicMock(is_active=True)
        partner_data.dict.return_value = {"is_active": True}

        # Simulate unexpected error on session.execute
        self.session.execute = AsyncMock(side_effect=Exception("DB error"))

        with pytest.raises(Exception) as exc_info:
            await self.partner_repository.toggle_partner_activation(
                partner_id=partner_id, partner_data=partner_data
            )

        assert "DB error" in str(exc_info.value)
        self.mock_logger.error.assert_any_call(
            "An unexpected error occured while updating the active status of partner id: {}".format(
                partner_id
            )
        )
