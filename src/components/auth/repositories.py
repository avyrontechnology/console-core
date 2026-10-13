import uuid
from uuid import UUID
from contextlib import AbstractContextManager
from datetime import datetime, timedelta, timezone
from typing import Callable, List, Optional

from sqlalchemy import and_, func, literal, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, aliased

from src.components.auth.constant import (
    AuthExceptionMsg,
    OtpConstants,
    OtpType,
    RoleDictKeys,
)
from src.components.auth.error import PermissionNotFoundError, RoleNotFoundError
from src.components.auth.models import OTP, Permission, Role
from src.components.auth.schema import PermissionData, RoleData, UpdatePermissionRquest
from src.components.common.datetime import DateTimeUtil
from src.components.default_role_permission.models import DefaultRolePermission
from src.components.partner_role_permission.models import PartnerRolePermission
from src.components.user.models import User
from src.exceptions import AuthException
from src.loggers.console_service_logger import ConsoleServiceLogger


class AuthRepository:

    def __init__(
        self,
        session_factory: Callable[..., AbstractContextManager[Session]],
        auth_service_logger: ConsoleServiceLogger = ConsoleServiceLogger(),
    ) -> None:
        self.__session_factory: Callable[..., AbstractContextManager[Session]] = (
            session_factory
        )
        self.__auth_service_logger: ConsoleServiceLogger = auth_service_logger

    async def add_role(
        self,
        user_role: RoleData,
        user_id: UUID,
    ) -> Role:
        try:
            async with self.__session_factory() as session:
                role = Role(
                    name=user_role.name,
                    slug=user_role.slug,
                    hierarchy=user_role.hierarchy,
                    description=user_role.description,
                    created_by=user_id,
                    is_internal=user_role.is_internal,
                )
                session.add(role)
                await session.commit()
                await session.refresh(role)
                self.__auth_service_logger.info(
                    "Role '{}' created successfully".format(role.name)
                )
                return role
        except IntegrityError as ex:
            self.__auth_service_logger.error(
                "IntegrityError while creating role: {}".format(str(ex))
            )
            raise AuthException(AuthExceptionMsg.ROLE_EXISTS)
        except Exception as ex:
            self.__auth_service_logger.error(
                "Error while creating role: {}".format(str(ex))
            )
            raise ex

    async def get_role_by_id(self, id: UUID) -> Role:
        try:
            async with self.__session_factory() as session:
                query = select(Role).where(Role.id == id, Role.is_active == True)
                result = await session.execute(query)
                role = result.scalars().one_or_none()
                if not role:
                    self.__auth_service_logger.error(
                        "Role not found: id: {}".format(id)
                    )
                    raise RoleNotFoundError(id)
                self.__auth_service_logger.info(
                    "Role '{}' get successfully".format(role.name)
                )
                return role
        except RoleNotFoundError as ex:
            self.__auth_service_logger.error("Not found role by id: {}".format(str(ex)))
            raise ex
        except Exception as ex:
            self.__auth_service_logger.error(
                "Error while fetching role by id: {}".format(str(ex))
            )
            raise ex

    async def resolve_role_for_partner(self, role_id: UUID, partner_id: UUID) -> int:
        """Return the partner-owned copy of role_id (matched by slug) if available, else role_id."""
        async with self.__session_factory() as session:
            result = await session.execute(select(Role.slug).where(Role.id == role_id))
            slug = result.scalar_one_or_none()
            if slug is None:
                return role_id
            result = await session.execute(
                select(Role.id).where(
                    Role.partner_id == partner_id,
                    Role.slug == slug,
                    Role.is_active == True,    # noqa: E712
                    Role.is_deleted == False,  # noqa: E712
                )
            )
            partner_role_id = result.scalar_one_or_none()
            return partner_role_id if partner_role_id is not None else role_id

    async def get_all_role(
        self, is_internal_partner: bool, partner_id: Optional[UUID] = None
    ) -> List[Role]:
        try:
            async with self.__session_factory() as session:
                filters = [Role.is_active == True]
                if not is_internal_partner:
                    filters.append(Role.is_internal == False)
                if partner_id is not None:
                    filters.append(Role.partner_id == partner_id)
                else:
                    filters.append(Role.partner_id.is_(None))

                roles = (
                    (await session.execute(select(Role).where(*filters)))
                    .scalars()
                    .all()
                )
                self.__auth_service_logger.info("All roles fetched successfully")
                return roles
        except Exception as ex:
            self.__auth_service_logger.error(
                "Error while fetching all roles: {}".format(str(ex))
            )
            raise ex

    async def delete_role(self, id: UUID, user_id: UUID) -> Role:
        try:
            async with self.__session_factory() as session:
                query = select(Role).where(Role.id == id, Role.is_active == True)
                result = await session.execute(query)
                role = result.scalars().one_or_none()
                if not role:
                    self.__auth_service_logger.warning(
                        "Role not found for deletion: id={}".format(id)
                    )
                    raise RoleNotFoundError(id)
                role.is_deleted = True
                role.is_active = False
                role.deleted_at = DateTimeUtil.get_current_time()
                role.deleted_by = user_id
                role.slug = str(role.id) + "_" + role.slug
                await session.commit()
                await session.refresh(role)
                self.__auth_service_logger.info(
                    "Role '{}' deleted successfully".format(role.name)
                )
                return role
        except RoleNotFoundError as ex:
            raise ex
        except Exception as ex:
            self.__auth_service_logger.error(
                "Error while deleting role: {}".format(str(ex))
            )
            raise ex

    async def add_permission(
        self,
        user_permission: PermissionData,
        user_id: UUID,
    ) -> Permission:
        try:
            self.__auth_service_logger.info(
                "Attempting to create a new permission: {}".format(
                    user_permission.title
                )
            )
            user_permission_dict: dict = user_permission.model_dump(exclude_unset=True)
            async with self.__session_factory() as session:
                # Create a new Permission object with the provided data
                if "is_internal" not in user_permission_dict:
                    permission = Permission(
                        **user_permission_dict, is_internal=user_permission.is_internal
                    )
                else:
                    permission = Permission(**user_permission_dict)

                session.add(permission)
                await session.commit()
                await session.refresh(permission)

                self.__auth_service_logger.info(
                    "Permission '{}' created successfully".format(permission.title)
                )

                return permission
        except IntegrityError as ex:
            self.__auth_service_logger.error(
                "IntegrityError while creating permission: {}".format(str(ex))
            )
            raise AuthException(AuthExceptionMsg.PERMISSIONS_EXISTS)
        except Exception as ex:
            self.__auth_service_logger.error(
                "Error while creating permission: {}".format(str(ex))
            )
            raise ex

    async def get_all_permission(self) -> List[Permission]:
        try:
            async with self.__session_factory() as session:
                permissions = (
                    (
                        await session.execute(
                            select(Permission).where(Permission.is_active == True)
                        )
                    )
                    .scalars()
                    .all()
                )
                self.__auth_service_logger.info("All permissions fetched successfully")
                return permissions
        except Exception as ex:
            self.__auth_service_logger.error(
                "Error while fetching all permissions: {}".format(str(ex))
            )
            raise

    # get permission object by id
    async def get_permission_by_id(self, id: UUID) -> Permission:
        try:
            async with self.__session_factory() as session:
                query = select(Permission).where(
                    Permission.id == id, Permission.is_active == True
                )
                result = await session.execute(query)
                permission = result.scalars().one_or_none()
                if not permission:
                    self.__auth_service_logger.error(
                        "Permission not found: id={}".format(id)
                    )
                    raise PermissionNotFoundError(id)
                return permission
        except PermissionNotFoundError as ex:
            self.__auth_service_logger.error(f"Role not found: {str(ex)}")
            raise ex
        except Exception as ex:
            self.__auth_service_logger.error(
                "Error while fetching permission by id: {}".format(str(ex))
            )
            raise ex

    async def delete_permission(self, id: UUID, user_id: UUID) -> Permission:
        try:
            async with self.__session_factory() as session:
                self.__auth_service_logger.info("Getting permission form DataBase")
                query = select(Permission).where(
                    Permission.id == id, Permission.is_active == True
                )
                result = await session.execute(query)
                permission = result.scalars().one_or_none()
                if not permission:
                    self.__auth_service_logger.warning(
                        "Permission not found for deletion: id={}".format(id)
                    )
                    raise PermissionNotFoundError(id)
                # Set soft delete flags
                permission.is_deleted = True
                permission.is_active = False
                permission.deleted_at = DateTimeUtil.get_current_time()
                permission.deleted_by = user_id
                permission.slug = str(permission.id) + "_" + permission.slug
                await session.commit()
                await session.refresh(permission)

                self.__auth_service_logger.info(
                    "Permission '{}' deleted successfully".format(permission.id)
                )
                return permission
        except PermissionNotFoundError as ex:
            raise ex
        except Exception as ex:
            self.__auth_service_logger.error(
                "Error while deleting permission: {}".format(str(ex))
            )
            raise ex

    async def get_user_permission(self, user_id: UUID) -> List[str]:
        try:
            async with self.__session_factory() as session:
                self.__auth_service_logger.info(
                    "Attempting to get list of user permissions ID: {}".format(user_id)
                )
                user_partner = aliased(User)

                query = (
                    select(Permission.slug)
                    .select_from(Permission)
                    .join(
                        PartnerRolePermission,
                        Permission.id == PartnerRolePermission.permission_id,
                    )
                    .join(
                        user_partner,
                        user_partner.partner_id == PartnerRolePermission.partner_id,
                    )
                    .where(user_partner.id == user_id)
                    .where(user_partner.role_id == PartnerRolePermission.role_id)
                )

                result = await session.execute(query)
                permissions = result.scalars().all()
                self.__auth_service_logger.info(
                    "All permissions fetched successfully {}".format(permissions)
                )
                return permissions
        except Exception as ex:
            self.__auth_service_logger.error(
                "Unexpected error during list of user permission {}".format(str(ex))
            )
            raise ex

    async def get_role_by_user_id(self, user_id: UUID) -> dict:
        try:
            async with self.__session_factory() as session:
                query = (
                    select(Role.slug, Role.hierarchy)
                    .select_from(User)
                    .join(Role, User.role_id == Role.id)
                    .where(User.id == user_id, Role.is_active == True)
                )
                result = await session.execute(query)
                role = result.one_or_none()
                user_role = {
                    RoleDictKeys.SLUG: role.slug,
                    RoleDictKeys.HIERARCHY: role.hierarchy,
                }
                return user_role
        except Exception as ex:
            self.__auth_service_logger.error(
                "Error while fetching role name and hierarchy by user_id: {}".format(
                    str(ex)
                )
            )
            raise ex

    async def reset_password(self, hashed_password: str, user: User) -> None:
        try:
            async with self.__session_factory() as session:
                self.__auth_service_logger.info("Attempting to update hash password")

                query = (
                    update(User)
                    .where(User.id == user.id)
                    .values(hashed_password=hashed_password)
                )
                await session.execute(query)
                await session.commit()
                return
        except Exception as exc:
            self.__auth_service_logger.error(
                "Error while updating password: {}".format(str(exc))
            )
            raise exc

    async def get_parent_users_by_role_id(
        self, role_id: UUID, partner_id: UUID
    ) -> List[User]:
        try:
            async with self.__session_factory() as session:
                self.__auth_service_logger.info(
                    "Attempting to get all parents by role id: {}".format(role_id)
                )
                role_query = select(Role.hierarchy).where(Role.id == role_id)
                role_result = await session.execute(role_query)
                role_hierarchy: int = role_result.scalar_one_or_none()

                if role_hierarchy is None:
                    self.__auth_service_logger.error(
                        "Role not found by id: {}".format(role_id)
                    )
                    raise RoleNotFoundError(role_id)

                filters = [
                    User.partner_id == partner_id,
                    User.is_active == True,
                ]

                if role_hierarchy > 0:
                    filters.append(
                        and_(Role.hierarchy > 0, Role.hierarchy < role_hierarchy)
                    )
                else:
                    filters.append(
                        and_(Role.hierarchy > role_hierarchy, Role.hierarchy < 1)
                    )

                self.__auth_service_logger.info(
                    "Role hierarchy fetched successfully : {} now fetching all the parents of current role hierarchy...".format(
                        role_hierarchy
                    )
                )

                parents_query = (
                    select(User).join(Role, User.role_id == Role.id).where(*filters)
                )
                result = await session.execute(parents_query)
                parents = result.scalars().all()

                self.__auth_service_logger.info(
                    "All parents fetched successfully: {}".format(parents)
                )
                return parents
        except RoleNotFoundError as exec:
            self.__auth_service_logger.error(
                "Role not found by id: {}".format(str(exec))
            )
            raise exec
        except Exception as exec:
            self.__auth_service_logger.error(
                "Error while fetching parents by role id: {}".format(str(exec))
            )
            raise exec

    async def get_default_role_permission_for_user(self, user_id: UUID) -> List[str]:
        """
        Fetch permission slugs for a user from DefaultRolePermission mapping.
        """
        try:
            async with self.__session_factory() as session:
                self.__auth_service_logger.info(
                    f"Attempting to get default role permissions for user ID: {user_id}"
                )
                user_alias = aliased(User)

                query = (
                    select(Permission.slug)
                    .select_from(Permission)
                    .join(
                        DefaultRolePermission,
                        Permission.id == DefaultRolePermission.permission_id,
                    )
                    .join(
                        user_alias,
                        user_alias.role_id == DefaultRolePermission.role_id,
                    )
                    .where(user_alias.id == user_id)
                )

                result = await session.execute(query)
                permissions = result.scalars().all()
                self.__auth_service_logger.info(
                    f"Default role permissions fetched successfully: {permissions}"
                )
                return permissions
        except Exception as ex:
            self.__auth_service_logger.error(
                f"Unexpected error during fetching default role permissions for user: {str(ex)}"
            )
            raise ex

    async def get_partner_role_permissions_by_partner_and_role(
        self, partner_id: UUID, role_id: UUID
    ) -> List[Permission]:
        """
        Fetch full Permission objects for a partner and role from PartnerRolePermission mapping.
        """
        try:
            async with self.__session_factory() as session:
                query = (
                    select(Permission)
                    .join(
                        PartnerRolePermission,
                        Permission.id == PartnerRolePermission.permission_id,
                    )
                    .where(
                        PartnerRolePermission.partner_id == partner_id,
                        PartnerRolePermission.role_id == role_id,
                    )
                )
                result = await session.execute(query)
                permissions = result.scalars().all()
                return permissions
        except Exception as ex:
            self.__auth_service_logger.error(
                f"Error fetching partner role permissions for partner_id={partner_id}, role_id={role_id}: {str(ex)}"
            )
            raise ex

    async def get_default_role_permissions_by_role_id(
        self, role_id: UUID
    ) -> List[Permission]:
        """
        Fetch full Permission objects for a role from DefaultRolePermission mapping.
        """
        try:
            async with self.__session_factory() as session:
                query = (
                    select(Permission)
                    .join(
                        DefaultRolePermission,
                        Permission.id == DefaultRolePermission.permission_id,
                    )
                    .where(DefaultRolePermission.role_id == role_id)
                )
                result = await session.execute(query)
                permissions = result.scalars().all()
                return permissions
        except Exception as ex:
            self.__auth_service_logger.error(
                f"Error fetching default role permissions for role_id={role_id}: {str(ex)}"
            )
            raise ex

    async def get_default_role_permission_matrix(
        self,
        is_internal_permission: Optional[bool] = False,
        filter_partner_id: Optional[UUID] = None,
    ):
        try:
            async with self.__session_factory() as session:
                self.__auth_service_logger.info(
                    "fetching all default and partner role permissions"
                )
                filters = [Permission.is_active == True]

                if is_internal_permission:
                    filters.append(Permission.is_internal == True)
                    filters.append(Role.is_internal == True)
                else:
                    filters.append(Permission.is_internal == False)
                    filters.append(Role.is_internal == False)

                if filter_partner_id is not None:
                    filters.append(Role.partner_id == filter_partner_id)
                else:
                    filters.append(Role.partner_id.is_(None))

                dafault_permission = aliased(DefaultRolePermission)

                query = (
                    select(
                        Role.id.label("role_id"),
                        Role.name.label("role_name"),
                        func.coalesce(
                            Permission.category, literal("Uncategorized")
                        ).label("category"),
                        Permission.slug,
                        Permission.id.label("permission_id"),
                        Permission.created_at,
                        Permission.description,
                        Permission.display_text,
                        (dafault_permission.permission_id != None).label("is_default"),
                    )
                    .select_from(Role)
                    .join(Permission, literal(True))
                    .outerjoin(
                        dafault_permission,
                        (dafault_permission.role_id == Role.id)
                        & (dafault_permission.permission_id == Permission.id),
                    )
                    .where(*filters)
                    .order_by(Role.id, Permission.category, Permission.id)
                )

                result = await session.execute(query)
                response = result.fetchall()
                self.__auth_service_logger.info(
                    "Permission matrix fetched successfully: {}".format(response)
                )
                return response
        except Exception as exec:
            self.__auth_service_logger.error(
                "Failed to fetch permission matrix: {}".format(exec)
            )
            raise exec

    async def update_permission(
        self, permission_id: UUID, permission_data: UpdatePermissionRquest
    ) -> Permission:
        try:
            async with self.__session_factory() as session:
                self.__auth_service_logger.info(
                    "Attempting to update permission with ID: {}".format(permission_id)
                )

                query = select(Permission).where(
                    Permission.id == permission_id, Permission.is_active == True
                )
                result = await session.execute(query)
                permission = result.scalars().one_or_none()

                if not permission:
                    self.__auth_service_logger.error(
                        "Permission not found: id={}".format(permission_id)
                    )
                    raise PermissionNotFoundError(permission_id)

                # Update the permission fields
                for key, value in permission_data.model_dump(
                    exclude_unset=True
                ).items():
                    setattr(permission, key, value)

                await session.commit()
                await session.refresh(permission)

                self.__auth_service_logger.info(
                    "Permission '{}' updated successfully".format(permission.title)
                )
                return permission
        except PermissionNotFoundError as exec:
            self.__auth_service_logger.error(
                "Permission not found: {}".format(str(exec))
            )
            raise exec
        except IntegrityError as exec:
            self.__auth_service_logger.error(
                "IntegrityError while updating permission: {}".format(str(exec))
            )
            raise AuthException(AuthExceptionMsg.PERMISSIONS_EXISTS)
        except Exception as exec:
            self.__auth_service_logger.error(
                "Error while updating permission: {}".format(str(exec))
            )
            raise exec

    async def get_internal_permissions(self) -> List[str]:
        try:
            async with self.__session_factory() as session:
                self.__auth_service_logger.info("Getting internal permissions")

                query = select(Permission.slug).where(Permission.is_internal == True)
                result = await session.execute(query)
                permissions: List[str] = list(result.scalars().all())
                return permissions

        except Exception as exc:
            self.__auth_service_logger.error(
                "Got the unexcpected Error: {}".format(exc)
            )
            raise exc

    async def update_role(
        self,
        role_id: UUID,
        **role_data,
    ) -> Role:
        try:
            async with self.__session_factory() as session:
                self.__auth_service_logger.info(
                    "Attempting to update role with ID: {}".format(role_id)
                )

                query = select(Role).where(Role.id == role_id, Role.is_active == True)
                result = await session.execute(query)
                role = result.scalars().one_or_none()

                if not role:
                    self.__auth_service_logger.error(
                        "Role not found: id={}".format(role_id)
                    )
                    raise RoleNotFoundError(role_id)

                # Update the role fields
                for key, value in role_data.items():
                    setattr(role, key, value)

                await session.commit()
                await session.refresh(role)

                self.__auth_service_logger.info(
                    "Role '{}' updated successfully".format(role.name)
                )
                return role
        except RoleNotFoundError as exec:
            self.__auth_service_logger.error("Role not found: {}".format(str(exec)))
            raise exec
        except IntegrityError as exec:
            self.__auth_service_logger.error(
                "IntegrityError while updating role: {}".format(str(exec))
            )
            raise AuthException(AuthExceptionMsg.ROLE_EXISTS)
        except Exception as exec:
            self.__auth_service_logger.error(
                "Error while updating role: {}".format(str(exec))
            )
            raise exec

    async def get_role_by_hierarchy(self, hierarchy: int) -> Role:
        try:
            self.__auth_service_logger.info(
                "Getting role details by hierarchy: {}.".format(hierarchy)
            )
            async with self.__session_factory() as session:
                query = select(Role).where(
                    Role.hierarchy == hierarchy,
                    Role.is_active == True,
                    Role.partner_id.is_(None),
                )
                result = await session.execute(query)
                role = result.scalars().one_or_none()
                return role
        except Exception as ex:
            self.__auth_service_logger.error(
                "Error while fetching role by hierarchy: {}, error: {}".format(
                    hierarchy, str(ex)
                )
            )
            raise ex

    async def create_otp(
        self, user_id: UUID, otp_type: OtpType, additional_info: dict = None
    ) -> OTP:
        """
        Async method to create or update OTP for a user per type.
        Only one OTP per (user_id, otp_type) exists.
        """
        try:
            self.__auth_service_logger.info(
                "Creating/updating OTP for user_id: {}, otp_type: {}.".format(
                    user_id, otp_type
                )
            )

            otp_value = str(uuid.uuid4().int)[:6]
            expires_at = int(
                (
                    datetime.now(timezone.utc)
                    + timedelta(minutes=OtpConstants.OTP_TIMEOUT)
                ).timestamp()
                * 1000
            )

            async with self.__session_factory() as session:
                query = select(OTP).where(
                    OTP.user_id == user_id, OTP.otp_type == otp_type
                )
                result = await session.execute(query)
                existing_otp = result.scalars().one_or_none()

                if existing_otp:
                    existing_otp.otp = otp_value
                    existing_otp.expires_at = expires_at
                    existing_otp.is_used = False
                    existing_otp.additional_info = additional_info
                    session.add(existing_otp)
                    await session.commit()
                    await session.refresh(existing_otp)
                    return existing_otp

                # Create new OTP
                new_otp = OTP(
                    user_id=user_id,
                    otp=otp_value,
                    otp_type=otp_type,
                    expires_at=expires_at,
                    additional_info=additional_info,
                )
                session.add(new_otp)
                await session.commit()
                await session.refresh(new_otp)
                return new_otp

        except Exception as ex:
            self.__auth_service_logger.error(
                "Error while creating/updating OTP for user_id: {}, otp_type: {}, error: {}".format(
                    user_id, otp_type, str(ex)
                )
            )
            raise ex

    async def get_active_otp(
        self, user_id: UUID, otp_type: OtpType, otp: str
    ) -> OTP | None:
        """
        Fetch OTP for a user that is:
        - Not used
        - Not expired
        - Matching the input OTP
        """

        async with self.__session_factory() as session:
            query = select(OTP).where(
                OTP.user_id == user_id,
                OTP.otp_type == otp_type.value,
                OTP.otp == otp,
                OTP.is_used.is_(False),
                OTP.expires_at > int(DateTimeUtil.get_current_time()),
            )
            result = await session.execute(query)
            return result.scalars().one_or_none()

    async def update_otp(self, otp_entry: OTP) -> None:
        """
        Update OTP entry (mark as used, update expiry, etc.)
        """
        try:
            async with self.__session_factory() as session:
                session.add(otp_entry)
                await session.commit()
                await session.refresh(otp_entry)
        except Exception as ex:
            self.__auth_service_logger.error(
                f"Error updating OTP for user_id={otp_entry.user_id}, otp_type={otp_entry.otp_type}: {str(ex)}"
            )
            raise ex

    async def get_all_roles(self, is_internal_partner: bool = False) -> List[dict]:
        """
        Fetch all active, non-deleted roles and return them as plain dicts.

        Args:
            is_internal_partner: When True, internal roles are included.
                Partners are never internal by default, so this defaults to False —
                only non-internal roles are returned unless explicitly requested.

        Returns:
            List of dicts with keys: id, name, slug, hierarchy,
            is_internal, is_active. Empty list if none found.
        """
        try:
            async with self.__session_factory() as session:
                filters = [
                    Role.is_active.is_(True),
                    Role.is_deleted.is_(False),
                ]
                if not is_internal_partner:
                    filters.append(Role.is_internal.is_(False))

                result = await session.execute(select(Role).where(*filters))
                roles = result.scalars().all()

                self.__auth_service_logger.info(
                    "get_all_roles: returned {} roles "
                    "(is_internal_partner={})".format(len(roles), is_internal_partner)
                )

                return [
                    {
                        "id": role.id,
                        "name": role.name or "",
                        "slug": role.slug or "",
                        "hierarchy": role.hierarchy or 0,
                        "is_internal": bool(role.is_internal),
                        "is_active": bool(role.is_active),
                        "data_scope": role.data_scope or "",
                    }
                    for role in roles
                ]
        except Exception as exc:
            self.__auth_service_logger.error("Error in get_all_roles: {}".format(exc))
            raise

    async def get_ancestor_ids(self, user_id: UUID) -> List[int]:
        try:
            async with self.__session_factory() as session:
                parent_cte = (
                    select(User.id.label("user_id"), User.parent_id)
                    .where(User.id == user_id)
                    .cte(name="parent_cte", recursive=True)
                )
                parent_cte = parent_cte.union_all(
                    select(User.id, User.parent_id)
                    .join(parent_cte, User.id == parent_cte.c.parent_id)
                )
                result = await session.execute(select(parent_cte.c.user_id))
                return [row.user_id for row in result.all()]
        except Exception as ex:
            self.__auth_service_logger.error(
                "Error fetching ancestor ids for user_id {}: {}".format(user_id, ex)
            )
            raise ex
