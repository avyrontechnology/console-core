"""Filter services module."""

from typing import Optional

from sqlalchemy import and_, case, func, select
from sqlalchemy.orm import joinedload

from src.components.auth.models import Role
from src.components.filters.criteria import BaseFilterCriteria
from src.components.user.filter_builder import UserRoleFilterBuilder
from src.components.user.models import User
from src.components.user.repositories import UserRepository
from src.components.user.schema import (
    Contrasts,
    PaginatedUserRoleResponse,
    UserRoleCombinedResponse,
    UserRoleFilterRequest,
)
from src.exceptions import UserException
from src.loggers.console_service_logger import ConsoleServiceLogger


class FilterService:
    def __init__(
        self,
        user_repository: UserRepository,
        console_service_logger: ConsoleServiceLogger,
    ):
        self.__user_repository = user_repository
        self.__console_service_logger = console_service_logger

    async def get_user_data(
        self,
        filter_request: "UserRoleFilterRequest",
    ) -> "Contrasts.PaginatedUserRoleResponse":
        """
        Fetch combined user and role information with dynamic filtering.

        PaginatedUserRoleResponse: Paginated combined user-role data

        """
        try:
            self.__console_service_logger.info(
                "Fetching combined user-role data with filters: {}".format(
                    filter_request.filters
                )
            )

            criteria = BaseFilterCriteria()

            for filter_item in filter_request.filters:
                criteria.add_filter(
                    filter_item.get("field"),
                    filter_item.get("operator"),
                    filter_item.get("value"),
                )

            for order in filter_request.order_by:
                criteria.add_order_by(order.get("field"), order.get("direction", "ASC"))

            base_query = (
                select(User, Role)
                .join(Role, User.role_id == Role.id)
                .options(
                    joinedload(User.country),
                    joinedload(User.parent),
                )
                .where(Role.is_active == True)
            )
            base_query = base_query.where(User.partner_id == filter_request.partner_id)
            if not filter_request.order_by:
                base_query = base_query.order_by(
                    case((Role.hierarchy == 1, 0), else_=1)
                )
            filter_builder = UserRoleFilterBuilder(
                criteria, base_query, partner_id=filter_request.partner_id
            )
            final_query = await filter_builder.build_query()

            total_count_query = select(func.count()).select_from(final_query.subquery())
            total_count = await self.__user_repository.execute_user_filter_scalar_query(
                total_count_query
            )

            final_query = final_query.limit(filter_request.limit).offset(
                filter_request.offset * filter_request.limit
            )

            result: list[tuple] = (
                await self.__user_repository.execure_user_filter_query(final_query)
            )

            combined_data: list = []
            for user, role in result:
                country_name: Optional[str] = (
                    user.country.name if user.country else None
                )
                parent_id = user.parent_id
                parent_name = user.parent.name if user.parent_id else None
                combined_item = UserRoleCombinedResponse(
                    # User fields
                    id=user.id,
                    name=user.name,
                    email=user.email,
                    phone_number=user.phone_number,
                    is_active=user.is_active,
                    designation=user.designation,
                    description=user.description,
                    created_at=user.created_at,
                    country_id=user.country_id,
                    state_id=user.state_id,
                    city_id=user.city_id,
                    country_name=country_name,
                    parent_id=parent_id,
                    parent_name=parent_name,
                    updated_at=user.updated_at,
                    updated_by=user.updated_by,
                    # Availability
                    current_status=getattr(user, "current_status", None),
                    current_status_icon=getattr(user, "current_status_icon", None),
                    # Role fields
                    role_id=role.id,
                    role_name=role.name,
                    role_description=role.description,
                    role_is_active=role.is_active,
                    role_created_at=role.created_at,
                    # Partner reference (for isolation)
                    partner_id=user.partner_id,
                )
                combined_data.append(combined_item)

            response = PaginatedUserRoleResponse(
                data=combined_data,
                total_count=total_count,
                limit=filter_request.limit,
                offset=filter_request.offset,
            )

            self.__console_service_logger.info(
                "Successfully fetched {} combined user-role records".format(
                    len(combined_data)
                )
            )

            return response
        except UserException as user_exc:
            self.__console_service_logger.error(
                "UserException occurred while fetching combined user-role data: {}".format(
                    str(user_exc)
                )
            )
            raise user_exc

        except Exception as exec:
            self.__console_service_logger.error(
                "Error fetching combined user-role data: {}".format(str(exec))
            )
            raise exec
