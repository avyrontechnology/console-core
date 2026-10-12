import traceback

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

from src.loggers.console_service_logger import ConsoleServiceLogger


class ErrorHandlingMiddleware(BaseHTTPMiddleware):
    """
    Middleware for handling errors.

    Captures exceptions and HTTP 500+ status codes and logs details.
    (Error notification emails retired with the mailer — errors are
    log-only now. Wire an external alerting integration here if needed.)
    """

    def __init__(self, app):
        """
        Initialize the ErrorHandlingMiddleware.

        Args:
            app: The FastAPI application instance

        Raises:
            Exception: If initialization fails
        """
        super().__init__(app)
        self.logger = ConsoleServiceLogger()
        try:
            self.logger.info("ErrorHandlingMiddleware initialized successfully")
        except Exception as e:
            self.logger.error(f"Failed to initialize ErrorHandlingMiddleware: {str(e)}")
            raise

    async def dispatch(self, request: Request, call_next):
        """
        Process incoming requests and handle errors.

        Args:
            request: FastAPI Request object
            call_next: Function to call the next middleware or route handler

        Returns:
            Response: HTTP response or error response if an exception occurs

        Raises:
            Exception: Caught and handled to return error response
        """
        self.logger.info(f"Processing request: {request.method} {request.url}")

        try:
            response = await call_next(request)
            self.logger.debug(
                f"Request processed with status: {response.status_code} for {request.url}"
            )

            if response.status_code >= 500:
                self.logger.warning(
                    f"Server error detected: {response.status_code} for {request.url}"
                )

            return response

        except Exception as e:
            trace = traceback.format_exc()
            request_url = str(request.url)

            try:
                error_context = {
                    "url": request_url,
                    "method": request.method,
                    "error": str(e),
                    "trace": trace,
                }
                self.logger.error(f"Unhandled exception caught: {error_context}")

                return Response(
                    content=f"An error occurred ({request_url}): {str(e)}",
                    status_code=500,
                    media_type="text/plain",
                )

            except Exception as response_error:
                self.logger.error(f"Failed to handle exception: {str(response_error)}")
                return Response(
                    content=f"Critical error processing request: {str(e)}",
                    status_code=500,
                    media_type="text/plain",
                )
