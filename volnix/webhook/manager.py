"""Webhook manager — bus subscriber that delivers events to registered webhooks.

NOT an engine. Subscribes to the event bus wildcard and delivers
matching events via HTTP POST. Same subscription pattern as the
WebSocket streaming endpoint.

C2 fix: deliveries are fire-and-forget async tasks (non-blocking).
H3 fix: exception handling in delivery — one failure doesn't affect others.
H4 fix: only world.* events forwarded to webhooks (internal events filtered).
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any

from volnix.webhook.config import WebhookConfig
from volnix.webhook.delivery import WebhookDelivery
from volnix.webhook.payloads import format_payload
from volnix.webhook.registry import WebhookRegistry

logger = logging.getLogger(__name__)


class WebhookManager:
    """Bus subscriber that delivers matching events to registered webhooks."""

    def __init__(self, config: WebhookConfig) -> None:
        self._config = config
        self._registry = WebhookRegistry(
            max_registrations=config.max_registrations
        )
        self._delivery = WebhookDelivery(
            max_retries=config.max_retries,
            backoff_base=config.retry_backoff_base,
            timeout=config.delivery_timeout,
        )
        self._bus: Any = None
        self._stats = {
            "delivered": 0,
            "failed": 0,
            "skipped": 0,
            "errors": 0,
        }
        # C2 fix: semaphore limits concurrent deliveries
        self._delivery_semaphore = asyncio.Semaphore(10)

    async def start(self, bus: Any) -> None:
        """Subscribe to event bus wildcard."""
        if not self._config.enabled:
            logger.info("WebhookManager: disabled")
            return
        self._bus = bus
        await bus.subscribe("*", self._on_event)
        logger.info("WebhookManager: started, listening for events")

    async def stop(self) -> None:
        """Unsubscribe from event bus."""
        if self._bus:
            try:
                await self._bus.unsubscribe("*", self._on_event)
            except Exception:
                pass
            self._bus = None

    async def _on_event(self, event: Any) -> None:
        """Bus callback — match, format, deliver (non-blocking)."""
        event_type = str(getattr(event, "event_type", ""))

        # H4 fix: only forward world events (not internal/engine events)
        if not event_type.startswith("world."):
            return

        service_id = str(getattr(event, "service_id", ""))

        matches = self._registry.match(event_type, service_id)
        if not matches:
            self._stats["skipped"] += 1
            return

        # C2 fix: fire-and-forget — don't block the bus consumer
        for sub in matches:
            asyncio.create_task(
                self._deliver_one(sub, event, service_id)
            )

    async def _deliver_one(
        self, sub: Any, event: Any, service_id: str
    ) -> None:
        """Deliver one event to one webhook (async task).

        H3 fix: exception handling — one bad delivery doesn't
        affect others.
        """
        async with self._delivery_semaphore:
            try:
                service = sub.service or service_id
                payload = format_payload(event, service=service)
                result = await self._delivery.send(
                    sub.url, payload, secret=sub.secret
                )
                if result.success:
                    self._stats["delivered"] += 1
                    logger.debug(
                        "Webhook delivered to %s (%d attempts)",
                        sub.url,
                        result.attempts,
                    )
                else:
                    self._stats["failed"] += 1
                    logger.warning(
                        "Webhook delivery failed to %s: %s",
                        sub.url,
                        result.error,
                    )
            except Exception as exc:
                self._stats["errors"] += 1
                logger.warning(
                    "Webhook delivery error for %s: %s",
                    sub.url, exc,
                )

    # -- Public API (called by HTTP endpoints) ---------------------------------

    def register(
        self,
        url: str,
        events: list[str],
        service: str = "",
        secret: str = "",
    ) -> str:
        """Register a webhook subscription. Returns ID."""
        return self._registry.register(
            url=url, events=events, service=service, secret=secret
        )

    def unregister(self, sub_id: str) -> bool:
        """Remove a webhook by ID."""
        return self._registry.unregister(sub_id)

    def list_webhooks(self) -> list[dict[str, Any]]:
        """List all registered webhooks (without secrets)."""
        return [
            {
                "id": s.id,
                "url": s.url,
                "events": s.events,
                "service": s.service,
                "created_at": s.created_at,
                "active": s.active,
            }
            for s in self._registry.list_all()
        ]

    def get_stats(self) -> dict[str, Any]:
        """Delivery statistics."""
        return {
            **self._stats,
            "registered": self._registry.count(),
        }
