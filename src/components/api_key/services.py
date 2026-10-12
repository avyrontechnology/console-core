from uuid import UUID
from typing import Optional

from src.components.api_key.constants import ApiKeyResponseMessage, ExceptionMessages
from src.components.api_key.errors import ApiKeyNotFoundError
from src.components.api_key.models import ApiKey
from src.components.api_key.repositories import ApiKeyRepository
from src.components.api_key.schemas import ApiKeyResponse
from src.components.auth.constant import RoleDictKeys, UserHierarchyLevel
from src.components.auth.service import AuthService
from src.components.cache.helper import CacheHelper
from src.components.common.constants import CurrentUserMap
from src.components.partner.error import PartnerNotFoundError
from src.components.user.errors import UserNotFoundError
from src.exceptions import ApiKeyException
from src.loggers.console_service_logger import ConsoleServiceLogger
from src.components.cache import Keys as RedisKeys
from src.components.cache import TTL as RedisTTL
class ApiKeyService:

    def __init__(
        self,
        api_key_repository: ApiKeyRepository,
        console_service_logger: ConsoleServiceLogger,
        cache_helper: CacheHelper,
        auth_service: AuthService = None,
        user_repository=None,
    ) -> None:
        self.__api_key_repository: ApiKeyRepository = api_key_repository
        self.__console_service_logger: ConsoleServiceLogger = console_service_logger
        self.__cache_helper: CacheHelper = cache_helper
        self.__auth_service: AuthService = auth_service
        self.__user_repository = user_repository

    async def generate_api_key(self, current_user: dict) -> ApiKeyResponse:
        try:
            current_user_id: UUID = current_user.get(CurrentUserMap.USER_ID)
            partner_id: UUID = current_user.get(CurrentUserMap.PARTNER_ID)
            self.__console_service_logger.info(
                f"Attempting to generate api key for partner: {partner_id}"
            )
            result = await self.__api_key_repository.generate_api_key(
                partner_id, current_user_id
            )
            response = ApiKeyResponse.model_validate(result)
            return response
        except Exception as ex:
            self.__console_service_logger.error(
                "Unexpected error fetching countries.{}".format(str(ex))
            )
            raise ex

    async def validate_api_key(self, key: str) -> ApiKeyResponse | None:
        """
        Validate the given API key using the repository method.
        If valid, return ApiKeyResponse; otherwise, return None.
        """
        try:
            self.__console_service_logger.info(
                f"Attempting to validate API key: {key[:10]}..."
            )

            result = await self.__api_key_repository.validate_api_key(key)

            if not result:
                self.__console_service_logger.warning(
                    f"Invalid or inactive API key: {key[:10]}..."
                )
                return None

            response = ApiKeyResponse.model_validate(result)

            self.__console_service_logger.info(
                f"API key validated successfully for partner_id: {result.partner_id}"
            )

            return response

        except Exception as ex:
            self.__console_service_logger.error(
                f"Unexpected error validating API key {key[:10]}...: {str(ex)}"
            )
            raise ex

    async def get_api_key(
        self,
        current_user: dict = None,
        partner_id: UUID = None,
        auth_service: AuthService = None,
    ) -> Optional[ApiKeyResponse]:

        try:
            auth_service = auth_service or self.__auth_service
            partner_id, _ = await self.__resolve_partner_access(
                current_user=current_user,
                partner_id=partner_id,
                auth_service=auth_service,
            )

            self.__console_service_logger.info(
                f"Fetching active API key for partner_id: {partner_id}"
            )

            cached_key = await self.__cache_helper.get_cache(key=RedisKeys.PARTNER_API_KEY.format(partner_id))
            if cached_key:
                return ApiKeyResponse.model_validate(cached_key)

            result: ApiKey = await self.__api_key_repository.get_active_api_key(
                partner_id
            )

            if not result:
                self.__console_service_logger.warning(
                    f"No active API key found for partner_id: {partner_id}"
                )
                raise ApiKeyNotFoundError(partner_id)
            await self.__cache_helper.set_cache(
                key=RedisKeys.PARTNER_API_KEY.format(partner_id),
                value=ApiKeyResponse.model_validate(result).dict(),
                ttl=RedisTTL.ONE_WEEK,
            )
            return ApiKeyResponse.model_validate(result)

        except Exception as ex:
            self.__console_service_logger.error(
                f"Unexpected error fetching API key for partner_id={partner_id}: {str(ex)}"
            )
            raise ex

    async def workflow_get_api_key(self, partner_id: UUID) -> Optional[ApiKeyResponse]:

        try:
            self.__console_service_logger.info(
                f"Fetching active API key for partner_id: {partner_id}"
            )

            result: ApiKey = await self.__api_key_repository.get_active_api_key(
                partner_id
            )

            if not result:
                self.__console_service_logger.warning(
                    f"No active API key found for partner_id: {partner_id}"
                )
                raise ApiKeyNotFoundError(partner_id)

            return ApiKeyResponse.model_validate(result)

        except Exception as ex:
            self.__console_service_logger.error(
                f"Unexpected error fetching API key for partner_id={partner_id}: {str(ex)}"
            )
            raise ex

    async def re_generate_api_key(
        self,
        current_user: dict = None,
        partner_id: UUID = None,
        scopes: list | None = None,
        user_context: dict | None = None,
        auth_service: AuthService = None,
    ) -> ApiKeyResponse:

        try:
            auth_service = auth_service or self.__auth_service
            partner_id, user_id = await self.__resolve_partner_access(
                current_user=current_user,
                partner_id=partner_id,
                auth_service=auth_service,
            )

            if scopes is not None:
                await self.__validate_scopes(scopes, auth_service)

            if user_context is not None:
                await self.__validate_user_context(user_context, partner_id)
            elif current_user:
                # Auto-derive from the generating user. user_context is strictly
                # {"user_id": <uuid-string>} — no other entries are allowed.
                # Stringified: user_context persists in a JSON column.
                user_context = {
                    "user_id": str(current_user.get(CurrentUserMap.USER_ID))
                }

            self.__console_service_logger.info(
                f"Re-generating API key for partner_id: {partner_id}"
            )

            await self.__cache_helper.delete_cache(
                key=RedisKeys.PARTNER_API_KEY.format(partner_id)
            )

            existing_key = await self.__api_key_repository.inactivate_api_key(
                partner_id=partner_id, current_user_id=user_id
            )

            if existing_key:
                self.__console_service_logger.info(
                    f"Previous API key inactivated for partner_id: {partner_id}"
                )

            new_key = await self.__api_key_repository.generate_api_key(
                partner_id=partner_id,
                current_user_id=user_id,
                scopes=scopes,
                user_context=user_context,
            )

            self.__console_service_logger.info(
                f"API key re-generated successfully for partner_id={partner_id}, key_id={new_key.id}"
            )

            return ApiKeyResponse.model_validate(new_key)

        except Exception as ex:
            self.__console_service_logger.error(
                f"Unexpected error generating API key for partner: {partner_id}, Error: {str(ex)}"
            )
            raise ex

    async def inactivate_api_key(
        self, partner_id: UUID, current_user: dict
    ) -> ApiKeyResponse | None:
        """
        Inactivate (disable) the active API key associated with the given partner.
        Records the user who performed the action.

        Args:
            partner_id (int): The partner whose API key should be inactivated.
            current_user (dict): The currently authenticated user performing the operation.

        Returns:
            ApiKeyResponse: Confirmation message if successful.
        """
        try:
            current_user_id: UUID = current_user.get(CurrentUserMap.USER_ID)
            self.__console_service_logger.info(
                f"Attempting to inactivate API key for partner_id={partner_id} by user_id={current_user_id}"
            )

            await self.__cache_helper.delete_cache(
                key=RedisKeys.PARTNER_API_KEY.format(partner_id)
            )

            result = await self.__api_key_repository.inactivate_api_key(
                partner_id, current_user_id
            )

            if not result:
                self.__console_service_logger.warning(
                    f"No active API key found or already inactive for partner_id={partner_id}"
                )
                raise ApiKeyNotFoundError(partner_id)

            self.__console_service_logger.info(
                f"API key successfully inactivated for partner_id: {partner_id} by user_id: {current_user_id}"
            )

            return ApiKeyResponseMessage.API_KEY_IN_ACTIVIATED

        except Exception as ex:
            self.__console_service_logger.error(
                f"Unexpected error validating API key {partner_id}...: {str(ex)}"
            )
            raise ex

    async def __resolve_partner_access(
        self,
        *,
        current_user: dict | None,
        partner_id: UUID | None,
        auth_service: AuthService,
    ) -> tuple[int, int | None]:
        """
        Resolves partner_id and validates access.
        Returns: (partner_id, user_id)
        """
        # User based request
        if current_user:
            current_user_id = current_user.get(CurrentUserMap.USER_ID)
            current_partner_id = current_user.get(CurrentUserMap.PARTNER_ID)

            resolved_partner_id = partner_id or current_partner_id

            if current_partner_id != resolved_partner_id:
                role_details = await auth_service.get_role_by_user_id(current_user_id)

                if (
                    role_details.get(RoleDictKeys.HIERARCHY)
                    != UserHierarchyLevel.SUPER_ADMIN_HIERARCHY
                ):
                    raise PartnerNotFoundError(resolved_partner_id)

            return resolved_partner_id, current_user_id

        # System call
        if not partner_id:
            raise ApiKeyException(ExceptionMessages.PARTNER_ID_REQUIRED_FOR_SYSTEM_CALL)

        return partner_id, None

    async def __validate_scopes(
        self, scopes: list, auth_service: AuthService
    ) -> None:
        """Reject any scope string that is not a known, active permission slug.

        ``scopes`` is expected to be a list[str] of RBAC permission slugs
        (e.g. ``talko:list_leads``). An empty list is valid (clears scopes).
        """
        if not scopes:
            return

        if not isinstance(scopes, list) or not all(
            isinstance(s, str) for s in scopes
        ):
            raise ApiKeyException(
                ExceptionMessages.INVALID_SCOPES.format(scopes)
            )

        permissions = await auth_service.get_all_permission()
        known_slugs = {p.slug for p in permissions}
        unknown = sorted(set(scopes) - known_slugs)
        if unknown:
            raise ApiKeyException(
                ExceptionMessages.INVALID_SCOPES.format(", ".join(unknown))
            )

    async def __validate_user_context(
        self, user_context: dict, partner_id: UUID
    ) -> None:
        """user_context is restricted to exactly ``{"user_id": <uuid>}`` where
        ``user_id`` is a real user of ``partner_id``. Any other key is rejected.
        Accepts UUID objects and UUID strings (JSON round-trips).
        Normalizes the dict in place to the uuid-string form for JSON storage.
        """
        if not isinstance(user_context, dict):
            raise ApiKeyException(ExceptionMessages.INVALID_USER_CONTEXT)

        extra = set(user_context.keys()) - {"user_id"}
        if extra:
            raise ApiKeyException(
                ExceptionMessages.USER_CONTEXT_ONLY_USER_ID.format(
                    ", ".join(sorted(str(k) for k in extra))
                )
            )

        uid = user_context.get("user_id")
        if isinstance(uid, UUID):
            pass
        elif isinstance(uid, str):
            try:
                uid = UUID(uid)
            except (ValueError, AttributeError, TypeError):
                raise ApiKeyException(ExceptionMessages.INVALID_USER_ID_IN_CONTEXT)
        else:
            raise ApiKeyException(ExceptionMessages.INVALID_USER_ID_IN_CONTEXT)

        user_context["user_id"] = str(uid)

        try:
            await self.__user_repository.get_user_by_user_id(uid, partner_id)
        except UserNotFoundError:
            raise ApiKeyException(
                ExceptionMessages.USER_CONTEXT_USER_NOT_FOUND.format(uid)
            )

    async def update_api_key_metadata(
        self,
        current_user: dict = None,
        partner_id: UUID = None,
        scopes: list | None = None,
        user_context: dict | None = None,
        auth_service: AuthService = None,
    ) -> ApiKeyResponse:
        """Update ``scopes`` / ``user_context`` on the partner's active API key
        in place (no rotation, key value unchanged).
        """
        try:
            auth_service = auth_service or self.__auth_service
            partner_id, user_id = await self.__resolve_partner_access(
                current_user=current_user,
                partner_id=partner_id,
                auth_service=auth_service,
            )

            if scopes is not None:
                await self.__validate_scopes(scopes, auth_service)

            if user_context is not None:
                await self.__validate_user_context(user_context, partner_id)

            self.__console_service_logger.info(
                f"Updating API key metadata for partner_id: {partner_id}"
            )

            row = await self.__api_key_repository.update_active_api_key_metadata(
                partner_id=partner_id,
                current_user_id=user_id,
                scopes=scopes,
                user_context=user_context,
            )

            if not row:
                raise ApiKeyNotFoundError(partner_id)

            await self.__cache_helper.delete_cache(
                key=RedisKeys.PARTNER_API_KEY.format(partner_id)
            )

            return ApiKeyResponse.model_validate(row)

        except Exception as ex:
            self.__console_service_logger.error(
                f"Unexpected error updating API key metadata for partner_id={partner_id}: {str(ex)}"
            )
            raise ex

    async def generated_api_key_while_partner_onboarding(self, partner_id: UUID):
        try:
            self.__console_service_logger.info(
                f"Generating API key during onboarding for partner_id={partner_id}"
            )

            result = await self.__api_key_repository.generated_api_key_while_partner_onboarding(
                partner_id
            )
            if not result:
                return None
            response = ApiKeyResponse.model_validate(result)
            self.__console_service_logger.info(
                f"API key generated successfully for partner_id={partner_id}, api key:{response}"
            )

            return response

        except Exception as ex:
            self.__console_service_logger.error(
                f"Error generating API key during onboarding for partner_id={partner_id}: {str(ex)}"
            )
            raise ex
