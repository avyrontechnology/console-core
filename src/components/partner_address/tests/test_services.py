from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.components.cache.helper import CacheHelper
from src.components.partner_address.error import AddressNotFoundError
from src.components.partner_address.models import PartnerAddress
from src.components.partner_address.schema import (
    Contrasts,
    UpdatePartnerAddressRequest,
    UpsertPartnerAddressResponse,
)
from src.components.partner_address.services import PartnerAddressService
from src.exceptions import PartnerException


@pytest.mark.asyncio
class TestPartnerAddressService:

    @pytest.fixture(autouse=True)
    def setup_class(self, mock_logger):
        self.mock_logger = mock_logger
        self.address_repository_mock = AsyncMock()
        self.audit_service_mock = AsyncMock()
        self.partner_address_service_cache = AsyncMock(spec=CacheHelper)

        # Initializing the PartnerAddressService with mocks
        self.partner_address_service = PartnerAddressService(
            address_repository=self.address_repository_mock,
            audit_service=self.audit_service_mock,
            console_service_logger=self.mock_logger,
            partner_address_service_cache=self.partner_address_service_cache,
        )

        # Test Data
        self.mock_address = PartnerAddress(
            address_1="123 Tech Lane",
            address_2="Suite 100",
            city="TechCity",
            state="TechState",
            country="Techland",
            pincode="123456",
            partner_id=1,
        )

        self.address_data = Contrasts.AddressData(
            address_1="123 Tech Lane",
            address_2="Suite 100",
            address_type="Billing",
            city="TechCity",
            state="TechState",
            country="Techland",
            pincode="123456",
            partner_id=1,
            is_address_same=True,
        )

    async def test_partner_exists_success(self):
        """Test checking if a partner exists and is active."""

        partner_id = 1
        # Mock repository's partner_exists method to return True
        self.address_repository_mock.partner_exists.return_value = True

        # Call the partner_exists method
        result = await self.partner_address_service.partner_exists(partner_id)

        # Assert that partner exists and is active
        assert result is True

        # Verify session.execute was called correctly
        self.address_repository_mock.partner_exists.assert_called_once_with(partner_id)

        # Verify the logger logged the success message
        self.mock_logger.info.assert_any_call(
            f"Checking existence of partner with id {partner_id}"
        )

    async def test_partner_exists_handles_exception(self):
        """Test handling exceptions when checking if a partner exists."""

        partner_id = 1
        # Mock repository's partner_exists method to raise an exception
        self.address_repository_mock.partner_exists.side_effect = Exception(
            "Database error"
        )

        # Call the partner_exists method and expect an exception to be raised
        with pytest.raises(Exception, match="Database error"):
            await self.partner_address_service.partner_exists(partner_id)

        # Verify session.execute was called
        self.address_repository_mock.partner_exists.assert_called_once_with(partner_id)

        # Verify that the logger logs the error with the exception message
        self.mock_logger.error.assert_any_call(
            "Error checking if partner exists: Database error"
        )

    async def test_get_by_id_success(self):
        """Test retrieving an address by ID successfully."""

        address_id = 1
        # Mock the repository's get_by_id method to return a mock address
        self.address_repository_mock.get_by_id.return_value = self.mock_address
        self.address_repository_mock.partner_exists.return_value = True

        # Call get_by_id method
        result = await self.partner_address_service.get_by_id(address_id)

        # Assert the result matches the mock address
        assert result.address_1 == "123 Tech Lane"

        # Check if the success log message was generated
        self.mock_logger.info.assert_any_call(
            f"Address fetched successfully. {self.mock_address.__dict__}"
        )

    async def test_delete_by_id_success(self):
        """Test successfully deleting an address by ID."""

        address_id = 1
        # Mock the repository's delete_by_id method
        self.address_repository_mock.delete_by_id.return_value = PartnerAddress(id=1, partner_id=123, address_1="Some street")

        # Call delete_by_id method
        await self.partner_address_service.delete_by_id(address_id)

        # Ensure the address was deleted
        self.address_repository_mock.delete_by_id.assert_called_once_with(address_id)

        # Verify the success log message
        self.mock_logger.info.assert_any_call(
            f"address with id: {address_id} is now deleted from the database"
        )

        # Ensure audit log is called
        self.audit_service_mock.log_action.assert_called_once()

    async def test_delete_by_id_handles_exception(self):
        """Test exception handling during address deletion."""

        address_id = 1
        # Mock the repository's delete_by_id method to raise an exception
        self.address_repository_mock.delete_by_id.side_effect = Exception(
            "Database error"
        )

        # Call delete_by_id and expect an exception
        with pytest.raises(Exception, match="Database error"):
            await self.partner_address_service.delete_by_id(address_id)

        # Ensure the error is logged
        self.mock_logger.error.assert_any_call("error deleting partner Database error")

    async def test_get_all_partner_address(self):
        """Test getting all partner addresses."""

        # Manually define the mock partner address to see if this works
        mock_partner_address = PartnerAddress(
            address_1="123 Tech Lane",
            address_2="Suite 100",
            city="TechCity",
            state="TechState",
            country="Techland",
            pincode="123456",
            partner_id=1,
        )

        # Mock the repository method to return this address
        self.address_repository_mock.get_all.return_value = [mock_partner_address]

        # Call the service method
        result = await self.partner_address_service.get_addresses()

        # Asserting that the result is a list
        assert isinstance(result, list)

        # Asserting that the returned list contains the mock partner address and that the attributes match
        assert len(result) == 1
        assert result[0].address_1 == "123 Tech Lane"
        assert result[0].address_2 == "Suite 100"
        assert result[0].city == "TechCity"
        assert result[0].state == "TechState"
        assert result[0].country == "Techland"
        assert result[0].pincode == "123456"
        assert result[0].partner_id == 1

        # Verify that the repository's get_all method was called
        self.address_repository_mock.get_all.assert_called_once()

        # Verify that the logger logged the success message
        self.mock_logger.info.assert_called_with(
            "Fetched all addresses successfully: {}".format(result)
        )

    async def test_get_all_partner_address(self):
        """Test getting all partner addresses."""

        # Mock the repository to return a list of mock addresses
        self.address_repository_mock.get_all.return_value = [self.mock_address]

        # Call the service method
        result = await self.partner_address_service.get_addresses()

        # Asserting that the result is a list
        assert isinstance(result, list)

        # Asserting that the returned list contains the mock partner address and that the attributes match
        assert len(result) == 1
        assert result[0].address_1 == "123 Tech Lane"
        assert result[0].address_2 == "Suite 100"
        assert result[0].city == "TechCity"
        assert result[0].state == "TechState"
        assert result[0].country == "Techland"
        assert result[0].pincode == "123456"
        assert result[0].partner_id == 1

        # Verify the repository method was called
        self.address_repository_mock.get_all.assert_called_once()

        # Verify the logger logged the expected info message
        self.mock_logger.info.assert_called_with(
            "Fetched all addresses successfully: {}".format(result)
        )

    async def test_get_by_id_partner_not_active(self):
        """Test the case when the address is found but the partner is not active."""

        address_id = "123"  # The ID of the address to fetch
        # Mock the repository's get_by_id method to return a mock address
        self.address_repository_mock.get_by_id.return_value = self.mock_address

        # Mock partner_exists to return False (i.e., the partner is not active)
        self.address_repository_mock.partner_exists.return_value = False

        # Call the service method and expect an AddressNotFoundError to be raised
        with pytest.raises(AddressNotFoundError) as exc_info:
            await self.partner_address_service.get_by_id(address_id)

        # Assert the correct error message was raised (expecting default message format)
        assert str(exc_info.value) == f"Partner address not found, id: {address_id}"

        # Verify repository's get_by_id was called with the correct address ID
        self.address_repository_mock.get_by_id.assert_called_once_with(address_id)

        # Verify repository's partner_exists was called with the partner_id from the address
        self.address_repository_mock.partner_exists.assert_called_once_with(
            self.mock_address.partner_id
        )

        # Verify logger error was called for inactive partner
        self.mock_logger.error.assert_any_call(
            f"Partner address not found, id: {address_id}"
        )

    async def test_get_by_id_generic_exception(self):
        """Test that generic exceptions are handled and logged."""

        address_id = "123"  # The ID of the address to fetch

        # Mock the repository's get_by_id method to raise a generic exception
        self.address_repository_mock.get_by_id.side_effect = Exception(
            "Generic error occurred while fetching the address."
        )

        # Call the service method and expect an exception to be raised
        with pytest.raises(Exception) as exc_info:
            await self.partner_address_service.get_by_id(address_id)

        # Assert the exception is a generic Exception
        assert (
            str(exc_info.value) == "Generic error occurred while fetching the address."
        )

        # Verify that the logger logged the generic exception
        self.mock_logger.error.assert_called_with(
            "error getting partner Generic error occurred while fetching the address."
        )

    async def test_get_addresses_generic_exception(self):
        """Test handling of a generic exception when retrieving all addresses."""

        # Simulate that the repository's `get_all` method raises a generic exception
        self.address_repository_mock.get_all.side_effect = Exception(
            "Unexpected database error"
        )

        # Call the service method to retrieve addresses and expect an exception to be raised
        with pytest.raises(Exception) as exc_info:
            await self.partner_address_service.get_addresses()

        # Assert that the exception raised is a generic Exception
        assert str(exc_info.value) == "Unexpected database error"

        # Verify that the error is logged correctly
        self.mock_logger.error.assert_any_call(
            "Error retriving addresses.{}".format(str(exc_info.value))
        )

        # Verify that `get_all` was called on the repository
        self.address_repository_mock.get_all.assert_called_once()

    async def test_delete_address_not_found(self):
        """Test handling of AddressNotFoundError when deleting an address."""

        # Simulate that the repository's `delete_by_id` method raises an AddressNotFoundError
        address_id_to_delete = 123
        self.address_repository_mock.delete_by_id.side_effect = AddressNotFoundError(
            address_id_to_delete
        )

        # Call the service method to delete the address and expect an AddressNotFoundError
        with pytest.raises(AddressNotFoundError) as exc_info:
            await self.partner_address_service.delete_by_id(address_id_to_delete)

        # Assert that the exception raised is an AddressNotFoundError
        assert (
            str(exc_info.value)
            == f"Partner address not found, id: {address_id_to_delete}"
        )

        # Verify that the logger captured the correct error message
        self.mock_logger.error.assert_any_call(
            f"Partner address not found, id: {address_id_to_delete}"
        )

        # Verify that `delete_by_id` was called on the repository
        self.address_repository_mock.delete_by_id.assert_called_once_with(
            address_id_to_delete
        )

    async def test_get_partner_address_by_partner_id_success(self):
        partner_id = 1
        mock_address_list = [MagicMock()]
        mock_response = MagicMock()
        # Repository now returns a list
        self.address_repository_mock.get_partner_address_by_partner_id = AsyncMock(
            return_value=mock_address_list
        )
        # Patch model_validate to return mock_response
        with pytest.MonkeyPatch.context() as m:
            m.setattr(
                Contrasts.GetAddressByAddressIdResponse,
                "model_validate",
                MagicMock(return_value=mock_response),
            )
            await self.partner_address_service.get_partner_address_by_partner_id(
                partner_id
            )

    async def test_get_partner_address_by_partner_id_not_found(self):
        partner_id = 2
        self.address_repository_mock.get_partner_address_by_partner_id = AsyncMock(
            side_effect=AddressNotFoundError(partner_id)
        )
        with pytest.raises(AddressNotFoundError):
            await self.partner_address_service.get_partner_address_by_partner_id(
                partner_id
            )
        self.mock_logger.error.assert_any_call(
            f"Partner address not found for the partner id: {partner_id}"
        )

    async def test_get_partner_address_by_partner_id_unexpected_exception(self):
        partner_id = 3
        self.address_repository_mock.get_partner_address_by_partner_id = AsyncMock(
            side_effect=Exception("DB error")
        )
        with pytest.raises(Exception, match="DB error"):
            await self.partner_address_service.get_partner_address_by_partner_id(
                partner_id
            )
        self.mock_logger.error.assert_any_call(
            "An error occured while fetching the user: DB error"
        )

    @pytest.mark.asyncio
    async def test_upsert_partner_address_success(self):
        partner_id = 1
        user_id = 2
        update_data = MagicMock(spec=UpdatePartnerAddressRequest)
        partner_service_mock = AsyncMock()
        partner_service_mock.get_partner_by_id.return_value = MagicMock()
        upserted_address = MagicMock()
        self.partner_address_service._PartnerAddressService__repository.upsert_partner_address = AsyncMock(
            return_value=[upserted_address]
        )
        with patch.object(
            UpsertPartnerAddressResponse,
            "model_validate",
            return_value="validated_response",
        ):
            result = await self.partner_address_service.upsert_partner_address(
                partner_id, user_id, update_data, partner_service=partner_service_mock
            )
        assert result == ["validated_response"]
        self.mock_logger.info.assert_any_call(
            f"Updating addresses for partner id {partner_id}"
        )

    @pytest.mark.asyncio
    async def test_upsert_partner_address_partner_not_found(self):
        partner_id = 1
        user_id = 2
        update_data = MagicMock(spec=UpdatePartnerAddressRequest)
        partner_service_mock = AsyncMock()
        partner_service_mock.get_partner_by_id.return_value = None
        with pytest.raises(PartnerException):
            await self.partner_address_service.upsert_partner_address(
                partner_id, user_id, update_data, partner_service=partner_service_mock
            )
        self.mock_logger.error.assert_any_call(
            f"Partner not found: Partner with id {partner_id} not found"
        )

    @pytest.mark.asyncio
    async def test_upsert_partner_address_generic_exception(self):
        partner_id = 1
        user_id = 2
        update_data = MagicMock(spec=UpdatePartnerAddressRequest)
        partner_service_mock = AsyncMock()
        partner_service_mock.get_partner_by_id.return_value = MagicMock()
        self.partner_address_service._PartnerAddressService__repository.upsert_partner_address = AsyncMock(
            side_effect=Exception("unexpected error")
        )
        with pytest.raises(Exception, match="unexpected error"):
            await self.partner_address_service.upsert_partner_address(
                partner_id, user_id, update_data, partner_service=partner_service_mock
            )
        self.mock_logger.error.assert_any_call(
            "Unexpected error while updating address: unexpected error"
        )
