from unittest.mock import AsyncMock, MagicMock

import pytest

from src.components.audit_log.repositories import AuditLogRepository


def _session_with_rows(rows):
    session = AsyncMock()
    execute_result = MagicMock()
    scalars = MagicMock()
    scalars.all.return_value = rows
    execute_result.scalars.return_value = scalars
    session.execute = AsyncMock(return_value=execute_result)
    factory_ctx = MagicMock()
    factory_ctx.__aenter__ = AsyncMock(return_value=session)
    factory_ctx.__aexit__ = AsyncMock(return_value=None)
    factory = MagicMock(return_value=factory_ctx)
    return factory, session


@pytest.mark.asyncio
async def test_list_audit_logs_filters_and_orders():
    factory, session = _session_with_rows(["row"])
    repo = AuditLogRepository(session_factory=factory)

    result = await repo.list_audit_logs(
        resource="AUTH", action="DENY", limit=10, offset=5
    )

    assert result == ["row"]
    query_str = str(session.execute.call_args[0][0])
    assert "console_audit_logs" in query_str
    assert "ORDER BY" in query_str


@pytest.mark.asyncio
async def test_list_audit_logs_no_filters():
    factory, _ = _session_with_rows([])
    repo = AuditLogRepository(session_factory=factory)

    assert await repo.list_audit_logs() == []
