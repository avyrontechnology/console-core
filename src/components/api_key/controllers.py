from uuid import UUID
from typing import List, Optional

from dependency_injector.wiring import Provide, inject
from fastapi import APIRouter, Depends, Query, Request, status

from src.components.api_key.errors import ApiKeyNotFoundError
from src.components.api_key.schemas import (
    ApiKeyGenerateRequest,
    ApiKeyResponse,
    ApiKeyUpdateRequest,
)
from src.components.api_key.services import ApiKeyService
from src.components.common.constants import CurrentUserMap
from src.components.common.errors import ErrorMsg
from src.components.common.response import (
    InternalServerErrorResponse,
    NotFoundResponse,
    SuccessResponse,
    BadRequestResponse
)
from src.components.rbac.permission_injector import permission_check
from src.core.container import Container
from src.loggers.console_service_logger import ConsoleServiceLogger
from src.components.partner.error import PartnerNotFoundError
from src.exceptions import ApiKeyException
class ApiKeysController:

    api_key_router = APIRouter()

    @api_key_router.get("/generate_api_key", response_model=ApiKeyResponse)
    @permission_check("console:generate_api_key")
    @inject
    async def generate_api_key(
        request: Request,
        partner_id: Optional[UUID] = None,
        api_key_service: ApiKeyService = Depends(Provide[Container.api_key_service]),
        console_service_logger: ConsoleServiceLogger = Depends(
            Provide[Container.console_service_logger]
        ),
    ):
        try:
            current_user: dict = request.state.user
            console_service_logger.info(
                f"Attempting to generate api key for partner: {partner_id}"
            )
            api_key = await api_key_service.re_generate_api_key(current_user, partner_id)
            return SuccessResponse(api_key)
        except ApiKeyException as exc:
            console_service_logger.warning(f"Error occrred found while generating api keys: {exc}")
            return BadRequestResponse(str(exc))
        except PartnerNotFoundError as exc:
            console_service_logger.warning(f"Partner not found while generating api keys: {exc}")
            return NotFoundResponse(str(exc))
        except Exception as exc:
            console_service_logger.error(
                "Unexpected error while generating api_key: {}".format(str(exc))
            )
            return InternalServerErrorResponse(ErrorMsg.INTERNAL_SERVER_ERROR)

    @api_key_router.post("/generate_api_key", response_model=ApiKeyResponse)
    @permission_check("console:generate_api_key_with_scopes")
    @inject
    async def generate_api_key_with_scopes(
        request: Request,
        payload: Optional[ApiKeyGenerateRequest] = None,
        partner_id: Optional[UUID] = None,
        api_key_service: ApiKeyService = Depends(Provide[Container.api_key_service]),
        console_service_logger: ConsoleServiceLogger = Depends(
            Provide[Container.console_service_logger]
        ),
    ):
        """
        Generate (rotate) an API key, optionally setting ``scopes`` and
        ``user_context``. ``user_context`` is auto-derived from the caller when
        not supplied. Equivalent to ``GET /generate_api_key`` when no body is
        sent.
        """
        try:
            current_user: dict = request.state.user
            scopes = payload.scopes if payload else None
            user_context = payload.user_context if payload else None
            console_service_logger.info(
                f"Attempting to generate api key (with scopes) for partner: {partner_id}"
            )
            api_key = await api_key_service.re_generate_api_key(
                current_user,
                partner_id,
                scopes=scopes,
                user_context=user_context,
                expires_at=payload.expires_at if payload else None,
            )
            return SuccessResponse(api_key)
        except ApiKeyException as exc:
            console_service_logger.warning(
                f"Error occurred while generating api keys: {exc}"
            )
            return BadRequestResponse(str(exc))
        except PartnerNotFoundError as exc:
            console_service_logger.warning(
                f"Partner not found while generating api keys: {exc}"
            )
            return NotFoundResponse(str(exc))
        except Exception as exc:
            console_service_logger.error(
                "Unexpected error while generating api_key: {}".format(str(exc))
            )
            return InternalServerErrorResponse(ErrorMsg.INTERNAL_SERVER_ERROR)

    @api_key_router.patch("/api_key", response_model=ApiKeyResponse)
    @permission_check("console:update_api_key")
    @inject
    async def update_api_key(
        request: Request,
        payload: ApiKeyUpdateRequest,
        partner_id: Optional[UUID] = None,
        api_key_service: ApiKeyService = Depends(Provide[Container.api_key_service]),
        console_service_logger: ConsoleServiceLogger = Depends(
            Provide[Container.console_service_logger]
        ),
    ):
        """
        Update ``scopes`` / ``user_context`` on the partner's active API key in
        place (no rotation, key value unchanged). A field left as ``null`` is
        untouched; pass ``[]`` / ``{}`` to clear.
        """
        try:
            current_user: dict = request.state.user
            console_service_logger.info(
                f"Attempting to update api key metadata for partner: {partner_id}"
            )
            api_key = await api_key_service.update_api_key_metadata(
                current_user=current_user,
                partner_id=partner_id,
                scopes=payload.scopes,
                user_context=payload.user_context,
                expires_at=payload.expires_at,
            )
            return SuccessResponse(api_key)
        except ApiKeyNotFoundError as exc:
            console_service_logger.warning(
                f"No active API key found for partner_id={partner_id}"
            )
            return NotFoundResponse(str(exc))
        except ApiKeyException as exc:
            console_service_logger.warning(
                f"Error occurred while updating api keys: {exc}"
            )
            return BadRequestResponse(str(exc))
        except PartnerNotFoundError as exc:
            console_service_logger.warning(
                f"Partner not found while updating api keys: {exc}"
            )
            return NotFoundResponse(str(exc))
        except Exception as exc:
            console_service_logger.error(
                "Unexpected error while updating api_key: {}".format(str(exc))
            )
            return InternalServerErrorResponse(ErrorMsg.INTERNAL_SERVER_ERROR)

    @api_key_router.get("/get_api_key", response_model=ApiKeyResponse)
    @permission_check("console:get_api_key")
    @inject
    async def get_api_key(
        request: Request,
        partner_id: Optional[UUID] = None,
        api_key_service: ApiKeyService = Depends(Provide[Container.api_key_service]),
        console_service_logger: ConsoleServiceLogger = Depends(
            Provide[Container.console_service_logger]
        ),
    ):
        """
        Get active API key for the current partner.
        """
        try:

            current_user: dict = request.state.user

            console_service_logger.info(
                f"Attempting to fetch API key for partner: {partner_id}"
            )

            # Call service layer to fetch the API key
            api_key_details: ApiKeyResponse = await api_key_service.get_api_key(
               current_user=current_user, partner_id=partner_id
            )
            console_service_logger.info(
                f"Successfully fetched API key for partner: {partner_id}"
            )
            return SuccessResponse(api_key_details)
        except ApiKeyNotFoundError as exc:
            console_service_logger.warning(
                f"No active API key found for partner_id={partner_id}"
            )
            return NotFoundResponse(str(exc))
        except ApiKeyException as exc:
            console_service_logger.warning(f"Error occrred found while getting api keys: {exc}")
            return BadRequestResponse(str(exc))
        except PartnerNotFoundError as exc:
            console_service_logger.warning(f"Partner not found while getting api keys: {exc}")
            return NotFoundResponse(str(exc))
        except Exception as exc:
            console_service_logger.error(
                f"Unexpected error while fetching API key for partner: {partner_id}. Error: {str(exc)}"
            )
            return InternalServerErrorResponse(ErrorMsg.INTERNAL_SERVER_ERROR)

    @api_key_router.put("/inactivate_api_key", response_model=ApiKeyResponse)
    @permission_check("console:inactivate_api_key")
    @inject
    async def inactivate_api_key(
        request: Request,
        api_key_service: ApiKeyService = Depends(Provide[Container.api_key_service]),
        console_service_logger: ConsoleServiceLogger = Depends(
            Provide[Container.console_service_logger]
        ),
    ):
        """
        Inactivate (mark inactive) an API key associated with a given partner ID.
        """
        try:
            current_user: dict = request.state.user
            partner_id: UUID = current_user.get(CurrentUserMap.PARTNER_ID)
            console_service_logger.info(
                f"User {current_user.get('id')} attempting to inactivate API key for partner_id={partner_id}"
            )

            api_key = await api_key_service.inactivate_api_key(partner_id, current_user)

            return SuccessResponse(api_key)

        except ApiKeyNotFoundError as exc:
            console_service_logger.warning(
                f"No active API key found for partner_id={partner_id}"
            )
            return NotFoundResponse(str(exc))
        except Exception as exc:
            console_service_logger.error(
                f"Unexpected error while inactivating API key for partner_id={partner_id}: {str(exc)}"
            )
            return InternalServerErrorResponse(ErrorMsg.INTERNAL_SERVER_ERROR)
