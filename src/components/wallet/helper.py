"""Wallet Util module."""

from uuid import UUID
from typing import Optional

from src.components.api_key.schemas import ApiKeyResponse
from src.components.api_key.services import ApiKeyService
from src.components.partner.models import Partner
from src.components.partner.services import PartnerService
from src.exceptions import AuthException
from src.loggers.console_service_logger import ConsoleServiceLogger


class WalletHelper:
    async def resolve_partner_id_with_api_key(
        current_user: dict,
        partner_id: Optional[UUID],
        api_key: Optional[str],
        api_key_service: ApiKeyService,
        partner_service: PartnerService,
        logger: ConsoleServiceLogger,
    ) -> int:
        try:
            current_user_partner_id = current_user.get("partner_id")
            if partner_id and api_key:
                api_key_obj: ApiKeyResponse = await api_key_service.get_api_key(
                    current_user, current_user_partner_id
                )

                if not api_key_obj:
                    raise AuthException("Invalid API key")

                if api_key_obj.partner_id == partner_id:
                    effective_partner_id = partner_id

                else:
                    partner_obj: Partner = await partner_service.get_partner_by_id(
                        api_key_obj.partner_id
                    )

                    if partner_obj.is_internal:
                        effective_partner_id = partner_id
                    else:
                        raise AuthException("Unauthorized user")

            elif partner_id and not api_key:
                effective_partner_id = partner_id
            else:
                effective_partner_id = current_user_partner_id

            return effective_partner_id
        except AuthException as exec:
            logger.error("Auth exception occured: {}".format(exec))
            raise exec
