"""Tier 2 generator -- profiled LLM responses."""

from __future__ import annotations

from typing import Any

from terrarium.core import ActionContext, ResponseProposal, StateEngineProtocol
from terrarium.llm.router import LLMRouter


class Tier2Generator:
    """Generates responses using LLM guided by curated service profiles."""

    def __init__(
        self, llm_router: LLMRouter, state: StateEngineProtocol
    ) -> None:
        self._llm_router = llm_router
        self._state = state

    async def generate(
        self, ctx: ActionContext, profile: Any
    ) -> ResponseProposal:
        """Generate a profiled LLM response.

        Args:
            ctx: The action context.
            profile: The curated service profile (ServiceProfile).

        Returns:
            A response proposal.
        """
        ...
