from fastapi import Request

from src.middlewares.constants import OPTIONAL_AUTH_ROUTES


class MiddlewareUtils:

    @staticmethod
    def is_optional_permission_path(request: Request) -> bool:
        try:
            scope = request.scope
        except AttributeError:
            scope = None
        route = scope.get("route") if isinstance(scope, dict) else None
        route_name = getattr(route, "name", None) or getattr(route, "path", None)
        return route_name in OPTIONAL_AUTH_ROUTES
