from uuid import UUID
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy.exc import IntegrityError

from src.components.partner.models import Partner
from src.components.partner_address.error import AddressNotFoundError
from src.components.partner_address.models import PartnerAddress
from src.components.partner_address.repositories import AddressRepository
from src.components.partner_address.schema import AddressType, Contrasts


@pytest.mark.asyncio
class TestAddressRepository:

    @pytest.fixture(autouse=True)
    def setup_class(self, mock_session_factory, mock_logger):
        """Set up the address repository using fixtures for mock session and logger."""
        self.address_repository = AddressRepository(
            session_factory=mock_session_factory, console_service_logger=mock_logger
        )
        self.session = mock_session_factory.return_value.__aenter__.return_value
        self.mock_logger = mock_logger

        self.session.commit = AsyncMock()
        self.session.refresh = AsyncMock()
        self.session.add = MagicMock()

        # Mock PartnerAddress object (this can be reused in multiple tests)
        self.mock_partner_address = MagicMock(spec=PartnerAddress)
        self.mock_partner_address.id = 1
        self.mock_partner_address.partner_id= UUID("11111111-1111-1111-1111-111111111111")
        self.mock_partner_address.address_1 = "123 Tech Lane"
        self.mock_partner_address.address_2 = "Suite 100"
        self.mock_partner_address.city = "Tech City"
        self.mock_partner_address.state = "Tech State"
        self.mock_partner_address.country = "Tech Country"
        self.mock_partner_address.pincode = "123456"
        self.mock_partner_address.address_type = "Business"

    async def test_get_all_partner_address(self):
        """Test getting all partner addresses."""

        # Mocking the result of session.execute() call and scalars().all() to return a list with one mock partner address
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = [
            self.mock_partner_address
        ]  # Returning a list with one mock partner address

        mock_execute = MagicMock()
        mock_execute.scalars.return_value = mock_scalars  # Return the mocked scalars

        # Mock session.execute() to return the mock execute result
        self.session.execute = AsyncMock(return_value=mock_execute)

        # Call the method being tested
        result = await self.address_repository.get_all()

        # Asserting that the result is a list
        assert isinstance(result, list)

        # Asserting that the returned list contains the mock partner address and that the attributes match
        assert len(result) == 1
        assert result[0].address_1 == "123 Tech Lane"
        assert result[0].address_2 == "Suite 100"

        # Verify session.execute was called correctly
        self.session.execute.assert_called_once()

        # Verify that the logger logged the success message for fetching all partner addresses
        self.mock_logger.info.assert_any_call(
            "Fetching all the addresses from the database"
        )

    async def test_get_by_id_address_not_found(self):
        """Test getting address by ID when not found."""
        # Mock session to return None (address not found)
        self.session.get = AsyncMock(return_value=None)

        # Call get_by_id method and assert it raises AddressNotFoundError
        with pytest.raises(AddressNotFoundError):
            await self.address_repository.get_by_id("non_existing_id")

        # Ensure the error is logged correctly
        self.mock_logger.error.assert_called_with(
            "Partner address not found, id: non_existing_id"
        )

    async def test_get_by_id_success(self):
        """Test getting address by ID successfully."""
        # Mock session to return a valid address
        mock_address = PartnerAddress(
            address_1="123 Tech Street",
            address_type="Billing",
            city="TechCity",
            state="TechState",
            country="Techland",
            pincode="123456",
            partner_id= UUID("11111111-1111-1111-1111-111111111111"),
        )
        self.session.get = AsyncMock(return_value=mock_address)

        # Call get_by_id method
        address = await self.address_repository.get_by_id("existing_id")

        # Assert that the address was returned
        assert address.address_1 == "123 Tech Street"
        self.mock_logger.info.assert_called_with("getting address with id existing_id")

    async def test_delete_by_id_address_not_found(self):
        """Test deleting an address by ID when not found."""
        # Mock session to return None (address not found)
        self.session.get = AsyncMock(return_value=None)

        # Call delete_by_id method and assert it raises AddressNotFoundError
        with pytest.raises(AddressNotFoundError):
            await self.address_repository.delete_by_id("non_existing_id")

        # Ensure the error is logged correctly
        self.mock_logger.error.assert_called_with(
            "Partner address not found, id: non_existing_id"
        )

    async def test_delete_by_id_success(self):
        """Test deleting an address by ID successfully."""
        # Mock session to return a valid address
        mock_address = PartnerAddress(
            address_1="123 Tech Street",
            address_type="Billing",
            city="TechCity",
            state="TechState",
            country="Techland",
            pincode="123456",
            partner_id= UUID("11111111-1111-1111-1111-111111111111"),
        )
        self.session.get = AsyncMock(return_value=mock_address)
        self.session.delete = AsyncMock()
        self.session.commit = AsyncMock()

        # Call delete_by_id method
        await self.address_repository.delete_by_id("existing_id")

        # Ensure the address was deleted
        self.session.delete.assert_called_with(mock_address)
        self.mock_logger.info.assert_called_with(
            "Address deleted succsessfully, id: existing_id"
        )

    async def test_partner_exists(self):
        """Test checking if a partner exists and is active."""

        partner_id= UUID("11111111-1111-1111-1111-111111111111")
        # Mock Partner object
        mock_partner = MagicMock(spec=Partner)
        mock_partner.id = partner_id
        mock_partner.is_active = True

        # Mocking the result of the session.execute() call and its scalars().first() method
        mock_scalars = MagicMock()
        mock_scalars.first.return_value = mock_partner  # Return the mock partner

        mock_execute = MagicMock()
        mock_execute.scalars.return_value = mock_scalars  # Return the mocked scalars

        # Mock session.execute() to return the mock execute result
        self.session.execute = AsyncMock(return_value=mock_execute)

        # Call the method being tested
        result = await self.address_repository.partner_exists(partner_id)

        # Asserting that the result is True (partner exists and is active)
        assert result is True

        # Verify session.execute was called correctly
        self.session.execute.assert_called_once()

        # Verify that the logger logged the success message
        self.mock_logger.info.assert_any_call(
            f"Checking existence of partner with id {partner_id}"
        )

    async def test_get_all_partner_address_generic_exception(self):
        """Test getting all partner addresses with an exception raised during database query."""

        # Mocking the result of session.execute() to raise an exception (simulating a DB error)
        self.session.execute = AsyncMock(side_effect=Exception("Database error"))

        # Call the method being tested and expect it to raise an exception
        with pytest.raises(Exception, match="Database error"):
            await self.address_repository.get_all()

        # Verify that the logger logs the error with the exception message
        self.mock_logger.error.assert_any_call("unexpected error Database error")

        # Verify that session.execute was called at least once
        self.session.execute.assert_called_once()

    async def test_get_by_id_generic_exception(self):
        """Test getting address by ID with an exception raised during session.get() call."""

        # Mock session.get() to raise an exception (simulating an error)
        self.session.get = AsyncMock(side_effect=Exception("Database error"))

        # Call get_by_id method and expect it to raise an exception
        with pytest.raises(Exception, match="Database error"):
            await self.address_repository.get_by_id("existing_id")

        # Verify that the logger logs the error with the exception message
        self.mock_logger.error.assert_any_call("unexpected error Database error")

        # Verify that session.get() was called once
        self.session.get.assert_called_once_with(PartnerAddress, "existing_id")

    async def test_delete_by_id_handles_exception(self):
        """Test deleting an address by ID with an exception raised during delete or commit."""

        # Mock session.get() to return a valid address
        mock_address = PartnerAddress(
            address_1="123 Tech Street",
            address_type="Billing",
            city="TechCity",
            state="TechState",
            country="Techland",
            pincode="123456",
            partner_id= UUID("11111111-1111-1111-1111-111111111111"),
        )
        self.session.get = AsyncMock(return_value=mock_address)

        # Mock session.delete() and session.commit() to raise an exception
        self.session.delete = AsyncMock()
        self.session.commit = AsyncMock(side_effect=Exception("Database error"))

        # Call delete_by_id method and expect it to raise an exception due to commit error
        with pytest.raises(Exception, match="Database error"):
            await self.address_repository.delete_by_id("existing_id")

        # Verify that session.delete() was called with the mock address
        self.session.delete.assert_called_once_with(mock_address)

        # Verify that session.commit() was called
        self.session.commit.assert_called_once()

        # Verify that the logger logs the error with the exception message
        self.mock_logger.error.assert_any_call("unexpected error Database error")

    async def test_partner_exists_handles_exception(self):
        """Test checking if a partner exists and is active with exception handling."""

        partner_id= UUID("11111111-1111-1111-1111-111111111111")
        # Mock Partner object
        mock_partner = MagicMock(spec=Partner)
        mock_partner.id = partner_id
        mock_partner.is_active = True

        # Mock the result of session.execute() call to raise an exception
        mock_execute = MagicMock()
        mock_execute.scalars.return_value.first.side_effect = Exception(
            "Database error"
        )

        self.session.execute = AsyncMock(return_value=mock_execute)

        # Call the partner_exists method and expect an exception to be raised
        with pytest.raises(Exception, match="Database error"):
            await self.address_repository.partner_exists(partner_id)

        # Verify that session.execute() was called
        self.session.execute.assert_called_once()

        # Verify that the logger logs the error with the exception message
        self.mock_logger.error.assert_any_call("unexpected error Database error")

    async def test_get_partner_address_by_partner_id_success(self):
        partner_id= UUID("10101010-1010-1010-1010-101010101010")
        partner_mock = MagicMock()
        result_mock = MagicMock()
        # Mock .scalars().all() to return a non-empty list
        result_mock.scalars.return_value.all.return_value = [partner_mock]
        self.session.execute = AsyncMock(return_value=result_mock)

        result = await self.address_repository.get_partner_address_by_partner_id(
            partner_id
        )

        assert result == [partner_mock]

    async def test_upsert_address_same_update_existing(self):
        update_data = MagicMock()
        update_data.is_address_same = True
        update_data.billing_address.model_dump.return_value = {
            "address_1": "New Lane",
            "city": "New City",
        }
        update_data.communication_address = None

        self.mock_partner_address.address_type = AddressType.COMMUNICATION_AND_BILLING
        self.session.execute = AsyncMock(
            return_value=MagicMock(
                scalars=MagicMock(
                    return_value=MagicMock(
                        all=MagicMock(return_value=[self.mock_partner_address])
                    )
                )
            )
        )

        result = await self.address_repository.upsert_partner_address(
            partner_id= UUID("11111111-1111-1111-1111-111111111111"), user_id= UUID("10101010-1010-1010-1010-101010101010"), update_data=update_data
        )

        assert len(result) == 1
        assert result[0] == self.mock_partner_address
        self.session.commit.assert_awaited_once()
        self.session.refresh.assert_awaited_once_with(self.mock_partner_address)

    async def test_upsert_address_same_create_new(self):
        update_data = MagicMock()
        update_data.is_address_same = True
        update_data.billing_address.model_dump.return_value = {
            "address_1": "New Lane",
            "city": "New City",
        }
        update_data.communication_address = None

        self.session.execute = AsyncMock(
            return_value=MagicMock(
                scalars=MagicMock(
                    return_value=MagicMock(all=MagicMock(return_value=[]))
                )
            )
        )

        result = await self.address_repository.upsert_partner_address(
            partner_id= UUID("11111111-1111-1111-1111-111111111111"), user_id= UUID("10101010-1010-1010-1010-101010101010"), update_data=update_data
        )

        assert len(result) == 1
        self.session.add.assert_called_once()
        self.session.commit.assert_awaited_once()
        self.session.refresh.assert_awaited_once()

    async def test_upsert_address_separate_update_both(self):
        update_data = MagicMock()
        update_data.is_address_same = False
        update_data.billing_address.model_dump.return_value = {"city": "Billing City"}
        update_data.communication_address.model_dump.return_value = {
            "city": "Comm City"
        }

        billing_address = MagicMock(spec=PartnerAddress)
        billing_address.address_type = AddressType.BILLING

        communication_address = MagicMock(spec=PartnerAddress)
        communication_address.address_type = AddressType.COMMUNICATION

        self.session.execute = AsyncMock(
            return_value=MagicMock(
                scalars=MagicMock(
                    return_value=MagicMock(
                        all=MagicMock(
                            return_value=[billing_address, communication_address]
                        )
                    )
                )
            )
        )

        result = await self.address_repository.upsert_partner_address(
            partner_id= UUID("11111111-1111-1111-1111-111111111111"), user_id= UUID("10101010-1010-1010-1010-101010101010"), update_data=update_data
        )

        assert len(result) == 2
        assert billing_address in result and communication_address in result
        self.session.commit.assert_awaited_once()

    async def test_upsert_address_separate_create_both(self):
        update_data = MagicMock()
        update_data.is_address_same = False
        update_data.billing_address.model_dump.return_value = {"city": "Billing City"}
        update_data.communication_address.model_dump.return_value = {
            "city": "Comm City"
        }

        self.session.execute = AsyncMock(
            return_value=MagicMock(
                scalars=MagicMock(
                    return_value=MagicMock(all=MagicMock(return_value=[]))
                )
            )
        )

        result = await self.address_repository.upsert_partner_address(
            partner_id= UUID("11111111-1111-1111-1111-111111111111"), user_id= UUID("10101010-1010-1010-1010-101010101010"), update_data=update_data
        )

        assert len(result) == 2
        assert self.session.add.call_count == 2
        self.session.commit.assert_awaited_once()

    async def test_upsert_address_separate_delete_combined(self):
        update_data = MagicMock()
        update_data.is_address_same = False
        update_data.billing_address.model_dump.return_value = {"city": "Billing City"}
        update_data.communication_address.model_dump.return_value = {
            "city": "Comm City"
        }

        combined_address = MagicMock(spec=PartnerAddress)
        combined_address.address_type = AddressType.COMMUNICATION_AND_BILLING

        self.session.execute = AsyncMock(
            return_value=MagicMock(
                scalars=MagicMock(
                    return_value=MagicMock(
                        all=MagicMock(return_value=[combined_address])
                    )
                )
            )
        )

        await self.address_repository.upsert_partner_address(
            partner_id= UUID("11111111-1111-1111-1111-111111111111"), user_id= UUID("10101010-1010-1010-1010-101010101010"), update_data=update_data
        )

        self.session.delete.assert_any_call(combined_address)

    async def test_upsert_partner_address_raises_exception(self):
        update_data = MagicMock()
        update_data.is_address_same = True
        update_data.billing_address.model_dump.side_effect = Exception(
            "Unexpected Error"
        )

        self.session.execute = AsyncMock(
            return_value=MagicMock(
                scalars=MagicMock(
                    return_value=MagicMock(all=MagicMock(return_value=[]))
                )
            )
        )

        with pytest.raises(Exception) as exc_info:
            await self.address_repository.upsert_partner_address(
                partner_id= UUID("11111111-1111-1111-1111-111111111111"), user_id= UUID("10101010-1010-1010-1010-101010101010"), update_data=update_data
            )

        assert "Unexpected Error" in str(exc_info.value)
        self.mock_logger.error.assert_any_call(
            "An error occurred while upserting partner address for partner id {}: {}".format(
                UUID("11111111-1111-1111-1111-111111111111"), "Unexpected Error"
            )
        )
