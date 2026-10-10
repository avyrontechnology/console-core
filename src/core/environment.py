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
    APP_ACCESS_TOKEN_EXPIRE_MINUTES = os.getenv("APP_ACCESS_TOKEN_EXPIRE_MINUTES")

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
    # Mail Configs (MailMG)
    # ----------------------
    MAILMG_CLIENT_NAME = os.getenv("MAILMG_CLIENT_NAME", "")
    MAILMG_CHANNEL_KEY = os.getenv("MAILMG_CHANNEL_KEY", "")
    MAILMG_API_URL = os.getenv("MAILMG_API_URL", "")
    MAILMG_NO_REPLY_CHANNEL_KEY = os.getenv("MAILMG_NO_REPLY_CHANNEL_KEY", "")

    # ----------------------
    # Babbler Configs
    # ----------------------

    BABBLER_OTP_TEMPLATE_NAME = os.getenv("BABBLER_OTP_TEMPLATE_NAME", "")
    BABBLER_OTP_SENDER_NUMBER = os.getenv("BABBLER_OTP_SENDER_NUMBER", "")
    BABBLER_PHONE_NUMBER_ID = os.getenv("BABBLER_PHONE_NUMBER_ID", "")
    BABBLER_BASE_URL = os.getenv("BABBLER_BASE_URL", "")

    # ----------------------
    # External API (Maglo)
    # ----------------------
    MAGLO_LEAD_INBOUND_API = os.getenv("MAGLO_LEAD_INBOUND_API", "")
    SOURCE_KEY = os.getenv("SOURCE_KEY", "")
    CHANNEL_KEY = os.getenv("CHANNEL_KEY", "")

    # ----------------------
    # Payment Configs
    # ----------------------

    RAZORPAY_KEY_ID = os.getenv("RAZORPAY_KEY_ID", "")
    RAZORPAY_KEY_SECRET = os.getenv("RAZORPAY_KEY_SECRET", "")
    RAZORPAY_WEBHOOK_SECRET = os.getenv("RAZORPAY_WEBHOOK_SECRET", "")

    PAYMENT_CLIENT = os.getenv("PAYMENT_CLIENT", "")
    # Maglo COnfig
    # ----------------------
    MAGLO_BASE_URL = os.getenv("MAGLO_BASE_URL", "")

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
    # Maglo Mailer Configs
    # ----------------------

    MAGLO_MAILER_CHANNEL_KEY = os.getenv("MAGLO_MAILER_CHANNEL_KEY")

    FIREBASE_CREDENTIALS_MAGLO_JSON = os.getenv("FIREBASE_CREDENTIALS_MAGLO_JSON", '{"type": "service_account", "project_id": "your-project", "private_key_id": "...", "private_key": "-----BEGIN PRIVATE KEY-----\n...\n-----END PRIVATE KEY-----\n", "client_email": "...", "client_id": "...", "auth_uri": "...", "token_uri": "...", "auth_provider_x509_cert_url": "...", "client_x509_cert_url": "..."}')
    FIREBASE_CREDENTIALS_BABBLER_JSON = os.getenv("FIREBASE_CREDENTIALS_BABBLER_JSON", '{"type": "service_account","project_id": "babbler-app-da3d7","private_key_id": "...","private_key": "-----BEGIN PRIVATE KEY-----\n...\n-----END PRIVATE KEY-----\n","client_email": "...","client_id": "...","auth_uri": "...","token_uri": "...","auth_provider_x509_cert_url": "...","client_x509_cert_url": "..."}')
    # ----------------------
    # OAuth 2.1 self-hosted authorization server
    # ----------------------
    # Only the *truthy-default* OAuth knobs live on this class so
    # validate_env_vars() (which rejects any empty-string class attr when
    # ENV is set) stays happy in deployments where OAuth is disabled. The
    # URL-shaped variables (OAUTH_ISSUER_URL, OAUTH_RESOURCE_URL,
    # OAUTH_LOGIN_REDIRECT_URL, OAUTH_CONSENT_REDIRECT_URL) are read inline
    # by ``src/components/oauth_server/config.py`` via ``os.getenv`` — they
    # don't need a redundant declaration here.
    #
    # Master gate — when "false" the OAuth routes are never registered. Safe
    # to leave "false" on every existing deployment; flipping to "true"
    # requires OAUTH_ISSUER_URL and OAUTH_SIGNING_KEY_PATH to be set.
    OAUTH_ENABLED = os.getenv("OAUTH_ENABLED", "false")

    # Directory of *.pem RSA signing keys (filename minus extension = kid).
    OAUTH_SIGNING_KEY_PATH = os.getenv("OAUTH_SIGNING_KEY_PATH", "/secrets/oauth-keys")

    # Token TTLs (seconds).
    OAUTH_ACCESS_TOKEN_TTL_SECONDS = os.getenv("OAUTH_ACCESS_TOKEN_TTL_SECONDS", "3600")
    OAUTH_REFRESH_TOKEN_TTL_SECONDS = os.getenv("OAUTH_REFRESH_TOKEN_TTL_SECONDS", "2592000")
    OAUTH_AUTH_CODE_TTL_SECONDS = os.getenv("OAUTH_AUTH_CODE_TTL_SECONDS", "600")
    OAUTH_AUTHORIZE_REQUEST_TTL_SECONDS = os.getenv("OAUTH_AUTHORIZE_REQUEST_TTL_SECONDS", "600")

    # DCR abuse guards.
    OAUTH_REGISTRATION_ENABLED = os.getenv("OAUTH_REGISTRATION_ENABLED", "true")
    OAUTH_REGISTRATION_RATE_PER_IP_PER_HOUR = os.getenv(
        "OAUTH_REGISTRATION_RATE_PER_IP_PER_HOUR", "30"
    )
    OAUTH_REGISTRATION_RATE_GLOBAL_PER_HOUR = os.getenv(
        "OAUTH_REGISTRATION_RATE_GLOBAL_PER_HOUR", "1000"
    )

    # Dev-only: allow http://127.0.0.1 redirect URIs at registration time.
    OAUTH_ALLOW_LOCAL_REDIRECT = os.getenv("OAUTH_ALLOW_LOCAL_REDIRECT", "false")


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
