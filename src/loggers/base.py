import inspect
import logging
import uuid

from starlette_context import context
from starlette_context.plugins.request_id import RequestIdPlugin

from src.components.common.constants import CurrentUserMap
from src.loggers import LogLevel


class RequestIdFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        try:
            request_id = context.get(RequestIdPlugin.key, "N/A")
            user = context.get("user", {})

            partner_id = user.get(CurrentUserMap.PARTNER_ID)
            user_id = user.get(CurrentUserMap.USER_ID)

            if partner_id and user_id:
                record.request_id = f"P{partner_id}-U{user_id}-{request_id}"
            else:
                record.request_id = request_id
        except RuntimeError:
            record.request_id = str(
                uuid.uuid4()  # Generate fallback if context unavailable
            )
        return True


class BaseLogger:
    _loggers = {}  # Per-class logger storage

    @classmethod
    def get_logger(cls):
        """Setup and return logger per class."""
        if cls not in cls._loggers:
            logger = logging.getLogger(cls._type())
            logger.setLevel(cls._get_log_level(LogLevel.Level.DEBUG))

            # Clear existing handlers to prevent duplication or conflicting formats
            logger.handlers.clear()

            cls._set_file_handler(logger)
            cls._set_stream_handler(logger)

            cls._loggers[cls] = logger

        return cls._loggers[cls]

    @classmethod
    def _set_file_handler(cls, logger):
        fh = logging.FileHandler("console_service.log")
        fh.addFilter(RequestIdFilter())
        fh.setFormatter(cls._get_log_format())
        logger.addHandler(fh)

    @classmethod
    def _set_stream_handler(cls, logger):
        sh = logging.StreamHandler()
        sh.addFilter(RequestIdFilter())
        sh.setFormatter(cls._get_log_format())
        logger.addHandler(sh)

    @classmethod
    def _get_log_format(cls):
        return logging.Formatter(
            fmt="%(asctime)s %(levelname)s %(process)d %(thread)d - Log ID: %(request_id)s | %(message)s"
        )

    @classmethod
    def _type(cls):
        return cls.__name__

    @classmethod
    def _get_log_level(cls, level: LogLevel.Level) -> int:
        match level:
            case LogLevel.Level.DEBUG:
                return logging.DEBUG
            case LogLevel.Level.INFO:
                return logging.INFO
            case LogLevel.Level.WARNING:
                return logging.WARNING
            case LogLevel.Level.CRITICAL:
                return logging.CRITICAL
            case LogLevel.Level.ERROR:
                return logging.ERROR
            case _:
                raise Exception(f"log level not found - {level.name}")

    def _log_with_context(self, level, message: str):
        frame = inspect.currentframe().f_back.f_back
        line_number = frame.f_lineno
        module_name = frame.f_globals["__name__"]

        formatted_message = f"({module_name}:{line_number}) {message}"
        self.get_logger().log(level, formatted_message)

    def debug(self, message: str, *args):
        if args:
            message = message % args
        self._log_with_context(logging.DEBUG, message)

    def info(self, message: str, *args):
        if args:
            message = message % args
        self._log_with_context(logging.INFO, message)

    def warning(self, message: str, *args):
        if args:
            message = message % args
        self._log_with_context(logging.WARNING, message)

    def critical(self, message: str, *args):
        if args:
            message = message % args
        self._log_with_context(logging.CRITICAL, message)

    def error(self, message: str, *args):
        if args:
            message = message % args
        self._log_with_context(logging.ERROR, message)
