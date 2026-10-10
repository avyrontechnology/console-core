"""Pydantic request / response models for the OAuth endpoints."""

from typing import List, Optional

from pydantic import BaseModel, Field


# ── DCR ───────────────────────────────────────────────────────────────────────
class ClientRegistrationRequest(BaseModel):
    """RFC 7591 §2 — fields we accept. We deliberately ignore unknown fields
    (extra=ignore by default) so future spec additions don't break clients."""

    client_name: str = Field(..., min_length=1, max_length=255)
    redirect_uris: List[str] = Field(..., min_length=1, max_length=10)
    token_endpoint_auth_method: Optional[str] = Field(
        default="client_secret_basic",
        description="One of client_secret_basic, client_secret_post, none",
    )
    grant_types: Optional[List[str]] = None  # we only honour the defaults
    scope: Optional[str] = None  # optional whitelist; we clamp to our catalog


class ClientRegistrationResponse(BaseModel):
    client_id: str
    client_secret: Optional[str] = None
    client_id_issued_at: int
    client_secret_expires_at: int = 0  # 0 = never
    client_name: str
    redirect_uris: List[str]
    grant_types: List[str]
    token_endpoint_auth_method: str
    scope: str


# ── Token endpoint ────────────────────────────────────────────────────────────
class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "Bearer"
    expires_in: int
    refresh_token: Optional[str] = None
    scope: str


# ── Consent endpoints ─────────────────────────────────────────────────────────
class ConsentDetailsResponse(BaseModel):
    client_name: str
    client_id: str
    scopes: List[str]
    scope_descriptions: List[str]


class ConsentDecisionRequest(BaseModel):
    oauth_request_id: str
    allow: bool


class ConsentDecisionResponse(BaseModel):
    redirect: str


# ── Authorize-continue ────────────────────────────────────────────────────────
class AuthorizeContinueRequest(BaseModel):
    oauth_request_id: str
