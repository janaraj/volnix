"""Slack service profile (Tier 2 -- profiled).

Extends the ``chat`` verified pack with Slack-specific response
schemas, behavioural annotations (e.g. Block Kit, threading, reactions),
and an LLM responder prompt that mimics the Slack Web API personality.
"""

from __future__ import annotations

from typing import ClassVar

from volnix.core.types import ToolName
from volnix.packs.base import ServiceProfile


class SlackProfile(ServiceProfile):
    """Profiled overlay for the Slack chat API.

    Extends the ``chat`` pack with Slack-specific behaviours.
    """

    profile_name: ClassVar[str] = "slack"
    extends_pack: ClassVar[str] = "chat"
    category: ClassVar[str] = "communication"
    fidelity_tier: ClassVar[int] = 2

    def get_additional_tools(self) -> list[dict]:
        """Return Slack-specific additional tools."""
        ...

    def get_additional_entities(self) -> dict:
        """Return Slack-specific entity schemas."""
        ...

    def get_behavioral_annotations(self) -> list[str]:
        """Return Slack-specific behavioural annotations."""
        ...

    def get_responder_prompt(self) -> str:
        """Return the Slack API responder system prompt."""
        ...

    def get_response_schema(self, action: ToolName) -> dict:
        """Return the Slack-specific response schema for an action."""
        ...
