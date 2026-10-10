import logging
from contextlib import contextmanager
from unittest.mock import MagicMock, patch

import pytest

from src.loggers import LogLevel
from src.loggers.base import RequestIdFilter
from src.loggers.console_service_logger import BaseLogger


@contextmanager
def starlette_context(data=None):
    """Mock starlette_context for tests."""
    with patch("src.loggers.base.context") as mock_context:
        mock_context.get = MagicMock(
            side_effect=lambda key, default=None: (data or {}).get(key, default)
        )
        yield mock_context


@pytest.mark.parametrize(
    "user_data, expected_request_id",
    [
        ({"partner_id": "456", "user_id": "789"}, "P456-U789-123"),
        ({"partner_id": "456"}, "123"),
        ({"user_id": "789"}, "123"),
        ({}, "123"),
    ],
    ids=[
        "both_partner_and_user_id",
        "only_partner_id",
        "only_user_id",
        "empty_user_data",
    ],
)
def test_request_id_filter_user_data_handling(user_data, expected_request_id):
    with patch(
        "src.components.common.constants.CurrentUserMap"
    ) as mock_user_map, patch("src.loggers.base.RequestIdPlugin") as mock_plugin:

        mock_plugin.key = "x-request-id"
        mock_user_map.PARTNER_ID = "partner_id"
        mock_user_map.USER_ID = "user_id"

        with starlette_context({"x-request-id": "123", "user": user_data}):
            filter_instance = RequestIdFilter()
            record = logging.LogRecord(
                name="test",
                level=logging.INFO,
                pathname="",
                lineno=0,
                msg="test",
                args=(),
                exc_info=None,
            )
            result = filter_instance.filter(record)

            assert result is True
            assert record.request_id == expected_request_id


def test_request_id_filter_runtime_error(mock_uuid):
    with patch("src.loggers.base.context.get", side_effect=RuntimeError), patch(
        "uuid.uuid4", return_value="mocked-uuid"
    ):
        filter_instance = RequestIdFilter()
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="",
            lineno=0,
            msg="test",
            args=(),
            exc_info=None,
        )
        result = filter_instance.filter(record)

        assert result is True
        assert record.request_id == "mocked-uuid"


@pytest.fixture
def mock_uuid():
    with patch("uuid.uuid4") as mock:
        mock.return_value = "mocked-uuid"
        yield mock


@pytest.fixture
def mock_logger():
    with patch("logging.getLogger") as mock:
        logger = MagicMock(spec=logging.Logger)
        logger.handlers = []
        mock.return_value = logger
        yield logger


@pytest.fixture
def mock_file_handler():
    with patch("logging.FileHandler") as mock:
        yield mock


@pytest.fixture
def mock_stream_handler():
    with patch("logging.StreamHandler") as mock:
        yield mock


@pytest.fixture
def mock_formatter():
    with patch("logging.Formatter") as mock:
        yield mock


@pytest.fixture
def mock_inspect():
    with patch("inspect.currentframe") as mock_frame:
        frame = MagicMock()
        frame.f_back.f_back.f_lineno = 42
        frame.f_back.f_back.f_globals = {"__name__": "test_module"}
        mock_frame.return_value = frame
        yield mock_frame


class TestLogger(BaseLogger):
    pass


def test_get_logger_initializes_once(
    mock_logger, mock_file_handler, mock_stream_handler, mock_formatter
):
    TestLogger._loggers.clear()
    logger = TestLogger.get_logger()
    assert logger == mock_logger
    assert TestLogger._loggers[TestLogger] == logger
    mock_logger.setLevel.assert_called_once_with(logging.DEBUG)
    assert not mock_logger.handlers
    assert mock_file_handler.call_count == 1
    assert mock_stream_handler.call_count == 1
    mock_file_handler.return_value.addFilter.assert_called_once()
    mock_stream_handler.return_value.addFilter.assert_called_once()
    mock_file_handler.return_value.setFormatter.assert_called_once_with(
        mock_formatter.return_value
    )
    mock_stream_handler.return_value.setFormatter.assert_called_once_with(
        mock_formatter.return_value
    )
    mock_logger.addHandler.assert_called()

    # Call again to confirm it's cached
    logger2 = TestLogger.get_logger()
    assert logger2 == logger
    assert mock_file_handler.call_count == 1


def test_get_log_level_invalid():
    with pytest.raises(AttributeError, match="'str' object has no attribute 'name'"):
        TestLogger._get_log_level("INVALID")


def test_log_with_context(mock_logger, mock_inspect):
    TestLogger._loggers.clear()
    logger_instance = TestLogger()
    logger_instance._log_with_context(logging.INFO, "Test message")
    mock_logger.log.assert_called_once_with(
        logging.INFO, "(test_module:42) Test message"
    )


@pytest.mark.parametrize(
    "method, level",
    [
        ("debug", logging.DEBUG),
        ("info", logging.INFO),
        ("warning", logging.WARNING),
        ("critical", logging.CRITICAL),
        ("error", logging.ERROR),
    ],
)
def test_logging_methods(mock_logger, mock_inspect, method, level):
    TestLogger._loggers.clear()
    logger_instance = TestLogger()
    getattr(logger_instance, method)("Test message")
    mock_logger.log.assert_called_once_with(level, "(test_module:42) Test message")


def test_get_log_level_info():
    assert TestLogger._get_log_level(LogLevel.Level.INFO) == logging.INFO


def test_get_log_level_warning():
    assert TestLogger._get_log_level(LogLevel.Level.WARNING) == logging.WARNING


def test_get_log_level_critical():
    assert TestLogger._get_log_level(LogLevel.Level.CRITICAL) == logging.CRITICAL


def test_get_log_level_error():
    assert TestLogger._get_log_level(LogLevel.Level.ERROR) == logging.ERROR
