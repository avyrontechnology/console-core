from uuid import UUID
from pydantic import BaseModel, ConfigDict
from typing import Optional, List, Dict


class ApiKeyResponse(BaseModel):
    id: UUID
    key: str
    description: Optional[str] = None
    scopes: Optional[List[str]] = None
    user_context: Optional[Dict] = None
    is_active: bool
    expires_at: Optional[int] = None
    partner_id: UUID

    model_config = ConfigDict(
        from_attributes=True,
    )


class ApiKeyGenerateRequest(BaseModel):
    """Optional body for the generate/rotate endpoint.

    ``user_context`` must be exactly ``{"user_id": <uuid>}`` (a real user of the
    partner); when omitted it is auto-derived from the caller.
    ``expires_at`` is epoch ms; omitted/None = never expires (legacy).
    """

    scopes: Optional[List[str]] = None
    user_context: Optional[Dict] = None
    expires_at: Optional[int] = None


class ApiKeyUpdateRequest(BaseModel):
    """Body for the in-place metadata update endpoint (PATCH /api_key).

    A field left as ``None`` is not touched. ``scopes: []`` clears scopes.
    ``user_context`` must be exactly ``{"user_id": <uuid>}`` (a real user of the
    partner) — no other keys are accepted.
    """

    scopes: Optional[List[str]] = None
    user_context: Optional[Dict] = None
    expires_at: Optional[int] = None
