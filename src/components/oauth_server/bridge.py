"""Server-rendered HTML bridge for the OAuth consent flow.

The Maglo wordmark sits alongside this file as ``maglo-logo.svg`` and is
read into ``_LOGO_INLINE_SVG`` at import time. We bake the SVG bytes into
the rendered HTML (rather than ``<img src="…">``) so the bridge has zero
external dependencies — no static-file mount, no CDN, no second HTTP
hop, and no CORS surface. Missing file → empty logo block, the rest of
the page renders unchanged.


Phase 8 (the proper SPA bridge — read ``?oauth_request_id`` on the login
screen + dedicated /oauth/consent page) is the frontend team's
responsibility, but until it ships we need *something* that lets a real
MCP client (Claude.ai Custom Connectors, ChatGPT) actually complete the
auth-code flow end-to-end.

This module is that stop-gap. A single FastAPI route renders one
self-contained HTML page that:

  1. Reads ``oauth_request_id`` from the URL.
  2. Shows the user a username/password form.
  3. POSTs to the existing ``/console-service/v1/do_login?svc_name=console``
     to get a session JWT.
  4. POSTs to ``/oauth/authorize/continue`` with that Bearer token.
  5. Handles whichever next-step the server returns:
       - ``next == "consent"``: fetches ``/oauth/consent/details``,
         renders a minimal Allow / Deny screen, calls
         ``/oauth/consent/decision``, redirects per the response.
       - ``next == "redirect"``: window.location to the redirect URL.

No framework — vanilla HTML + fetch — so it works in any browser
without a build step. The whole page is plain text, easy to audit, and
hosted on the same origin as the OAuth endpoints (no CORS hop required
when the page POSTs to /do_login / /oauth/*).

Production swap-out: when the FE team ships the real consent UI, point
``OAUTH_LOGIN_REDIRECT_URL`` at the SPA's URL instead of this bridge
and this module can be deleted.
"""

from pathlib import Path


# Read the Maglo wordmark once at import time. Production swap-out is a
# straight file replace — drop a new SVG with the same filename, restart.
# The file is part of the source tree (no env var / runtime configuration)
# so the bridge has a known-good logo without any deploy-time wiring.
_LOGO_FILE = Path(__file__).parent / "maglo-logo.svg"
try:
    _LOGO_INLINE_SVG = _LOGO_FILE.read_text(encoding="utf-8")
    # XML prologs (``<?xml ... ?>``) are valid in standalone SVG files
    # but illegal mid-document in HTML. Modern browsers tolerate the
    # noise; strict validators and a few mobile WebViews don't. Strip
    # it so the inlined wordmark stays HTML-clean.
    _stripped = _LOGO_INLINE_SVG.lstrip()
    if _stripped.startswith("<?xml"):
        _LOGO_INLINE_SVG = _stripped[_stripped.index("?>") + 2:].lstrip()
except OSError:
    # Missing / unreadable file degrades to "no logo" rather than failing
    # the whole bridge — the consent panel below the logo still loads.
    _LOGO_INLINE_SVG = ""

# HTML wrapper for the SVG. Substituted into the template via
# ``str.replace`` AFTER ``.format()`` runs, so the SVG's content cannot
# collide with the CSS/JS brace-escaping the format string already does.
_LOGO_BLOCK_HTML = (
    f'<div class="logo-wrap" aria-label="Maglo">{_LOGO_INLINE_SVG}</div>'
    if _LOGO_INLINE_SVG
    else ""
)

# Sentinel the template carries verbatim; replaced after .format() to
# inject the logo block (or nothing).
_LOGO_PLACEHOLDER = "<!--__OAUTH_BRIDGE_LOGO__-->"


# Inline page. We use ``{{`` and ``}}`` to escape literal braces because
# the controller wraps the page with a tiny template-string call to inject
# the OAuth API base URL.
BRIDGE_HTML_TEMPLATE = r"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Authorize Maglo MCP access</title>
  <style>
    :root {{
      --bg: #f8fafc;
      --panel: #ffffff;
      --border: #e2e8f0;
      --text: #1e293b;
      --muted: #64748b;
      --primary: #2563eb;
      --primary-hover: #1d4ed8;
      --danger: #dc2626;
      --danger-hover: #b91c1c;
      --success: #16a34a;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0; padding: 24px;
      background: var(--bg);
      color: var(--text);
      font-family: system-ui, -apple-system, "Segoe UI", Roboto, sans-serif;
      display: flex; justify-content: center; align-items: flex-start;
      min-height: 100vh;
    }}
    .panel {{
      background: var(--panel);
      border: 1px solid var(--border);
      border-radius: 12px;
      padding: 32px;
      max-width: 480px;
      width: 100%;
      margin-top: 48px;
      box-shadow: 0 1px 3px rgb(0 0 0 / 0.04);
    }}
    h1 {{ margin: 0 0 8px; font-size: 1.5rem; }}
    .subtitle {{ color: var(--muted); margin: 0 0 24px; font-size: 0.95rem; }}
    label {{ display: block; font-size: 0.875rem; font-weight: 500; margin: 16px 0 6px; }}
    input[type="email"], input[type="password"], input[type="text"] {{
      width: 100%; padding: 10px 12px;
      border: 1px solid var(--border); border-radius: 8px;
      font-size: 0.95rem;
      background: #fff;
    }}
    input:focus {{ outline: 2px solid var(--primary); outline-offset: -1px; }}
    .row {{ display: flex; gap: 12px; margin-top: 24px; }}
    button {{
      flex: 1; padding: 10px 16px; border-radius: 8px; border: none;
      font-size: 0.95rem; font-weight: 500; cursor: pointer;
      transition: background 0.15s;
    }}
    button.primary {{ background: var(--primary); color: white; }}
    button.primary:hover {{ background: var(--primary-hover); }}
    button.primary:disabled {{ background: #93c5fd; cursor: wait; }}
    button.danger {{ background: white; color: var(--danger); border: 1px solid var(--danger); }}
    button.danger:hover {{ background: #fef2f2; }}
    button.ghost {{ background: white; color: var(--muted); border: 1px solid var(--border); }}
    button.ghost:hover {{ background: #f1f5f9; }}
    .scope-list {{ list-style: none; padding: 0; margin: 0 0 16px; }}
    .scope-list li {{
      padding: 8px 12px; background: #f1f5f9; border-radius: 6px; margin-bottom: 6px;
      font-size: 0.9rem;
    }}
    .scope-list li::before {{ content: "✓ "; color: var(--success); font-weight: bold; }}
    .error {{
      background: #fef2f2; border: 1px solid #fecaca; color: var(--danger);
      padding: 12px; border-radius: 8px; font-size: 0.875rem; margin-top: 16px;
    }}
    .info {{
      background: #eff6ff; border: 1px solid #bfdbfe; color: #1e40af;
      padding: 12px; border-radius: 8px; font-size: 0.875rem; margin: 16px 0;
    }}
    .hidden {{ display: none; }}
    .client-name {{ font-weight: 600; color: var(--primary); }}
    .footnote {{
      margin-top: 24px; font-size: 0.8rem; color: var(--muted);
      border-top: 1px solid var(--border); padding-top: 16px;
    }}
    code {{
      font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
      font-size: 0.85em; background: #f1f5f9; padding: 1px 5px; border-radius: 4px;
    }}
    .logo-wrap {{
      display: flex; justify-content: center; align-items: center;
      margin: -8px 0 20px; padding: 0;
    }}
    .logo-wrap svg {{
      width: auto; height: 56px;
      max-width: 100%; display: block;
    }}
  </style>
</head>
<body>
  <div class="panel">
    <!--__OAUTH_BRIDGE_LOGO__-->
    <h1 id="title">Authorize MCP access</h1>
    <p class="subtitle" id="subtitle">Sign in to grant access to your Maglo account.</p>

    <!-- Stage 1: login -->
    <div id="login-stage">
      <label for="email">Email</label>
      <input id="email" type="email" autocomplete="username" placeholder="you@example.com" />
      <label for="password">Password</label>
      <input id="password" type="password" autocomplete="current-password" placeholder="••••••••" />
      <div class="row">
        <button class="primary" id="login-btn">Sign in &amp; continue</button>
      </div>
    </div>

    <!-- Stage 2: consent -->
    <div id="consent-stage" class="hidden">
      <p class="subtitle">
        <span class="client-name" id="consent-client">…</span>
        wants the following access to your Maglo account:
      </p>
      <ul class="scope-list" id="consent-scopes"></ul>
      <div class="row">
        <button class="danger" id="deny-btn">Deny</button>
        <button class="primary" id="allow-btn">Allow</button>
      </div>
    </div>

    <!-- Stage 3: redirecting -->
    <div id="redirect-stage" class="hidden">
      <div class="info">Authorisation complete — returning you to the application…</div>
    </div>

    <div id="error-box" class="error hidden"></div>

    <p class="footnote">
      You're seeing this page because you clicked a "Connect Maglo" button in another
      application. Token issuance is governed by your Maglo OAuth server at
      <code id="footnote-issuer">{api_base}</code>.
    </p>
  </div>

<script>
(function () {{
  const apiBase = {api_base_js};
  const params = new URLSearchParams(window.location.search);
  const oauthRequestId = params.get("oauth_request_id") || "";

  const loginStage = document.getElementById("login-stage");
  const consentStage = document.getElementById("consent-stage");
  const redirectStage = document.getElementById("redirect-stage");
  const errorBox = document.getElementById("error-box");
  const loginBtn = document.getElementById("login-btn");
  const allowBtn = document.getElementById("allow-btn");
  const denyBtn = document.getElementById("deny-btn");
  const emailInput = document.getElementById("email");
  const passwordInput = document.getElementById("password");
  const clientLabel = document.getElementById("consent-client");
  const scopeList = document.getElementById("consent-scopes");

  let userJwt = "";

  function showError(message) {{
    errorBox.textContent = message;
    errorBox.classList.remove("hidden");
  }}
  function clearError() {{
    errorBox.classList.add("hidden");
    errorBox.textContent = "";
  }}
  function showStage(stage) {{
    loginStage.classList.toggle("hidden", stage !== "login");
    consentStage.classList.toggle("hidden", stage !== "consent");
    redirectStage.classList.toggle("hidden", stage !== "redirect");
  }}

  if (!oauthRequestId) {{
    showError("Missing oauth_request_id in the URL. Restart the connection from the calling application.");
    loginBtn.disabled = true;
    return;
  }}

  async function login() {{
    clearError();
    loginBtn.disabled = true;
    try {{
      // svc_name is a FastAPI Query param (ServiceNames enum); body
      // holds credential + password. Path stays at /do_login so it
      // matches AuthMiddleware's ``do_login`` suffix in excluded_paths.
      const resp = await fetch(apiBase + "/do_login?svc_name=console", {{
        method: "POST",
        headers: {{"Content-Type": "application/json"}},
        body: JSON.stringify({{
          credential: emailInput.value.trim(),
          password: passwordInput.value,
        }}),
      }});
      const body = await resp.json();
      if (!resp.ok) {{
        const detail = (body && (body.detail || body.message)) || "Sign-in failed";
        showError(detail);
        return;
      }}
      // Accept several known login-response shapes. Update here if your
      // /do_login wrapper differs.
      userJwt = (body && body.data && body.data.access_token)
             || (body && body.access_token)
             || (body && body.data && body.data.token);
      if (!userJwt) {{
        showError("Login succeeded but no access_token returned. Check do_login response shape.");
        return;
      }}
      await continueAuthorize();
    }} catch (e) {{
      showError("Network error during login: " + e.message);
    }} finally {{
      loginBtn.disabled = false;
    }}
  }}

  async function continueAuthorize() {{
    const resp = await fetch(apiBase + "/oauth/authorize/continue", {{
      method: "POST",
      headers: {{
        "Content-Type": "application/json",
        "Authorization": "Bearer " + userJwt,
      }},
      body: JSON.stringify({{oauth_request_id: oauthRequestId}}),
    }});
    const body = await resp.json();
    if (!resp.ok) {{
      showError((body && body.error_description) || (body && body.error) || "Authorize step failed");
      return;
    }}
    if (body.next === "redirect" && body.redirect) {{
      showStage("redirect");
      window.location = body.redirect;
      return;
    }}
    if (body.next === "consent") {{
      await loadConsentDetails();
      return;
    }}
    showError("Unexpected response from /oauth/authorize/continue: " + JSON.stringify(body));
  }}

  async function loadConsentDetails() {{
    const url = apiBase + "/oauth/consent/details?oauth_request_id=" + encodeURIComponent(oauthRequestId);
    const resp = await fetch(url, {{
      headers: {{"Authorization": "Bearer " + userJwt}},
    }});
    const body = await resp.json();
    if (!resp.ok) {{
      showError((body && body.error_description) || "Failed to load consent details");
      return;
    }}
    clientLabel.textContent = body.client_name || body.client_id || "An application";
    scopeList.innerHTML = "";
    (body.scope_descriptions || []).forEach(desc => {{
      const li = document.createElement("li");
      li.textContent = desc;
      scopeList.appendChild(li);
    }});
    showStage("consent");
  }}

  async function decide(allow) {{
    allowBtn.disabled = true;
    denyBtn.disabled = true;
    try {{
      const resp = await fetch(apiBase + "/oauth/consent/decision", {{
        method: "POST",
        headers: {{
          "Content-Type": "application/json",
          "Authorization": "Bearer " + userJwt,
        }},
        body: JSON.stringify({{
          oauth_request_id: oauthRequestId,
          allow: !!allow,
        }}),
      }});
      const body = await resp.json();
      if (!resp.ok) {{
        showError((body && body.error_description) || "Consent decision failed");
        return;
      }}
      if (body.redirect) {{
        showStage("redirect");
        window.location = body.redirect;
        return;
      }}
      showError("Unexpected response from /oauth/consent/decision");
    }} catch (e) {{
      showError("Network error during consent decision: " + e.message);
    }} finally {{
      allowBtn.disabled = false;
      denyBtn.disabled = false;
    }}
  }}

  loginBtn.addEventListener("click", e => {{ e.preventDefault(); login(); }});
  allowBtn.addEventListener("click", () => decide(true));
  denyBtn.addEventListener("click", () => decide(false));
  passwordInput.addEventListener("keydown", e => {{ if (e.key === "Enter") login(); }});
}})();
</script>
</body>
</html>
"""


def render(api_base: str) -> str:
    """Return the bridge HTML with ``api_base`` interpolated.

    Uses ``str.format`` with deliberately-escaped braces (``{{`` / ``}}``)
    so the giant CSS / JS body doesn't need a templating engine.
    """
    import json as _json

    rendered = BRIDGE_HTML_TEMPLATE.format(
        api_base=api_base,
        # JS literal of the same value — JSON-escaped so quotes/specials
        # can't break out of the string.
        api_base_js=_json.dumps(api_base),
    )
    # Inject the wordmark AFTER ``.format()`` so the SVG's content (which
    # may contain characters that are special to format strings) cannot
    # collide with the CSS/JS brace-escaping the template already does.
    return rendered.replace(_LOGO_PLACEHOLDER, _LOGO_BLOCK_HTML, 1)
