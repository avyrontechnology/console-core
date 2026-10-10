from functools import wraps

from fastapi import Request

from src.components.rbac.constant import ServiceName


def permission_check(permission_class):
    """
    Decorator to dynamically check permissions for a route.

    Args:
        permission_class: Class implementing the permission check logic.
    """

    def decorator(func):
        @wraps(func)
        async def wrapper(request: Request, *args, **kwargs):
            # Dynamically retrieve the route name
            route_name = request.scope["route"].name
            permission_name = ServiceName.SERVICE_NAME + ":" + route_name

            # Create an instance of the permission class and perform the check
            instance = permission_class(permission_name=permission_name)
            await instance(
                request=request,  
            )

            # Proceed with the original function
            return await func(request, *args, **kwargs)

        return wrapper

    return decorator
