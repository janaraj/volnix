"""State machine definitions for chat entities.

Channels use a boolean ``is_archived`` flag rather than status-based
transitions.  Messages are immutable after creation.  Consequently
there are no status-driven state machines for this pack.
"""

from __future__ import annotations

CHANNEL_TRANSITIONS: dict[str, list[str]] = {}
"""No status-based transitions -- channels use is_archived boolean."""

MESSAGE_TRANSITIONS: dict[str, list[str]] = {}
"""Messages are immutable after creation -- no transitions."""
