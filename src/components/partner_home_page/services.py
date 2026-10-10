import asyncio
from typing import Dict, List

from dependency_injector.wiring import Provide
from fastapi import Depends

from src.components.audit_log.services import AuditService
from src.components.entitlement.services import EntitlementService
from src.components.entitlement.utils import EntitlementUtils
from src.components.grace.repositories import GraceRepository
from src.components.order.constants import ServiceSubscriptionStatus
from src.components.partner_config.constants import (
    PartnerConfigEnum,
    SubscriptionModeEnum,
)
from src.components.partner_config.services import PartnerConfigService
from src.components.partner_home_page.constants import RoleActionFlagKeys
from src.components.partner_home_page.repositories import PartnerHomePageRepositories
from src.components.partner_home_page.role_mapper import RoleFlagMapper
from src.components.partner_home_page.schemas import (
    ParnterInfo,
    RoleActionFlagResponse,
    SusbscribedServices,
    UserDetails,
    UserEntityData,
)
from src.components.plan.constants import Platform
from src.loggers.console_service_logger import ConsoleServiceLogger


class PartnerHomePageService:

    def __init__(
        self,
        partner_home_page_repository: PartnerHomePageRepositories,
        audit_service: AuditService,
        console_service_logger: ConsoleServiceLogger,
    ):

        self.__partner_home_page_repository: PartnerHomePageRepositories = (
            partner_home_page_repository
        )
        self.__audit_service: AuditService = audit_service
        self.__console_service_logger: ConsoleServiceLogger = console_service_logger

    async def get_partner_homepage_details(
        self,
        user_id: int,
        partner_id: int,
        partner_config_service: PartnerConfigService = Depends(
            Provide["partner_config_service"]
        ),
        entitlement_service: EntitlementService = Depends(
            Provide["entitlement_service"]
        ),
        grace_repo: GraceRepository = Depends(Provide["grace_repository"]),
    ) -> UserEntityData:
        try:
            self.__console_service_logger.info(
                "Fetching partner homepage details | user_id={}".format(user_id)
            )

            # Run all independent I/O concurrently
            (
                hierarchy_details,
                user_information,
                partner_details,
                subscription_mode,
                partner_configs,
            ) = await asyncio.gather(
                self.__partner_home_page_repository.get_user_hierarchy(user_id),
                self.__partner_home_page_repository.get_partner_homepage_details(
                    user_id
                ),
                self.__partner_home_page_repository._get_parnter_by_id(partner_id),
                partner_config_service.get_partner_config_by_key(
                    partner_id=partner_id,
                    key=PartnerConfigEnum.SUBSCRIPTION_MODE.value,
                ),
                partner_config_service.get_partner_configs_by_partner_id(partner_id),
            )

            current_user_hierarchy: int = hierarchy_details.get("role_hierarchy_level")

            # ── Partner info ──────────────────────────────────────────────────────

            default_service_info = {
                "status": ServiceSubscriptionStatus.SUSPENDED,
                "entitlement_start_date": None,
                "entitlement_end_date": None,
            }

            subscription_status = {
                Platform.CONSOLE: default_service_info.copy(),
                Platform.MAGLO: default_service_info.copy(),
                Platform.BABBLER: default_service_info.copy(),
                Platform.OBOTAAI: default_service_info.copy(),
            }

            try:
                fetched = await entitlement_service.get_subscription_status(
                    partner_id=partner_id,
                    grace_repo=grace_repo,
                )
                # Merge fetched results over the defaults — unknown services are
                # included, known platforms that came back empty stay as SUSPENDED.
                subscription_status = {**subscription_status, **fetched}

                self.__console_service_logger.info(
                    "Subscription status for partner_id={}: {}".format(
                        partner_id,
                        {s: v["status"] for s, v in subscription_status.items()},
                    )
                )

            except Exception as exc:
                self.__console_service_logger.warning(
                    "Subscription status fetch failed for partner_id={}: {}. "
                    "Defaulting to suspended.".format(partner_id, exc)
                )

            # ── Popup flags ───────────────────────────────────────────────────────────
            user_additional_info: dict = user_information.get("additional_info") or {}
            popup_last_closed: dict = (
                user_additional_info.get("popup_last_closed") or {}
            )

            show_popup: Dict[str, bool] = EntitlementUtils.compute_show_popup(
                user_hierarchy=current_user_hierarchy,
                subscription_status=subscription_status,
                popup_last_closed=popup_last_closed,
            )

            for service, status_info in subscription_status.items():
                status_info["show_popup"] = show_popup.get(service, False)

            partner_info = ParnterInfo(
                partner_id=partner_id,
                partner_name=partner_details.name or "",
                subscription_mode=(
                    subscription_mode.value
                    if subscription_mode
                    else SubscriptionModeEnum.SELF_SERVED
                ),
                subscription_status=subscription_status,
            )

            # ── Role flags ────────────────────────────────────────────────────────
            role_flag_mapper: Dict = RoleFlagMapper.get_flags(
                current_user_hierarchy, partner_details.is_internal
            )
            flag_defaults = {
                RoleActionFlagKeys.CAN_VIEW_DASHBOARD: False,
                RoleActionFlagKeys.CAN_VIEW_PARTNERS: False,
                RoleActionFlagKeys.CAN_VIEW_PERMISSIONS: False,
                RoleActionFlagKeys.CAN_VIEW_USERS: False,
                RoleActionFlagKeys.CAN_VIEW_CONFIGURATIONS: False,
                RoleActionFlagKeys.CAN_VIEW_ADD_PERMISSIONS: False,
                RoleActionFlagKeys.CAN_VIEW_PARTNER_INFO: False,
                RoleActionFlagKeys.CAN_VIEW_INTERNAL_ROLES: False,
                RoleActionFlagKeys.CAN_EDIT_INTERNAL_ROLES: False,
                RoleActionFlagKeys.CAN_VIEW_PARTNER_CONFIG: False,
                RoleActionFlagKeys.CAN_ASSUME_USER: current_user_hierarchy == 0,
                RoleActionFlagKeys.CAN_VIEW_PLANS: False,
                RoleActionFlagKeys.CAN_VIEW_ORDER_HISTORY: False,
                RoleActionFlagKeys.CAN_EDIT_BABBLER_PRICING: False,
                RoleActionFlagKeys.CAN_VIEW_API_ADMIN: False,
            }
            role_action_response = RoleActionFlagResponse(
                **{
                    key: role_flag_mapper.get(key, default)
                    for key, default in flag_defaults.items()
                }
            )

            # ── Services info ─────────────────────────────────────────────────────
            if partner_configs:
                if isinstance(partner_configs[0], dict):
                    services_dict = {
                        item["key"]: item["value"] for item in partner_configs
                    }
                else:
                    services_dict = {item.key: item.value for item in partner_configs}
            else:
                services_dict = {}

            services_info = SusbscribedServices(
                is_maglo_enabled=services_dict.get("is_maglo_enabled", False),
                is_talko_enabled=services_dict.get("is_talko_enabled", False),
                is_babbler_enabled=services_dict.get("is_babbler_enabled", False),
                is_obotaai_enabled=services_dict.get("is_obotaai_enabled", False),
                is_add_number_enabled=services_dict.get("is_add_number_enabled", False),

            )

            user_entity_data = UserEntityData(
                user_info=UserDetails(**user_information),
                partner_info=partner_info,
                user_permissions=role_action_response,
                services_info=services_info,
            )

            self.__console_service_logger.info(
                "Fetched partner homepage details | user_id={}".format(user_id)
            )
            return user_entity_data

        except Exception as ex:
            self.__console_service_logger.error(
                "Unexpected error occurred while getting partner homepage details by user_id {}".format(
                    user_id
                )
            )
            raise ex

    async def partner_dashboard_cards(self, current_user_id: int) -> List[dict]:
        try:
            self.__console_service_logger.info(
                "trying to get partner dashboard card counts."
            )
            dashboard_cards: List[dict] = (
                await self.__partner_home_page_repository.partner_dashboard_cards(
                    current_user_id
                )
            )
            self.__console_service_logger.info(
                "successfully fetched partner dashboard card counts: {}".format(
                    dashboard_cards
                )
            )
            return dashboard_cards
        except Exception as exec:
            self.__console_service_logger.error(
                "Error fetching partner dashboard card counts: {}".format(str(exec))
            )
            raise exec
