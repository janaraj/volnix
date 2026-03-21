"""Organic event generator -- LLM-driven autonomous world activity."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from terrarium.core import StateEngineProtocol
from terrarium.engines.animator.config import AnimatorConfig
from terrarium.llm.router import LLMRouter


class OrganicGenerator:
    """Generates organic (non-scheduled) world events using an LLM."""

    def __init__(
        self,
        llm_router: LLMRouter,
        state: StateEngineProtocol,
        config: AnimatorConfig,
        conditions: Any = None,
    ) -> None:
        self._llm_router = llm_router
        self._state = state
        self._config = config
        self._conditions = conditions

    async def generate(
        self, world_time: datetime, creativity_remaining: int
    ) -> list[dict[str, Any]]:
        """Generate organic events within the remaining creativity budget."""
        ...

    def _should_generate(self, world_state: dict[str, Any], intensity: str) -> bool:
        """Decide whether to generate an organic event given current state."""
        ...

    def _apply_condition_probabilities(self, event_type: str, conditions: Any) -> bool:
        """Apply condition probabilities to decide if an organic event occurs.

        E.g., if injection_content is 5%, 5% of generated messages contain manipulation.
        """
        ...
