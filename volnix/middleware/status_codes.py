"""Status code middleware — maps response body errors to HTTP status codes.

Currently Volnix returns 200 for all responses, with errors in the
body as ``{"error": "..."}`` or ``{"error": {"message": "..."}}``. Real
API SDKs check HTTP status codes for error handling. This middleware
reclassifies 200 JSON responses that contain error bodies to appropriate
HTTP status codes.

Only processes ``application/json`` responses. Non-JSON, streaming, and
non-200 responses pass through unchanged with all headers preserved.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from volnix.middleware.config import MiddlewareConfig

logger = logging.getLogger(__name__)

# Error message patterns → HTTP status codes (first match wins)
_ERROR_PATTERNS: list[tuple[int, list[str]]] = [
    (404, ["not found", "does not exist", "no such", "not available"]),
    (403, ["permission denied", "forbidden", "not authorized"]),
    (400, ["invalid", "required field", "missing param", "malformed"]),
    (422, ["validation failed", "schema error"]),
    (429, ["rate limit", "budget exhausted", "quota exceeded"]),
    (409, ["conflict", "already exists", "duplicate"]),
]

# Pipeline short-circuit step → HTTP status code
_STEP_STATUS_MAP: dict[str, int] = {
    "permission": 403,
    "policy": 403,
    "budget": 429,
    "capability": 404,
    "validation": 422,
}

# Max response size to parse (skip large responses — unlikely errors)
_MAX_BODY_SIZE = 1_000_000  # 1MB


class StatusCodeMiddleware(BaseHTTPMiddleware):
    """Maps error response bodies to proper HTTP status codes.

    Only reclassifies responses where:
    - status_code == 200
    - Content-Type is application/json
    - Body contains a truthy ``"error"`` key

    Non-200, non-JSON, and non-error responses pass through unchanged.
    Custom response headers are preserved on reclassification.
    """

    def __init__(self, app: Any, config: MiddlewareConfig) -> None:
        super().__init__(app)
        self._enabled = config.status_codes_enabled

    async def dispatch(self, request: Request, call_next: Any) -> Response:
        """Process response and reclassify errors."""
        if not self._enabled:
            return await call_next(request)

        response = await call_next(request)

        # Only reclassify 200 responses
        if response.status_code != 200:
            return response

        # C1 fix: only parse JSON responses (check Content-Type)
        content_type = response.headers.get("content-type", "")
        if "application/json" not in content_type:
            return response

        # Read response body
        body_bytes = b""
        async for chunk in response.body_iterator:
            if isinstance(chunk, bytes):
                body_bytes += chunk
            else:
                body_bytes += chunk.encode()
            # M5 fix: skip large responses
            if len(body_bytes) > _MAX_BODY_SIZE:
                return self._rebuild_response(response, body_bytes, 200)

        # Try to parse as JSON
        try:
            body = json.loads(body_bytes)
        except (json.JSONDecodeError, UnicodeDecodeError):
            return self._rebuild_response(response, body_bytes, 200)

        # Not a dict or no error key — pass through
        if not isinstance(body, dict) or "error" not in body:
            return self._rebuild_response(response, body_bytes, 200)

        # H4 fix: skip falsy error values (null, "", 0, False)
        error = body["error"]
        if not error:
            return self._rebuild_response(response, body_bytes, 200)

        # Extract error message
        if isinstance(error, dict):
            error_msg = error.get("message", str(error))
        else:
            error_msg = str(error)
        error_lower = error_msg.lower()

        # Check pipeline short-circuit step
        step = body.get("step", "")
        if step and step in _STEP_STATUS_MAP:
            return self._rebuild_response(response, body_bytes, _STEP_STATUS_MAP[step])

        # Check error message patterns
        for status_code, patterns in _ERROR_PATTERNS:
            if any(p in error_lower for p in patterns):
                return self._rebuild_response(response, body_bytes, status_code)

        # Default: 400 for unmatched errors
        return self._rebuild_response(response, body_bytes, 400)

    @staticmethod
    def _rebuild_response(
        original: Response,
        body: bytes,
        status_code: int,
    ) -> Response:
        """Rebuild response with new status code, preserving headers.

        C1 fix: copies all original headers (X-RateLimit-*, etc.)
        and preserves the original media type.
        """
        # Copy headers, excluding content-length (will be recalculated)
        headers = {k: v for k, v in original.headers.items() if k.lower() != "content-length"}
        return Response(
            content=body,
            status_code=status_code,
            headers=headers,
            media_type=original.media_type,
        )
