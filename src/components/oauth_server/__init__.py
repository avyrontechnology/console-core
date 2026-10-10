"""Self-hosted OAuth 2.1 Authorization Server.

This package implements the OAuth 2.1 + RFC 7591 (DCR) endpoints that power
remote MCP clients (Claude.ai Custom Connectors, ChatGPT MCP Connectors)
and any future "Connect Maglo" integrations.

Endpoints exposed (all PUBLIC — must be skipped by AuthMiddleware):
    GET  /.well-known/oauth-authorization-server   (RFC 8414)
    GET  /.well-known/oauth-protected-resource     (RFC 9728)
    GET  /oauth/jwks.json
    POST /oauth/register                            (RFC 7591 DCR)
    GET  /oauth/authorize                           (PKCE)
    POST /oauth/token                               (auth-code + refresh)
    POST /oauth/revoke                              (RFC 7009)
    POST /oauth/introspect                          (RFC 7662)

Endpoints requiring a logged-in console-service session:
    POST /oauth/authorize/continue                  (resumes after login)
    GET  /oauth/consent/details
    POST /oauth/consent/decision

The package is self-contained and additive: it neither touches the existing
console-service `AuthMiddleware` JWT path nor the `SECRET_KEY` used by it.
Tokens we issue are RS256 JWTs signed with keys loaded from a separate
directory; the public set is published at /oauth/jwks.json and consumed by
maglo-service for Bearer validation on /mcp.
"""
