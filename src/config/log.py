import os

ROOT_LEVEL = os.environ.get("PROD", "INFO")

LOGGING_CONFIG = {
    "version": 1,
    "disable_existing_loggers": True,
    "formatters": {
        "standard": {
            "format": "%(asctime)s %(levelname)s %(process)d %(thread)d (%(module)s.%(funcName)s:%(lineno)s) %(message)s"
        },
    },
    "handlers": {
        "default": {
            "level": "INFO",
            "formatter": "standard",
            "class": "logging.StreamHandler",
            "stream": "ext://sys.stdout",  # Default is stderr
        },
        # "file": {
        #     "class": "logging.handlers.RotatingFileHandler",
        #     "formatter": "standard",
        #     "level": "INFO",
        #     "filename": "console_service.log",
        #     "mode": "a",
        #     "encoding": "utf-8",
        #     "maxBytes": 500000,
        #     "backupCount": 4,
        # },
    },
    "loggers": {
        "": {  # root logger
            "level": ROOT_LEVEL,  # "INFO",
            "handlers": [],
            "propagate": False,
        },
        "uvicorn.error": {
            "level": "DEBUG",
            "handlers": [
                "default",
            ],
        },
        "uvicorn.access": {
            "level": "DEBUG",
            "handlers": [
                "default",
            ],
        },
    },
}
