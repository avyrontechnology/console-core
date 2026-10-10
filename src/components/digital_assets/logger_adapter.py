import importlib.util
import logging
import os

from src.core.environment import ENV


class LoggerAdapter:
    def __init__(self, config_path: str = ENV.LOGGING_CONFIG_PATH):
        """
        Initialize LoggerAdapter with the specified config path.
        """
        self.logging_config_path = config_path
        self.logger = self._initialize_logger()

    def _initialize_logger(self):
        """
        Initialize the logger by loading configuration from the provided path.
        """
        self._load_logging_config()
        return logging.getLogger("digital_assets")

    def _load_logging_config(self):
        """
        Load logging configuration either from the specified config path or default to basicConfig.
        """
        if not os.path.exists(self.logging_config_path):
            raise FileNotFoundError(
                f"Logging config not found at: {self.logging_config_path}"
            )

        spec = importlib.util.spec_from_file_location(
            "logging_config", self.logging_config_path
        )
        logging_config = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(logging_config)

        setup_logging = getattr(logging_config, "setup_logging", None)
        if setup_logging:
            setup_logging()
        else:
            logging.basicConfig(
                level=logging.DEBUG,
                format="%(asctime)s - %(levelname)s - %(message)s",
            )

    def get_logger(self):
        """
        Return the logger instance.
        """
        return self.logger
