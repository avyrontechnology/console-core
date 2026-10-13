from functools import wraps

from fastapi import Request


def permission_check(permission_name: str, permission_class=None):
    """
    Decorator to check a permission for a route.

    Args:
        permission_name: Explicit permission slug, e.g. "console:plan_create".
            Written out at each route so renames are reviewable and greppable —
            never derived from function names at runtime.
        permission_class: Class implementing the permission check logic.
            Defaults to PermissionDependency (imported lazily to avoid cycles).
    """
    if permission_class is None:
        from src.components.rbac.permission_dependency import PermissionDependency

        permission_class = PermissionDependency

    def decorator(func):
        @wraps(func)
        async def wrapper(request: Request, *args, **kwargs):
            # Create an instance of the permission class and perform the check
            instance = permission_class(permission_name=permission_name)
            await instance(
                request=request,
            )

            # Proceed with the original function
            return await func(request, *args, **kwargs)

        return wrapper

    return decorator
