"""
Package: rbac (Role Based Access Control System)

This package is designed to manage role-based access control (RBAC) for FastAPI applications. It provides a modular, scalable, and flexible solution for efficiently handling role and permission validation for a large number of users.

Modules:
---------
1. `role_permission_handler`:
    This module contains the `RolePermissionHandler` class, which is responsible for:
    - Retrieving and validating roles and permissions from JWT tokens.
    - Checking user access based on roles and permissions for specific API endpoints.
    - Supporting various permission validation strategies such as role-based and permission-based access control.

2. `role_permission_dependency`:
    This module provides the `RolePermissionDependency` class, which injects role and permission data into FastAPI routes.
    - Dynamically retrieves the user’s role and permissions from the token and provides them as dependencies for API endpoints.
    - Ensures that role-based access checks are efficiently handled for large-scale systems.

"""
