import os

from dotenv import load_dotenv

load_dotenv()


class ENV:
    """
    Centralized environment configuration for the User Service.
    """

    # ----------------------
    # Security & Auth
    # ----------------------
    SECRET_KEY = os.getenv("SECRET_KEY")
    ALGORITHM = os.getenv("ALGORITHM")
    ACCESS_TOKEN_EXPIRE_MINUTES = os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES")

    # ----------------------
    # Storage Spaces
    # ----------------------
    DO_ENDPOINT_URL = os.getenv("DO_ENDPOINT_URL", "")
    DO_SPACE_NAME = os.getenv("DO_SPACE_NAME", "")
    DO_SECRET_ACCESS_KEY = os.getenv("DO_SECRET_ACCESS_KEY", "")
    DO_ACCESS_KEY_ID = os.getenv("DO_ACCESS_KEY_ID", "")
    STORAGE_SERVICE_PROVIDER = os.getenv("STORAGE_SERVICE_PROVIDER", "")

    # ----------------------
    # Service Info
    # ----------------------
    ENVIRONMENT = os.getenv("ENV", "")
    SERVICE_NAME = os.getenv("SERVICE_NAME", "")

    # ----------------------
    # Database (Postgres)
    # ----------------------
    POSTGRES_DB = os.getenv("POSTGRES_DB", "userservice")
    POSTGRES_USER = os.getenv("POSTGRES_USER", "jaggerbomb")
    POSTGRES_PASSWORD = os.getenv("POSTGRES_PASSWORD", "jaggerbomb")
    POSTGRES_HOST = os.getenv("POSTGRES_HOST", "console-db")
    POSTGRES_PORT = os.getenv("POSTGRES_PORT", "5432")

    # ----------------------
    # Logging
    # ----------------------
    LOGGING_CONFIG_PATH = os.getenv("LOGGING_CONFIG_PATH", "src/config/log.py")

    # ----------------------
    # Caching (Redis)
    # ----------------------
    CACHE_PROTOCOL = os.getenv("CACHE_PROTOCOL", "redis")
    CACHE_USERNAME = os.getenv("CACHE_USERNAME", "default")
    CACHE_PASSWORD = os.getenv("CACHE_PASSWORD", "pwd")
    CACHE_HOST = os.getenv("CACHE_HOST", "console-redis")
    CACHE_PORT = os.getenv("CACHE_PORT", "6379")
    CACHE_DB = os.getenv("CACHE_DB", "1")

    # ----------------------
    # TLS Certificates
    # ----------------------
    CERT = os.getenv("CERT", "None")
    KEY = os.getenv("KEY", "None")

    # ----------------------
    # Payment Configs
    # ----------------------

    RAZORPAY_KEY_ID = os.getenv("RAZORPAY_KEY_ID", "")
    RAZORPAY_KEY_SECRET = os.getenv("RAZORPAY_KEY_SECRET", "")
    RAZORPAY_WEBHOOK_SECRET = os.getenv("RAZORPAY_WEBHOOK_SECRET", "")

    PAYMENT_CLIENT = os.getenv("PAYMENT_CLIENT", "")

    # ----------------------
    # Telephony gRPC (Phase-2: console-core as CLIENT)
    # ----------------------
    # Address of the telephony plane's gRPC server (mock: localhost:50052).
    TELEPHONY_GRPC_URL = os.getenv("TELEPHONY_GRPC_URL", "")
    # API key sent as x-api-key metadata on every outbound call.
    TELEPHONY_GRPC_API_KEY = os.getenv("TELEPHONY_GRPC_API_KEY", "")
    # Kill-switch: "true" routes GetCallStatus via gRPC, else HTTP path.
    TELEPHONY_VIA_GRPC = os.getenv("TELEPHONY_VIA_GRPC", "false")

    # ----------------------
    # Relay gate (Phase-3b: rate-limit per caller key, per minute)
    # ----------------------
    RELAY_RATE_LIMIT_PER_MINUTE = os.getenv("RELAY_RATE_LIMIT_PER_MINUTE", "60")

    # Relay client default (talko-role callers; demo/tests override)
    # ----------------------
    RELAY_GRPC_URL = os.getenv("RELAY_GRPC_URL", "")

    # MongoDB Configs
    # ----------------------
    MONGO_DB = os.getenv("MONGO_DB")
    MONGO_USER = os.getenv("MONGO_USER")
    MONGO_PASSWORD = os.getenv("MONGO_PASSWORD")
    MONGO_HOST = os.getenv("MONGO_HOST")
    MONGO_PORT = os.getenv("MONGO_PORT")

    # User Walkthrough Configs
    # ----------------------

    WALKTHROUGH_LAUNCH_DATE = os.getenv("WALKTHROUGH_LAUNCH_DATE")

    # ----------------------
    # Validation
    # ----------------------
    @classmethod
    def validate_env_vars(cls):
        """
        Validate that all required environment variables are defined.
        """
        missing_vars = [
            var
            for var in cls.__dict__
            if not var.startswith("__") and not getattr(cls, var)
        ]
        if missing_vars:
            raise EnvironmentError(
                "The following required environment variables are missing or empty: {}".format(
                    ", ".join(missing_vars)
                )
            )


# Run validation only if ENV is set
if os.getenv("ENV"):
    ENV.validate_env_vars()
