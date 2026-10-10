from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.components.api_logs.schemas import ApiLog, ApiLogResponse
from src.components.api_logs.services import APILogService


@pytest.mark.asyncio
class TestAPILogService:

    @pytest.fixture(autouse=True)
    def setup_class(self, mock_logger):
        """Setup APILogService with mocked dependencies."""
        self.mock_logger = mock_logger
        self.api_log_repository_mock = AsyncMock()

        # Create service instance
        self.api_log_service = APILogService(
            api_log_repository=self.api_log_repository_mock,
            console_service_logger=self.mock_logger,
        )

        # Example valid API log input
        self.raw_log_data = {
            "log_id": "c0660bb275044e109118cf644d8f2175",
            "client_ip": "172.18.0.1",
            "request": {
                "request_method": "GET",
                "request_url": "http://localhost:8001/api/test",
                "request_headers": {"authorization": "Bearer abc123"},
                "request_body": {"sensitive_data": "should be masked"},
            },
            "response": {
                "response_status_code": 200,
                "response_body": {"status": "ok"},
                "response_time": 0.032,
            },
            "timestamp": 1762202968.9239995,
        }

        self.api_log_dict = {
            "_id": "690915583ffae6b797116337",
            "log_id": "c0660bb275044e109118cf644d8f2175",
            "client_ip": "172.18.0.1",
            "request": {"request_method": "GET"},
            "response": {"response_status_code": 200},
            "timestamp": 1762202968.9239995,
        }

    async def test_log_api_success(self):
        """Test successful API log insertion."""
        with patch.object(
            ApiLog, "filter_sensitive_data", return_value=self.raw_log_data
        ):
            await self.api_log_service.log_api(self.raw_log_data)

        # Assertions
        self.mock_logger.info.assert_any_call("Attempting to insert the api logs.")
        self.api_log_repository_mock.save_log.assert_awaited_once()

    async def test_log_api_failure(self):
        """Test log_api when repository raises an exception."""
        self.api_log_repository_mock.save_log.side_effect = Exception("DB insert error")

        with patch.object(
            ApiLog, "filter_sensitive_data", return_value=self.raw_log_data
        ), pytest.raises(Exception, match="DB insert error"):
            await self.api_log_service.log_api(self.raw_log_data)

        self.mock_logger.error.assert_called_with(
            "Error occured while saving API log: {}".format("DB insert error")
        )

    async def test_get_api_log_by_log_id_success(self):
        """Test fetching and validating API log successfully."""
        # Mock repository return value
        self.api_log_repository_mock.get_api_logs_by_log_id.return_value = (
            self.api_log_dict
        )

        # Act
        result = await self.api_log_service.get_api_log_by_log_id(
            "c0660bb275044e109118cf644d8f2175"
        )

        # Assert
        assert isinstance(result, list)
        assert result[0]["log_id"] == self.api_log_dict["log_id"]

        self.mock_logger.info.assert_any_call(
            "Attempting to retrieve API log for log_id: {}".format(
                self.api_log_dict["log_id"]
            )
        )
        self.mock_logger.info.assert_any_call(
            "Successfully validated API log for log_id: {}".format(
                self.api_log_dict["log_id"]
            )
        )

    async def test_get_api_log_by_log_id_not_found(self):
        """Test when no API log exists for the given log_id."""
        self.api_log_repository_mock.get_api_logs_by_log_id.return_value = None

        result = await self.api_log_service.get_api_log_by_log_id("nonexistent-id")

        assert result == []
        self.mock_logger.warning.assert_called_with(
            "No API log found for log_id: {}".format("nonexistent-id")
        )

    async def test_get_api_log_by_log_id_failure(self):
        """Test when repository raises an exception."""
        self.api_log_repository_mock.get_api_logs_by_log_id.side_effect = Exception(
            "DB fetch error"
        )

        with pytest.raises(Exception, match="DB fetch error"):
            await self.api_log_service.get_api_log_by_log_id(
                "c0660bb275044e109118cf644d8f2175"
            )

        self.mock_logger.error.assert_called_with(
            "Error retrieving API log for log_id={}: {}".format(
                "c0660bb275044e109118cf644d8f2175", "DB fetch error"
            )
        )
