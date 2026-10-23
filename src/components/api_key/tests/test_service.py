from uuid import UUID
import pytest
from unittest.mock import AsyncMock, MagicMock
from src.components.api_key.services import ApiKeyService
from src.components.api_key.schemas import ApiKeyResponse
from src.components.api_key.errors import ApiKeyNotFoundError
from src.components.api_key.constants import ApiKeyResponseMessage
from src.exceptions import ApiKeyException
from src.components.common.constants import CurrentUserMap
from src.loggers.console_service_logger import ConsoleServiceLogger
from src.components.partner.error import PartnerNotFoundError
from src.components.cache import Keys as RedisKeys
from src.components.cache import TTL as RedisTTL


@pytest.mark.asyncio
class TestApiKeyService:

    @pytest.fixture(autouse=True)
    def setup(self):
        self.api_key_repository_mock = AsyncMock()
        self.logger_mock = AsyncMock(spec=ConsoleServiceLogger)
        self.cache_helper_mock = AsyncMock()
        self.auth_service_mock = AsyncMock()
        # Permission catalog used by scope validation.
        self.auth_service_mock.get_all_permission.return_value = [
            MagicMock(slug="talko:get_leads"),
            MagicMock(slug="talko:list_leads"),
        ]
        self.user_repository_mock = AsyncMock()
        # get_user_by_user_id succeeds (valid user) unless a test overrides it.
        self.user_repository_mock.get_user_by_user_id.return_value = MagicMock(id= UUID("11111111-1111-1111-1111-111111111111"))
        self.api_key_service = ApiKeyService(
            api_key_repository=self.api_key_repository_mock,
            console_service_logger=self.logger_mock,
            cache_helper=self.cache_helper_mock,
            auth_service=self.auth_service_mock,
            user_repository=self.user_repository_mock,
        )

        self.current_user = {
            CurrentUserMap.USER_ID: UUID("11111111-1111-1111-1111-111111111111"),
            CurrentUserMap.PARTNER_ID: UUID("10101010-1010-1010-1010-101010101010"),
            "name": "Api Key User",
        }

        self.api_key_response = ApiKeyResponse(
            id= UUID("11111111-1111-1111-1111-111111111111"),
            key="abcd1234efgh5678ijkl9012mnop3456qrst7890uvwx1234yzab5678cdef9012",
            description="Partner API key",
            scopes=["talko:get_leads"],
            user_context={"user_id": 1},
            is_active=True,
            partner_id= UUID("10101010-1010-1010-1010-101010101010"),
        )
        self.cache_helper_mock.get_cache.return_value = None

    # -------------------- generate_api_key --------------------

    async def test_generate_api_key_success(self):
        self.api_key_repository_mock.generate_api_key.return_value = self.api_key_response

        result = await self.api_key_service.generate_api_key(self.current_user)

        assert isinstance(result, ApiKeyResponse)
        assert result.partner_id== UUID("10101010-1010-1010-1010-101010101010")
        self.logger_mock.info.assert_called_with("Attempting to generate api key for partner: 10101010-1010-1010-1010-101010101010")

    async def test_generate_api_key_exception(self):
        self.api_key_repository_mock.generate_api_key.side_effect = Exception("DB error")

        with pytest.raises(Exception, match=r".*DB error.*"):
            await self.api_key_service.generate_api_key(self.current_user)

        self.logger_mock.error.assert_called_with("Unexpected error fetching countries.DB error")

    # -------------------- validate_api_key --------------------

    async def test_validate_api_key_success(self):
        self.api_key_repository_mock.validate_api_key.return_value = self.api_key_response

        result = await self.api_key_service.validate_api_key("abcd1234")

        assert isinstance(result, ApiKeyResponse)
        self.logger_mock.info.assert_any_call("Attempting to validate API key: abcd1234...")
        self.logger_mock.info.assert_any_call("API key validated successfully for partner_id: 10101010-1010-1010-1010-101010101010")

    async def test_validate_api_key_invalid(self):
        self.api_key_repository_mock.validate_api_key.return_value = None

        result = await self.api_key_service.validate_api_key("invalidkey")

        assert result is None
        self.logger_mock.warning.assert_called_with("Invalid or inactive API key: invalidkey...")

    async def test_validate_api_key_exception(self):
        self.api_key_repository_mock.validate_api_key.side_effect = Exception("DB error")

        with pytest.raises(Exception, match=r".*DB error.*"):
            await self.api_key_service.validate_api_key("abcd1234")

        self.logger_mock.error.assert_called_with(
            "Unexpected error validating API key abcd1234...: DB error"
        )

    # -------------------- get_api_key --------------------

    async def test_get_api_key_success(self):
        self.api_key_repository_mock.get_active_api_key.return_value = self.api_key_response
        current_user = {CurrentUserMap.USER_ID: UUID("12121212-1212-1212-1212-121212121212"), CurrentUserMap.PARTNER_ID: UUID("10101010-1010-1010-1010-101010101010")}
        auth_service = AsyncMock()
        result = await self.api_key_service.get_api_key(current_user=current_user,partner_id= UUID("10101010-1010-1010-1010-101010101010"), auth_service=auth_service)

        assert isinstance(result, ApiKeyResponse)
        assert result.scopes == ["talko:get_leads"]
        self.cache_helper_mock.get_cache.assert_awaited_once_with(
            key=RedisKeys.PARTNER_API_KEY.format(UUID("10101010-1010-1010-1010-101010101010"))
        )
        self.api_key_repository_mock.get_active_api_key.assert_awaited_once_with(UUID("10101010-1010-1010-1010-101010101010"))
        self.cache_helper_mock.set_cache.assert_awaited_once_with(
            key=RedisKeys.PARTNER_API_KEY.format(UUID("10101010-1010-1010-1010-101010101010")),
            value=self.api_key_response.dict(),
            ttl=RedisTTL.ONE_WEEK,
        )
        self.logger_mock.info.assert_any_call("Fetching active API key for partner_id: 10101010-1010-1010-1010-101010101010")

    async def test_get_api_key_success_by_super_admin(self):
        self.api_key_repository_mock.get_active_api_key.return_value = self.api_key_response
        current_user = {CurrentUserMap.USER_ID: UUID("12121212-1212-1212-1212-121212121212"), CurrentUserMap.PARTNER_ID: UUID("20020020-2002-2002-2002-200200200200")}
        auth_service = AsyncMock()
        auth_service.get_role_by_user_id.return_value = {"hierarchy": 0}
        result = await self.api_key_service.get_api_key(current_user=current_user,partner_id= UUID("10101010-1010-1010-1010-101010101010"), auth_service=auth_service)

        assert isinstance(result, ApiKeyResponse)
        auth_service.get_role_by_user_id.assert_awaited_once_with(UUID("12121212-1212-1212-1212-121212121212"))
      
    async def test_get_api_key_success_from_cache(self):
        self.cache_helper_mock.get_cache.return_value = self.api_key_response.dict()
        current_user = {CurrentUserMap.USER_ID: UUID("12121212-1212-1212-1212-121212121212"), CurrentUserMap.PARTNER_ID: UUID("10101010-1010-1010-1010-101010101010")}
        auth_service = AsyncMock()

        result = await self.api_key_service.get_api_key(
            current_user=current_user,
            partner_id= UUID("10101010-1010-1010-1010-101010101010"),
            auth_service=auth_service,
        )

        assert isinstance(result, ApiKeyResponse)
        assert result == self.api_key_response
        self.cache_helper_mock.get_cache.assert_awaited_once_with(
            key=RedisKeys.PARTNER_API_KEY.format(UUID("10101010-1010-1010-1010-101010101010"))
        )
        self.api_key_repository_mock.get_active_api_key.assert_not_awaited()
        self.cache_helper_mock.set_cache.assert_not_awaited()

    async def test_get_api_key_not_found(self):
        self.api_key_repository_mock.get_active_api_key.return_value = None
        current_user = {CurrentUserMap.USER_ID: UUID("12121212-1212-1212-1212-121212121212"), CurrentUserMap.PARTNER_ID: UUID("10101010-1010-1010-1010-101010101010")}
        auth_service = AsyncMock()
        with pytest.raises(ApiKeyNotFoundError):
            await self.api_key_service.get_api_key(current_user=current_user, partner_id= UUID("10101010-1010-1010-1010-101010101010"), auth_service=auth_service)

        self.logger_mock.warning.assert_called_with("No active API key found for partner_id: 10101010-1010-1010-1010-101010101010")

    async def test_get_api_key_exception(self):
        self.api_key_repository_mock.get_active_api_key.side_effect = Exception("DB error")
        current_user = {CurrentUserMap.USER_ID: UUID("12121212-1212-1212-1212-121212121212"), CurrentUserMap.PARTNER_ID: UUID("10101010-1010-1010-1010-101010101010")}
        auth_service = AsyncMock()
        with pytest.raises(Exception, match=r".*DB error.*"):
            await self.api_key_service.get_api_key(current_user=current_user, partner_id= UUID("10101010-1010-1010-1010-101010101010"), auth_service=auth_service)

        self.cache_helper_mock.get_cache.assert_awaited_once_with(
            key=RedisKeys.PARTNER_API_KEY.format(UUID("10101010-1010-1010-1010-101010101010"))
        )
        self.api_key_repository_mock.get_active_api_key.assert_awaited_once_with(UUID("10101010-1010-1010-1010-101010101010"))
        self.logger_mock.error.assert_called_with(
            "Unexpected error fetching API key for partner_id=10101010-1010-1010-1010-101010101010: DB error"
        )

    async def test_get_api_key_partner_not_found(self):
        self.api_key_repository_mock.get_active_api_key.side_effect = Exception("DB error")
        current_user = {CurrentUserMap.USER_ID: UUID("12121212-1212-1212-1212-121212121212"), CurrentUserMap.PARTNER_ID: UUID("10010010-1001-1001-1001-100100100100")}
        auth_service = AsyncMock()
        auth_service.get_role_by_user_id.return_value = {"hierarchy": 1}
        with pytest.raises(PartnerNotFoundError, match=r".*Partner not found, id: 10101010-1010-1010-1010-101010101010*"):
            await self.api_key_service.get_api_key(current_user=current_user, partner_id= UUID("10101010-1010-1010-1010-101010101010"), auth_service=auth_service)


    # -------------------- re_generate_api_key --------------------

    async def test_re_generate_api_key_success(self):
        self.api_key_repository_mock.inactivate_api_key.return_value = True
        self.api_key_repository_mock.generate_api_key.return_value = self.api_key_response

        result = await self.api_key_service.re_generate_api_key(self.current_user)

        assert isinstance(result, ApiKeyResponse)
        

    async def test_re_generate_api_key_exception(self):
        self.api_key_repository_mock.generate_api_key.side_effect = Exception("DB error")

        with pytest.raises(Exception, match=r".*DB error.*"):
            await self.api_key_service.re_generate_api_key(self.current_user)

        self.logger_mock.error.assert_called_with(
            "Unexpected error generating API key for partner: 10101010-1010-1010-1010-101010101010, Error: DB error"
        )

    # -------------------- inactivate_api_key --------------------

    async def test_inactivate_api_key_success(self):
        self.api_key_repository_mock.inactivate_api_key.return_value = True

        result = await self.api_key_service.inactivate_api_key(UUID("10101010-1010-1010-1010-101010101010"), self.current_user)

        assert result == ApiKeyResponseMessage.API_KEY_IN_ACTIVIATED
        self.logger_mock.info.assert_any_call(
            "Attempting to inactivate API key for partner_id=10101010-1010-1010-1010-101010101010 by user_id=11111111-1111-1111-1111-111111111111"
        )
        self.logger_mock.info.assert_any_call(
            "API key successfully inactivated for partner_id: 10101010-1010-1010-1010-101010101010 by user_id: 11111111-1111-1111-1111-111111111111"
        )

    async def test_inactivate_api_key_not_found(self):
        self.api_key_repository_mock.inactivate_api_key.return_value = None

        with pytest.raises(ApiKeyNotFoundError):
            await self.api_key_service.inactivate_api_key(UUID("10101010-1010-1010-1010-101010101010"), self.current_user)

        self.logger_mock.warning.assert_called_with(
            "No active API key found or already inactive for partner_id=10101010-1010-1010-1010-101010101010"
        )

    async def test_inactivate_api_key_exception(self):
        self.api_key_repository_mock.inactivate_api_key.side_effect = Exception("DB error")

        with pytest.raises(Exception, match=r".*DB error.*"):
            await self.api_key_service.inactivate_api_key(10, self.current_user)

        self.logger_mock.error.assert_called_with(
            "Unexpected error validating API key 10...: DB error"
        )

    # -------------------- scopes + user_context --------------------

    async def test_re_generate_api_key_with_valid_scopes(self):
        self.api_key_repository_mock.inactivate_api_key.return_value = True
        self.api_key_repository_mock.generate_api_key.return_value = self.api_key_response

        await self.api_key_service.re_generate_api_key(
            self.current_user, scopes=["talko:get_leads", "talko:list_leads"]
        )

        # scopes validated against the catalog, and user_context auto-derived
        # from the generating user (strictly {"user_id": <int>}).
        self.auth_service_mock.get_all_permission.assert_awaited_once()
        _, kwargs = self.api_key_repository_mock.generate_api_key.call_args
        assert kwargs["scopes"] == ["talko:get_leads", "talko:list_leads"]
        assert kwargs["user_context"] == {"user_id": "11111111-1111-1111-1111-111111111111"}

    async def test_re_generate_api_key_rejects_unknown_scope(self):
        with pytest.raises(ApiKeyException, match=r".*talko:bogus.*"):
            await self.api_key_service.re_generate_api_key(
                self.current_user, scopes=["talko:get_leads", "talko:bogus"]
            )
        self.api_key_repository_mock.generate_api_key.assert_not_awaited()

    async def test_update_api_key_metadata_success(self):
        self.api_key_repository_mock.update_active_api_key_metadata.return_value = (
            self.api_key_response
        )

        result = await self.api_key_service.update_api_key_metadata(
            current_user=self.current_user,
            partner_id= UUID("10101010-1010-1010-1010-101010101010"),
            scopes=["talko:list_leads"],
            user_context={"user_id": UUID("11111111-1111-1111-1111-111111111111")},
        )

        assert isinstance(result, ApiKeyResponse)
        self.api_key_repository_mock.update_active_api_key_metadata.assert_awaited_once_with(
            partner_id= UUID("10101010-1010-1010-1010-101010101010"),
            current_user_id= UUID("11111111-1111-1111-1111-111111111111"),
            scopes=["talko:list_leads"],
            user_context={"user_id": "11111111-1111-1111-1111-111111111111"},
            expires_at=None,
        )
        self.cache_helper_mock.delete_cache.assert_awaited_once_with(
            key=RedisKeys.PARTNER_API_KEY.format(UUID("10101010-1010-1010-1010-101010101010"))
        )

    async def test_update_api_key_metadata_no_active_key(self):
        self.api_key_repository_mock.update_active_api_key_metadata.return_value = None

        with pytest.raises(ApiKeyNotFoundError):
            await self.api_key_service.update_api_key_metadata(
                current_user=self.current_user,
                partner_id= UUID("10101010-1010-1010-1010-101010101010"),
                scopes=["talko:list_leads"],
            )

    # -------------------- user_context validation --------------------

    async def test_user_context_rejects_extra_keys(self):
        with pytest.raises(ApiKeyException, match=r".*name.*"):
            await self.api_key_service.re_generate_api_key(
                self.current_user, user_context={"user_id": 1, "name": "x"}
            )
        self.api_key_repository_mock.generate_api_key.assert_not_awaited()

    async def test_user_context_rejects_non_int_user_id(self):
        with pytest.raises(ApiKeyException, match=r".*must be a valid UUID.*"):
            await self.api_key_service.re_generate_api_key(
                self.current_user, user_context={"user_id": "5"}
            )

    async def test_user_context_rejects_unknown_user(self):
        from src.components.user.errors import UserNotFoundError

        self.user_repository_mock.get_user_by_user_id.side_effect = UserNotFoundError(UUID("99999999-9999-9999-9999-999999999999"))
        with pytest.raises(ApiKeyException, match=r".*not a valid user.*"):
            await self.api_key_service.re_generate_api_key(
                self.current_user, user_context={"user_id": UUID("99999999-9999-9999-9999-999999999999")}
            )

    async def test_user_context_accepts_valid_user_id(self):
        self.api_key_repository_mock.inactivate_api_key.return_value = True
        self.api_key_repository_mock.generate_api_key.return_value = self.api_key_response

        await self.api_key_service.re_generate_api_key(
            self.current_user, user_context={"user_id": UUID("11111111-1111-1111-1111-111111111111")}
        )

        self.user_repository_mock.get_user_by_user_id.assert_awaited_once_with(UUID("11111111-1111-1111-1111-111111111111"), UUID("10101010-1010-1010-1010-101010101010"))
        _, kwargs = self.api_key_repository_mock.generate_api_key.call_args
        assert kwargs["user_context"] == {"user_id": "11111111-1111-1111-1111-111111111111"}
