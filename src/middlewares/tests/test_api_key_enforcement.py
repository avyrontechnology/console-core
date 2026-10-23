"""Security tests for API-key enforcement (deny-all) + token precedence."""
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID

import pytest

from src.middlewares.authentication import AuthMiddleware


def _api_key_details(**over):
    base = dict(
        is_active=True,
        partner_id=UUID("12312312-3123-1231-2312-312312312312"),
        expires_at=None,
        scopes=["console:get_all_users"],
        user_context={"user_id": "99999999-9999-9999-9999-999999999999"},
        id=UUID("11111111-1111-1111-1111-111111111111"),
    )
    base.update(over)
    return SimpleNamespace(**base)


async def _handle(mw, key_details):
    from unittest.mock import patch

    request = MagicMock()
    request.url.path = "/x"
    api_key_service = MagicMock()
    api_key_service.validate_api_key = AsyncMock(return_value=key_details)
    user_repo = MagicMock()
    user_repo.get_system_admin_user = AsyncMock(
        return_value=SimpleNamespace(
            id=UUID("99999999-9999-9999-9999-999999999999"),
            role_id=UUID("77777777-7777-7777-7777-777777777777"),
        )
    )
    with patch("src.middlewares.authentication.context"):
        resp = await mw._handle_api_key(
            request=request,
            api_key="k",
            call_next=AsyncMock(return_value="OK"),
            api_key_service=api_key_service,
            user_repository=user_repo,
            console_service_logger=MagicMock(),
        )
    return resp, request


@pytest.mark.asyncio
async def test_expired_key_rejected():
    mw = AuthMiddleware(app=MagicMock())
    resp, _ = await _handle(mw, _api_key_details(expires_at=1))
    assert json.loads(resp.body.decode())["detail"] == "Expired API Key"


@pytest.mark.asyncio
async def test_null_expiry_legacy_key_allowed():
    mw = AuthMiddleware(app=MagicMock())
    resp, request = await _handle(mw, _api_key_details(expires_at=None))
    assert resp == "OK"
    assert request.state.api_key["scopes"] == ["console:get_all_users"]


@pytest.mark.asyncio
async def test_malformed_user_context_rejected():
    mw = AuthMiddleware(app=MagicMock())
    resp, _ = await _handle(mw, _api_key_details(user_context={"user_id": "nope"}))
    assert json.loads(resp.body.decode())["detail"] == "Invalid API Key"


@pytest.mark.asyncio
async def test_conflicting_credentials_rejected():
    from unittest.mock import patch

    from src.middlewares.authentication import AuthMiddleware as M

    mw = M(app=MagicMock())
    request = MagicMock()
    request.url.path = "/x"
    request.scope = {"route": SimpleNamespace(name="get_all_users")}
    request.headers = {"API-KEY": "k", "Authorization": "Bearer t"}
    with patch("src.middlewares.authentication.context"):
        resp = await mw.dispatch(
            request, AsyncMock(), console_service_logger=MagicMock()
        )
    assert json.loads(resp.body.decode())["detail"].startswith(
        "Ambiguous credentials"
    )


@pytest.mark.asyncio
async def test_scope_missing_denies_before_db():
    from fastapi import HTTPException

    from src.components.rbac.permission_dependency import PermissionDependency

    request = MagicMock()
    request.url.path = "/x"
    request.state.user = {
        "user_id": UUID("99999999-9999-9999-9999-999999999999"),
        "partner_id": UUID("12312312-3123-1231-2312-312312312312"),
    }
    request.state.api_key = {"scopes": ["console:get_all_users"], "key_id": "k1"}
    dep = PermissionDependency("console:delete_partner")
    with pytest.raises(HTTPException) as exc:
        await dep(
            request,
            auth_repo=MagicMock(),
            partner_config_service=MagicMock(),
            redis_pool=MagicMock(),
            logger=MagicMock(),
        )
    assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_scope_match_passes_scope_gate():
    """Scope gate passes; downstream user check still applies (mocked allow)."""
    from unittest.mock import patch

    from src.components.rbac.permission_dependency import PermissionDependency

    request = MagicMock()
    request.url.path = "/x"
    request.state.user = {
        "user_id": UUID("99999999-9999-9999-9999-999999999999"),
        "partner_id": UUID("12312312-3123-1231-2312-312312312312"),
    }
    request.state.api_key = {"scopes": ["console:get_all_users"], "key_id": "k1"}
    dep = PermissionDependency("console:get_all_users")
    pcs = MagicMock()
    pcs.custom_role_permission_check = AsyncMock(
        return_value=["console:get_all_users"]
    )
    with patch(
        "src.components.partner_config.services.PartnerConfigService.custom_role_permission_check",
        AsyncMock(return_value=["console:get_all_users"]),
    ):
        await dep(
            request,
            auth_repo=MagicMock(),
            partner_config_service=pcs,
            redis_pool=MagicMock(),
            logger=MagicMock(),
        )  # must not raise
