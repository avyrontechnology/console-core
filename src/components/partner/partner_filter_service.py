from dependency_injector.wiring import Provide
from fastapi import Depends
from sqlalchemy import String, cast, func, select, text
from sqlalchemy.future import select
from sqlalchemy.orm import aliased
from sqlalchemy.dialects.postgresql import JSONB

from src.components.auth.constant import UserHierarchyLevel
from src.components.filters.criteria import BaseFilterCriteria
from src.components.partner.constant import DashboardFilters
from src.components.partner.models import Partner
from src.components.partner.partner_filter_builder import PartnerFilterBuilder
from src.components.partner.repositories import PartnerRepository
from src.components.partner.schema import (
    PaginatedPartnerResponse,
    PartnerFilterRequest,
    PartnerResponse,
)
from src.components.partner_config.models import PartnerConfig
from src.components.partner_meta_data.services import PartnerMetaDataServices
from src.components.user.services import UserService
from src.exceptions import PartnerException
from src.loggers.console_service_logger import ConsoleServiceLogger
from src.components.user_config.models import UserConfig
from src.components.user.models import User


class PartnerFilterService:

    def __init__(
        self,
        partner_repository: PartnerRepository,
        console_service_logger: ConsoleServiceLogger,
    ):
        self.__partner_repository = partner_repository
        self.__console_service_logger = console_service_logger

    async def enlist_partners_dynamically(
        self,
        filter_request: "PartnerFilterRequest",
        user_service: UserService = Depends(Provide["console_service"]),
        partner_meta_data_service: PartnerMetaDataServices = Depends(
            Provide["partner_meta_data_service"]
        ),
    ) -> "PaginatedPartnerResponse":
        """
        Fetch partner information with dynamic filtering.

        PaginatedPartnerResponse: Paginated partner data

        """
        try:
            self.__console_service_logger.info(
                "Fetching partner data with filters: {}".format(filter_request.filters)
            )

            criteria = BaseFilterCriteria()

            dashboard_filter = None
            if filter_request.dashboard_filters:
                dashboard_filter = filter_request.dashboard_filters.value

            for filter_item in filter_request.filters:
                criteria.add_filter(
                    filter_item.get("field"),
                    filter_item.get("operator"),
                    filter_item.get("value"),
                )

            for order in filter_request.order_by:
                criteria.add_order_by(order.get("field"), order.get("direction", "ASC"))

            query = select(Partner)

            if filter_request.is_custom_role_permission_enabled:
                query = query.join(
                    PartnerConfig, Partner.id == PartnerConfig.partner_id
                ).where(
                    PartnerConfig.key == "is_custom_role_permission_enabled",
                    cast(PartnerConfig.value, String) == "true",
                )

            feature_flag_filters: dict = {
                DashboardFilters.PARTNERS_USING_TALKO.value: "is_talko_enabled",
            }

            if dashboard_filter in feature_flag_filters:
                alias = aliased(PartnerConfig)
                query = query.join(alias, Partner.id == alias.partner_id).where(
                    alias.key == feature_flag_filters[dashboard_filter],
                    cast(alias.value, String) == "true",
                )
            elif dashboard_filter == DashboardFilters.PARTNERS_GT_FIFTY_LICENSES.value:
                query = query.where(Partner.active_license > 50)
            elif dashboard_filter == DashboardFilters.PARTNERS_LAST_SEVEN_DAYS.value:
                import time

                cutoff = int(time.time() * 1000) - (7 * 24 * 60 * 60 * 1000)
                query = query.where(Partner.created_at >= cutoff)

            filter_builder = PartnerFilterBuilder(criteria, query)
            final_query = await filter_builder.build_query()

            total_count_query = select(func.count()).select_from(final_query.subquery())
            total_count = (
                await self.__partner_repository.execute_partner_filter_scalar_query(
                    total_count_query
                )
            )

            final_query = final_query.limit(filter_request.limit).offset(
                filter_request.offset * filter_request.limit
            )

            result: list[tuple] = (
                await self.__partner_repository.execure_partner_filter_query(
                    final_query
                )
            )

            partner_ids = [partner.id for (partner,) in result]

            meta_map = (
                await partner_meta_data_service.get_partner_meta_data_by_partner_ids(
                    partner_ids
                )
            )

            admin_hierarchy: int = UserHierarchyLevel.ADMIN_LEVEL_HIERARCHY

            admin_users = await user_service.get_admin_credentials_by_hierarchy(
                user_hierarchy=admin_hierarchy, partner_id=partner_ids
            )
            admin_map = {admin.partner_id: admin for admin in admin_users}
           
            partner_user_counts: dict = await self._get_active_user_counts_for_partners(partner_ids)
            
            partners_data: list = []
            for (partner,) in result:
                is_trial = meta_map.get(partner.id, {}).get(
                    "is_talko_free_trial__enabled", False
                )
                admin_credentials = admin_map.get(partner.id)
                partner_response: PartnerResponse = PartnerResponse(
                    id=partner.id,
                    name=partner.name,
                    company_legal_name=partner.company_legal_name,
                    gst_no=partner.gst_no,
                    cin_no=partner.cin_no,
                    active_license=partner.active_license,
                    description=partner.description,
                    email=admin_credentials.email if admin_credentials else None,
                    phone_number=(
                        admin_credentials.phone_number if admin_credentials else None
                    ),
                    is_active=partner.is_active,
                    is_partner_paid=None,
                    is_free_trial_enabled=is_trial,
                    active_talko_users=partner_user_counts.get(partner.id, {}).get("is_talko_enabled", 0),
                )
                partners_data.append(partner_response)

            response = PaginatedPartnerResponse(
                total_count=total_count,
                limit=filter_request.limit,
                offset=filter_request.offset,
                partners_data=partners_data,
            )

            self.__console_service_logger.info(
                "Successfully fetched {} partner records".format(len(partners_data))
            )

            return response
        except PartnerException as user_exc:
            self.__console_service_logger.error(
                "UserException occurred while fetching partner data: {}".format(
                    str(user_exc)
                )
            )
            raise user_exc

        except Exception as exec:
            self.__console_service_logger.error(
                "Error fetching partner data: {}".format(str(exec))
            )
            raise exec
        
    async def _get_active_user_counts_for_partners(self, partner_ids: list[int]):
        try: 
            active_keys: list[str] = ["is_talko_enabled"]
            partner_user_counts: dict = {
                pid: dict.fromkeys(active_keys, 0) for pid in partner_ids
            } if partner_ids else {}

            counts_query = (
                select(
                    User.partner_id,
                    UserConfig.key,
                    func.count().label("count"),
                )
                .join(User, User.id == UserConfig.user_id)
                .where(
                    User.partner_id.in_(partner_ids),
                    User.is_active.is_(True),
                    UserConfig.is_active.is_(True),
                    UserConfig.key.in_(active_keys),
                    cast(UserConfig.value, JSONB) == cast(True, JSONB),
                )
                .group_by(User.partner_id, UserConfig.key)
            )

            counts_result = await self.__partner_repository.execure_partner_filter_query(
                counts_query
            )
            for row in counts_result:
                partner_id_val, key_val, cnt = row
                if partner_id_val in partner_user_counts:
                    partner_user_counts[partner_id_val][key_val] = int(cnt)
            return partner_user_counts
        except Exception as exec:
            self.__console_service_logger.error("An un expected error occured while fetching the active user counts")
            raise exec
        

