"""World responder engine implementation.

Generates simulated service responses across two fidelity tiers:
Tier 1 (verified packs) and Tier 2 (profiled LLM, including bootstrapped services).
"""

from __future__ import annotations

from typing import ClassVar

from terrarium.core import (
    ActionContext,
    BaseEngine,
    Event,
    PipelineStep,
    ResponseProposal,
    StepResult,
)


class WorldResponderEngine(BaseEngine):
    """Generates simulated service responses.

    Also acts as the ``responder`` pipeline step.
    """

    engine_name: ClassVar[str] = "responder"
    subscriptions: ClassVar[list[str]] = []
    dependencies: ClassVar[list[str]] = ["state"]

    # -- PipelineStep interface ------------------------------------------------

    @property
    def step_name(self) -> str:
        """Return the pipeline step name."""
        return "responder"

    async def execute(self, ctx: ActionContext) -> StepResult:
        """Execute the responder pipeline step."""
        ...

    # -- BaseEngine hook -------------------------------------------------------

    async def _handle_event(self, event: Event) -> None:
        """Handle an inbound event from the bus."""
        ...

    # -- Responder operations --------------------------------------------------

    async def generate_response(self, ctx: ActionContext) -> ResponseProposal:
        """Generate a response proposal for the action context."""
        ...
