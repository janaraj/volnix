"""Auth middleware — validates Authorization header shape per service.

Accepts structurally valid tokens (e.g., ``Bearer sk_test_*`` for Stripe).
Does NOT validate against real auth servers, check scopes, or handle
token refresh/expiry. Returns 401 for invalid token shapes.

All rules come from TOML config — no hardcoded values.
"""
from __future__ import annotations

import logging
import re
from typing import Any

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from volnix.middleware.config import MiddlewareConfig

logger = logging.getLogger(__name__)

# Paths that skip auth (internal Volnix API, MCP, health, WebSocket)
_SKIP_PREFIXES = (
    "/api/v1/",
    "/mcp/",
    "/mcp",
    "/health",
    "/docs",
    "/openapi.json",
    "/ws/",
)

# Max auth header length (C3 fix: prevent ReDoS on long inputs)
_MAX_AUTH_HEADER_LENGTH = 500


class AuthMiddleware(BaseHTTPMiddleware):
    """Validates Authorization header shape for service API routes.

    Skips auth for internal Volnix endpoints (/api/v1/*, /mcp, /health).
    Unknown services (no rule configured) pass through.
    """

    def __init__(self, app: Any, config: MiddlewareConfig) -> None:
        super().__init__(app)
        self._enabled = config.auth_enabled
        self._rules: dict[str, re.Pattern[str]] = {}
        for service, pattern in config.auth_rules.items():
            try:
                self._rules[service] = re.compile(pattern)
            except re.error as exc:
                logger.warning(
                    "Invalid auth rule for '%s': %s", service, exc
                )
        self._prefixes = config.service_prefixes

    async def dispatch(
        self, request: Request, call_next: Any
    ) -> Response:
        """Check auth header if enabled and route matches a service."""
        if not self._enabled:
            return await call_next(request)

        # H6/M6 fix: skip CORS preflight (OPTIONS) requests
        if request.method == "OPTIONS":
            return await call_next(request)

        path = request.url.path

        # Skip internal endpoints (C2 fix: includes /ws/ paths)
        if any(path.startswith(p) for p in _SKIP_PREFIXES):
            return await call_next(request)

        # Resolve which service this request targets
        service = self._resolve_service(path)

        # If we have a rule for this service, validate
        if service and service in self._rules:
            # H3 fix: distinguish missing vs empty header
            auth_header = request.headers.get("authorization")
            if auth_header is None:
                return JSONResponse(
                    status_code=401,
                    content={
                        "error": {
                            "message": "Missing Authorization header",
                            "type": "authentication_error",
                        }
                    },
                )
            if not auth_header.strip():
                return JSONResponse(
                    status_code=401,
                    content={
                        "error": {
                            "message": "Empty Authorization header",
                            "type": "authentication_error",
                        }
                    },
                )
            # C3 fix: reject excessively long headers (ReDoS prevention)
            if len(auth_header) > _MAX_AUTH_HEADER_LENGTH:
                return JSONResponse(
                    status_code=401,
                    content={
                        "error": {
                            "message": "Authorization header too long",
                            "type": "authentication_error",
                        }
                    },
                )
            if not self._rules[service].fullmatch(auth_header):
                return JSONResponse(
                    status_code=401,
                    content={
                        "error": {
                            "message": "Invalid authentication credentials",
                            "type": "authentication_error",
                        }
                    },
                )

        return await call_next(request)

    def _resolve_service(self, path: str) -> str | None:
        """Extract service name from URL path.

        Checks configured service prefixes first (e.g., /stripe/v1/...),
        then falls back to known path patterns.
        """
        # Check configured prefixes
        for service, prefix in self._prefixes.items():
            if path.startswith(prefix):
                return service

        # Fallback: match service name from first path segment
        # /gmail/v1/* → "gmail" (first segment matches a service)
        # /v1/charges (un-prefixed) → no match (intentionally open)
        # Use service_prefixes for auth on specific paths:
        #   stripe = "/stripe" → /stripe/v1/charges is auth-checked
        parts = path.strip("/").split("/")
        if parts:
            first = parts[0]
            if first in self._rules:
                return first

        return None

        return None
