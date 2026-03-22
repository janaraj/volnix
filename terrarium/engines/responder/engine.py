"""World responder engine implementation.

Generates simulated service responses across two fidelity tiers:
Tier 1 (verified packs) and Tier 2 (profiled LLM, including bootstrapped services).
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import ClassVar

from terrarium.core import (
    ActionContext,
    BaseEngine,
    Event,
    PipelineStep,
    ResponseProposal,
    StepResult,
    StepVerdict,
)

logger = logging.getLogger(__name__)


class WorldResponderEngine(BaseEngine):
    """Generates simulated service responses.

    Also acts as the ``responder`` pipeline step.
    """

    engine_name: ClassVar[str] = "responder"
    subscriptions: ClassVar[list[str]] = []
    dependencies: ClassVar[list[str]] = ["state"]

    # -- BaseEngine hooks ------------------------------------------------------

    async def _on_initialize(self) -> None:
        """Set up pack registry, runtime, and Tier1 dispatcher."""
        from terrarium.packs.registry import PackRegistry
        from terrarium.packs.runtime import PackRuntime
        from terrarium.engines.responder.tier1 import Tier1Dispatcher

        self._pack_registry = PackRegistry()
        # Discover packs from the verified directory
        verified_dir = self._config.get("verified_packs_dir")
        if verified_dir:
            self._pack_registry.discover(verified_dir)
        else:
            # Default: discover from package path
            pack_base = Path(__file__).resolve().parents[2] / "packs" / "verified"
            if pack_base.is_dir():
                self._pack_registry.discover(str(pack_base))

        self._pack_runtime = PackRuntime(self._pack_registry)
        self._tier1 = Tier1Dispatcher(self._pack_runtime)

    # -- PipelineStep interface ------------------------------------------------

    @property
    def step_name(self) -> str:
        """Return the pipeline step name."""
        return "responder"

    async def execute(self, ctx: ActionContext) -> StepResult:
        """Execute the responder pipeline step.

        Checks Tier 1 pack availability, builds world state from StateEngine,
        dispatches to pack via Tier1Dispatcher, and sets ctx.response_proposal.
        """
        # Check if we have a Tier 1 pack for this action
        if not self._tier1.has_pack_for_tool(ctx.action):
            return StepResult(
                step_name="responder",
                verdict=StepVerdict.ERROR,
                message=f"No pack found for action '{ctx.action}'",
            )

        # Build world state for the pack
        state = await self._build_state_for_pack(ctx)

        # Dispatch to Tier 1 pack
        proposal = await self._tier1.dispatch(ctx, state=state)

        # Set on context for downstream steps (validation, commit)
        ctx.response_proposal = proposal

        return StepResult(
            step_name="responder",
            verdict=StepVerdict.ALLOW,
            metadata={"fidelity_tier": proposal.fidelity.tier if proposal.fidelity else None},
        )

    # -- BaseEngine hook -------------------------------------------------------

    async def _handle_event(self, event: Event) -> None:
        """Handle an inbound event from the bus."""
        logger.debug("Responder received event: %s", event.event_type)

    # -- Internal helpers ------------------------------------------------------

    @staticmethod
    def _pluralize(name: str) -> str:
        """Simple English pluralization for entity type names."""
        if name.endswith(("s", "x", "ch", "sh")):
            return f"{name}es"
        return f"{name}s"

    async def _build_state_for_pack(self, ctx: ActionContext) -> dict:
        """Fetch relevant entity state from StateEngine for the pack.

        Note: Currently fetches ALL entities per type. For large worlds,
        this should be optimized to fetch only entities relevant to the
        action (e.g., by actor, by target_entity). Phase D+ optimization.
        """
        state_engine = self._dependencies.get("state")
        if state_engine is None:
            return {}

        # Query entities of all types the pack manages
        pack = self._pack_registry.get_pack_for_tool(ctx.action)
        entity_types = list(pack.get_entity_schemas().keys())

        result = {}
        for etype in entity_types:
            key = self._pluralize(etype)
            try:
                entities = await state_engine.query_entities(etype)
                result[key] = entities
            except Exception as exc:
                logger.warning("Failed to query entities of type '%s': %s", etype, exc)
                result[key] = []
        return result

    # -- Responder operations --------------------------------------------------

    async def generate_response(self, ctx: ActionContext) -> ResponseProposal:
        """Stub -- Phase E implementation."""
        ...
