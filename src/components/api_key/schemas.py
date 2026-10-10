from pydantic import BaseModel, ConfigDict
from typing import Optional, List, Dict


class ApiKeyResponse(BaseModel):
    id: int
    key: str
    description: Optional[str] = None
    scopes: Optional[List[str]] = None
    user_context: Optional[Dict] = None
    is_active: bool
    partner_id: int

    model_config = ConfigDict(
        from_attributes=True,
    )


class ApiKeyGenerateRequest(BaseModel):
    """Optional body for the generate/rotate endpoint.

    ``user_context`` must be exactly ``{"user_id": <int>}`` (a real user of the
    partner); when omitted it is auto-derived from the caller.
    """

    scopes: Optional[List[str]] = None
    user_context: Optional[Dict] = None


class ApiKeyUpdateRequest(BaseModel):
    """Body for the in-place metadata update endpoint (PATCH /api_key).

    A field left as ``None`` is not touched. ``scopes: []`` clears scopes.
    ``user_context`` must be exactly ``{"user_id": <int>}`` (a real user of the
    partner) — no other keys are accepted.
    """

    scopes: Optional[List[str]] = None
    user_context: Optional[Dict] = None
