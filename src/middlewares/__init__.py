from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware import Middleware

from .allowed_hosts import AllowedHostsMiddleware
from .authentication import AuthMiddleware
from .context import ContextMiddleware
from .logging_request_and_response import RequestResponseLoggingMiddleware
from src.config.settings import local_settings

# from src.components.services.email_service import EmailService
# from src.core.container import Container
# from src.middlewares.exception import ErrorHandlingMiddleware


# container = Container()

# email_service_instance: EmailService = container.email_service()

# All these values will come from env file

allow_methods = ["*"]
allow_headers = ["*"]

origins = local_settings.cors_origins_list()
allow_hosts = local_settings.allowed_hosts_list()

allowed_middlewares = [
    Middleware(ContextMiddleware),
    Middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=True,
        allow_headers=allow_headers,
        allow_methods=allow_methods,
    ),
    Middleware(AllowedHostsMiddleware, allowed_hosts=allow_hosts),
    Middleware(AuthMiddleware),
    Middleware(RequestResponseLoggingMiddleware),
    # Middleware(ErrorHandlingMiddleware, error_email_service=email_service_instance),
]
