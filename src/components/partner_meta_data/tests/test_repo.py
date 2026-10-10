from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from src.components.partner.models import Partner
from src.components.partner_meta_data.error import PartnerMetaDataNotFoundError
from src.components.partner_meta_data.models import PartnerMetaData
from src.components.partner_meta_data.repositories import PartnerMetaDataRepository
from src.components.partner_meta_data.schema import (
    PartnerMetadata,
    UpdatePartnerMetaData,
)
from src.exceptions import PartnerMetaDataException


@pytest.mark.asyncio
class TestPartnerMetaDataRepository:

    @pytest.fixture(autouse=True)
    def setup_class(self, mock_session_factory, mock_logger):
        """Set up partner_metadata_repository_mock with mocked session and logger."""
        self.partner_metadata_repository_mock = PartnerMetaDataRepository(
            session_factory=mock_session_factory, console_service_logger=mock_logger
        )
        self.session = mock_session_factory.return_value.__aenter__.return_value
        self.mock_logger = mock_logger

        # Test data
        self.partner_metadata = PartnerMetaData(
            id=1,
            partner_id=1,
            api_key="5f715b8f-3ae7-4fce-a685-cc0f766359a5",
            timezone="UTC",
            number_of_users=30,
        )

        self.partner_metadata_instance = PartnerMetadata(
            partner_id=123,
            timezone="UTC",
            number_of_users=50,
        )

        self.partner_update_data = UpdatePartnerMetaData(
            timezone="PST",
            number_of_users=100,
        )

    async def test_get_partner_metadata_by_id(self):
        """Test getting a partner metadata by ID."""
        partner_id = 1

        # Mock the database execution and response
        mock_scalars = MagicMock()
        mock_scalars.one_or_none.return_value = self.partner_metadata
        mock_execute = MagicMock()
        mock_execute.scalars.return_value = mock_scalars
        self.session.execute = AsyncMock(return_value=mock_execute)

        # Call the method
        result = await self.partner_metadata_repository_mock.get_partner_meta_data_by_partner_id(
            partner_id
        )

        # Assert the results
        assert result == self.partner_metadata

    async def test_add_partner_metadata_repository_already_exists(self):
        """Test adding partner metadata when metadata already exists."""
        partner_id = 1

        # Simulate existing partner metadata by setting return value for is_partner_meta_data_exists
        self.partner_metadata_repository_mock.is_partner_meta_data_exists = AsyncMock(
            return_value=True
        )

        with pytest.raises(PartnerMetaDataException) as exc:
            await self.partner_metadata_repository_mock.add_partner_metadata_repository(
                partner_id, self.partner_metadata_instance
            )

        assert (
            str(exc.value)
            == "Meta data for partner id: 1 is already exists, you can update it if needed."
        )

    async def test_get_all_partner_meta_data(self):
        """Test fetching all partner metadata."""
        # Mock database execution and response
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = [self.partner_metadata]
        mock_execute = MagicMock()
        mock_execute.scalars.return_value = mock_scalars
        self.session.execute = AsyncMock(return_value=mock_execute)

        # Call the method
        result = await self.partner_metadata_repository_mock.get_all_partner_meta_data()

        # Assert the results
        assert len(result) == 1
        assert result[0].id == self.partner_metadata.id
        self.mock_logger.info.assert_called_with(
            "Successfully fetched all partner metadata: {}".format(result)
        )

    async def test_add_partner_metadata_repository(self):
        """Test adding new partner metadata."""
        partner_id = 1

        # Mock is_partner_meta_data_exists to return False
        with patch.object(
            self.partner_metadata_repository_mock,
            "is_partner_meta_data_exists",
            AsyncMock(return_value=False),
        ):
            # Mock the session methods
            self.session.add = AsyncMock()
            self.session.commit = AsyncMock()
            self.session.refresh = AsyncMock()
            # Call the method
            result = await self.partner_metadata_repository_mock.add_partner_metadata_repository(
                partner_id, self.partner_metadata_instance
            )

            # Assert the results
            assert result.partner_id == partner_id
            self.session.add.assert_called_once()
            self.session.commit.assert_called_once()
            self.mock_logger.info.assert_any_call(
                "Successfully insert partner metadata for partner id: {}".format(
                    partner_id
                )
            )

    async def test_update_partner_meta_data(self):
        """Test updating an existing partner metadata."""
        partner_id = 1
        update_data = UpdatePartnerMetaData(timezone="PST", number_of_users=100)

        # Mock the database execution and response
        mock_scalars = MagicMock()
        mock_scalars.one_or_none.return_value = self.partner_metadata
        mock_execute = MagicMock()
        mock_execute.scalars.return_value = mock_scalars
        self.session.execute = AsyncMock(return_value=mock_execute)
        self.session.commit = AsyncMock()
        self.session.refresh = AsyncMock()

        # Call the method
        result = await self.partner_metadata_repository_mock.update_partner_meta_data(
            partner_id, update_data
        )

        # Assert the results
        assert result.number_of_users == 30
        self.session.commit.assert_called_once()

    async def test_update_partner_meta_data_not_found(self):
        """Test updating non-existent partner metadata."""
        partner_id = 999
        update_data = UpdatePartnerMetaData(timezone="PST")

        # Mock the session to simulate no existing record
        mock_scalars = MagicMock()
        mock_scalars.one_or_none.return_value = None
        self.session.execute.return_value.scalars.return_value = mock_scalars

        # Call the update method and assert it raises the expected error
        with pytest.raises(PartnerMetaDataNotFoundError) as exc:
            await self.partner_metadata_repository_mock.update_partner_meta_data(
                partner_id, update_data
            )

        assert str(exc.value) == "Partner Meta Data not found, id: 999"

    async def test_is_partner_exists(self):
        """Test checking if a partner exists with the given partner ID."""
        partner_id = 1

        # Mock the database response to simulate that a partner exists
        mock_scalars = MagicMock()
        mock_scalars.first.return_value = Partner(id=partner_id, is_active=True)
        mock_execute = MagicMock()
        mock_execute.scalars.return_value = mock_scalars
        self.session.execute = AsyncMock(return_value=mock_execute)

        # Call the method
        result = await self.partner_metadata_repository_mock.is_partner_exists(
            partner_id
        )

        # Assert that the partner was found
        assert result is True
        self.mock_logger.info.assert_called_with(
            "Checking existence of partner with id {}".format(partner_id)
        )

    async def test_is_partner_exists_not_found(self):
        """Test checking if a partner does not exist with the given partner ID."""
        partner_id = 999

        # Mock the database response to simulate that no partner was found
        mock_scalars = MagicMock()
        mock_scalars.first.return_value = None
        mock_execute = MagicMock()
        mock_execute.scalars.return_value = mock_scalars
        self.session.execute = AsyncMock(return_value=mock_execute)

        # Call the method
        result = await self.partner_metadata_repository_mock.is_partner_exists(
            partner_id
        )

        # Assert that the partner was not found
        assert result is False
        self.mock_logger.info.assert_called_with(
            "Checking existence of partner with id {}".format(partner_id)
        )

    async def test_is_partner_exists_database_error(self):
        """Test handling of a database error during partner existence check."""
        partner_id = 1

        # Simulate a SQLAlchemyError when executing the query
        self.session.execute = AsyncMock(side_effect=SQLAlchemyError("Database error"))

        # Call the method and assert that the exception is raised
        with pytest.raises(SQLAlchemyError) as exc:
            await self.partner_metadata_repository_mock.is_partner_exists(partner_id)

        assert str(exc.value) == "Database error"
        self.mock_logger.error.assert_called_with(
            "Database error while fetching partner, id: {}".format(partner_id)
        )

    async def test_is_partner_meta_data_exists_found(self):
        """Test case where partner metadata exists for the given partner ID."""
        partner_id = 1

        # Mock the database response to simulate that partner metadata exists
        mock_scalars = MagicMock()
        mock_scalars.first.return_value = Partner(id=partner_id, is_active=True)
        mock_execute = MagicMock()
        mock_execute.scalars.return_value = mock_scalars
        self.session.execute = AsyncMock(return_value=mock_execute)

        # Call the method
        result = (
            await self.partner_metadata_repository_mock.is_partner_meta_data_exists(
                self.session, partner_id
            )
        )

        # Assert the result is True (metadata exists)
        assert result is True
        self.mock_logger.info.assert_called_with(
            "Checking if partner meta data already exists or not, partner id: {}".format(
                partner_id
            )
        )

    async def test_add_partner_metadata_repository_integrity_error(self):
        """Test handling of a database integrity error during partner metadata addition."""
        partner_id = 1

        # Mock IntegrityError with required arguments
        mock_statement = "INSERT INTO partner_meta_data (...) VALUES (...)"
        mock_params = {"partner_id": partner_id}
        mock_orig = Exception("Mocked DB integrity constraint violation")

        self.session.execute = AsyncMock(
            side_effect=IntegrityError(mock_statement, mock_params, mock_orig)
        )

        # Call the method and assert that PartnerMetaDataException is raised
        with pytest.raises(PartnerMetaDataException):
            await self.partner_metadata_repository_mock.add_partner_metadata_repository(
                partner_id, self.partner_metadata_instance
            )

    async def test_add_partner_metadata_repository_generic_exception(self):
        partner_id = 1
        # Mock generic Exception
        self.session.execute = AsyncMock(side_effect=Exception("Unexpected Error"))

        with pytest.raises(Exception) as exc_info:
            await self.partner_metadata_repository_mock.add_partner_metadata_repository(
                partner_id, self.partner_metadata_instance
            )

        assert str(exc_info.value) == "Unexpected Error"

    async def test_get_all_partner_meta_data_generic_exception(self):
        # Mock generic Exception
        self.session.execute = AsyncMock(side_effect=Exception("Unexpected Error"))

        with pytest.raises(Exception) as exc_info:
            await self.partner_metadata_repository_mock.get_all_partner_meta_data()

        assert str(exc_info.value) == "Unexpected Error"

    async def test_get_by_partner_id_not_found(self):
        """Test case when partner metadata is not found, expecting PartnerMetaDataNotFoundError."""
        partner_id = 999

        self.partner_metadata_repository_mock.get_by_partner_id = AsyncMock(
            side_effect=PartnerMetaDataNotFoundError(1)
        )

        with pytest.raises(PartnerMetaDataNotFoundError) as exc:
            await self.partner_metadata_repository_mock.get_by_partner_id(partner_id)

        assert str(exc.value) == "Partner Meta Data not found, id: 1"

    async def test_get_by_partner_id_meta_data_generic_exception(self):
        # Mock generic Exception
        self.session.execute = AsyncMock(side_effect=Exception("Unexpected Error"))

        with pytest.raises(Exception) as exc_info:
            await self.partner_metadata_repository_mock.get_partner_meta_data_by_partner_id(
                1
            )

        assert str(exc_info.value) == "Unexpected Error"

    async def test_update_partner_meta_data_generic_exception(self):
        # Mock generic Exception
        self.session.execute = AsyncMock(side_effect=Exception("Unexpected Error"))

        with pytest.raises(Exception) as exc_info:
            await self.partner_metadata_repository_mock.update_partner_meta_data(
                1, self.partner_update_data
            )

        assert str(exc_info.value) == "Unexpected Error"

    async def test_update_partner_meta_data_generic_exception(self):
        # Mock generic Exception
        self.session.execute = AsyncMock(side_effect=Exception("Unexpected Error"))

        with pytest.raises(Exception) as exc_info:
            await self.partner_metadata_repository_mock.update_partner_meta_data(
                1, self.partner_update_data
            )

        assert str(exc_info.value) == "Unexpected Error"

    # New tests for get_partner_meta_data_by_partner_ids
    async def test_get_partner_meta_data_by_partner_ids_success_multiple(self):
        """Test fetching multiple partner metadata by partner_ids (multiple results)."""
        partner_ids = [1, 2]
        partner_meta_1 = self.partner_metadata
        partner_meta_2 = PartnerMetaData(
            id=2, partner_id=2, api_key="key2", timezone="UTC", number_of_users=10
        )

        mock_scalars = MagicMock()
        mock_scalars.all.return_value = [partner_meta_1, partner_meta_2]
        mock_execute = MagicMock()
        mock_execute.scalars.return_value = mock_scalars
        self.session.execute = AsyncMock(return_value=mock_execute)

        result = await self.partner_metadata_repository_mock.get_partner_meta_data_by_partner_ids(
            partner_ids
        )

        assert result == [partner_meta_1, partner_meta_2]
        self.mock_logger.info.assert_any_call(
            "Attempting to get partner metadata by partner_ids {}".format(partner_ids)
        )
        self.mock_logger.info.assert_any_call(
            "Successfully fetched partner metadata by partner_ids {} {}".format(
                partner_ids, result
            )
        )

    async def test_get_partner_meta_data_by_partner_ids_empty_list(self):
        """Test calling with empty partner_ids list returns empty list."""
        partner_ids: list[int] = []

        mock_scalars = MagicMock()
        mock_scalars.all.return_value = []
        mock_execute = MagicMock()
        mock_execute.scalars.return_value = mock_scalars
        self.session.execute = AsyncMock(return_value=mock_execute)

        result = await self.partner_metadata_repository_mock.get_partner_meta_data_by_partner_ids(
            partner_ids
        )

        assert result == []
        self.mock_logger.info.assert_any_call(
            "Attempting to get partner metadata by partner_ids {}".format(partner_ids)
        )
        self.mock_logger.info.assert_any_call(
            "Successfully fetched partner metadata by partner_ids {} {}".format(
                partner_ids, result
            )
        )

    async def test_get_partner_meta_data_by_partner_ids_none_found(self):
        """Test when partner_ids provided but no metadata found (empty result)."""
        partner_ids = [999]

        mock_scalars = MagicMock()
        mock_scalars.all.return_value = []
        mock_execute = MagicMock()
        mock_execute.scalars.return_value = mock_scalars
        self.session.execute = AsyncMock(return_value=mock_execute)

        result = await self.partner_metadata_repository_mock.get_partner_meta_data_by_partner_ids(
            partner_ids
        )

        assert result == []
        self.mock_logger.info.assert_any_call(
            "Attempting to get partner metadata by partner_ids {}".format(partner_ids)
        )
        self.mock_logger.info.assert_any_call(
            "Successfully fetched partner metadata by partner_ids {} {}".format(
                partner_ids, result
            )
        )

    async def test_get_partner_meta_data_by_partner_ids_partial_found(self):
        """Test when some partner_ids have metadata and some do not."""
        partner_ids = [1, 999]
        partner_meta_1 = self.partner_metadata

        mock_scalars = MagicMock()
        mock_scalars.all.return_value = [partner_meta_1]
        mock_execute = MagicMock()
        mock_execute.scalars.return_value = mock_scalars
        self.session.execute = AsyncMock(return_value=mock_execute)

        result = await self.partner_metadata_repository_mock.get_partner_meta_data_by_partner_ids(
            partner_ids
        )

        assert result == [partner_meta_1]
        self.mock_logger.info.assert_any_call(
            "Attempting to get partner metadata by partner_ids {}".format(partner_ids)
        )
        self.mock_logger.info.assert_any_call(
            "Successfully fetched partner metadata by partner_ids {} {}".format(
                partner_ids, result
            )
        )

    async def test_get_partner_meta_data_by_partner_ids_exception(self):
        """Test that exceptions during DB execution are logged and re-raised."""
        partner_ids = [1, 2]

        self.session.execute = AsyncMock(side_effect=Exception("DB Error"))

        with pytest.raises(Exception) as exc:
            await self.partner_metadata_repository_mock.get_partner_meta_data_by_partner_ids(
                partner_ids
            )

        assert str(exc.value) == "DB Error"
        self.mock_logger.error.assert_called_with(
            "Error occurred while get partner metadata by partner_ids {}".format(
                exc.value
            )
        )
