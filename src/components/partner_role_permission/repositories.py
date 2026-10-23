from uuid import UUID
from contextlib import AbstractContextManager
from typing import Callable, Iterator, Optional
from asyncpg.exceptions import UniqueViolationError
from fastapi import HTTPException, status
from sqlalchemy import and_, exists, select, func, literal, String
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, aliased
from src.components.partner_config.constants import PartnerConfigEnum
from src.components.auth.models import Permission, Role
from src.components.partner.models import Partner
from src.components.partner_role_permission.constant import ExceptionMsg
from src.components.partner_role_permission.error import (
    PartnerRolePermissionNotFoundError,
)
from src.components.partner_role_permission.models import PartnerRolePermission
from src.components.partner_role_permission.schema import PartnerPermissionData
from src.components.partner_config.models import PartnerConfig
from src.exceptions import PartnerRolePermissionException
from src.loggers.console_service_logger import ConsoleServiceLogger


class PartnerPermissionRepository:

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
    async def add_partner_permission(
        self,
        add_data: PartnerPermissionData,
        user_id: UUID,
    ) -> PartnerRolePermission:
        try:
            async with self.__session_factory() as session:
                # check partner, role, permission is not deleted
                # Create the subqueries for checking existence

                partner_exists_subquery = exists().where(
                    and_(Partner.id == add_data.partner_id, Partner.is_deleted == False)
                )

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
                    partner_exists_subquery.label("partner_exists"),
                    permission_exists_subquery.label("permission_exists"),
                    role_exists_subquery.label("role_exists"),
                )
                result = await session.execute(combined_query)
                data = result.fetchone()

                if not data.partner_exists:
                    raise PartnerRolePermissionException(ExceptionMsg.PARTNER_NOT_FOUND)

                if not data.permission_exists:
                    raise PartnerRolePermissionException(
                        ExceptionMsg.PERMISSION_NOT_FOUND
                    )

                if not data.role_exists:
                    raise PartnerRolePermissionException(ExceptionMsg.ROLE_NOT_FOUND)

                self.__console_service_logger.info(
                    "Inserting partner role permission mapping for partner id: {}".format(
                        add_data.partner_id
                    )
                )
                insert = PartnerRolePermission(
                    partner_id=add_data.partner_id,
                    permission_id=add_data.permission_id,
                    role_id=add_data.role_id,
                    created_by=user_id,
                )
                session.add(insert)
                await session.commit()
                await session.refresh(insert)
                self.__console_service_logger.info(
                    "Successfully inserted mapping in db for partner id {}".format(
                        insert.partner_id
                    )
                )
                return insert
        except UniqueViolationError as exc:
            self.__console_service_logger.error(
                "UniqueViolationError  A record with this combination already exists.{}".format(
                    exc
                )
            )
            raise PartnerRolePermissionException(str(exc))
        except IntegrityError as exc:
            self.__console_service_logger.error(
                "A record with this combination already exists: {}".format(exc)
            )
            raise PartnerRolePermissionException(
                "A record with this combination already exists."
            )
        except PartnerRolePermissionException as exc:
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

    # From partner_role_permission table get all mapping
    async def get_all_partner_role_permission(self) -> Iterator[PartnerRolePermission]:
        try:
            async with self.__session_factory() as session:
                self.__console_service_logger.info(
                    "Attempting to get all partner role permission mapping"
                )
                query = select(PartnerRolePermission).filter(
                    exists().where(
                        and_(
                            Partner.id == PartnerRolePermission.partner_id,
                            Partner.is_deleted == False,
                            Role.id == PartnerRolePermission.role_id,
                            Role.is_deleted == False,
                            Permission.id == PartnerRolePermission.permission_id,
                            Permission.is_deleted == False,
                        )
                    )
                )
                permissions = (await session.execute(query)).scalars().all()
                self.__console_service_logger.info(
                    "Successfully retrieved all partner role permissions:{}".format(
                        permissions
                    )
                )
                return permissions
        except Exception as exc:
            self.__console_service_logger.error(
                "Unexpected error during getting all partner role permission: {}".format(
                    str(exc)
                )
            )
            raise exc

    async def get_partner_role_permission_by_id(self, id: UUID) -> PartnerRolePermission:
        try:
            async with self.__session_factory() as session:
                self.__console_service_logger.info(
                    "Attempting to get partner role permission mapping by id: {}".format(
                        id
                    )
                )
                query = (
                    select(PartnerRolePermission)
                    .filter(PartnerRolePermission.id == id)
                    .filter(
                        exists().where(
                            and_(
                                Partner.id == PartnerRolePermission.partner_id,
                                Partner.is_deleted == False,
                                Role.id == PartnerRolePermission.role_id,
                                Role.is_deleted == False,
                                Permission.id == PartnerRolePermission.permission_id,
                                Permission.is_deleted == False,
                            )
                        )
                    )
                )
                partner_role_permission = (
                    (await session.execute(query)).scalars().one_or_none()
                )
                if not partner_role_permission:
                    raise PartnerRolePermissionNotFoundError(id)
                self.__console_service_logger.info(
                    "Successfully retrieved partner role permissions by id  {}".format(
                        partner_role_permission
                    )
                )
                return partner_role_permission
        except PartnerRolePermissionNotFoundError as exc:
            self.__console_service_logger.error(
                "Unexpected error during getting partner role permission by id: {}".format(
                    str(exc)
                )
            )
            raise PartnerRolePermissionException(str(exc))
        except Exception as exc:
            self.__console_service_logger.error(
                "Unexpected error during getting partner role permission: {}".format(
                    str(exc)
                )
            )
            raise exc

    async def get_by_partner_id(
        self, partner_id: UUID
    ) -> Iterator[PartnerRolePermission]:
        try:
            async with self.__session_factory() as session:
                self.__console_service_logger.info(
                    "Attempting to get partner role permissions for partner_id {}".format(
                        partner_id
                    )
                )
                query = (
                    select(PartnerRolePermission)
                    .filter(PartnerRolePermission.partner_id == partner_id)
                    .filter(
                        exists().where(
                            and_(
                                Partner.id == PartnerRolePermission.partner_id,
                                Partner.is_deleted == False,
                                Role.id == PartnerRolePermission.role_id,
                                Role.is_deleted == False,
                                Permission.id == PartnerRolePermission.permission_id,
                                Permission.is_deleted == False,
                            )
                        )
                    )
                )
                partner_permissions = (await session.execute(query)).scalars().all()
                self.__console_service_logger.info(
                    "Successfully retrieved partner role permissions by partner id: {}, {}".format(
                        partner_id, partner_permissions
                    )
                )

                if not partner_permissions:
                    self.__console_service_logger.warning(
                        "Partner role permissions found for partner_id: {}".format(
                            partner_id
                        )
                    )
                    raise PartnerRolePermissionNotFoundError(partner_id)
                return partner_permissions

        except PartnerRolePermissionNotFoundError as exc:
            self.__console_service_logger.error(
                "Unexpected error during getting partner role permissions by partner id: {}".format(
                    str(exc)
                )
            )
            raise PartnerRolePermissionException(str(exc))
        except Exception as exc:
            self.__console_service_logger.error(
                "Unexpected error during getting partner role permissions: {}".format(
                    str(exc)
                )
            )
            raise exc

    async def delete_partner_role_permission(self, id: UUID) -> None:
        try:
            async with self.__session_factory() as session:
                self.__console_service_logger.info(
                    "Attempting to delete partner role permission mapping by id {}".format(
                        str(id)
                    )
                )
                query = (
                    select(PartnerRolePermission)
                    .filter(PartnerRolePermission.id == id)
                    .filter(
                        exists().where(
                            and_(
                                Partner.id == PartnerRolePermission.partner_id,
                                Partner.is_deleted == False,
                                Role.id == PartnerRolePermission.role_id,
                                Role.is_deleted == False,
                                Permission.id == PartnerRolePermission.permission_id,
                                Permission.is_deleted == False,
                            )
                        )
                    )
                )
                partner_role_permission = (
                    (await session.execute(query)).scalars().one_or_none()
                )
                if not partner_role_permission:
                    raise PartnerRolePermissionNotFoundError(id)
                await session.delete(partner_role_permission)
                self.__console_service_logger.info(
                    "Successfully deleted partner role permission, id: {}".format(id)
                )
                await session.commit()
        except PartnerRolePermissionNotFoundError as exc:
            self.__console_service_logger.error(
                "Unexpected error  during delete partner role permission: {}".format(
                    str(exc)
                )
            )
            raise PartnerRolePermissionException(exc)
        except Exception as exc:
            self.__console_service_logger.error(
                "Unexpected error during delete partner role permission: {}".format(
                    str(exc)
                )
            )
            raise exc
        
    async def get_partner_role_permission_matrix(self, key: str, partner_id: UUID, is_internal_partner: bool)-> Iterator[tuple]:
        try:
            async with self.__session_factory() as session:
                self.__console_service_logger.info("Fetching full partner permission matrix for all the partners with config key: {}".format(key))
                filters = [Permission.is_active == True, Partner.id == partner_id, Permission.is_internal== False]
                if is_internal_partner:
                    filters.append(Role.is_internal == True)
                else:
                    filters.append(Role.is_internal == False)

                partner_permission = aliased(PartnerRolePermission)
                query = (
                    select(
                        Partner.name.label("partner_name"),                  
                        Role.name.label("role_name"),
                        func.coalesce(Permission.category, literal("Uncategorized")).label("category"),
                        Permission.slug,
                        Permission.id.label("permission_id"),
                        Permission.created_at,
                        Permission.description,
                        Permission.display_text,
                        (partner_permission.permission_id != None).label("is_partner"),
                    )
                    .select_from(Partner)
                    .join(PartnerConfig, PartnerConfig.partner_id == Partner.id)
                    .filter(PartnerConfig.key == key, PartnerConfig.value.cast(String) == 'true')
                    .join(Role, literal(True))
                    .join(Permission, literal(True))
                    .outerjoin(
                        partner_permission,
                        (partner_permission.role_id == Role.id)
                        & (partner_permission.permission_id == Permission.id)
                        & (partner_permission.partner_id == Partner.id),
                    )
                    .where(*filters)
                    .order_by(Partner.id, Role.id, Permission.category, Permission.id)
                )

                result = await session.execute(query)
                response = result.fetchall()
                self.__console_service_logger.info("Successfully fetched partner permissions matrix for config key: {}".format(key))
                return response
        except PartnerRolePermissionException as exec:
            self.__console_service_logger.error("Error fetching partner permissions matrix: {}".format(exec))
            raise exec

        except Exception as exec:
            self.__console_service_logger.error("Error fetching partner permissions: {}".format(exec))
            raise exec
        
        