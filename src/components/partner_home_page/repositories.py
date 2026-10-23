from uuid import UUID
from contextlib import AbstractContextManager
from datetime import datetime, timedelta
from typing import Callable, List

from sqlalchemy import String, case, cast, func
from sqlalchemy.future import select
from sqlalchemy.orm import Session

from src.components.auth.models import Role
from src.components.partner.constant import DashboardFilters
from src.components.partner.models import Partner
from src.components.partner_config.models import PartnerConfig
from src.components.partner_home_page.constants import PartnerDashboardCardsAttributes
from src.components.user.models import User
from src.loggers.console_service_logger import ConsoleServiceLogger


class PartnerHomePageRepositories:

    def __init__(
        self,
        session_factory: Callable[..., AbstractContextManager[Session]],
        console_service_logger: ConsoleServiceLogger,
    ) -> None:
        self.__session_factory: Callable[..., AbstractContextManager[Session]] = (
            session_factory
        )
        self.__console_service_logger: ConsoleServiceLogger = console_service_logger

    async def get_partner_homepage_details(self, user_id: UUID) -> User:
        try:
            async with self.__session_factory() as session:
                self.__console_service_logger.info(
                    "Attempting to get partner homepage details by user_id {}".format(
                        user_id
                    )
                )
                query = select(
                    User.id.label("id"),
                    User.name.label("name"),
                    User.designation.label("designation"),
                    User.email.label("email"),
                    User.is_internal.label("is_internal"),
                    User.additional_info.label("additional_info"),
                ).where(User.id == user_id)
                result = await session.execute(query)
                user = result.mappings().first()
                return user
        except Exception as exc:
            self.__console_service_logger.info(
                "Unexpected error occurred while getting partner homepage details by user_id {}".format(
                    user_id
                )
            )
            raise exc

    async def get_user_hierarchy(self, user_id: UUID) -> List[Role]:
        try:
            async with self.__session_factory() as session:
                self.__console_service_logger.info(
                    "Attempting to get the user hierarchy for the user id: {}".format(
                        user_id
                    )
                )
                query = (
                    select(Role.hierarchy.label("role_hierarchy_level"))
                    .join(User, User.role_id == Role.id)
                    .filter(User.id == user_id)
                )

                result = await session.execute(query)
                user_hierarchy_level = result.mappings().first()
                return user_hierarchy_level
        except Exception as exc:
            self.__console_service_logger.info(
                "Unexpected error occurred while getting user hierarchy by user_id {}".format(
                    user_id
                )
            )
            raise exc

    async def partner_dashboard_cards(self, current_user_id: UUID) -> List[dict]:
        try:
            async with self.__session_factory() as session:
                self.__console_service_logger.info(
                    "Checking if current user is internal or not, user id: {}".format(
                        current_user_id
                    )
                )
                query = select(User).where(
                    User.id == current_user_id, User.is_internal == True
                )
                result = await session.execute(query)
                user = result.scalar_one()
                self.__console_service_logger.info(
                    "Fetching partner dashboard cards data."
                )
                if not user:
                    self.__console_service_logger.info(
                        "User is not internal. Returning all counts as 0."
                    )
                    return [
                        {
                            "title": PartnerDashboardCardsAttributes.TOTAL_PARTNERS,
                            "key": None,
                            "count": 0,
                        },
                        {
                            "title": PartnerDashboardCardsAttributes.LAST_WEEK_PARTNERS,
                            "key": DashboardFilters.PARTNERS_LAST_SEVEN_DAYS,
                            "count": 0,
                        },
                        {
                            "title": PartnerDashboardCardsAttributes.PARTNERS_MORE_THAN_FIFTY_LICENSES,
                            "key": DashboardFilters.PARTNERS_GT_FIFTY_LICENSES,
                            "count": 0,
                        },
                        {
                            "title": PartnerDashboardCardsAttributes.PARTNERS_USING_HOLLAR,
                            "key": DashboardFilters.PARTNERS_USING_TALKO,
                            "count": 0,
                        },

                    ]

                # Total Partners
                total_partners = await session.scalar(
                    select(func.count(Partner.id)).where(Partner.is_active == True)
                )

                # Last 7 Days Partners
                seven_days_ago = int(
                    (datetime.utcnow() - timedelta(days=7)).timestamp() * 1000
                )
                last_week_partners = await session.scalar(
                    select(func.count(Partner.id)).where(
                        Partner.is_active == True, Partner.created_at >= seven_days_ago
                    )
                )

                # Partners > 50 Licenses
                partners_with_50_licenses = await session.scalar(
                    select(func.count(Partner.id)).where(
                        Partner.is_active == True, Partner.active_license > 50
                    )
                )

                partner_configs_counts = await session.execute(
                    select(
                        func.sum(
                            case(
                                (
                                    (PartnerConfig.key == "is_talko_enabled")
                                    & (cast(PartnerConfig.value, String) == "true"),
                                    1,
                                ),
                                else_=0,
                            )
                        ).label("partners_using_talko"),
                    )
                    .select_from(Partner)
                    .join(PartnerConfig, Partner.id == PartnerConfig.partner_id)
                    .where(Partner.is_active == True)
                )

                (partners_using_talko,) = (
                    partner_configs_counts.one()
                )

                # Constructing the response
                dashboard_cards = [
                    {
                        "title": PartnerDashboardCardsAttributes.TOTAL_PARTNERS,
                        "key": None,
                        "count": total_partners,
                    },
                    {
                        "title": PartnerDashboardCardsAttributes.LAST_WEEK_PARTNERS,
                        "key": DashboardFilters.PARTNERS_LAST_SEVEN_DAYS,
                        "count": last_week_partners,
                    },
                    {
                        "title": PartnerDashboardCardsAttributes.PARTNERS_MORE_THAN_FIFTY_LICENSES,
                        "key": DashboardFilters.PARTNERS_GT_FIFTY_LICENSES,
                        "count": partners_with_50_licenses,
                    },
                    {
                        "title": PartnerDashboardCardsAttributes.PARTNERS_USING_HOLLAR,
                        "key": DashboardFilters.PARTNERS_USING_TALKO,
                        "count": partners_using_talko,
                    },

                ]

                self.__console_service_logger.info(
                    "Partner dashboard cards data fetched successfully: {}".format(
                        dashboard_cards
                    )
                )
                return dashboard_cards

        except Exception as ex:
            self.__console_service_logger.error(
                "Error while fetching partner dashboard cards: {}".format(str(ex))
            )
            raise ex

    async def _get_parnter_by_id(self, parnter_id: UUID) -> Partner:
        self.__console_service_logger.info(
            "Getting Parnter with id: {}".format(parnter_id)
        )
        try:
            async with self.__session_factory() as session:
                query = select(Partner).filter(Partner.id == parnter_id)
                result = await session.execute(query)
                parnter: Partner = result.scalars().first()
                return parnter
        except Exception as exc:
            self.__console_service_logger.info(
                "Un Expected Error came while getting Parnter with id: {}".format(
                    parnter_id
                )
            )
            raise exc
