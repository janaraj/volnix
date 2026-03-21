"""Gmail service profile (Tier 2 -- profiled).

Extends the ``email`` verified pack with Gmail-specific response
schemas, behavioural annotations (e.g. label system, threading model),
and an LLM responder prompt that mimics the Gmail API personality.
"""

from __future__ import annotations

from typing import ClassVar

from terrarium.core.types import ToolName
from terrarium.packs.base import ServiceProfile


class GmailProfile(ServiceProfile):
    """Profiled overlay for the Gmail email API.

    Extends the ``email`` pack with Gmail-specific behaviours.
    """

    profile_name: ClassVar[str] = "gmail"
    extends_pack: ClassVar[str] = "email"
    category: ClassVar[str] = "communication"
    fidelity_tier: ClassVar[int] = 2

    def get_additional_tools(self) -> list[dict]:
        """Return Gmail-specific additional tools."""
        ...

    def get_additional_entities(self) -> dict:
        """Return Gmail-specific entity schemas."""
        ...

    def get_behavioral_annotations(self) -> list[str]:
        """Return Gmail-specific behavioural annotations."""
        ...

    def get_responder_prompt(self) -> str:
        """Return the Gmail API responder system prompt."""
        ...

    def get_response_schema(self, action: ToolName) -> dict:
        """Return the Gmail-specific response schema for an action."""
        ...
