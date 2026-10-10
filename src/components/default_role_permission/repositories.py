from contextlib import AbstractContextManager
from typing import Callable, Iterator, Optional

from asyncpg.exceptions import UniqueViolationError
from fastapi import HTTPException, status
from sqlalchemy import and_, exists, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from src.components.auth.models import Permission, Role
from src.components.default_role_permission.models import DefaultRolePermission
from src.components.default_role_permission.schemas import DefaultRolePermissionData
from src.components.partner.models import Partner
from src.components.partner_role_permission.models import PartnerRolePermission
from src.components.partner_role_permission.constant import ExceptionMsg
from src.components.partner_role_permission.error import (
    PartnerRolePermissionNotFoundError,
)
from src.exceptions import DefaultRolePermissionException
from src.loggers.console_service_logger import ConsoleServiceLogger


class DefaultRolePermissionRepository:

    def __init__(
        self,
        session_factory: Callable[..., AbstractContextManager[Session]],
        console_service_logger: ConsoleServiceLogger = ConsoleServiceLogger(),
    ) -> None:
        self.__session_factory: Callable[..., AbstractContextManager[Session]] = (
            session_factory
        )
        self.__console_service_logger: ConsoleServiceLogger = console_service_logger

    # add new mapping partner role permission
    async def add_default_role_permission(
        self,
        add_data: DefaultRolePermissionData,
        user_id: int,
    ) -> DefaultRolePermission:
        try:
            async with self.__session_factory() as session:
                # check partner, role, permission is not deleted
                # Create the subqueries for checking existence

                permission_exists_subquery = exists().where(
                    and_(
                        Permission.id == add_data.permission_id,
                        Permission.is_deleted == False,
                    )
                )

                role_exists_subquery = exists().where(
                    and_(Role.id == add_data.role_id, Role.is_deleted == False)
                )

                # Combine all the checks into a single query
                combined_query = select(
                    permission_exists_subquery.label("permission_exists"),
                    role_exists_subquery.label("role_exists"),
                )
                result = await session.execute(combined_query)
                data = result.fetchone()

                if not data.permission_exists:
                    raise DefaultRolePermissionException(
                        ExceptionMsg.PERMISSION_NOT_FOUND
                    )

                if not data.role_exists:
                    raise DefaultRolePermissionException(ExceptionMsg.ROLE_NOT_FOUND)

                self.__console_service_logger.info(
                    "Inserting default role permission mapping for role id: {} and permission id: {}".format(
                        add_data.role_id, add_data.permission_id
                    )
                )
                insert = DefaultRolePermission(
                    permission_id=add_data.permission_id,
                    role_id=add_data.role_id,
                    created_by=user_id,
                )
                session.add(insert)
                await session.commit()
                await session.refresh(insert)
                self.__console_service_logger.info(
                    "Successfully inserted mapping in db for role id: {} and permission id: {}".format(
                        insert.role_id, insert.permission_id
                    )
                )
                return insert
        except UniqueViolationError as exc:
            self.__console_service_logger.error(
                "UniqueViolationError  A record with this combination already exists.{}".format(
                    exc
                )
            )
            raise DefaultRolePermissionException(str(exc))
        except IntegrityError as exc:
            self.__console_service_logger.error(
                "A record with this combination already exists: {}".format(exc)
            )
            raise DefaultRolePermissionException(
                "A record with this combination already exists."
            )
        except DefaultRolePermissionException as exc:
            self.__console_service_logger.error(
                "Unexpected error during inserting partner role permission: {}".format(
                    str(exc)
                )
            )
            raise exc
        except Exception as exc:
            self.__console_service_logger.error(
                "Unexpected error during inserting partner role permission: {}".format(
                    str(exc)
                )
            )
            raise exc

    async def get_default_role_permissions(self, partner_id: Optional[int] = None):
        try:
            async with self.__session_factory() as session:
                self.__console_service_logger.info(
                    "getting all the default role permissions mappings..."
                )
                query = (
                    select(
                        DefaultRolePermission.id.label("id"),
                        DefaultRolePermission.role_id.label("role_id"),
                        DefaultRolePermission.permission_id.label("permission_id"),
                        Permission.title.label("permission_name"),
                    )
                    .join(Permission, Permission.id == DefaultRolePermission.permission_id)
                    .join(Role, Role.id == DefaultRolePermission.role_id)
                    .where(Permission.is_active == True)
                )
                if partner_id is not None:
                    query = query.where(Role.partner_id == partner_id)
                else:
                    query = query.where(Role.partner_id.is_(None))

                result = await session.execute(query)
                self.__console_service_logger.info(
                    "The default role permissions fetched successfully: {}".format(
                        result
                    )
                )
                return result
        except Exception as exec:
            self.__console_service_logger.error(
                "An unexpected error occured while getting default role permission: {}".format(
                    exec
                )
            )
            raise exec

    async def get_default_role_permissions_by_role_id(self, role_id: int):
        try:
            async with self.__session_factory() as session:
                self.__console_service_logger.info(
                    "getting all the default role permissions mappings by role id: {}".format(
                        role_id
                    )
                )
                query = (
                    select(
                        DefaultRolePermission.id.label("id"),
                        DefaultRolePermission.role_id.label("role_id"),
                        DefaultRolePermission.permission_id.label("permission_id"),
                        Permission.title.label("permission_name"),
                    )
                    .join(
                        Permission, Permission.id == DefaultRolePermission.permission_id
                    )
                    .where(DefaultRolePermission.role_id == role_id)
                )
                result = await session.execute(query)
                response = result.fetchall()
                if not response:
                    self.__console_service_logger.error(
                        "No default role permissions found for role id: {}".format(
                            role_id
                        )
                    )
                    raise DefaultRolePermissionException(
                        "No default role permissions found for role id: {}".format(
                            role_id
                        )
                    )
                self.__console_service_logger.info(
                    "The default role permissions fetched successfully: {}".format(
                        result
                    )
                )
                return response
        except DefaultRolePermissionException as exec:
            self.__console_service_logger.error(
                "PartnerRolePermissionException while getting default role permission: {}".format(
                    exec
                )
            )
            raise exec
        except Exception as exec:
            self.__console_service_logger.error(
                "An unexpected error occured while getting default role permission: {}".format(
                    exec
                )
            )
            raise exec

    async def get_permission_ids_by_slugs(self, slugs: list) -> dict:
        """Map active permission slugs -> permission_id. Unknown/inactive slugs are
        simply absent from the returned dict (the caller reports them)."""
        if not slugs:
            return {}
        async with self.__session_factory() as session:
            query = select(Permission.slug, Permission.id).where(
                and_(
                    Permission.slug.in_(slugs),
                    Permission.is_active == True,
                    Permission.is_deleted == False,
                )
            )
            result = await session.execute(query)
            return {row.slug: row.id for row in result.all()}

    async def set_role_action_permissions(
        self,
        role_id: int,
        partner_id: int,
        enable_ids: set,
        disable_ids: set,
        user_id: int,
    ) -> tuple:
        """Diff a partner-owned role's action-flag permissions in one transaction.

        Baseline lives in ``DefaultRolePermission`` keyed by the partner's OWN role
        copy (materialise snapshots it there), so editing it is partner-scoped and
        supports both enable (insert) and disable (delete) — unlike the union-only
        ``PartnerRolePermission`` layer. On disable we also clear any stray
        ``PartnerRolePermission`` row so the effective-permission union can't re-add
        the button. Returns ``(granted_ids, revoked_ids)`` of the rows actually changed.
        """
        async with self.__session_factory() as session:
            touched_ids = enable_ids | disable_ids
            existing_rows = (
                await session.execute(
                    select(DefaultRolePermission).where(
                        and_(
                            DefaultRolePermission.role_id == role_id,
                            DefaultRolePermission.permission_id.in_(touched_ids),
                        )
                    )
                )
            ).scalars().all()
            existing_ids = {row.permission_id: row for row in existing_rows}

            granted_ids: list = []
            for permission_id in enable_ids:
                if permission_id not in existing_ids:
                    session.add(
                        DefaultRolePermission(
                            role_id=role_id,
                            permission_id=permission_id,
                            created_by=user_id,
                        )
                    )
                    granted_ids.append(permission_id)

            revoked_ids: list = []
            for permission_id in disable_ids:
                row = existing_ids.get(permission_id)
                if row is not None:
                    await session.delete(row)
                    revoked_ids.append(permission_id)

            if disable_ids:
                # Clear any partner-custom grant for the disabled permissions so the
                # default ∪ partner union cannot re-enable the button.
                partner_rows = (
                    await session.execute(
                        select(PartnerRolePermission).where(
                            and_(
                                PartnerRolePermission.role_id == role_id,
                                PartnerRolePermission.partner_id == partner_id,
                                PartnerRolePermission.permission_id.in_(disable_ids),
                            )
                        )
                    )
                ).scalars().all()
                for row in partner_rows:
                    await session.delete(row)
                    if row.permission_id not in revoked_ids:
                        revoked_ids.append(row.permission_id)

            await session.commit()
            self.__console_service_logger.info(
                "set_role_action_permissions role_id={} partner_id={} granted={} revoked={}".format(
                    role_id, partner_id, granted_ids, revoked_ids
                )
            )
            return granted_ids, revoked_ids

    async def delete_default_role_permission(
        self,
        default_role_permission_id: int,
    ):
        try:
            async with self.__session_factory() as session:
                self.__console_service_logger.info(
                    "Deleting default role permission with id: {}".format(
                        default_role_permission_id
                    )
                )
                query = select(DefaultRolePermission).where(
                    DefaultRolePermission.id == default_role_permission_id
                )
                result = await session.execute(query)
                default_role_permission = result.scalar_one_or_none()

                if not default_role_permission:
                    raise DefaultRolePermissionException(
                        ExceptionMsg.DEFAULT_ROLE_PERMISSION_NOT_FOUND
                    )

                await session.delete(default_role_permission)
                await session.commit()
                self.__console_service_logger.info(
                    "Successfully deleted default role permission with id: {}".format(
                        default_role_permission_id
                    )
                )
        except DefaultRolePermissionException as exec:
            self.__console_service_logger.error(str(exec))
            raise exec
        except Exception as exec:
            self.__console_service_logger.error(str(exec))
            raise exec
