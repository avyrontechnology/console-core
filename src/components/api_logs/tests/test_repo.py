from unittest.mock import AsyncMock, MagicMock

import pytest

from src.components.api_logs.repositories import APILogRepository
from src.components.api_logs.schemas import ApiLog


@pytest.mark.asyncio
class TestAPILogRepository:

    @pytest.fixture(autouse=True)
    def setup_class(self, mock_mongo_db_session, mock_logger):
        """Setup APILogRepository with proper Mongo mock chain."""
        self.api_log_repository = APILogRepository(
            mongo_db_session=mock_mongo_db_session, logger=mock_logger
        )
        self.mock_logger = mock_logger

        self.mock_collection = MagicMock()
        self.mock_collection.insert_one = AsyncMock()
        self.mock_collection.find_one = AsyncMock()

        mock_collection_context = MagicMock()
        mock_collection_context.__aenter__.return_value = self.mock_collection
        mock_collection_context.__aexit__.return_value = None

        mock_session_context = MagicMock()
        mock_session_context.collection.return_value = mock_collection_context

        mock_mongo_db_session.collection.return_value = mock_collection_context
        mock_mongo_db_session.return_value.__aenter__.return_value = (
            mock_session_context
        )

        # Example log data
        self.mock_api_log = ApiLog(
            log_id="c0660bb275044e109118cf644d8f2175",
            client_ip="172.18.0.1",
            request={
                "request_method": "GET",
                "request_url": "http://localhost:8001/api/test",
                "request_headers": {"content-type": "application/json"},
                "request_body": None,
            },
            response={
                "response_status_code": 200,
                "response_body": {"status": "ok"},
                "response_time": 0.023,
            },
            timestamp=1762202968.9239995,
        )

    async def test_save_log_success(self):
        """Test saving API log successfully."""
        self.mock_collection.insert_one = AsyncMock(return_value=None)

        await self.api_log_repository.save_log(self.mock_api_log)

        self.mock_logger.info.assert_any_call("Inserting the api logs into database...")
        self.mock_logger.info.assert_any_call(
            "Api logs successfully inserted into the database: {}".format(
                self.mock_api_log
            )
        )

    async def test_get_api_logs_by_log_id_success(self):
        """Test fetching API log by log_id successfully."""
        # Arrange
        self.mock_collection.find_one.return_value = self.mock_api_log.dict()

        # Act
        result = await self.api_log_repository.get_api_logs_by_log_id(
            self.mock_api_log.log_id
        )

        # Assert
        assert result == self.mock_api_log.dict()
        self.mock_logger.info.assert_any_call(
            "Fetching API log from database for log_id: {}".format(
                self.mock_api_log.log_id
            )
        )
        self.mock_logger.info.assert_any_call(
            "Successfully fetched API log for log_id: {}".format(
                self.mock_api_log.log_id
            )
        )

    async def test_get_api_logs_by_log_id_not_found(self):
        """Test fetching API log when no record is found."""
        self.mock_collection.find_one = AsyncMock(return_value=None)

        result = await self.api_log_repository.get_api_logs_by_log_id("nonexistent-id")

        assert result is None
        self.mock_logger.warning.assert_called_with(
            "No API log found in database for log_id: {}".format("nonexistent-id")
        )

    async def test_get_api_logs_by_log_id_failure(self):
        """❌ Test fetching API log raises exception and logs error."""
        self.mock_collection.find_one = AsyncMock(
            side_effect=Exception("DB query failed")
        )

        with pytest.raises(Exception, match="DB query failed"):
            await self.api_log_repository.get_api_logs_by_log_id(
                "c0660bb275044e109118cf644d8f2175"
            )

        self.mock_logger.error.assert_called_with(
            "Error fetching API log for log_id={}: {}".format(
                "c0660bb275044e109118cf644d8f2175", "DB query failed"
            )
        )
