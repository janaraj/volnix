"""Webhook subscription registry — stores and matches registered webhooks."""

from __future__ import annotations

import fnmatch
import ipaddress
import logging
from datetime import UTC, datetime
from urllib.parse import urlparse
from uuid import uuid4

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

# C1 fix: blocked hostnames for SSRF prevention
_BLOCKED_HOSTS = frozenset(
    {
        "localhost",
        "metadata.google.internal",
        "metadata.internal",
    }
)


def _validate_url(url: str) -> None:
    """Validate webhook URL to prevent SSRF attacks.

    Blocks:
    - Non-http/https schemes (file://, gopher://, etc.)
    - Private/loopback IPs (127.x, 10.x, 172.16-31.x, 192.168.x)
    - Link-local IPs (169.254.x — cloud metadata endpoints)
    - Known metadata hostnames
    - .internal domains

    Raises:
        ValueError: If URL is unsafe.
    """
    if not url:
        raise ValueError("Webhook URL cannot be empty")

    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise ValueError(f"URL scheme must be http or https, got '{parsed.scheme}'")

    hostname = parsed.hostname or ""
    if not hostname:
        raise ValueError("URL must have a hostname")

    if hostname in _BLOCKED_HOSTS:
        raise ValueError(f"Blocked hostname: {hostname}")

    if hostname.endswith(".internal"):
        raise ValueError(f"Blocked .internal domain: {hostname}")

    # Check if hostname is an IP address
    try:
        ip = ipaddress.ip_address(hostname)
        if ip.is_private or ip.is_loopback or ip.is_link_local:
            raise ValueError(f"Blocked private/loopback/link-local IP: {ip}")
    except ValueError as exc:
        # Not an IP address — that's fine, it's a hostname
        if "Blocked" in str(exc):
            raise


class WebhookSubscription(BaseModel, frozen=True):
    """A registered webhook endpoint."""

    id: str = ""
    url: str = ""
    events: list[str] = Field(default_factory=list)
    service: str = ""
    secret: str = ""
    created_at: str = ""
    active: bool = True


class WebhookRegistry:
    """Stores and matches webhook subscriptions.

    Pattern matching uses ``fnmatch`` (glob-style):
    - ``"world.email_*"`` matches ``"world.email_send"``
    - ``"world.*"`` matches everything
    - ``"world.email_send"`` matches exactly
    """

    def __init__(self, max_registrations: int = 100) -> None:
        self._subscriptions: dict[str, WebhookSubscription] = {}
        self._max = max_registrations

    def register(
        self,
        url: str,
        events: list[str],
        service: str = "",
        secret: str = "",
    ) -> str:
        """Register a webhook. Returns subscription ID.

        Raises:
            ValueError: If URL is invalid/unsafe or max registrations reached.
        """
        _validate_url(url)  # C1 fix: SSRF prevention
        if len(self._subscriptions) >= self._max:
            raise ValueError(f"Maximum webhook registrations ({self._max}) reached")

        sub_id = f"wh_{uuid4().hex[:12]}"
        sub = WebhookSubscription(
            id=sub_id,
            url=url,
            events=events,
            service=service,
            secret=secret,
            created_at=datetime.now(UTC).isoformat(),
        )
        self._subscriptions[sub_id] = sub
        logger.info(
            "Registered webhook %s → %s (events=%s)",
            sub_id,
            url,
            events,
        )
        return sub_id

    def unregister(self, sub_id: str) -> bool:
        """Remove a webhook by ID. Returns True if found."""
        if sub_id in self._subscriptions:
            del self._subscriptions[sub_id]
            logger.info("Unregistered webhook %s", sub_id)
            return True
        return False

    def match(self, event_type: str, service_id: str = "") -> list[WebhookSubscription]:
        """Find all subscriptions matching an event.

        Matches against event patterns (fnmatch glob) and
        optional service filter.
        """
        matches: list[WebhookSubscription] = []
        for sub in self._subscriptions.values():
            if not sub.active:
                continue

            # Check service filter
            if sub.service and service_id and sub.service != service_id:
                continue

            # Check event patterns
            for pattern in sub.events:
                if fnmatch.fnmatch(event_type, pattern):
                    matches.append(sub)
                    break  # One match is enough per subscription

        return matches

    def list_all(self) -> list[WebhookSubscription]:
        """All active subscriptions."""
        return [s for s in self._subscriptions.values() if s.active]

    def count(self) -> int:
        """Number of active subscriptions (M2 fix: consistent with list_all)."""
        return sum(1 for s in self._subscriptions.values() if s.active)
