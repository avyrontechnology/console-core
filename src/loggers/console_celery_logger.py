import logging


class CeleryLogger:

    @staticmethod
    def get_logger():
        logger = logging.getLogger("celery_logger")
        logger.setLevel(logging.DEBUG)

        if not logger.handlers:
            # Console handler
            console_handler = logging.StreamHandler()
            console_handler.setLevel(logging.DEBUG)

            # File handler
            log_file_path = "celery.log"
            file_handler = logging.FileHandler(log_file_path)
            file_handler.setLevel(logging.DEBUG)

            # Formatter
            formatter = logging.Formatter(
                "%(asctime)s %(levelname)s %(process)d %(thread)d (%(module)s.%(funcName)s:%(lineno)s) %(message)s"
            )
            console_handler.setFormatter(formatter)
            file_handler.setFormatter(formatter)

            # Attach handlers
            logger.addHandler(console_handler)
            logger.addHandler(file_handler)

        return logger
