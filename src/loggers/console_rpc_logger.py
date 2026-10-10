import logging


class ConsoleRpcLogger:

    @staticmethod
    def get_logger():
        # Create a logger
        logger = logging.getLogger("console_rpc")
        logger.setLevel(logging.DEBUG)

        # Create a console handler
        console_handler = logging.StreamHandler()
        console_handler.setLevel(logging.DEBUG)

        # Create a file handler
        log_file_path = "console_rpc.log"
        file_handler = logging.FileHandler(log_file_path)
        file_handler.setLevel(logging.DEBUG)

        # Create a formatter and set it for both handlers
        formatter = logging.Formatter(
            "%(asctime)s %(levelname)s %(process)d %(thread)d (%(module)s.%(funcName)s:%(lineno)s) %(message)s"
        )
        console_handler.setFormatter(formatter)
        file_handler.setFormatter(formatter)

        # Add the handlers to the logger
        logger.addHandler(console_handler)
        logger.addHandler(file_handler)
        return logger
