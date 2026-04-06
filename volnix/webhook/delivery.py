"""Webhook delivery — async HTTP POST with retry and HMAC signing."""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import logging
from typing import Any

import httpx
from pydantic import BaseModel

logger = logging.getLogger(__name__)


class DeliveryResult(BaseModel, frozen=True):
    """Outcome of a webhook delivery attempt."""

    success: bool
    attempts: int
    status_code: int = 0
    error: str = ""


class WebhookDelivery:
    """Delivers webhook payloads via HTTP POST with retry.

    Retry policy:
    - 2xx/3xx: success, no retry
    - 4xx: client error, no retry (caller's problem)
    - 5xx: server error, retry with exponential backoff
    - Connection error: retry with backoff
    """

    def __init__(
        self,
        max_retries: int = 3,
        backoff_base: float = 1.0,
        timeout: float = 10.0,
    ) -> None:
        self._max_retries = max_retries
        self._backoff_base = backoff_base
        self._timeout = timeout

    async def send(
        self,
        url: str,
        payload: dict[str, Any],
        secret: str = "",
    ) -> DeliveryResult:
        """POST payload to url with retry on 5xx.

        If ``secret`` is provided, adds ``X-Volnix-Signature``
        HMAC-SHA256 header for payload verification.
        """
        last_status = 0  # H1 fix: track last 5xx status
        for attempt in range(self._max_retries + 1):
            try:
                headers: dict[str, str] = {
                    "Content-Type": "application/json",
                    "User-Agent": "Volnix-Webhook/1.0",
                }
                if secret:
                    headers["X-Volnix-Signature"] = self._sign(payload, secret)

                async with httpx.AsyncClient(timeout=self._timeout) as client:
                    resp = await client.post(url, json=payload, headers=headers)

                if resp.status_code < 400:
                    return DeliveryResult(
                        success=True,
                        attempts=attempt + 1,
                        status_code=resp.status_code,
                    )

                # 4xx = client error, don't retry
                if resp.status_code < 500:
                    return DeliveryResult(
                        success=False,
                        attempts=attempt + 1,
                        status_code=resp.status_code,
                        error=f"HTTP {resp.status_code}",
                    )

                # 5xx = server error, retry
                last_status = resp.status_code
                logger.debug(
                    "Webhook delivery to %s returned %d (attempt %d/%d)",
                    url,
                    resp.status_code,
                    attempt + 1,
                    self._max_retries + 1,
                )

            except httpx.ConnectError as exc:
                logger.debug(
                    "Webhook connect error to %s: %s (attempt %d/%d)",
                    url,
                    exc,
                    attempt + 1,
                    self._max_retries + 1,
                )
                if attempt == self._max_retries:
                    return DeliveryResult(
                        success=False,
                        attempts=attempt + 1,
                        error=f"Connection error: {exc}",
                    )

            except httpx.TimeoutException as exc:
                logger.debug(
                    "Webhook timeout to %s (attempt %d/%d)",
                    url,
                    attempt + 1,
                    self._max_retries + 1,
                )
                if attempt == self._max_retries:
                    return DeliveryResult(
                        success=False,
                        attempts=attempt + 1,
                        error=f"Timeout: {exc}",
                    )

            except Exception as exc:
                if attempt == self._max_retries:
                    return DeliveryResult(
                        success=False,
                        attempts=attempt + 1,
                        error=str(exc),
                    )

            # Exponential backoff before retry
            if attempt < self._max_retries:
                delay = self._backoff_base * (2**attempt)
                await asyncio.sleep(delay)

        return DeliveryResult(
            success=False,
            attempts=self._max_retries + 1,
            status_code=last_status,
            error=f"Max retries exhausted (last status: {last_status})"
            if last_status
            else "Max retries exhausted",
        )

    @staticmethod
    def _sign(payload: dict[str, Any], secret: str) -> str:
        """HMAC-SHA256 signature for webhook verification."""
        body = json.dumps(payload, sort_keys=True).encode()
        return hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
