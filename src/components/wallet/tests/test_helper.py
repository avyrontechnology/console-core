import pytest
from unittest.mock import AsyncMock, MagicMock

from src.components.api_key.schemas import ApiKeyResponse
from src.components.wallet.helper import WalletHelper
from src.exceptions import AuthException

current_user = {"partner_id":12, "user_id":33}

@pytest.mark.asyncio
async def test_returns_current_user_when_no_partner_and_no_api_key(mock_logger):
    api_key_service = AsyncMock()
    partner_service = AsyncMock()

    res = await WalletHelper.resolve_partner_id_with_api_key(
        current_user,
        partner_id=None,
        api_key=None,
        api_key_service=api_key_service,
        partner_service=partner_service,
        logger=mock_logger,
    )

    assert res == 12
    api_key_service.get_api_key.assert_not_awaited()
    partner_service.get_partner_by_id.assert_not_awaited()


@pytest.mark.asyncio
async def test_matching_api_key_returns_partner_id(mock_logger):
    api_key_service = AsyncMock()
    partner_service = AsyncMock()

    api_key_obj = ApiKeyResponse(
        id=1, key="k", description=None, scopes=None, is_active=True, partner_id=5
    )
    api_key_service.get_api_key.return_value = api_key_obj

    res = await WalletHelper.resolve_partner_id_with_api_key(
        current_user,
        partner_id=5,
        api_key="some-key",
        api_key_service=api_key_service,
        partner_service=partner_service,
        logger=mock_logger,
    )

    assert res == 5
    api_key_service.get_api_key.assert_awaited_once()


@pytest.mark.asyncio
async def test_missing_api_key_raises_and_logs(mock_logger):
    api_key_service = AsyncMock()
    partner_service = AsyncMock()

    api_key_service.get_api_key.return_value = None

    with pytest.raises(AuthException):
        await WalletHelper.resolve_partner_id_with_api_key(
            current_user,
            partner_id=5,
            api_key="bad-key",
            api_key_service=api_key_service,
            partner_service=partner_service,
            logger=mock_logger,
        )

    assert mock_logger.error.called


@pytest.mark.asyncio
async def test_mismatch_api_key_but_internal_partner_allows(mock_logger):
    api_key_service = AsyncMock()
    partner_service = AsyncMock()

    api_key_obj = ApiKeyResponse(
        id=1, key="k", description=None, scopes=None, is_active=True, partner_id=99
    )
    api_key_service.get_api_key.return_value = api_key_obj

    partner_obj = MagicMock()
    partner_obj.is_internal = True
    partner_service.get_partner_by_id.return_value = partner_obj

    res = await WalletHelper.resolve_partner_id_with_api_key(
        current_user,
        partner_id=5,
        api_key="some-key",
        api_key_service=api_key_service,
        partner_service=partner_service,
        logger=mock_logger,
    )

    assert res == 5
    partner_service.get_partner_by_id.assert_awaited_once()


@pytest.mark.asyncio
async def test_mismatch_api_key_and_non_internal_raises_and_logs(mock_logger):
    api_key_service = AsyncMock()
    partner_service = AsyncMock()

    api_key_obj = ApiKeyResponse(
        id=1, key="k", description=None, scopes=None, is_active=True, partner_id=99
    )
    api_key_service.get_api_key.return_value = api_key_obj

    partner_obj = MagicMock()
    partner_obj.is_internal = False
    partner_service.get_partner_by_id.return_value = partner_obj

    with pytest.raises(AuthException):
        await WalletHelper.resolve_partner_id_with_api_key(
            current_user,
            partner_id=5,
            api_key="some-key",
            api_key_service=api_key_service,
            partner_service=partner_service,
            logger=mock_logger,
        )

    assert mock_logger.error.called