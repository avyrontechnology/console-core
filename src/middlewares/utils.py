from fastapi import Request

from src.middlewares.constants import OPTIONAL_AUTH_PATHS


class MiddlewareUtils:

    @staticmethod
    def is_optional_permission_path(request: Request) -> bool:
        return any(request.url.path.endswith(path) for path in OPTIONAL_AUTH_PATHS)
