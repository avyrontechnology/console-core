# OAuth 2.1 Authorization Server (console-service)

**Status:** Live on integration since 2026-06-10. Production roll-out gated on Phase 8 (UI), Phase 11 (QA sign-off) and Phase 12 (security review).

**What this is:** the Authorization-Server half of Maglo's self-hosted OAuth 2.1 stack. It issues access + refresh tokens to MCP clients (Claude.ai, ChatGPT) that want to call tools on maglo-service. Maglo-service consumes those tokens as the Resource Server — see [`maglo-service/docs/mcp/02-mcp-remote-self-hosted.md`](../../../maglo-service/docs/mcp/02-mcp-remote-self-hosted.md) for that half.

**Audience:**
- Backend engineers maintaining OAuth endpoints
- Frontend engineers picking up **Phase 8** (replace the bridge stop-gap with proper SPA pages)
- QA running **Phase 11** end-to-end test sweeps
- Security reviewers running **Phase 12**

---

## Contents

1. [TL;DR](#1-tldr)
2. [Architecture](#2-architecture)
3. [Glossary](#3-glossary)
4. [End-to-end flow](#4-end-to-end-flow)
5. [What was built (files + endpoints + tables)](#5-what-was-built-files--endpoints--tables)
6. [Environment variables](#6-environment-variables)
7. [Phase 8 — UI team scope](#7-phase-8--ui-team-scope)
8. [Phase 11 — QA team scope](#8-phase-11--qa-team-scope)
9. [Phase 12 — Security review checklist](#9-phase-12--security-review-checklist)
10. [Operational runbook](#10-operational-runbook)
11. [Maintenance](#11-maintenance)
12. [FAQ](#12-faq)
13. [Appendix](#13-appendix)

---

## 1. TL;DR

When a user clicks **"Connect Maglo"** inside Claude.ai (or any other MCP-compatible client):

1. The client discovers our OAuth server through two `.well-known/*` documents we publish.
2. The client registers itself automatically via Dynamic Client Registration (RFC 7591).
3. The client redirects the user's browser to `/oauth/authorize`. We bounce them through Maglo login and a consent screen.
4. We hand back a short-lived authorization code, then exchange it for a signed RS256 access JWT + a long-lived refresh token (with rotation + theft detection).
5. The client puts that JWT in `Authorization: Bearer …` on every MCP tool call to maglo-service.

The whole thing is a normal OAuth 2.1 + PKCE + DCR server. No third-party vendor. The same plumbing can later power partner APIs, mobile, or any other "Connect Maglo" surface.

**Feature gate:** the whole subsystem is mounted only when `OAUTH_ENABLED=true`. Defaults to `false`; deployments without the env flag are byte-for-byte unchanged.

---

## 2. Architecture

```
┌──────────────────────────────┐                ┌──────────────────────────────┐
│    MCP client (Claude.ai)    │                │   console-service            │
│    + user's browser          │                │   (OAuth 2.1 Server)         │
│                              │                │                              │
│ ① /.well-known/oauth-…       │ ─────────────▶ │ /.well-known/oauth-…         │
│ ② POST /oauth/register (DCR) │ ─────────────▶ │ /oauth/register              │
│ ③ GET  /oauth/authorize      │ ─────────────▶ │ /oauth/authorize             │
│      (PKCE challenge)        │                │     ├─ stash request         │
│                              │                │     └─ redirect to bridge    │
│ ④ user logs in + consents    │ ─── browser ──▶│ /oauth/bridge (stop-gap)     │
│                              │                │  → /do_login                 │
│                              │                │  → /oauth/authorize/continue │
│                              │                │  → /oauth/consent/decision   │
│ ⑤ 302 → redirect_uri?code=…  │ ◀───────────── │                              │
│ ⑥ POST /oauth/token          │ ─────────────▶ │ /oauth/token                 │
│      (PKCE verifier)         │                │     ├─ verify PKCE           │
│                              │                │     └─ mint RS256 JWT        │
│ ⑦ Bearer JWT on every        │                │ /oauth/jwks.json (public)    │
│   MCP request                │                │                              │
└──────────────────────────────┘                └──────────────────────────────┘
                  │                                            ▲
                  │ Authorization: Bearer <jwt>                │
                  ▼                                            │
┌──────────────────────────────┐                               │ JWKS fetch
│   maglo-service              │ ──────────────────────────────┘
│   (Resource Server)          │
│   /maglo-service/v1/mcp      │
└──────────────────────────────┘
```

Token validation happens **on the maglo side**, fetching our JWKS (cached in Redis). console-service never sees the MCP tool calls themselves — only the OAuth handshake.

---

## 3. Glossary

| Term | Meaning |
|---|---|
| **OAuth 2.1** | Updated OAuth 2.0 — bakes in PKCE, drops insecure grants. The spec MCP clients require. |
| **OIDC** | OpenID Connect — identity layer on OAuth. We expose minimal user claims (`sub`, `maglo_user_id`, `partner_id`) inside the access JWT; no separate ID token. |
| **PKCE** (RFC 7636) | Hash-challenge pair sent on `/authorize` and verified on `/token`. Prevents auth-code interception. Mandatory for our DCR clients. |
| **DCR** (RFC 7591) | Dynamic Client Registration — clients self-register by POSTing to `/oauth/register`. No pre-shared secret. |
| **JWKS** (RFC 7517) | JSON Web Key Set — the public half of our signing keys. Published at `/oauth/jwks.json` so resource servers can verify our JWTs. |
| **Authorization code** | Short-lived (~10 min), single-use string exchanged for tokens. Stored hashed, consumed via atomic `UPDATE … RETURNING`. |
| **Access token** | Short-lived (~1 h) RS256 JWT. Carries scopes + user claims. Stateless — validated by JWKS, no DB hop. |
| **Refresh token** | Long-lived (~30 d) opaque string. Stored hashed. Single-use + rotation; replay triggers chain revocation. |
| **Scope** | Named permission (e.g. `maglo:leads:read`). Listed in the consent screen, embedded in the JWT, checked by maglo's `PermissionDependency`. |
| **MCP** (Model Context Protocol) | Anthropic's open protocol for LLMs to call remote tools. Our resource server speaks it. |

---

## 4. End-to-end flow

The complete chain when a user clicks "Connect Maglo" in Claude.ai:

```
①  Claude.ai → maglo:            POST /maglo-service/v1/mcp  (no token)
                                   ← 401 + WWW-Authenticate:
                                       Bearer realm="maglo-mcp",
                                       resource_metadata="…/.well-known/
                                                          oauth-protected-resource"

②  Claude.ai → console:          GET /.well-known/oauth-protected-resource
                                   ← { authorization_servers: ["…/console-service/v1"], … }

③  Claude.ai → console:          GET /.well-known/oauth-authorization-server
                                       /console-service/v1
                                   ← { token_endpoint, registration_endpoint, jwks_uri,
                                       scopes_supported, code_challenge_methods: ["S256"],
                                       … }

④  Claude.ai → console:          POST /oauth/register
                                       { client_name: "Claude", redirect_uris: [...] }
                                   ← 201 { client_id, client_secret, … }

⑤  Browser → console:            GET /oauth/authorize?client_id=…&code_challenge=…&…
                                   ← 302 → /oauth/bridge?oauth_request_id=…

⑥  Bridge JS → console:          POST /do_login?svc_name=console
                                       { credential, password }
                                   ← { access_token: <maglo session JWT> }

⑦  Bridge JS → console:          POST /oauth/authorize/continue
                                       Bearer <maglo session JWT>
                                       { oauth_request_id }
                                   ← { next: "consent" }

⑧  Bridge JS → console:          GET /oauth/consent/details?oauth_request_id=…
                                       Bearer <maglo session JWT>
                                   ← { client_name, scopes, scope_descriptions }

⑨  Bridge JS → console:          POST /oauth/consent/decision
                                       Bearer <maglo session JWT>
                                       { oauth_request_id, allow: true }
                                   ← { redirect: "https://claude.ai/.../auth_callback?code=…" }

⑩  Claude.ai → console:          POST /oauth/token
                                       grant_type=authorization_code &
                                       code=… & code_verifier=… &
                                       client_id=… & client_secret=… &
                                       redirect_uri=…
                                   ← { access_token: <RS256 JWT>, expires_in: 3600,
                                       refresh_token, scope }

⑪  Claude.ai → maglo:            POST /maglo-service/v1/mcp  (with Bearer JWT)
                                   → tools/list, tools/call, … ← 200
```

Token refresh (when access token nears expiry):

```
Claude.ai → console:  POST /oauth/token
                          grant_type=refresh_token & refresh_token=… &
                          client_id=… & client_secret=…
                      ← { access_token, refresh_token (NEW), scope }
                      (old refresh token marked consumed; replay → chain revoked)
```

---

## 5. What was built (files + endpoints + tables)

### Package layout

```
src/components/oauth_server/
├── __init__.py
├── config.py          ── env-driven settings, SCOPE_CATALOG, TTL constants, feature gate
├── constants.py       ── OAuthScope enum + SCOPE_CATALOG (consent-screen descriptions)
├── keys.py            ── KeyRing: loads *.pem from OAUTH_SIGNING_KEY_PATH,
│                         lexicographic newest = primary, all keys in JWKS
├── models.py          ── 5 SQLAlchemy models (oauth_clients, oauth_authorization_codes,
│                         oauth_refresh_tokens, oauth_consents, oauth_authorize_requests)
├── schemas.py         ── Pydantic request/response shapes
├── errors.py          ── OAuth-spec error helpers (JSON for /token, safe-redirect helper
│                         only called after redirect_uri is validated)
├── repositories.py    ── atomic UPDATE…RETURNING for consume_auth_code /
│                         consume_refresh_token; chain-revocation walker
├── service.py         ── PKCE S256 verifier, RS256 minting via pyjwt, bcrypt secrets,
│                         replay detection, refresh-token rotation
├── rate_limit.py      ── DCR rate limiter (per-IP + global hourly), Redis-backed via
│                         CacheHelper.incr_with_ttl, fail-closed on Redis outage
├── controllers.py     ── OAuthController with 4 routers: discovery_router,
│                         well_known_root_router, oauth_public_router,
│                         oauth_authenticated_router
└── bridge.py          ── Phase 8 stop-gap: server-rendered login + consent HTML page;
                          DELETE this file once the SPA pages ship
```

### Endpoints (all under the `/console-service/v1` prefix unless noted)

| Method | Path | Spec | Auth | Purpose |
|---|---|---|---|---|
| GET | `/.well-known/oauth-protected-resource` | RFC 9728 | public | Discovery — points to the resource (`/maglo-service/v1/mcp`) and its issuer |
| GET | `/.well-known/oauth-authorization-server` | RFC 8414 | public | Discovery — lists `token_endpoint`, `registration_endpoint`, `jwks_uri`, scopes, PKCE methods, etc. |
| GET | `/.well-known/oauth-protected-resource/console-service/v1` | RFC 8414 spec-strict path | public | Same JSON as the prefixed variant — RFC 8414 inserts `/.well-known/<name>` BEFORE the issuer path. Spec-strict clients (Claude.ai) compute this path; naive clients follow our explicit `WWW-Authenticate` URL. We serve both. Mounted at app root via `well_known_root_router`. |
| GET | `/.well-known/oauth-authorization-server/console-service/v1` | RFC 8414 spec-strict path | public | Same as above for auth-server metadata. |
| GET | `/oauth/jwks.json` | RFC 7517 | public | Public keys for verifying our RS256 JWTs. `Cache-Control: no-cache` in non-prod, `public, max-age=3600` in prod (env-gated). |
| POST | `/oauth/register` | RFC 7591 (DCR) | public, rate-limited | Dynamic Client Registration. Returns `client_id` + `client_secret` (client_secret returned **only** here, ever). |
| GET | `/oauth/authorize` | OAuth 2.1 + PKCE | public (delegates) | Validates `client_id`, `redirect_uri` (exact match), PKCE challenge. Stashes the request and redirects browser to the bridge (or SPA login page once Phase 8 ships). |
| POST | `/oauth/authorize/continue` | internal (SPA hook) | maglo session JWT | Called by the bridge / SPA after login succeeds. Resumes the authorize flow and returns either `{next:"consent"}` or `{next:"redirect", redirect}`. |
| GET | `/oauth/consent/details` | internal (SPA hook) | maglo session JWT | Returns client name + scope descriptions for the consent screen. |
| POST | `/oauth/consent/decision` | internal (SPA hook) | maglo session JWT | Records the user's Allow/Deny + mints the auth code + returns the redirect URL back to the MCP client. |
| POST | `/oauth/token` | OAuth 2.1 | client auth | `authorization_code` and `refresh_token` grants. Mints RS256 JWT + rotates refresh token. |
| POST | `/oauth/revoke` | RFC 7009 | client auth | Revokes a refresh token. Access tokens are stateless JWTs — they live until `exp`. |
| POST | `/oauth/introspect` | RFC 7662 | client auth | Returns `{active, …claims}` for a presented token. |
| GET | `/oauth/bridge` | internal stop-gap | public | Server-rendered HTML page that drives login + consent until the SPA ships. **Will be removed in Phase 8.** |

### Database tables (migration `v41_oauth_server`, additive-only)

| Table | Purpose |
|---|---|
| `oauth_clients` | One row per DCR-registered client (Claude, ChatGPT, …). Stores `client_secret_hash` (bcrypt), allowed `redirect_uris` (exact-match list), allowed `grant_types`, allowed `scope`, registration metadata, and a `disabled_at` kill switch. |
| `oauth_authorization_codes` | Short-lived single-use auth codes. PK is `code_hash` (sha256). PKCE challenge persisted alongside. Consumed atomically via `UPDATE … RETURNING`. |
| `oauth_refresh_tokens` | Long-lived hashed refresh tokens. Single-use with rotation; `parent_token_hash` links the rotation chain so theft detection can revoke an entire family. |
| `oauth_consents` | One row per `(user_id, client_id)`. Records the scopes the user has granted. Reconnect with same scopes skips the consent screen. |
| `oauth_authorize_requests` | Short-lived stash of an in-progress `/authorize` while the user is bouncing through login + consent. PK is the `oauth_request_id` ferried in the URL. |

Access tokens are **stateless JWTs** — no DB table. Validated by JWKS on the resource server.

**Cleanup:** a daily Celery beat job (TODO if not yet wired) should delete rows from `oauth_authorization_codes`, `oauth_authorize_requests`, and `oauth_refresh_tokens` whose `expires_at` is more than 7 days in the past.

### Wiring touched (outside the package)

- [`src/main.py`](../../src/main.py) — mounts `OAuthController.well_known_root_router` at app root for the RFC 8414 spec-strict discovery paths.
- [`src/routes/base.py`](../../src/routes/base.py) — registers the three OAuth routers via the existing `Router.register_all_routes()` pattern, gated on `OAUTH_ENABLED`.
- [`src/middlewares/authentication.py`](../../src/middlewares/authentication.py) — every OAuth public-endpoint suffix added to `excluded_paths` (RFC 8414 paths, JWKS, register, authorize, token, revoke, introspect, bridge). Spec-mandated to be unauthenticated.
- [`src/core/environment.py`](../../src/core/environment.py) — `OAUTH_*` env block.
- [`src/components/cache/helper.py`](../../src/components/cache/helper.py) — added `incr_with_ttl(key, ttl, prefix)`: one canonical multi-instance-safe atomic counter primitive (INCR + EXPIRE pipelined) usable by every future rate-limiter.

---

## 6. Environment variables

### Required (production)

| Var | Example | Notes |
|---|---|---|
| `OAUTH_ENABLED` | `true` | Master gate. Defaults to `false`. |
| `OAUTH_ISSUER_URL` | `https://int-console-service.makunaiglobal.ai/console-service/v1` | The `iss` claim and the URL discovery documents advertise. **No trailing slash** — RFC 8414 is strict. |
| `OAUTH_RESOURCE_URL` | `https://int-maglo-service.makunaiglobal.ai/maglo-service/v1/mcp` | The `aud` claim. Must match what the resource server (maglo) enforces. |
| `OAUTH_SIGNING_KEY_PATH` | `/secrets/oauth-keys` | Directory of `*.pem` private keys. Files named `<kid>.pem`. `KeyRing` loads them all into JWKS; lex-newest becomes the signer. **Provision via `kubectl create secret --from-file` (never paste through chat — invisible whitespace can break PEM framing).** |
| `OAUTH_ACCESS_TOKEN_TTL_SECONDS` | `3600` | Stateless JWT — keep short. |
| `OAUTH_REFRESH_TOKEN_TTL_SECONDS` | `2592000` | 30 days. Revocable. |
| `OAUTH_AUTH_CODE_TTL_SECONDS` | `600` | 10 minutes. |
| `OAUTH_LOGIN_REDIRECT_URL` | `https://int-console-service.makunaiglobal.ai/console-service/v1/oauth/bridge` | Where `/oauth/authorize` sends an unauthenticated user. Today: the bridge stop-gap. **Phase 8: point at the SPA login route.** |

### Optional / abuse-control

| Var | Default | Effect |
|---|---|---|
| `OAUTH_REGISTRATION_ENABLED` | `true` | Hard kill switch for DCR — set `false` to stop new client registrations without affecting existing ones. |
| `OAUTH_REGISTRATION_RATE_PER_IP_PER_HOUR` | `30` | Per-IP DCR cap. |
| `OAUTH_REGISTRATION_RATE_GLOBAL_PER_HOUR` | `1000` | Global DCR cap. |
| `OAUTH_ALLOW_LOCAL_REDIRECT` | `false` | Dev only — allows `http://127.0.0.1:*` redirect URIs. Never enable in prod. |

---

## 7. Phase 8 — UI team scope

### Why this exists

Today the OAuth consent flow is handled by a **server-rendered HTML stop-gap** at [`src/components/oauth_server/bridge.py`](../../src/components/oauth_server/bridge.py). It works (the full Claude.ai handshake completes through it on int), but it's not the long-term experience we want:

- It lives outside the Console SPA, so it doesn't share styling, error states, or session UX.
- The login form there bypasses every UX nicety the SPA already has (password reset link, MFA, "remember me", etc.).
- It needs to be deleted once the SPA can do this properly.

### Goal of Phase 8

Replace `bridge.py` with two SPA touchpoints:

1. **8a — Login screen tweak.** When the existing login screen sees `?oauth_request_id=<id>` in the URL, complete the OAuth dance after login instead of routing to the dashboard. Roughly 30 lines of frontend code.
2. **8b — New `/oauth/consent` screen.** A dedicated page that lists the requesting client, the scopes it wants, and offers Allow / Deny buttons.

### What you'll integrate with (backend is done — do NOT change it)

The console-service backend already exposes three endpoints designed for this exact integration. Call them from the SPA exactly as documented; the bridge stop-gap calls them today, so the contracts are battle-tested on int.

| Method | Path | Auth | Body / Query | Returns |
|---|---|---|---|---|
| `POST` | `/console-service/v1/oauth/authorize/continue` | `Authorization: Bearer <maglo session JWT>` | `{ "oauth_request_id": "<id>" }` | `{ "next": "consent" }` **or** `{ "next": "redirect", "redirect": "<url>" }` |
| `GET` | `/console-service/v1/oauth/consent/details?oauth_request_id=<id>` | `Authorization: Bearer <maglo session JWT>` | — | `{ "client_id", "client_name", "scopes": [...], "scope_descriptions": [...] }` |
| `POST` | `/console-service/v1/oauth/consent/decision` | `Authorization: Bearer <maglo session JWT>` | `{ "oauth_request_id": "<id>", "allow": true \| false }` | `{ "redirect": "<url>" }` — full URL incl. query string; the SPA must `window.location = redirect` |

The maglo session JWT is the same JWT `POST /do_login` returns today; nothing new on the auth side.

### 8a — Login screen tweak

**Where:** the existing Console login screen.

**Behaviour change:** when the user lands at `/login?oauth_request_id=XYZ`:

1. Read `oauth_request_id` from the query string, hold it in component state.
2. Run the **existing** login flow as normal (call `/do_login`, get the maglo session JWT, persist it the way you already do).
3. **Instead of** redirecting to `/dashboard`, call:
   ```http
   POST /console-service/v1/oauth/authorize/continue
   Authorization: Bearer <maglo session JWT>
   Content-Type: application/json

   { "oauth_request_id": "XYZ" }
   ```
4. Branch on the response:
   - `{ "next": "redirect", "redirect": "<url>" }` → `window.location = redirect`. Done — the user goes straight back to the third-party app (this happens when prior consent already covers the requested scopes).
   - `{ "next": "consent" }` → `window.location = "/oauth/consent?oauth_request_id=XYZ"` (the new screen in 8b).

**Error handling:**
- Non-2xx response → show the existing login-error UI; the user can retry. Do NOT silently drop the `oauth_request_id`.
- If the user navigates away mid-flow, no cleanup needed — the request expires server-side after ~10 minutes.

### 8b — `/oauth/consent` screen

**New route:** `/oauth/consent?oauth_request_id=XYZ`. Authenticated — requires the maglo session JWT (use the same gate as the rest of the SPA).

**On page load:**

1. Read `oauth_request_id` from the URL.
2. Call:
   ```http
   GET /console-service/v1/oauth/consent/details?oauth_request_id=XYZ
   Authorization: Bearer <maglo session JWT>
   ```
3. Render a panel similar to the wireframe below. The exact copy is in `scope_descriptions[]` — render them verbatim, do not rewrite.

```
   ┌─────────────────────────────────────────────────────────────┐
   │  {client_name} wants to access your Maglo account            │
   │                                                              │
   │  {client_name} is requesting the following access:           │
   │                                                              │
   │    ✓  Read leads, lead requests, history, activity           │
   │    ✓  Read follow-ups and comments                           │
   │    ✓  Read service boards and management overview            │
   │    ✓  Read custom field definitions and values               │
   │    ✓  Read section catalogue and board mappings              │
   │                                                              │
   │  {client_name} will NOT be able to:                          │
   │    ✗  Modify or delete any data                              │
   │    ✗  Change settings                                        │
   │    ✗  Access other users' data                               │
   │                                                              │
   │  You can revoke this access at any time in                   │
   │  Settings → Connected Apps.                                  │
   │                                                              │
   │     [ Deny ]                            [ Allow ]            │
   └─────────────────────────────────────────────────────────────┘
```

**On click:**

```http
POST /console-service/v1/oauth/consent/decision
Authorization: Bearer <maglo session JWT>
Content-Type: application/json

{ "oauth_request_id": "XYZ", "allow": true }
```

Response:

```json
{ "redirect": "https://claude.ai/api/mcp/auth_callback?code=…&state=…" }
```

`window.location = redirect`. The user lands back in the third-party app, which now has its auth code and continues silently.

**Error handling:**
- If the GET returns 401/403/404, the request has expired or doesn't belong to the user. Show: *"This authorization request has expired. Please restart the connection from the calling app."*
- If the POST returns non-2xx, show the same expiry message and a "Try again" button that re-runs the GET.
- Network errors → standard retry banner.

### 8c — "Connected apps" management (optional, post-MVP)

A `Settings → Connected Apps` page that lets users see and revoke connections. Schema is in place — query `oauth_consents` joined with `oauth_clients`, filtered to the current user. Revocation requires:

- Update all matching `oauth_refresh_tokens.revoked_at = now()` for `(user_id, client_id)`.
- Update `oauth_consents.revoked_at = now()` for the same pair.

This can ship as a follow-up; the OAuth flow itself doesn't require it.

### Exit criteria

- [ ] User without session, hitting `/oauth/authorize?...`, bounces through SPA login then consent
- [ ] User with active consent skips the consent screen (sees `next:"redirect"` from `/authorize/continue`)
- [ ] Cancel returns the user to the original app with `?error=access_denied&state=...` preserved
- [ ] Reconnect with same scopes skips consent; reconnect with new scopes re-asks
- [ ] [`src/components/oauth_server/bridge.py`](../../src/components/oauth_server/bridge.py) deleted
- [ ] `OAUTH_LOGIN_REDIRECT_URL` env updated to point at the SPA login route, not the bridge
- [ ] `bridge` entry removed from `AuthMiddleware` `excluded_paths`

---

## 8. Phase 11 — QA team scope

### Setup

You will need:

- A non-prod environment (int) with `OAUTH_ENABLED=true` and the signing key provisioned
- Access to the integration logs (Loki / Grafana — `console-service` namespace)
- A Claude.ai or ChatGPT account
- A Maglo user account on the same environment
- `curl` + `jq` for the scripted scenarios
- Optional: MCP Inspector — `npx @modelcontextprotocol/inspector` — for transport-level smoke

### Test catalogue

#### Group A — Discovery (RFC 8414, RFC 9728)

| # | Test | Expected | Notes |
|---|---|---|---|
| A1 | `curl -fsS https://<host>/console-service/v1/.well-known/oauth-protected-resource` | 200, JSON contains `authorization_servers[0]`, `resource`, `scopes_supported`. | Naive-client path |
| A2 | `curl -fsS https://<host>/console-service/v1/.well-known/oauth-authorization-server` | 200, JSON contains `token_endpoint`, `registration_endpoint`, `jwks_uri`, `code_challenge_methods_supported: ["S256"]`. | Naive-client path |
| A3 | `curl -fsS https://<host>/.well-known/oauth-protected-resource/console-service/v1` | Same JSON as A1. | RFC-strict path — what Claude.ai actually computes |
| A4 | `curl -fsS https://<host>/.well-known/oauth-authorization-server/console-service/v1` | Same JSON as A2. | RFC-strict path |
| A5 | All discovery URLs returned in the bodies match `OAUTH_ISSUER_URL` exactly, **no trailing slash**. | yes | A single trailing-slash mismatch will silently break Claude.ai discovery |

#### Group B — JWKS

| # | Test | Expected |
|---|---|---|
| B1 | `curl -fsS https://<host>/console-service/v1/oauth/jwks.json \| jq .keys[0]` | 200, object with `kty: "RSA"`, `use: "sig"`, `alg: "RS256"`, `kid`, `n`, `e`. No `d` / `p` / `q` (those are private — must be absent). |
| B2 | `Cache-Control` header is `no-cache` in non-prod, `public, max-age=3600` in prod. | yes |

#### Group C — Dynamic Client Registration (RFC 7591)

| # | Test | Expected |
|---|---|---|
| C1 | Happy path: `POST /oauth/register` with `{ client_name, redirect_uris: ["https://example.com/cb"] }` | 201, returns `client_id`, `client_secret`, `client_id_issued_at`, echoes the request. `client_secret` ≥ 32 chars. |
| C2 | Reject `http://` redirect_uri | 400 / `invalid_redirect_uri` |
| C3 | Reject redirect_uri containing `#` (fragment) | 400 |
| C4 | Reject relative redirect_uri | 400 |
| C5 | Hit `POST /oauth/register` 31 times in a row from the same IP within an hour | First 30 succeed, 31st → 429 |
| C6 | With `OAUTH_REGISTRATION_ENABLED=false` set on the pod | 503 returned immediately |
| C7 | Audit log: row appears in `oauth_clients` with `registered_by_ip`, `registered_user_agent`, `registered_at`. | yes — verify in DB |

#### Group D — Full OAuth handshake (manual, end-to-end)

> Pre-condition for D1–D5: Claude.ai connected to a fresh int environment. Use **Settings → Connectors → Add custom connector** and paste `https://int-maglo-service.makunaiglobal.ai/maglo-service/v1/mcp`.

| # | Test | Expected |
|---|---|---|
| D1 | Add the connector. Browser bounces to the bridge / SPA. | Page loads, no console errors, oauth_request_id in URL |
| D2 | Sign in with a valid Maglo user | Consent screen renders with `client_name="Claude"` and the 5 read scopes |
| D3 | Click **Allow** | Redirects to `claude.ai/api/mcp/auth_callback?code=…&state=…`; Claude.ai UI shows "Connected" |
| D4 | Sign in with wrong password | Stays on login, error banner visible, no oauth_request_id leak in URL |
| D5 | Click **Deny** instead of Allow | Redirects to Claude.ai with `?error=access_denied&state=…`; Claude.ai UI shows the cancellation; no `oauth_consents` row created |
| D6 | Connect a second time with the same Maglo user + same Claude.ai client + same scopes | Consent screen **skipped**; goes straight to redirect (because prior consent exists) |
| D7 | Disconnect in Claude.ai, then reconnect | Consent screen still skipped (the saved consent is per-user-per-client, not per-Claude.ai-session) |

#### Group E — Token endpoint

| # | Test | Expected |
|---|---|---|
| E1 | Happy `authorization_code` grant | 200 + `access_token` (JWT), `refresh_token`, `expires_in: 3600`, `scope`, `token_type: "Bearer"` |
| E2 | Replay the same auth code | 400 / `invalid_grant` |
| E3 | Wrong `code_verifier` | 400 / `invalid_grant` |
| E4 | `redirect_uri` differs from what was registered | 400 / `invalid_grant` |
| E5 | Confidential client without `client_secret` | 401 |
| E6 | Wrong `client_secret` | 401 |
| E7 | Token JWT decoded (e.g. on https://jwt.io with our JWKS): `iss` matches `OAUTH_ISSUER_URL`, `aud` matches `OAUTH_RESOURCE_URL`, `sub=maglo:<id>`, `scope` is space-separated, custom claims `maglo_user_id` + `partner_id` present, header includes correct `kid` | yes |
| E8 | Refresh grant: `POST /oauth/token` with `grant_type=refresh_token` and the refresh token from E1 | 200, returns **new** `refresh_token` (rotated), new `access_token` |
| E9 | Replay the OLD refresh token (the one used in E8) | 400 / `invalid_grant`; the **entire chain** is revoked. Next legitimate refresh of the new token also fails. (Theft-detection invariant.) |
| E10 | `grant_type=client_credentials` | 400 / `unsupported_grant_type` (we don't enable this) |

#### Group F — Revoke + Introspect

| # | Test | Expected |
|---|---|---|
| F1 | `POST /oauth/revoke` with a valid refresh token | 200, no body. Next `/oauth/token` refresh with that token → 400. |
| F2 | `POST /oauth/revoke` with an unknown token | 200 (spec says success regardless — RFC 7009 §2.2) |
| F3 | `POST /oauth/introspect` with a valid access JWT | `{active: true, …claims}` |
| F4 | `POST /oauth/introspect` with an expired token | `{active: false}` |
| F5 | `POST /oauth/introspect` with garbage | `{active: false}` |

#### Group G — Resource-server interaction

These exercise the maglo side too — keep them on this list because they prove the contract holds end-to-end.

| # | Test | Expected |
|---|---|---|
| G1 | Use the access token from D3 to call `POST /maglo-service/v1/mcp` with `tools/list` | 200, returns ≥ 30 tools |
| G2 | Call `tools/call` for a tool inside the granted scope (e.g. `lead.list_leads` under `maglo:leads:read`) | 200 + result payload |
| G3 | Call `tools/call` for a tool **outside** the granted scope | JSON-RPC error / 403 |
| G4 | Wait for `expires_in` to elapse (or set `OAUTH_ACCESS_TOKEN_TTL_SECONDS=60` in a test env) and reuse the token | 401 + `WWW-Authenticate` header pointing back at our discovery doc |
| G5 | Rotate the signing key (drop a new PEM into `OAUTH_SIGNING_KEY_PATH`, restart) — tokens issued by the old key are still valid until `exp`, new tokens use the new `kid`, maglo's JWKS cache picks up the new key on next miss | yes |

#### Group H — Negative + abuse

| # | Test | Expected |
|---|---|---|
| H1 | `GET /oauth/authorize` with unknown `client_id` | 400 (NOT a redirect — never redirect to an unvalidated URI) |
| H2 | `GET /oauth/authorize` with bad `redirect_uri` | 400 |
| H3 | `GET /oauth/authorize` without `code_challenge` | error redirect with `invalid_request` |
| H4 | `GET /oauth/authorize` with `code_challenge_method=plain` | error redirect with `invalid_request` (S256 required) |
| H5 | `GET /oauth/authorize` requesting a scope not in `SCOPE_CATALOG` | error redirect with `invalid_scope` |
| H6 | `POST /oauth/token` with malformed JSON / wrong content-type | 400 |
| H7 | Audit logs do NOT contain full access tokens, full auth codes, or full client_secrets (only prefixes or hashes) | spot-check 20 random log entries |

### Exit criteria for Phase 11

- [ ] Every test in Groups A–H either passes or is formally accepted with a documented mitigation
- [ ] The CI smoke script (Phase 11a in the original plan — `scripts/oauth_smoke.py`) runs green on every PR touching `oauth_server/`
- [ ] At least one Claude.ai and one ChatGPT manual run captured end-to-end (screenshots in the test report)
- [ ] Audit-log review signed off by security

---

## 9. Phase 12 — Security review checklist

Give this list to the reviewer. Everything is implemented; the reviewer verifies.

- [ ] `redirect_uri` is **exact-match only**. No prefix, no substring, no query-string strip, no port wildcards.
- [ ] PKCE is **required**. No fallback to `plain` or `none`. Verifier checked with constant-time compare on the base64url-encoded sha256 digest.
- [ ] Auth codes are **single-use**. Stored hashed. Replay triggers chain revocation.
- [ ] Refresh tokens are **single-use with rotation**. Stored hashed. Replay triggers chain revocation. `parent_token_hash` walked to revoke the entire family.
- [ ] `client_secret` is returned **only at registration time**. Never queryable. Stored bcrypt-hashed.
- [ ] DCR has per-IP + global hourly rate limits (Redis-backed, atomic INCR + EXPIRE) AND a kill-switch env var.
- [ ] Signing key files are `chmod 600` and live behind a Kubernetes Secret. Never paste a PEM through chat — invisible whitespace breaks framing.
- [ ] JWKS endpoint returns **public** key parameters only (`n`, `e`, never `d`/`p`/`q`).
- [ ] All endpoints validate `Content-Type` and reject unexpected fields with 400.
- [ ] Error responses do not reflect raw user input (XSS vector if any path ever renders HTML).
- [ ] Logs do not record full tokens, full auth codes, or client_secrets (mask via `mask_for_logs` in the api-log middleware — see [`src/components/auth/masker.py`](../../src/components/auth/masker.py)).
- [ ] CORS allowlist excludes wildcards and is scoped to the `/mcp` prefix on the resource server.
- [ ] Bearer middleware **fails closed** — any verification exception returns 401, never 200.
- [ ] Trailing slashes in `issuer` / `audience` are consistent everywhere (one mismatch silently breaks Claude.ai).
- [ ] No `client_credentials` grant exposed.
- [ ] DCR client_name is treated as decorative — never used in security decisions.

---

## 10. Operational runbook

### Kill switches

- **Disable OAuth entirely:** `OAUTH_ENABLED=false`, restart. Router un-mounts. REST + existing JWT auth keep working byte-for-byte.
- **Stop new DCR registrations** (existing clients keep working): `OAUTH_REGISTRATION_ENABLED=false`, restart.
- **Disable one specific client** (e.g. compromised registration): `UPDATE oauth_clients SET disabled_at = now() WHERE client_id = '…';`. Every token issued for that client becomes 401-able the next time it hits the resource server.
- **Revoke one user's connector:** `UPDATE oauth_refresh_tokens SET revoked_at = now() WHERE user_id = ?; UPDATE oauth_consents SET revoked_at = now() WHERE user_id = ?;`. User must reconnect.
- **Mass disconnect (panic button):** `UPDATE oauth_refresh_tokens SET revoked_at = now(); UPDATE oauth_consents SET revoked_at = now();`. Extreme — every user must reconnect.

### Incident playbook

**Suspected token theft / refresh-token-reuse alarm**

1. Find the `client_id` and `user_id` in the alarm.
2. The chain-revocation has already fired automatically when the consumed refresh token was replayed. Confirm via:
   ```sql
   SELECT COUNT(*) FROM oauth_refresh_tokens
   WHERE user_id = ? AND client_id = ? AND revoked_at IS NOT NULL;
   ```
3. If broader compromise is suspected, disable the `client_id` (`UPDATE oauth_clients SET disabled_at = now() …`).
4. Inform the user out of band; consider forcing a password rotation if their Maglo account is the suspected entry point.

**Compromised `client_secret`**

1. Disable the `client_id`.
2. The secret is only ever returned at `/oauth/register` time — logs of that endpoint are the audit trail. Identify the leak vector.
3. The client integrator re-registers and reconfigures.

**Signing-key leak**

1. Generate a new key, deploy it (`kubectl create secret … --from-file=oauth-rs256-<n+1>.pem=…`), restart the pods.
2. **Immediately delete the old key from the secret** (don't wait for the rotation window) — this invalidates every outstanding token.
3. All clients reconnect via OAuth refresh. If refresh tokens were also leaked, users must re-auth from scratch.
4. Post-mortem + key-storage hardening.

**Claude.ai shows "Unauthorized" but `/oauth/token` returns 200**

This pattern means the OAuth handshake works but the resource server is rejecting the token. Almost always one of:

- Maglo's `MCP_OAUTH_AUDIENCE` env doesn't match `OAUTH_RESOURCE_URL` here (trailing-slash drift)
- Maglo's `MCP_OAUTH_ISSUER_URL` doesn't match `OAUTH_ISSUER_URL` here
- Maglo's JWKS cache is cold and console-service is unreachable

Cross-check both env blocks for byte-identical strings and confirm both services share network reachability.

### Provisioning a fresh signing key

```bash
# Locally:
openssl genrsa -out oauth-rs256-1.pem 2048
chmod 600 oauth-rs256-1.pem

# Upload to the cluster (NEVER paste through chat — whitespace breaks PEM framing):
kubectl -n <ns> create secret generic oauth-signing-keys \
  --from-file=oauth-rs256-1.pem=./oauth-rs256-1.pem \
  --dry-run=client -o yaml | kubectl apply -f -

# Confirm:
kubectl -n <ns> exec deploy/console-service -- \
  ls -l /secrets/oauth-keys/
```

---

## 11. Maintenance

### Quarterly

- **Rotate the signing key.**
  1. `openssl genrsa -out oauth-rs256-<n+1>.pem 2048`
  2. Upload to the Kubernetes Secret alongside the existing key.
  3. Restart the pods. `KeyRing` picks up the new key; `primary_kid` switches to it (lexicographic newest). The old key stays in JWKS until step 5.
  4. Wait ≥ `OAUTH_ACCESS_TOKEN_TTL_SECONDS` + buffer (e.g. 24 h). All previously-issued JWTs have now expired naturally.
  5. Remove the old PEM file from the Secret + restart. JWKS shrinks to just the new key.
- **Audit `oauth_clients`** — investigate any one IP creating many clients; archive disabled clients.
- **Dependency upgrades:** `pyjwt`, `cryptography`, `bcrypt`, `authlib` (if added later).
- **Re-run the Phase 11 verification matrix** before any release that touches `oauth_server/`.

### Monthly

- Review MCP spec changelog at https://modelcontextprotocol.io
- Review OAuth 2.1 / DCR / PKCE drafts (low-frequency but real)
- Review 401, 403, refresh-reuse rates for anomalies

### Off-boarding a user

```sql
-- 1. Disable in the existing user table (your existing flow)
-- 2. Revoke OAuth artefacts:
UPDATE oauth_refresh_tokens SET revoked_at = now() WHERE user_id = ?;
UPDATE oauth_consents       SET revoked_at = now() WHERE user_id = ?;
```

Stateless access tokens expire on their own within `OAUTH_ACCESS_TOKEN_TTL_SECONDS`.

---

## 12. FAQ

**Q: Why store auth codes as hashes but make refresh tokens single-use with rotation?**
Different threat models. Auth codes are short-lived (10 min) and exchanged once over TLS; hashing protects against a leaked DB snapshot replaying codes. Refresh tokens are long-lived (30 d) — rotation + theft detection gives you a chance to spot a compromise mid-stream.

**Q: Should access tokens be JWTs or opaque?**
JWTs here, because validating tokens on every MCP call must be fast and a network hop to console-service per request would dominate. Tradeoff: can't revoke individual access tokens — they live until `exp`. Mitigation: short `OAUTH_ACCESS_TOKEN_TTL_SECONDS` (1 h) + revoke at the refresh-token layer. Add a `jti` deny-list table if fast revoke ever matters.

**Q: Can a user have multiple connected clients?**
Yes. Each `client_id` has its own consent and its own refresh-token chain. Revoking one doesn't affect others.

**Q: Why is `redirect_uri` exact-match so critical?**
A surprising amount of OAuth-exploit history is "the matcher was too lenient." Substring match, suffix match, query-string normalisation, fragment-tolerant match — each one became a CVE. Exact-match has no edge cases.

**Q: Do we need `client_credentials`?**
No — that's for service-to-service. MCP is user-driven. Don't enable; it's another attack surface.

**Q: Why is DCR open by default?**
The spec requires it — clients can't be pre-issued credentials. The protection is rate-limit + kill switch, not auth.

**Q: What is the bridge for?**
A server-rendered HTML stop-gap that drives login + consent today so the OAuth flow could ship end-to-end before the SPA work was scheduled. It will be deleted in Phase 8.

**Q: Where do I add a new scope?**
See the scope-contract section in the [maglo-service MCP doc](../../../maglo-service/docs/mcp/02-mcp-remote-self-hosted.md) — must be added on **both** sides in the right order.

---

## 13. Appendix

### Useful links

- OAuth 2.1 draft: https://datatracker.ietf.org/doc/html/draft-ietf-oauth-v2-1
- PKCE (RFC 7636): https://datatracker.ietf.org/doc/html/rfc7636
- DCR (RFC 7591): https://datatracker.ietf.org/doc/html/rfc7591
- Token Revocation (RFC 7009): https://datatracker.ietf.org/doc/html/rfc7009
- Token Introspection (RFC 7662): https://datatracker.ietf.org/doc/html/rfc7662
- Authorization Server Metadata (RFC 8414): https://datatracker.ietf.org/doc/html/rfc8414
- Protected Resource Metadata (RFC 9728): https://datatracker.ietf.org/doc/html/rfc9728
- MCP spec: https://modelcontextprotocol.io

### Example payloads

**`POST /oauth/register`:**

```http
POST /console-service/v1/oauth/register
Content-Type: application/json

{
  "client_name": "Claude",
  "redirect_uris": ["https://claude.ai/api/mcp/auth_callback"],
  "token_endpoint_auth_method": "client_secret_basic"
}
```

```json
{
  "client_id": "AbC123dEf456",
  "client_secret": "long-random-secret-returned-only-here",
  "client_id_issued_at": 1715251200,
  "client_secret_expires_at": 0,
  "client_name": "Claude",
  "redirect_uris": ["https://claude.ai/api/mcp/auth_callback"],
  "grant_types": ["authorization_code", "refresh_token"],
  "token_endpoint_auth_method": "client_secret_basic"
}
```

**`GET /oauth/authorize` URL:**

```
GET /console-service/v1/oauth/authorize
    ?client_id=AbC123dEf456
    &response_type=code
    &redirect_uri=https%3A%2F%2Fclaude.ai%2Fapi%2Fmcp%2Fauth_callback
    &scope=maglo%3Aleads%3Aread%20maglo%3Afollowups%3Aread
    &state=opaque-csrf-value
    &code_challenge=…
    &code_challenge_method=S256
```

**`POST /oauth/token` (authorization_code):**

```http
POST /console-service/v1/oauth/token
Content-Type: application/x-www-form-urlencoded
Authorization: Basic base64(client_id:client_secret)

grant_type=authorization_code
&code=…
&redirect_uri=https%3A%2F%2Fclaude.ai%2Fapi%2Fmcp%2Fauth_callback
&code_verifier=…
```

```json
{
  "access_token": "eyJhbGciOiJSUzI1NiIs…",
  "token_type": "Bearer",
  "expires_in": 3600,
  "refresh_token": "long-random-opaque",
  "scope": "maglo:leads:read maglo:followups:read"
}
```

**Example decoded access token:**

```json
{
  "iss": "https://int-console-service.makunaiglobal.ai/console-service/v1",
  "sub": "maglo:33",
  "aud": "https://int-maglo-service.makunaiglobal.ai/maglo-service/v1/mcp",
  "exp": 1715254800,
  "iat": 1715251200,
  "jti": "S__L-o2As-iLlYy4DH5tyg",
  "scope": "maglo:custom_fields:read maglo:followups:read maglo:leads:read maglo:sections:read maglo:service_boards:read",
  "client_id": "AbC123dEf456",
  "maglo_user_id": 33,
  "partner_id": 12,
  "role_hierarchy_level": 1
}
```

### Troubleshooting commands

```bash
# Discovery — naive path
curl -fsS https://<host>/console-service/v1/.well-known/oauth-authorization-server | jq .

# Discovery — RFC 8414 spec-strict path (what Claude.ai actually calls)
curl -fsS https://<host>/.well-known/oauth-authorization-server/console-service/v1 | jq .

# JWKS
curl -fsS https://<host>/console-service/v1/oauth/jwks.json | jq .

# Manual DCR
curl -X POST https://<host>/console-service/v1/oauth/register \
     -H 'Content-Type: application/json' \
     -d '{"client_name":"smoke","redirect_uris":["https://example.com/cb"]}' | jq .

# Validate a token locally (pyjwt + httpx)
python -c "
import jwt as pyjwt, httpx, sys
jwks = httpx.get('https://<host>/console-service/v1/oauth/jwks.json').json()
header = pyjwt.get_unverified_header(sys.argv[1])
key = next(k for k in jwks['keys'] if k['kid'] == header['kid'])
claims = pyjwt.decode(sys.argv[1], key=pyjwt.algorithms.RSAAlgorithm.from_jwk(key),
                     algorithms=['RS256'], audience='<aud>')
print(claims)
" "$ACCESS_TOKEN"
```
