from unittest.mock import AsyncMock, MagicMock
from uuid import UUID

import pytest

from src.components.audit_log.schema import AuditLogResponse
from src.components.audit_log.services import AuditService


@pytest.mark.asyncio
async def test_get_audit_logs_maps_rows():
    repo = MagicMock()
    row = MagicMock(
        id=UUID("11111111-1111-1111-1111-111111111111"),
        action="DENY",
        resource="AUTH",
        resource_id="console:get_all_users",
        performed_by=UUID("22222222-2222-2222-2222-222222222222"),
        resource_previous_state=None,
        resource_current_state=None,
        details="denied",
        created_at=1700000000000,
    )
    repo.list_audit_logs = AsyncMock(return_value=[row])
    service = AuditService(audit_log_repository=repo)

    result = await service.get_audit_logs(resource="AUTH", action="DENY")

    assert len(result) == 1
    assert isinstance(result[0], AuditLogResponse)
    assert result[0].action == "DENY"
    assert result[0].resource_id == "console:get_all_users"
    repo.list_audit_logs.assert_awaited_once_with(
        resource="AUTH", action="DENY", limit=50, offset=0
    )


@pytest.mark.asyncio
async def test_get_audit_logs_empty():
    repo = MagicMock()
    repo.list_audit_logs = AsyncMock(return_value=[])
    service = AuditService(audit_log_repository=repo)

    assert await service.get_audit_logs() == []
