# from src.main import app
import fastapi
from fastapi import Request
from fastapi.exceptions import RequestValidationError

from src.components.common.response import BadRequestResponse


def handler(app: fastapi):

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(
        request: Request, exc: RequestValidationError
    ):
        custom_errors = exc.errors()[0]["msg"]
        custom_errors = custom_errors.removeprefix("Value error,").strip()
        return BadRequestResponse(custom_errors)
