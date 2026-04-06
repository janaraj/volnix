"""Organic event generator -- LLM-driven autonomous world activity.

REUSES: AnimatorContext (which reuses WorldGenerationContext pattern)
REUSES: PromptTemplate framework -- ANIMATOR_EVENT template
NO DUPLICATION of context assembly.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Any

from volnix.engines.animator.config import AnimatorConfig
from volnix.engines.animator.context import AnimatorContext
from volnix.engines.world_compiler.prompt_templates import ANIMATOR_EVENT
from volnix.llm.router import LLMRouter

logger = logging.getLogger(__name__)


class OrganicGenerator:
    """LLM-driven organic event generation.

    REUSES: AnimatorContext (which reuses WorldGenerationContext pattern)
    REUSES: PromptTemplate framework -- ANIMATOR_EVENT template
    NO DUPLICATION of context assembly.
    """

    def __init__(
        self,
        llm_router: LLMRouter,
        context: AnimatorContext,
        config: AnimatorConfig,
    ) -> None:
        self._router = llm_router
        self._context = context  # AnimatorContext -- NOT rebuilt each call
        self._config = config

    async def generate(
        self,
        world_time: datetime,
        budget: int,
        recent_actions: list[dict[str, Any]] | None = None,
        recent_organic: list[dict[str, str]] | None = None,
    ) -> list[dict[str, Any]]:
        """Generate organic events within the remaining creativity budget.

        Args:
            world_time: Current simulation time.
            budget: Maximum number of events to generate.
            recent_actions: Optional recent agent actions for reactive mode.
            recent_organic: Recent organic events from previous ticks (for variety).

        Returns:
            List of event definition dicts, capped at budget.
        """
        if budget <= 0:
            return []

        # Get template variables from AnimatorContext (NOT rebuilding)
        base_vars = self._context.for_organic_generation(recent_actions)

        # Build recent organic history for LLM context
        organic_history = ""
        if recent_organic:
            lines = [f"- {e['actor']}: {e['action']} ({e['service']})" for e in recent_organic]
            organic_history = "Recent organic events (vary the actor and action):\n" + "\n".join(lines)

        try:
            response = await ANIMATOR_EVENT.execute(
                self._router,
                **base_vars,
                creativity=self._config.creativity,
                event_frequency=self._config.event_frequency,
                escalation_on_inaction=str(self._config.escalation_on_inaction),
                recent_actions=json.dumps(recent_actions or [], default=str)[:1000],
                recent_organic=organic_history,
                budget=str(budget),
            )

            parsed = ANIMATOR_EVENT.parse_json_response(response)
            events: list[dict[str, Any]] = parsed if isinstance(parsed, list) else [parsed]
            return events[:budget]

        except Exception:
            logger.exception("Organic event generation failed")
            return []
