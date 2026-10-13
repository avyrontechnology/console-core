from uuid import UUID
from typing import List

from dependency_injector.wiring import Provide, inject
from fastapi import APIRouter, Body, Depends, Query, Request, status

from src.components.auth.constant import TokenKeys
from src.components.common.errors import ErrorMsg
from src.components.common.response import InternalServerErrorResponse, SuccessResponse
from src.components.partner_home_page.schemas import UserEntityData
from src.components.partner_home_page.services import PartnerHomePageService
from src.core.container import Container
from src.loggers.console_service_logger import ConsoleServiceLogger


class PartnerHomePageController:
    # User controller, all user related endpoints will be in this class.
    partner_home_page_router = APIRouter()

    @partner_home_page_router.get(
        "/partner_homepage_details", response_model=UserEntityData
    )
    @inject
    async def get_partner_homepage_details(
        request: Request,
        partner_home_page_service: PartnerHomePageService = Depends(
            Provide[Container.partner_home_page_service]
        ),
        console_service_logger: ConsoleServiceLogger = Depends(
            Provide[Container.console_service_logger]
        ),
    ):
        try:
            current_user: dict = request.state.user
            user_id: UUID = current_user.get(TokenKeys.USER_ID)
            partner_id: UUID = current_user.get(TokenKeys.PARTNER)
            console_service_logger.info(
                "Fetching partner homepage details for user: {}".format(user_id)
            )
            partner_homepage_details: UserEntityData = await partner_home_page_service.get_partner_homepage_details(user_id, partner_id)
            console_service_logger.info(
                "Fetched partner homepage details for user: {} having partner_id: {}".format(user_id, partner_id)
            )
            return SuccessResponse(partner_homepage_details)
        except Exception as exec:
            console_service_logger.error(
                "Error fetching partner homepage details: {}".format(exec)
            )
            return InternalServerErrorResponse(ErrorMsg.INTERNAL_SERVER_ERROR)

    @partner_home_page_router.get("/partner_dashboard_cards")
    # @permission_check("console:get_partner_dashboard_cards")
    @inject
    async def get_partner_dashboard_cards(
        request: Request,
        partner_home_page_service: PartnerHomePageService = Depends(
            Provide[Container.partner_home_page_service]
        ),
        console_service_logger: ConsoleServiceLogger = Depends(
            Provide[Container.console_service_logger]
        ),
    ):
        try:
            current_user: dict = request.state.user
            current_user_id: UUID = current_user.get(TokenKeys.USER_ID)
            console_service_logger.info("Getting partner dashboard cards")
            dashboard_cards: List[dict] = (
                await partner_home_page_service.partner_dashboard_cards(current_user_id)
            )
            console_service_logger.info(
                "Fetched partner dashboard cards: {}".format(dashboard_cards)
            )
            return SuccessResponse(dashboard_cards)
        except Exception as exec:
            console_service_logger.error(
                "Error fetching partner dashboard cards: {}".format(str(exec))
            )
            return InternalServerErrorResponse(ErrorMsg.INTERNAL_SERVER_ERROR)
