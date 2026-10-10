from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.components.common.datetime import DateTimeUtil
from src.components.partner.error import PartnerNotFoundError
from src.components.partner_meta_data.models import PartnerMetaData
from src.components.partner_meta_data.schema import (
    PartnerMetadata,
    PartnerMetaDataResponse,
    PartnerPlanDetailsResponse,
    UpdatePartnerMetaData,
)
from src.components.partner_meta_data.services import PartnerMetaDataServices
from src.exceptions import PartnerMetaDataException


@pytest.mark.asyncio
class TestPartnerMetaDataServices:

    @pytest.fixture(autouse=True)
    def setup_class(self):

        self.partner_meta_data_repository = AsyncMock()
        self.mock_logger = MagicMock()
        self.audit_log_mock = AsyncMock()

        self.partner_metadata_service_mock = PartnerMetaDataServices(
            partner_meta_data_repository=self.partner_meta_data_repository,
            console_service_logger=self.mock_logger,
            audit_service=self.audit_log_mock,
        )

        # Test Data

        self.new_partner_meta_data = PartnerMetadata(
            partner_id=1,
            api_key="new-api-key",
            timezone="Etc/UTC",
            number_of_users=50,
        )

        self.mock_partner_metadata = PartnerMetaDataResponse(
            id=1,
            partner_id=1,
            api_key="5f715b8f-3ae7-4fce-a685-cc0f766359a5",
            timezone="Etc/UTC",
            number_of_users=30,
        )

        self.update_data = UpdatePartnerMetaData(
            partner_id=1,
            timezone="Etc/UTC",
            number_of_users=100,
        )

    async def test_get_by_partner_id(self):
        self.partner_meta_data_repository.get_partner_meta_data_by_partner_id.return_value = (
            self.mock_partner_metadata
        )
        response = await self.partner_metadata_service_mock.get_partner_meta_data_by_partner_id(
            partner_id=1
        )
        assert response.id == 1

    async def test_get_all_partner_meta_data(self):
        self.partner_meta_data_repository.get_all_partner_meta_data.return_value = [
            self.mock_partner_metadata
        ]
        response = await self.partner_metadata_service_mock.get_all_partner_meta_data()
        assert isinstance(response, list)
        assert response[0].id == 1

    async def test_update_partner_meta_data(self):
        """Test successful update of partner metadata when partner exists."""

        # Arrange
        self.partner_meta_data_repository.is_partner_exists.return_value = True

        # Mock current partner metadata as PartnerMetaData (model)
        existing_meta_data = PartnerMetaData(
            id=1,
            partner_id=1,
            api_key="existing-api-key",
            timezone="Etc/UTC",
            number_of_users=30,
        )

        self.partner_meta_data_repository.get_partner_meta_data_by_partner_id.return_value = (
            existing_meta_data
        )

        # Mock updated metadata returned by repository after update
        updated_metadata = PartnerMetaData(
            id=1,
            partner_id=1,
            api_key="updated-api-key",
            timezone="Etc/UTC",
            number_of_users=50,
        )

        self.partner_meta_data_repository.update_partner_meta_data.return_value = (
            updated_metadata
        )

        # Act
        response = await self.partner_metadata_service_mock.update_partner_meta_data(
            partner_id=1, update_data=self.update_data
        )

        # Assert
        assert isinstance(response, PartnerMetaData)
        assert response.id == 1
        assert response.api_key == "updated-api-key"

        # Verify interactions
        self.partner_meta_data_repository.is_partner_exists.assert_awaited_once_with(1)
        self.partner_meta_data_repository.get_partner_meta_data_by_partner_id.assert_awaited_once_with(
            1
        )
        self.partner_meta_data_repository.update_partner_meta_data.assert_awaited_once_with(
            1, self.update_data
        )
        self.mock_logger.info.assert_any_call(
            "Partner metadata updated successfully, id: 1"
        )
        self.audit_log_mock.log_action.assert_awaited_once()

    async def test_get_by_partner_id_exception(self):

        self.partner_meta_data_repository.get_partner_meta_data_by_partner_id.side_effect = PartnerMetaDataException(
            "Internal server error"
        )

        with pytest.raises(PartnerMetaDataException):
            await self.partner_metadata_service_mock.get_partner_meta_data_by_partner_id(
                partner_id=1
            )

    async def test_update_partner_meta_data_exception(self):
        self.partner_meta_data_repository.update_partner_meta_data.side_effect = (
            PartnerMetaDataException("Error updating metadata")
        )

        with pytest.raises(PartnerMetaDataException) as exc:
            await self.partner_metadata_service_mock.update_partner_meta_data(
                partner_id=1, update_data=self.update_data
            )

        assert str(exc.value) == "Error updating metadata"

    async def test_get_all_partner_meta_data_exception(self):

        self.partner_meta_data_repository.get_all_partner_meta_data.side_effect = (
            Exception("Error fetching all metadata")
        )

        with pytest.raises(Exception) as exc:
            await self.partner_metadata_service_mock.get_all_partner_meta_data()

        assert str(exc.value) == "Error fetching all metadata"

    async def test_get_by_partner_id_general_exception(self):

        self.partner_meta_data_repository.get_partner_meta_data_by_partner_id.side_effect = Exception(
            "Some unexpected error"
        )

        with pytest.raises(Exception) as exc:
            await self.partner_metadata_service_mock.get_partner_meta_data_by_partner_id(
                partner_id=1
            )

        assert str(exc.value) == "Some unexpected error"

    async def test_update_partner_meta_data_general_exception(self):

        self.partner_meta_data_repository.update_partner_meta_data.side_effect = (
            Exception("Some unexpected error")
        )

        with pytest.raises(Exception) as exc:
            await self.partner_metadata_service_mock.update_partner_meta_data(
                partner_id=1, update_data=self.update_data
            )

        assert str(exc.value) == "Some unexpected error"

    async def test_partner_exists(self):

        self.partner_meta_data_repository.is_partner_exists = AsyncMock(
            return_value=True
        )

        result = await self.partner_metadata_service_mock.is_partner_exists(
            partner_id=1
        )

        assert result == True

    async def test_partner_exists_general_exception(self):

        self.partner_meta_data_repository.is_partner_exists.side_effect = Exception(
            "Some unexpected error"
        )

        with pytest.raises(Exception) as exc:
            await self.partner_metadata_service_mock.is_partner_exists(partner_id=1)

        assert str(exc.value) == "Some unexpected error"

    async def test_create_partner_metadata_success(self):
        # Arrange
        self.partner_meta_data_repository.is_partner_exists.return_value = True
        self.partner_meta_data_repository.add_partner_metadata_repository.return_value = (
            self.mock_partner_metadata
        )

        # Act
        response = await self.partner_metadata_service_mock.create_partner_metadata(
            partner_id=1, partner_meta_data=self.new_partner_meta_data
        )

        # Assert
        assert response == self.mock_partner_metadata
        self.partner_meta_data_repository.is_partner_exists.assert_awaited_once_with(1)
        self.partner_meta_data_repository.add_partner_metadata_repository.assert_awaited_once_with(
            partner_id=1, partner_meta_data=self.new_partner_meta_data
        )
        self.mock_logger.info.assert_any_call(
            "Creating partner data for partner id : 1"
        )
        self.mock_logger.info.assert_any_call(
            "Partner metadata created successfully, partner id: 1"
        )
        self.audit_log_mock.log_action.assert_awaited_once()

    async def test_create_partner_metadata_partner_not_found(self):
        # Arrange
        self.partner_meta_data_repository.is_partner_exists.return_value = False

        # Act & Assert
        with pytest.raises(PartnerNotFoundError, match="Partner not found, id: 1"):
            await self.partner_metadata_service_mock.create_partner_metadata(
                partner_id=1, partner_meta_data=self.new_partner_meta_data
            )

        # Verify logger and repository interactions
        self.mock_logger.info.assert_any_call(
            "Creating partner data for partner id : 1"
        )
        self.partner_meta_data_repository.is_partner_exists.assert_awaited_once_with(1)
        self.mock_logger.error.assert_called_once_with(
            "an unexpected error occured while creating partner metadata for partner id: 1"
        )

    async def test_create_partner_metadata_raises_partner_metadata_exception(self):
        # Arrange
        self.partner_meta_data_repository.is_partner_exists.return_value = True
        self.partner_meta_data_repository.add_partner_metadata_repository.side_effect = PartnerMetaDataException(
            "Integrity error"
        )

        # Act & Assert
        with pytest.raises(PartnerMetaDataException) as exc:
            await self.partner_metadata_service_mock.create_partner_metadata(
                partner_id=1, partner_meta_data=self.new_partner_meta_data
            )

        assert str(exc.value) == "Integrity error"

    async def test_create_partner_metadata_raises_general_exception(self):
        # Arrange
        self.partner_meta_data_repository.is_partner_exists.return_value = True
        self.partner_meta_data_repository.add_partner_metadata_repository.side_effect = Exception(
            "Unexpected error"
        )

        # Act & Assert
        with pytest.raises(Exception) as exc:
            await self.partner_metadata_service_mock.create_partner_metadata(
                partner_id=1, partner_meta_data=self.new_partner_meta_data
            )

        assert str(exc.value) == "Unexpected error"
        self.mock_logger.error.assert_called_once_with(
            "an unexpected error occured while creating partner metadata for partner id: 1"
        )

    @pytest.mark.asyncio
    async def test_returns_plan_details_with_free_trial(self):
        partner_id = 1

        # Make sure trial expiry is in the future
        now = DateTimeUtil.get_current_time()
        meta = SimpleNamespace(
            id=1,
            maglo_trail_expiry_time=now + (8 * 24 * 60 * 60 * 1000),  # +8 days in ms
            maglo_app_trail_expiry_time=now + (8 * 24 * 60 * 60 * 1000),
        )

        # Stub the internal metadata fetch the service calls
        self.partner_metadata_service_mock.get_partner_meta_data_by_partner_id = (
            AsyncMock(return_value=meta)
        )

        # Mock partner_config_service to return the enabled services (list of dicts branch)
        partner_config_service_mock = MagicMock()
        partner_config_service_mock.get_partner_configs_by_partner_id = AsyncMock(
            return_value=[
                {"key": "is_maglo_enabled", "value": True},
                {"key": "is_talko_enabled", "value": False},
                {"key": "is_babbler_enabled", "value": False},
            ]
        )

        # Act
        response: PartnerPlanDetailsResponse = (
            await self.partner_metadata_service_mock.get_partner_plan_details(
                partner_id, partner_config_service=partner_config_service_mock
            )
        )

        # Assert
        self.partner_metadata_service_mock.get_partner_meta_data_by_partner_id.assert_awaited_once_with(
            partner_id=partner_id
        )
        partner_config_service_mock.get_partner_configs_by_partner_id.assert_awaited_once_with(
            partner_id
        )

        assert response.is_maglo_service_enabled is True
        assert response.is_talko_service_enabled is False
        assert response.is_babbler_service_enabled is False
        assert response.is_maglo_service_free_trial_enabled is True

    @pytest.mark.asyncio
    async def test_returns_plan_details_without_free_trial(self):
        partner_id = 1

        # Expiry time in the past → no free trial
        past_time = 14565432  # much less than current time
        meta = SimpleNamespace(id=1, maglo_trail_expiry_time=past_time, maglo_app_trail_expiry_time=past_time)

        # Stub the internal metadata fetch (service calls with keyword arg)
        self.partner_metadata_service_mock.get_partner_meta_data_by_partner_id = (
            AsyncMock(return_value=meta)
        )

        # Mock partner_config_service (dict list branch)
        partner_config_service_mock = MagicMock()
        partner_config_service_mock.get_partner_configs_by_partner_id = AsyncMock(
            return_value=[
                {"key": "is_maglo_enabled", "value": True},
                {"key": "is_talko_enabled", "value": False},
                {"key": "is_babbler_enabled", "value": False},
            ]
        )

        # Act
        response: PartnerPlanDetailsResponse = (
            await self.partner_metadata_service_mock.get_partner_plan_details(
                partner_id, partner_config_service=partner_config_service_mock
            )
        )

        # Assert
        self.partner_metadata_service_mock.get_partner_meta_data_by_partner_id.assert_awaited_once_with(
            partner_id=partner_id
        )
        partner_config_service_mock.get_partner_configs_by_partner_id.assert_awaited_once_with(
            partner_id
        )

        assert response.is_maglo_service_enabled is True
        assert response.is_talko_service_enabled is False
        assert response.is_babbler_service_enabled is False
        assert response.is_maglo_service_free_trial_enabled is False

    @pytest.mark.asyncio
    async def test_returns_empty_response_when_no_metadata(self):
        partner_id = 1

        # Stub the internal metadata fetch to return None
        self.partner_metadata_service_mock.get_partner_meta_data_by_partner_id = (
            AsyncMock(return_value=None)
        )

        # Mock partner_config_service (doesn't matter since metadata is None)
        partner_config_service_mock = MagicMock()
        partner_config_service_mock.get_partner_configs_by_partner_id = AsyncMock(
            return_value=[]
        )

        # Act
        response: PartnerPlanDetailsResponse = (
            await self.partner_metadata_service_mock.get_partner_plan_details(
                partner_id, partner_config_service=partner_config_service_mock
            )
        )

        # Assert
        self.partner_metadata_service_mock.get_partner_meta_data_by_partner_id.assert_awaited_once_with(
            partner_id=partner_id
        )
        partner_config_service_mock.get_partner_configs_by_partner_id.assert_awaited_once_with(
            partner_id
        )

        assert isinstance(response, PartnerPlanDetailsResponse)
        assert response.is_maglo_service_enabled is False
        assert response.is_talko_service_enabled is False
        assert response.is_babbler_service_enabled is False
        assert response.is_maglo_service_free_trial_enabled is False

    async def test_logs_error_when_exception_occurs(self):
        self.partner_metadata_service_mock.get_partner_meta_data_by_partner_id = (
            AsyncMock(side_effect=Exception("DB error"))
        )

        with pytest.raises(Exception):
            await self.partner_metadata_service_mock.get_partner_plan_details(1)

        self.mock_logger.error.assert_called()

    async def test_logs_error_when_exception_occurs(self):
        self.partner_metadata_service_mock.get_partner_meta_data_by_partner_id = (
            AsyncMock(side_effect=Exception("DB error"))
        )

        with pytest.raises(Exception):
            await self.partner_metadata_service_mock.get_partner_plan_details(1)

        self.mock_logger.error.assert_called()

    # Tests for get_partner_meta_data_by_partner_ids service method
    async def test_get_partner_meta_data_by_partner_ids_success_multiple(
        self, monkeypatch
    ):
        partner_ids = [1, 2]
        now = 1_000_000

        meta1 = SimpleNamespace(partner_id=1, maglo_trail_expiry_time=now + 1000)
        meta2 = SimpleNamespace(partner_id=2, maglo_trail_expiry_time=now - 1000)

        self.partner_meta_data_repository.get_partner_meta_data_by_partner_ids = (
            AsyncMock(return_value=[meta1, meta2])
        )

        monkeypatch.setattr(DateTimeUtil, "get_current_time", lambda: now)

        result = await self.partner_metadata_service_mock.get_partner_meta_data_by_partner_ids(
            partner_ids=partner_ids
        )

        assert set(result.keys()) == {1, 2}
        assert result[1]["meta"] is meta1
        assert result[1]["is_maglo_free_trial_enabled"] is True
        assert result[2]["meta"] is meta2
        assert result[2]["is_maglo_free_trial_enabled"] is False

        self.partner_meta_data_repository.get_partner_meta_data_by_partner_ids.assert_awaited_once_with(
            partner_ids
        )
        self.mock_logger.info.assert_any_call(
            "Attempting to get partner metadata by partner ids: {}".format(partner_ids)
        )
        self.mock_logger.info.assert_any_call(
            "Successfully fetched partner metadata by partner_ids {} {}".format(
                partner_ids, [meta1, meta2]
            )
        )

    async def test_get_partner_meta_data_by_partner_ids_empty_input(self, monkeypatch):
        partner_ids: list[int] = []

        self.partner_meta_data_repository.get_partner_meta_data_by_partner_ids = (
            AsyncMock(return_value=[])
        )

        monkeypatch.setattr(DateTimeUtil, "get_current_time", lambda: 0)

        result = await self.partner_metadata_service_mock.get_partner_meta_data_by_partner_ids(
            partner_ids=partner_ids
        )

        assert result == {}
        self.partner_meta_data_repository.get_partner_meta_data_by_partner_ids.assert_awaited_once_with(
            partner_ids
        )
        self.mock_logger.info.assert_any_call(
            "Attempting to get partner metadata by partner ids: {}".format(partner_ids)
        )
        self.mock_logger.info.assert_any_call(
            "Successfully fetched partner metadata by partner_ids {} {}".format(
                partner_ids, []
            )
        )

    async def test_get_partner_meta_data_by_partner_ids_none_found(self, monkeypatch):
        partner_ids = [999]

        self.partner_meta_data_repository.get_partner_meta_data_by_partner_ids = (
            AsyncMock(return_value=[])
        )

        monkeypatch.setattr(DateTimeUtil, "get_current_time", lambda: 5000)

        result = await self.partner_metadata_service_mock.get_partner_meta_data_by_partner_ids(
            partner_ids=partner_ids
        )

        assert set(result.keys()) == {999}
        assert result[999]["meta"] is None
        assert result[999]["is_maglo_free_trial_enabled"] is False

    async def test_get_partner_meta_data_by_partner_ids_maglo_trail_none(
        self, monkeypatch
    ):
        partner_ids = [1]
        now = 2000
        meta = SimpleNamespace(partner_id=1, maglo_trail_expiry_time=None)

        self.partner_meta_data_repository.get_partner_meta_data_by_partner_ids = (
            AsyncMock(return_value=[meta])
        )

        monkeypatch.setattr(DateTimeUtil, "get_current_time", lambda: now)

        result = await self.partner_metadata_service_mock.get_partner_meta_data_by_partner_ids(
            partner_ids=partner_ids
        )

        assert result[1]["meta"] is meta
        assert result[1]["is_maglo_free_trial_enabled"] is False

    async def test_get_partner_meta_data_by_partner_ids_with_duplicate_ids(
        self, monkeypatch
    ):
        partner_ids = [1, 1, 2]
        now = 10
        meta1 = SimpleNamespace(partner_id=1, maglo_trail_expiry_time=now + 1)
        meta2 = SimpleNamespace(partner_id=2, maglo_trail_expiry_time=now + 1)

        self.partner_meta_data_repository.get_partner_meta_data_by_partner_ids = (
            AsyncMock(return_value=[meta1, meta2])
        )

        monkeypatch.setattr(DateTimeUtil, "get_current_time", lambda: now)

        result = await self.partner_metadata_service_mock.get_partner_meta_data_by_partner_ids(
            partner_ids=partner_ids
        )

        # duplicates in input should collapse to unique keys in the returned dict
        assert set(result.keys()) == {1, 2}
        assert result[1]["meta"] is meta1
        assert result[2]["meta"] is meta2

    async def test_get_partner_meta_data_by_partner_ids_repo_exception(self):
        partner_ids = [1, 2]

        self.partner_meta_data_repository.get_partner_meta_data_by_partner_ids = (
            AsyncMock(side_effect=Exception("DB failure"))
        )

        with pytest.raises(Exception) as exc:
            await self.partner_metadata_service_mock.get_partner_meta_data_by_partner_ids(
                partner_ids=partner_ids
            )

        assert str(exc.value) == "DB failure"
        self.mock_logger.error.assert_called_with(
            "Error occurred while get partner metadata by partner_ids {}".format(
                exc.value
            )
        )
