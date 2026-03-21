"""Stripe service profile (Tier 2 -- profiled).

Extends the ``payments`` verified pack with Stripe-specific response
schemas, behavioural annotations (e.g. idempotency keys, Stripe error
codes), and an LLM responder prompt that mimics the Stripe API
personality.
"""

from __future__ import annotations

from typing import ClassVar

from terrarium.core.types import ToolName
from terrarium.packs.base import ServiceProfile


class StripeProfile(ServiceProfile):
    """Profiled overlay for the Stripe payment API.

    Extends the ``payments`` pack with Stripe-specific behaviours.
    """

    profile_name: ClassVar[str] = "stripe"
    extends_pack: ClassVar[str] = "payments"
    category: ClassVar[str] = "money_transactions"
    fidelity_tier: ClassVar[int] = 2

    def get_additional_tools(self) -> list[dict]:
        """Return Stripe-specific additional tools."""
        ...

    def get_additional_entities(self) -> dict:
        """Return Stripe-specific entity schemas."""
        ...

    def get_behavioral_annotations(self) -> list[str]:
        """Return Stripe-specific behavioural annotations."""
        ...

    def get_responder_prompt(self) -> str:
        """Return the Stripe API responder system prompt."""
        ...

    def get_response_schema(self, action: ToolName) -> dict:
        """Return the Stripe-specific response schema for an action."""
        ...
