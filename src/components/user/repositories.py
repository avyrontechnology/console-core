"""Repositories module."""

from uuid import UUID
from contextlib import AbstractContextManager
from typing import Any, Callable, Dict, List, Optional, Tuple, Union

from dependency_injector.wiring import Provide
from fastapi import Depends
from sqlalchemy import and_, case, func, insert, join, select
from sqlalchemy.dialects.postgresql import INTEGER
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, aliased, joinedload
from sqlalchemy.orm.attributes import flag_modified

from src.components.auth.constant import SignupConfigKeys
from src.components.auth.masker import mask_for_logs
from src.components.auth.models import Role
from src.components.auth.repositories import AuthRepository
from src.components.auth.schema import UserData
from src.components.common.datetime import DateTimeUtil
from src.components.common.errors import NotFoundError
from src.components.filters.criteria import BaseFilterCriteria
from src.components.user.filter_builder import UserRoleFilterBuilder
from src.components.partner.models import Partner
from src.components.partner_home_page.constants import RoleHierarchyLevel
from src.components.user.constants import UserLogMsg, UserRoles
from src.components.user.errors import UserNotFoundError
from src.components.user.helpers import safe_dict
from src.components.user.models import User
from src.components.user_config.models import UserConfig
from src.exceptions import UserException
from src.loggers.console_service_logger import ConsoleServiceLogger


class UserRepository:

    def __init__(
        self,
        session_factory: Callable[..., AbstractContextManager[Session]],
        console_service_logger: ConsoleServiceLogger,
    ) -> None:
        self.__session_factory: Callable[..., AbstractContextManager[Session]] = (
            session_factory
        )
        self.__console_service_logger: ConsoleServiceLogger = console_service_logger

    # =====================================================
    # get_all() — split into 3 helpers to bring Cognitive
    # Complexity from 16 down under the 15 threshold. Each
    # helper does exactly what the corresponding block of the
    # original function did; no query or behavior changed.
    # =====================================================
    async def _resolve_hierarchy_root(
        self,
        session: Session,
        current_user_id: UUID,
        auth_repository: AuthRepository,
    ) -> Tuple[int, List[int]]:
        """
        Returns (effective_root_user_id, exclude_ids).

        For a non-MAINTAINER, the hierarchy root is the user themself and
        nothing is excluded from the listing. For a MAINTAINER, the root
        becomes the partner's admin (if one exists) instead, and both the
        maintainer's own id and the admin's id are excluded from the
        final result set — exactly the behavior the original inline
        MAINTAINER branch implemented.
        """
        current_user_query = select(User).where(User.id == current_user_id)
        current_user_result = await session.execute(current_user_query)
        current_user = current_user_result.scalars().one_or_none()

        current_user_role = await auth_repository.get_role_by_id(current_user.role_id)

        if current_user_role.slug != UserRoles.MAINTAINER:
            return current_user_id, []

        self.__console_service_logger.info(
            "User with id {} has MAINTAINER role, fetching admin users...".format(
                current_user_id
            )
        )

        admin_role_query = select(Role).where(
            Role.slug == UserRoles.ADMIN, Role.is_active == True
        )
        admin_role_result = await session.execute(admin_role_query)
        admin_role = admin_role_result.scalars().first()

        if not admin_role:
            self.__console_service_logger.error("Admin role not found in the database.")
            raise UserException("Admin role not found.")

        admin_query = select(User).where(
            User.role_id == admin_role.id,
            User.partner_id == current_user.partner_id,
            User.is_active.is_(True),
        )
        admin_result = await session.execute(admin_query)
        admin_user = admin_result.scalars().first()

        admin_user_id = admin_user.id if admin_user else None
        effective_root_id = admin_user.id if admin_user else current_user_id

        exclude_ids = [id for id in [current_user_id, admin_user_id] if id is not None]
        return effective_root_id, exclude_ids

    def _build_hierarchy_cte(self, root_user_id: UUID):
        """Recursive CTE walking User.parent_id from root_user_id downward, with a level counter."""
        cte = (
            select(
                User.id.label("user_id"),
                User.parent_id,
                func.cast(0, INTEGER).label("level"),
            )
            .where(User.id == root_user_id)
            .cte(name="user_hierarchy", recursive=True)
        )
        recursive_part = select(
            User.id.label("user_id"),
            User.parent_id,
            (cte.c.level + 1).label("level"),
        ).join(cte, User.parent_id == cte.c.user_id)
        return cte.union_all(recursive_part)

    async def _apply_filters_and_count(
        self,
        session: Session,
        query,
        filter_criteria: Optional[BaseFilterCriteria],
    ):
        """Applies optional listing filters, then counts the (already-filtered) result set."""
        if filter_criteria and filter_criteria.filters:
            filter_fields = [item.get("field") for item in filter_criteria.filters]
            if UserRoleFilterBuilder.requires_role_join(filter_fields):
                query = query.join(Role, User.role_id == Role.id)
            query = await UserRoleFilterBuilder(filter_criteria, query).build_query()

        count_query = select(func.count()).select_from(query.subquery())
        count_result = await session.execute(count_query)
        total_count = count_result.scalar()
        return query, total_count

    async def get_all(
        self,
        current_user_id: UUID,
        limit: int,
        offset: int,
        auth_repository: AuthRepository = Depends(Provide["auth_repository"]),
        filter_criteria: Optional[BaseFilterCriteria] = None,
    ) -> Tuple[List[User], int]:
        """
        Get active users in a user's hierarchy along with total count, excluding maintainer and admin if applicable.

        Args:
            current_user_id: ID of user for hierarchy.
            limit: Max users to return.
            offset: Pagination start.
            filter_criteria: Optional listing filters. When omitted the query is
                the unfiltered hierarchy listing, exactly as before.

        Returns:
            Tuple[List[User], int]: Active users with country/parent data and total count.

        Raises:
            SQLAlchemyError: For database errors.
        """
        async with self.__session_factory() as session:
            try:
                effective_root_id, exclude_ids = await self._resolve_hierarchy_root(
                    session, current_user_id, auth_repository
                )

                self.__console_service_logger.info(
                    "Getting all users under the hierarchy of user_id={} from the database...".format(
                        effective_root_id
                    )
                )

                cte = self._build_hierarchy_cte(effective_root_id)
                query = select(User).join(cte, User.id == cte.c.user_id)

                if exclude_ids:
                    query = query.where(User.id.not_in(exclude_ids))

                # Apply listing filters before counting so pagination and the
                # total both operate on the filtered result set.
                query, total_count = await self._apply_filters_and_count(
                    session, query, filter_criteria
                )

                query = (
                    query.options(joinedload(User.country), joinedload(User.parent))
                    .order_by(cte.c.level, cte.c.user_id)
                    .limit(limit)
                    .offset((offset - 1) * limit)
                )

                result = await session.execute(query)
                all_users = result.scalars().all()

                self.__console_service_logger.info(
                    "Fetched users in the user id: {} hierarchy successfully, total count: {}".format(
                        effective_root_id, total_count
                    )
                )
                return all_users, total_count

            except UserException as uex:
                self.__console_service_logger.error(
                    "User role not found while getting all users: {}".format(str(uex))
                )
                raise uex

            except SQLAlchemyError as e:
                self.__console_service_logger.error("Database error: {}".format(e))
                raise

    async def get_by_id(
        self, user_id: UUID, show_inactive_users: bool = False
    ) -> User:
        async with self.__session_factory() as session:
            try:
                self.__console_service_logger.info(
                    "Getting user by id : {}".format(user_id)
                )
                user = await session.get(User, user_id)
                if show_inactive_users:
                    # Deactivated users are allowed; soft-deleted are not.
                    is_not_found = not user or user.is_deleted
                else:
                    is_not_found = not user or user.is_active == False
                if is_not_found:
                    self.__console_service_logger.error(
                        UserLogMsg.USER_NOT_FOUND
                    )
                    raise UserNotFoundError(user_id)
                # _safe_dict(user) to hide hashed_password
                self.__console_service_logger.info(
                    "User fetched successfully.{}".format(safe_dict(user))
                )
                return user
            except SQLAlchemyError as e:
                self.__console_service_logger.error("Database error:{}".format(e))
                raise            
    async def add_user(
        self, user_data: UserData, services: Optional[SignupConfigKeys] = None
    ) -> User:
        async with self.__session_factory() as session:
            try:
                user_data_dict: dict = user_data.model_dump()
                user_data_dict["hashed_password"] = user_data_dict.pop("password")
                user_data_dict.pop("team_id", None)
                user_data_dict.pop("team_role_id", None)
                user = User(**user_data_dict, is_active=True)
                # _safe_dict(user) to hide hashed_password
                self.__console_service_logger.info(
                    "Adding user to the database: {}".format(safe_dict(user))
                )
                session.add(user)
                await session.flush()

                if not services:
                    enabled_flags: list[dict[str, Any]] = [
                        {
                            "key": SignupConfigKeys.TALKO.to_config_key(),
                            "value": True,
                            "user_id": user.id,
                        },
                    ]
                else:
                    enabled_flags: list[dict[str, Any]] = [
                        {
                            "key": services.to_config_key(),
                            "value": True,
                            "user_id": user.id,
                        }
                    ]

                if enabled_flags:
                    user_config_query = insert(UserConfig).values(enabled_flags)
                    await session.execute(user_config_query)
                await session.commit()
                await session.refresh(user)
                self.__console_service_logger.info(
                    "User with the user id {} is now added to the database".format(
                        user.id
                    )
                )
                return user
            except SQLAlchemyError as e:
                self.__console_service_logger.error("Database error: {}".format(e))
                raise e
            except UserException as ex:
                self.__console_service_logger.error(
                    "Failed to create user: {}".format(ex)
                )
                raise ex

    async def get_user_by_field(self, field_name: str, value) -> User:
        """
        Fetch a User by a given field dynamically.

        :param field_name: The field name to filter by (must exist on User)
        :param value: The value to compare against
        :return: User instance or None if not found
        """
        if not hasattr(User, field_name):
            raise ValueError(f"User model has no attribute '{field_name}'")

        async with self.__session_factory() as session:
            try:
                self.__console_service_logger.info(
                    f"Getting user by {field_name}: {value}"
                )
                query = select(User).filter(
                    and_(
                        getattr(User, field_name) == value,
                        User.is_deleted.is_(False),
                        User.is_active.is_(True),
                    )
                )
                result = await session.execute(query)
                user = result.scalar_one_or_none()
                self.__console_service_logger.info(
                    f"User fetched successfully by {field_name}: {value}"
                )
                return user
            except SQLAlchemyError as e:
                self.__console_service_logger.error(f"Database error: {e}")
                raise

    async def delete_by_id(self, user_id: UUID) -> User:
        async with self.__session_factory() as session:
            try:
                self.__console_service_logger.info(
                    "Deleting user with id : {}".format(user_id)
                )
                entity: User = await session.get(User, user_id)

                if not entity or entity.is_active == False:
                    self.__console_service_logger.error(
                        UserLogMsg.USER_NOT_FOUND
                    )
                    raise UserNotFoundError(user_id)
                entity.is_active = False
                entity.is_deleted = True
                # making the email unique
                unique_mail = str(user_id) + "_" + entity.email
                entity.email = unique_mail
                unique_phone_number = entity.phone_number + "_" + str(user_id)
                entity.phone_number = unique_phone_number
                entity.deleted_at = DateTimeUtil.get_current_time()
                # _safe_dict(entity) to hide hashed_password
                self.__console_service_logger.info(
                    "User deleted successfully:{}".format(safe_dict(entity))
                )
                session.add(entity)
                await session.commit()
                await session.refresh(entity)
                return entity
            except SQLAlchemyError as e:
                self.__console_service_logger.error("Database error:{}".format(e))
                raise

    async def update_user(
        self,
        user_id: UUID,
        current_user_id: UUID,
        **update_fields,
    ) -> User:
        async with self.__session_factory() as session:
            try:
                result = await session.execute(select(User).filter(User.id == user_id))
                user = result.scalar_one_or_none()

                # A soft-deleted user can never be edited, regardless of what
                # this update contains — deletion is terminal, deactivation is not.
                if not user or user.is_deleted:
                    self.__console_service_logger.error(
                        "User with ID {} not found".format(user_id)
                    )
                    NotFoundError.entity_name = "User"
                    raise NotFoundError(user_id)

                # An inactive user can only be touched by an update that is
                # explicitly reactivating them (is_active=True in this same call)
                is_reactivating: bool = update_fields.get("is_active") is True
                if not user.is_active and not is_reactivating:
                    self.__console_service_logger.error(
                        "User with ID {} is inactive; only a reactivating "
                        "update (is_active=True) is permitted".format(user_id)
                    )
                    NotFoundError.entity_name = "User"
                    raise NotFoundError(user_id)

                update_fields["updated_by"] = current_user_id

                if "email" in update_fields and update_fields["email"] != user.email:
                    update_fields["is_email_verified"] = False
                if (
                    "phone_number" in update_fields
                    and update_fields["phone_number"] != user.phone_number
                ):
                    update_fields["is_phone_number_verified"] = False

                for field, value in update_fields.items():
                    if field == "password":
                        setattr(user, "hashed_password", value)
                    else:
                        setattr(user, field, value)

                # was user.__dict__, now _safe_dict(user) to hide hashed_password
                self.__console_service_logger.info(
                    "Updating user in the database: {}".format(safe_dict(user))
                )
                session.add(user)
                await session.commit()
                await session.refresh(user)
                return user
            except SQLAlchemyError as ex:
                self.__console_service_logger.error(f"Database error: {ex}")
                raise ex
            except Exception as exec:
                self.__console_service_logger.error("Database error:{}".format(exec))
                raise exec

    async def get_users_by_partner_id(self, partner_id: UUID) -> List[dict]:
        try:
            async with self.__session_factory() as session:
                self.__console_service_logger.info(
                    "Attempting to get list of user by partner_id: {}".format(
                        partner_id
                    )
                )

                role_alias = aliased(Role)

                stmt = (
                    select(
                        User.id,
                        User.name,
                        User.email,
                        User.phone_number,
                        role_alias.name.label("role_name"),
                        role_alias.hierarchy.label("role_hierarchy"),
                        role_alias.data_scope.label("role_data_scope"),
                    )
                    .select_from(join(User, role_alias, User.role_id == role_alias.id))
                    .where(User.partner_id == partner_id, User.is_active == True)
                )

                result = await session.execute(stmt)
                users = [
                    {
                        "id": row.id,
                        "name": row.name,
                        "email": row.email,
                        "phone_number": row.phone_number,
                        "role": row.role_name,
                        "role_hierarchy": row.role_hierarchy,
                        "role_data_scope": row.role_data_scope,
                    }
                    for row in result.all()
                ]

                return users
        except Exception as ex:
            self.__console_service_logger.error(
                "Unexpected error during get users by partner_id: {}, error: {}".format(
                    partner_id, str(ex)
                )
            )
            raise ex

    async def get_user_with_role(self, user_id: UUID) -> User:
        async with self.__session_factory() as session:
            try:
                self.__console_service_logger.info(
                    "Getting user with role by user_id: {}".format(user_id)
                )

                role_alias = aliased(Role)

                query = (
                    select(User, role_alias)
                    .join(role_alias, User.role_id == role_alias.id)
                    .where(User.id == user_id, User.is_active == True)
                )

                result = await session.execute(query)
                user_role = result.one_or_none()

                if user_role is None:
                    self.__console_service_logger.error(
                        "User not found or inactive, user_id: {}".format(user_id)
                    )
                    raise UserNotFoundError(user_id)

                # Unpack the user and role from user_role
                _, role = user_role
                return role
            except UserNotFoundError as ex:
                self.__console_service_logger.error(
                    "Unexpected error during get user with role: {}, error: {}".format(
                        user_id, str(ex)
                    )
                )
                raise ex
            except Exception as ex:
                self.__console_service_logger.error(
                    "Unexpected error during get user with role: {}, error: {}".format(
                        user_id, str(ex)
                    )
                )
                raise ex

    async def partner_user_limit(self, partner_id: UUID) -> int:
        try:
            async with self.__session_factory() as session:

                self.__console_service_logger.info(
                    "Checking user limit for partner_id: {}".format(partner_id)
                )

                partner = await session.get(Partner, partner_id)

                if not partner:
                    self.__console_service_logger.error(
                        "Partner with ID {} not found.".format(partner_id)
                    )
                    raise UserException(f"Partner with ID {partner_id} not found.")

                # Count the total number of active users under the partner
                total_users = await session.scalar(
                    select(func.count(User.id)).where(
                        User.partner_id == partner_id, User.is_active == True
                    )
                )

                self.__console_service_logger.info(
                    "Partner {} is within the user limit. Active users: {}, License limit: {}".format(
                        partner_id, total_users, partner.active_license
                    )
                )
                return total_users

        except SQLAlchemyError as ex:
            self.__console_service_logger.error(
                "Database error when checking user limit for partner_id {}: error: {}".format(
                    partner_id, ex
                )
            )
            raise ex
        except Exception as ex:
            self.__console_service_logger.error(
                "Unexpected error during user limit check for partner_id {}: {}".format(
                    partner_id, ex
                )
            )
            raise ex

    async def get_user_details(self, user_id: UUID) -> Any:
        try:
            async with self.__session_factory() as session:
                self.__console_service_logger.info(
                    "Attempting to get user details by user_id {}".format(user_id)
                )
                query = (
                    select(
                        User.id.label("user_id"),
                        User.name.label("name"),
                        User.email.label("email"),
                        User.partner_id.label("partner_id"),
                        Role.hierarchy.label("role_hierarchy_level"),
                    )
                    .join(Role, Role.id == User.role_id, isouter=True)
                    .where(User.id == user_id)
                )
                result = await session.execute(query)
                user: Any = result.mappings().first()
                return user
        except Exception as exc:
            self.__console_service_logger.info(
                "Unexpected error occurred while getting user details by user_id {}".format(
                    user_id
                )
            )
            raise exc

    async def get_service_board_users_details(
        self, user_ids: list, show_inactive_users: Optional[bool] = False
    ) -> List[User]:
        try:
            async with self.__session_factory() as session:
                self.__console_service_logger.info(
                    "Attempting to get service board users by user_ids: {}".format(
                        user_ids
                    )
                )

                query = (
                    select(
                        User.id.label("user_id"),
                        User.email.label("email"),
                        User.is_active.label("is_active"),
                        User.is_suspended.label("is_suspended"),
                        case(
                            (
                                User.is_active == False,
                                func.concat(User.name, " (Inactive)"),
                            ),
                            else_=User.name,
                        ).label("name"),
                        Role.name.label("role"),
                        Role.hierarchy.label("role_hierarchy_level"),
                        func.coalesce(User.current_status, "Away").label(
                            "current_status"
                        ),
                    )
                    .join(Role, Role.id == User.role_id, isouter=True)
                    .where(User.id.in_(user_ids))
                )

                if not show_inactive_users:
                    query = query.where(User.is_active.is_(True))

                result = await session.execute(query)
                users = result.mappings().all()
                return users
        except Exception as ex:
            self.__console_service_logger.error(
                "Unexpected error during get service board users by user_ids: {}, error: {}".format(
                    user_ids, str(ex)
                )
            )
            raise ex

    async def get_admin_credentials_by_hierarchy(
        self, user_hierarchy: int, partner_id: Union[int, list[int]]
    ) -> Optional[Dict[str, str]]:
        try:
            async with self.__session_factory() as session:
                self.__console_service_logger.info(
                    "Trying to fetch the admin's email and phone number by user hierarchy : {}".format(
                        user_hierarchy
                    )
                )
                query = (
                    select(
                        User.id.label("user_id"),
                        User.name.label("name"),
                        User.email.label("email"),
                        User.phone_number.label("phone_number"),
                        Role.name.label("role"),
                        User.partner_id.label("partner_id"),
                    )
                    .join(Role, Role.id == User.role_id)
                    .where(
                        Role.hierarchy == user_hierarchy,
                        User.is_active == True,
                    )
                )
                if isinstance(partner_id, list):
                    query = query.where(User.partner_id.in_(partner_id))
                else:
                    query = query.where(User.partner_id == partner_id)

                result = await session.execute(query)
                admin_credentials = result.mappings().all()
                return admin_credentials
        except Exception as exec:
            self.__console_service_logger.error(
                "Unexpected error while fetching admin credentials: {}".format(exec)
            )
            raise exec

    async def is_admin_exists(self, partner_id: UUID, role_id: UUID) -> bool:
        try:
            async with self.__session_factory() as session:
                self.__console_service_logger.info(
                    f"Attempting to check if admin exists with role_id: {role_id}, for partner_id: {partner_id}."
                )
                query = select(User).where(
                    User.partner_id == partner_id,
                    User.role_id == role_id,
                    User.is_active.is_(True),
                )

                result = await session.execute(query)
                admin = result.scalars().all()
                return len(admin) > 0
        except Exception as exc:
            self.__console_service_logger.error(
                f"Unexpected error while fetching admin: {exc}"
            )
            raise exc

    async def get_user_by_user_id(
        self, user_id: UUID, partner_id, show_inactive_users: bool = False
    ) -> User:
        try:
            async with self.__session_factory() as session:
                self.__console_service_logger.info(
                    "Fetching user by user_id: {}".format(user_id)
                )
                query = select(User).where(
                    User.id == user_id, User.partner_id == partner_id
                )
                # Inactive users are not returned by default, so callers such as
                # Lead assignment cannot pick a deactivated user.
                if not show_inactive_users:
                    query = query.where(User.is_active.is_(True))

                result = await session.execute(query)
                response = result.scalars().first()
                if not response:
                    self.__console_service_logger.error(
                        "User with id: {} is not found.".format(user_id)
                    )
                    raise UserNotFoundError(user_id)
                self.__console_service_logger.info(
                    "user_fetched_successfully: {}".format(response)
                )
                return response
        except UserNotFoundError as exec:
            self.__console_service_logger.error(
                "User not found for user id: {}".format(user_id)
            )
            raise exec
        except Exception as exec:
            self.__console_service_logger.error(
                "An error occured while fetching the user: {}".format(exec)
            )
            raise exec
        
    async def get_admin_details_by_partner_id(self, partner_id: UUID) -> Optional[User]:
        """
        Fetch the admin user details for a given partner_id.

        Matching by slug alone (with no partner scope) is ambiguous once any
        partner has materialized its own copy of the shared "admin" role:
        materializing repoints that partner's existing users to the copy's
        id, so a slug match that happens to land on the global default (or a
        different partner's copy) would silently find zero users. Prefer the
        partner's own "admin"-slugged role if it has one; fall back to the
        shared default otherwise.
        """
        try:
            async with self.__session_factory() as session:
                self.__console_service_logger.info(
                    "Fetching admin user details for partner_id: {}".format(partner_id)
                )
                admin_role_result = await session.execute(
                    select(Role).where(
                        Role.partner_id == partner_id,
                        Role.slug == UserRoles.ADMIN,
                        Role.is_active == True,
                    )
                )
                admin_role = admin_role_result.scalars().first()

                if not admin_role:
                    admin_role_result = await session.execute(
                        select(Role).where(
                            Role.partner_id.is_(None),
                            Role.slug == UserRoles.ADMIN,
                            Role.is_active == True,
                        )
                    )
                    admin_role = admin_role_result.scalars().first()

                if not admin_role:
                    self.__console_service_logger.error(
                        "Admin role not found in the database."
                    )
                    raise UserException("Role not found")

                query = select(User).where(
                    User.partner_id == partner_id,
                    User.role_id == admin_role.id,
                    User.is_active == True,
                )
                result = await session.execute(query)
                admin_user = result.scalars().first()
                self.__console_service_logger.info(
                    "Admin user fetched successfully for partner_id: {}: {}".format(
                        partner_id, admin_user
                    )
                )
                return admin_user

        except UserException as exec:
            self.__console_service_logger.error(
                "Error while fetching admin details for partner id: {}: {}".format(
                    partner_id, exec
                )
            )
            raise exec
        except Exception as exec:
            self.__console_service_logger.error(
                "Unexpected error while fetching admin details for partner_id {}: {}".format(
                    partner_id, exec
                )
            )
            raise exec

    async def execure_user_filter_query(self, query) -> List[Tuple]:

        async with self.__session_factory() as session:
            try:
                result = await session.execute(query)
                return result.fetchall()
            except SQLAlchemyError as exec:
                self.__console_service_logger.error(
                    "Database error while executing query: {}".format(exec)
                )
                raise exec

    async def execute_user_filter_scalar_query(self, query) -> Any:
        async with self.__session_factory() as session:
            try:
                result = await session.execute(query)
                return result.scalar()
            except SQLAlchemyError as exec:
                self.__console_service_logger.error(
                    "Database error while executing scalar query: {}".format(exec)
                )
                raise exec

    async def get_users_by_user_ids(
        self, partner_id: UUID, user_ids: List[int]
    ) -> List[User]:
        try:
            async with self.__session_factory() as session:
                self.__console_service_logger.info(
                    "Attempting to get list of user by user_ids: {}".format(user_ids)
                )

                query = select(User).where(
                    User.id.in_(user_ids),
                    User.is_active == True,
                    User.partner_id == partner_id,
                )

                result = await session.execute(query)
                users = result.scalars().all()
                return users
        except Exception as ex:
            self.__console_service_logger.error(
                "Unexpected error during get users by user_ids: {}, error: {}".format(
                    user_ids, str(ex)
                )
            )
            raise ex

    async def get_users_availability_status(self, user_ids: List[int]) -> List[Any]:
        try:
            async with self.__session_factory() as session:
                self.__console_service_logger.info(
                    "Trying to fetch current_status for user_ids: {}".format(
                        user_ids
                    )
                )
                query = select(
                    User.id.label("user_id"),
                    func.coalesce(User.current_status, "Away").label(
                        "current_status"
                    ),
                ).where(User.id.in_(user_ids))

                result = await session.execute(query)
                users_status: List[Any] = result.mappings().all()
                return users_status
        except Exception as exec:
            self.__console_service_logger.error(
                "Unexpected error while fetching users status: {}".format(exec)
            )
            raise exec

    async def has_child_users(self, user_id: UUID) -> bool:
        """
        Check if the given user has any child users.
        Returns True if child users exist, otherwise False.
        """
        try:
            async with self.__session_factory() as session:
                self.__console_service_logger.info(
                    f"Checking if user_id: {user_id} has child users"
                )

                query = (
                    select(User.id)
                    .where(
                        User.parent_id == user_id,
                        User.is_deleted == False,
                        User.is_active == True,
                    )
                    .limit(1)
                )

                result = await session.execute(query)
                has_child = result.scalar_one_or_none() is not None

                self.__console_service_logger.info(
                    f"User_id: {user_id} has_child_users: {has_child}"
                )

                return has_child

        except Exception as exc:
            self.__console_service_logger.error(
                f"Unexpected error while checking child users for user_id: {user_id}, error: {exc}"
            )
            raise exc

    async def get_system_admin_user(self) -> Optional[User]:
        try:
            self.__console_service_logger.info("Fetching system admin user")
            async with self.__session_factory() as session:
                query = (
                    select(User)
                    .join(Role, Role.id == User.role_id)
                    .where(
                        Role.hierarchy == RoleHierarchyLevel.SYSTEM_ADMIN,
                        User.is_active.is_(True),
                    )
                    .order_by(User.created_at.asc())
                )
                result = await session.execute(query)
                user = result.scalars().first()

                return user
        except Exception as exc:
            self.__console_service_logger.error(
                f"Unexpected error while getting system admnin user: {exc}"
            )
            raise exc

    async def toggle_walkthrough_key_activation(
        self, user_id: UUID, **update_fields
    ) -> User:
        async with self.__session_factory() as session:
            try:
                result = await session.execute(select(User).filter(User.id == user_id))
                user = result.scalar_one_or_none()

                if not user or not user.is_active:
                    self.__console_service_logger.error(
                        "User with ID {} not found".format(user_id)
                    )
                    NotFoundError.entity_name = "User"
                    raise NotFoundError(user_id)

                for field, value in update_fields.items():
                    setattr(user, field, value)

                # _safe_dict(user) to hide hashed_password
                self.__console_service_logger.info(
                    "Updating user walkthrough key in the database: {}".format(
                        safe_dict(user)
                    )
                )
                session.add(user)
                await session.commit()
                await session.refresh(user)
                return user
            except NotFoundError as exec:
                self.__console_service_logger.error(
                    "Not forund error occured: {}".format(exec)
                )
                raise exec
            except Exception as exec:
                self.__console_service_logger.error(
                    "An unexpected error occured while updating the user walkthrough key: {}".format(
                        exec
                    )
                )
                raise exec

    async def update_popup_last_closed(
        self,
        user_id: UUID,
        service_name: str,
    ) -> None:
        """
        Upserts popup_last_closed[service_name] = now_ms
        into user.additional_info without overwriting other keys.
        """
        async with self.__session_factory() as session:
            try:
                result = await session.execute(select(User).where(User.id == user_id))
                user = result.scalars().first()

                now_ms = int(DateTimeUtil.get_current_time())
                additional_info = dict(user.additional_info or {})
                popup_last_closed = dict(additional_info.get("popup_last_closed", {}))
                popup_last_closed[service_name] = now_ms
                additional_info["popup_last_closed"] = popup_last_closed

                user.additional_info = additional_info
                flag_modified(user, "additional_info")

                await session.commit()
                self.__console_service_logger.info(
                    "popup_last_closed updated | user_id={} service={} ts={}".format(
                        user_id, service_name, now_ms
                    )
                )
            except Exception as e:
                await session.rollback()
                self.__console_service_logger.error(
                    "Error updating popup_last_closed | user_id={} error={}".format(
                        user_id, e
                    )
                )
                raise

    async def get_users_by_emails(self, emails: List[str]) -> List[str]:
        """
        Return any of the given emails that already exist in the DB.

        Used by AuthService.bulk_create_users() for a pre-flight
        uniqueness check before the main transaction begins.

        Args:
            emails: Lowercased email addresses to check.

        Returns:
            List of already-registered emails. Empty = all are free.
        """
        if not emails:
            return []
        try:
            async with self.__session_factory() as session:
                result = await session.execute(
                    select(User.email).where(
                        User.email.in_(emails),
                        User.is_deleted == False,  # noqa: E712
                    )
                )
                existing = [row[0] for row in result.all()]
                self.__console_service_logger.info(
                    "get_users_by_emails: {}/{} already registered".format(
                        len(existing), len(emails)
                    )
                )
                return existing
        except Exception as exc:
            self.__console_service_logger.error(
                "Error in get_users_by_emails: {}".format(exc)
            )
            raise

    async def get_users_by_phones(self, phones: List[str]) -> List[str]:
        """
        Return any of the given phone numbers that already exist in the DB.

        Checks both ``phone_number`` and ``alternate_phone_number`` columns
        so that a number used as an alternate for one user cannot be
        registered as the primary for another user in the same batch.

        Args:
            phones: Phone numbers in international format (+XXXXXXXXXX).

        Returns:
            List of already-registered phone numbers. Empty = all are free.
        """
        if not phones:
            return []
        try:
            async with self.__session_factory() as session:
                primary_result = await session.execute(
                    select(User.phone_number).where(
                        User.phone_number.in_(phones),
                        User.is_deleted == False,  # noqa: E712
                    )
                )
                existing_primary = [row[0] for row in primary_result.all()]

                alt_result = await session.execute(
                    select(User.alternate_phone_number).where(
                        User.alternate_phone_number.in_(phones),
                        User.alternate_phone_number.isnot(None),
                        User.is_deleted == False,  # noqa: E712
                    )
                )
                existing_alt = [row[0] for row in alt_result.all()]

                existing = list(set(existing_primary + existing_alt))
                self.__console_service_logger.info(
                    "get_users_by_phones: {}/{} already registered".format(
                        len(existing), len(phones)
                    )
                )
                return existing
        except Exception as exc:
            self.__console_service_logger.error(
                "Error in get_users_by_phones: {}".format(exc)
            )
            raise

    async def get_users_id_hierarchy_by_emails(
        self, emails: List[str]
    ) -> Dict[str, Dict[str, Any]]:
        """
        Batch-resolve {email: {"id": ..., "role_hierarchy": ...}} for active,
        non-deleted users. Used by bulk-upload parent resolution to look up a
        Parent email against users that already exist in the DB (i.e. not
        created earlier in the same CSV/XLSX).
        """
        if not emails:
            return {}
        try:
            async with self.__session_factory() as session:
                query = (
                    select(
                        User.email,
                        User.id,
                        Role.hierarchy.label("role_hierarchy"),
                    )
                    .join(Role, Role.id == User.role_id, isouter=True)
                    .where(
                        User.email.in_(emails),
                        User.is_active.is_(True),
                        User.is_deleted.is_(False),
                    )
                )
                result = await session.execute(query)
                return {
                    row.email: {"id": row.id, "role_hierarchy": row.role_hierarchy}
                    for row in result.all()
                }
        except Exception as exc:
            self.__console_service_logger.error(
                "Error in get_users_id_hierarchy_by_emails: {}".format(exc)
            )
            raise