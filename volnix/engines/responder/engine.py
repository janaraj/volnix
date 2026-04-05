"""World responder engine implementation.

Generates simulated service responses across two fidelity tiers:
Tier 1 (verified packs) and Tier 2 (profiled LLM, including bootstrapped services).
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, ClassVar

from volnix.core import (
    ActionContext,
    BaseEngine,
    Event,
    ResponseProposal,
    StepResult,
    StepVerdict,
)
from volnix.packs.profile_schema import ServiceProfileData

logger = logging.getLogger(__name__)


class WorldResponderEngine(BaseEngine):
    """Generates simulated service responses.

    Dispatch order:
    1. Tier 1 pack (verified, deterministic)
    2. Tier 2 profile (LLM-constrained by profile)
    3. Error: no handler

    Also acts as the ``responder`` pipeline step.
    """

    engine_name: ClassVar[str] = "responder"
    subscriptions: ClassVar[list[str]] = []
    dependencies: ClassVar[list[str]] = ["state"]

    # -- BaseEngine hooks ------------------------------------------------------

    async def _on_initialize(self) -> None:
        """Set up pack registry, runtime, Tier1 dispatcher, and Tier2 generator."""
        from volnix.engines.responder.tier1 import Tier1Dispatcher
        from volnix.engines.responder.tier2 import Tier2Generator
        from volnix.packs.profile_loader import ProfileLoader
        from volnix.packs.profile_registry import ProfileRegistry
        from volnix.packs.registry import PackRegistry
        from volnix.packs.runtime import PackRuntime

        # Tier 1: Verified packs
        self._pack_registry = PackRegistry()
        verified_dir = self._config.get("verified_packs_dir")
        if verified_dir:
            self._pack_registry.discover(verified_dir)
        else:
            pack_base = Path(__file__).resolve().parents[2] / "packs" / "verified"
            if pack_base.is_dir():
                self._pack_registry.discover(str(pack_base))

        self._pack_runtime = PackRuntime(self._pack_registry)
        self._tier1 = Tier1Dispatcher(self._pack_runtime)

        # Tier 2: Profile-based services
        # Prefer profiles_dir from config, fall back to default
        configured_profiles_dir = self._config.get("profiles_dir")
        if configured_profiles_dir:
            profile_base = Path(configured_profiles_dir)
        else:
            profile_base = Path(__file__).resolve().parents[2] / "packs" / "profiles"
        self._profile_loader = ProfileLoader(profile_base)
        self._profile_registry = ProfileRegistry()

        # Discover and register all profiles
        for profile in self._profile_loader.list_profiles():
            self._profile_registry.register(profile)

        # Tier 2 generator -- created lazily via _get_tier2() because the
        # LLM router is injected into _config AFTER _on_initialize runs.
        # See _get_tier2() for the actual creation.
        self._tier2: Any = None

    @property
    def pack_registry(self) -> Any:
        """Public accessor for the pack registry."""
        return self._pack_registry

    @property
    def profile_registry(self) -> Any:
        """Public accessor for the profile registry."""
        return self._profile_registry

    @property
    def profile_loader(self) -> Any:
        """Public accessor for the profile loader."""
        return self._profile_loader

    # -- PipelineStep interface ------------------------------------------------

    @property
    def step_name(self) -> str:
        """Return the pipeline step name."""
        return "responder"

    def _get_tier2(self) -> Any:
        """Lazily create the Tier2Generator on first use.

        The LLM router is injected into ``_config["_llm_router"]`` by
        ``app._inject_cross_engine_deps()``, which runs AFTER
        ``_on_initialize()``.  This method creates the generator the
        first time it is needed, guaranteeing the router is available.
        """
        if self._tier2 is not None:
            return self._tier2
        llm_router = self._config.get("_llm_router")
        if llm_router is None:
            return None
        from volnix.engines.responder.tier2 import Tier2Generator

        self._tier2 = Tier2Generator(llm_router=llm_router, seed=42)
        return self._tier2

    async def execute(self, ctx: ActionContext) -> StepResult:
        """Execute the responder pipeline step.

        Dispatch order:
        1. Tier 1 pack (verified, deterministic)
        2. Tier 2 profile (LLM-constrained by profile)
        3. Error: no handler
        """
        # Tier 1: check pack
        if self._tier1.has_pack_for_tool(ctx.action):
            state = await self._build_state_for_pack(ctx)
            proposal = await self._tier1.dispatch(ctx, state=state)
            ctx.response_proposal = proposal
            return StepResult(
                step_name="responder",
                verdict=StepVerdict.ALLOW,
                metadata={
                    "fidelity_tier": proposal.fidelity.tier if proposal.fidelity else None,
                },
            )

        # Tier 2: check profile registry
        profile = self._find_profile_for_action(ctx.action)
        if profile is not None:
            tier2 = self._get_tier2()
            if tier2 is not None:
                state = await self._build_state_for_profile(ctx, profile)
                proposal = await tier2.generate(ctx, profile, state)
                ctx.response_proposal = proposal
                return StepResult(
                    step_name="responder",
                    verdict=StepVerdict.ALLOW,
                    metadata={
                        "fidelity_tier": 2,
                        "profile": profile.profile_name,
                    },
                )
            # Profile found but no LLM router available
            return StepResult(
                step_name="responder",
                verdict=StepVerdict.ERROR,
                message=(
                    f"Profile found for '{ctx.action}' but Tier 2 generator "
                    f"unavailable (no LLM router)"
                ),
            )

        # No handler
        return StepResult(
            step_name="responder",
            verdict=StepVerdict.ERROR,
            message=f"No pack or profile found for action '{ctx.action}'",
        )

    # -- BaseEngine hook -------------------------------------------------------

    async def _handle_event(self, event: Event) -> None:
        """Handle an inbound event from the bus."""
        logger.debug("Responder received event: %s", event.event_type)

    # -- Internal helpers ------------------------------------------------------

    def _find_profile_for_action(self, action: str) -> ServiceProfileData | None:
        """Find a profile that provides the given action."""
        return self._profile_registry.get_profile_for_action(action)

    @staticmethod
    def _pluralize(name: str) -> str:
        """Simple English pluralization for entity type names."""
        if name.endswith(("s", "x", "ch", "sh")):
            return f"{name}es"
        return f"{name}s"

    async def _query_with_visibility(
        self,
        state_engine: Any,
        permission_engine: Any,
        actor_id: Any,
        entity_type: str,
    ) -> list[dict[str, Any]]:
        """Query entities filtered by actor visibility.

        If no visibility rules exist → return ALL (backward compat).
        If rules exist → return only visible entities.
        """
        if permission_engine is None:
            return await state_engine.query_entities(entity_type)

        has_rules = await permission_engine.has_visibility_rules(actor_id, entity_type)
        if not has_rules:
            return await state_engine.query_entities(entity_type)

        visible_ids = await permission_engine.get_visible_entities(actor_id, entity_type)
        if not visible_ids:
            return await state_engine.query_entities(entity_type)

        all_entities = await state_engine.query_entities(entity_type)
        visible_set = {str(eid) for eid in visible_ids}
        return [e for e in all_entities if e.get("id", "") in visible_set]

    async def _build_state_for_pack(self, ctx: ActionContext) -> dict:
        """Fetch relevant entity state from StateEngine for the pack.

        Uses visibility scoping when visibility rules exist for the actor.
        Falls back to returning all entities when no rules are defined
        (backward compatible).
        """
        state_engine = self._dependencies.get("state")
        if state_engine is None:
            return {}

        permission_engine = self._dependencies.get("permission")
        pack = self._pack_registry.get_pack_for_tool(ctx.action)
        entity_types = list(pack.get_entity_schemas().keys())

        result = {}
        for etype in entity_types:
            key = self._pluralize(etype)
            try:
                entities = await self._query_with_visibility(
                    state_engine, permission_engine, ctx.actor_id, etype,
                )
                result[key] = entities
            except Exception as exc:
                logger.warning("Failed to query entities of type '%s': %s", etype, exc)
                result[key] = []
        return result

    async def _build_state_for_profile(
        self, ctx: ActionContext, profile: ServiceProfileData
    ) -> dict[str, Any]:
        """Fetch relevant entity state from StateEngine for a profiled service.

        Uses visibility scoping when visibility rules exist for the actor.
        """
        state_engine = self._dependencies.get("state")
        if state_engine is None:
            return {}

        permission_engine = self._dependencies.get("permission")
        result: dict[str, Any] = {}
        for entity_def in profile.entities:
            key = self._pluralize(entity_def.name)
            try:
                entities = await self._query_with_visibility(
                    state_engine, permission_engine, ctx.actor_id, entity_def.name,
                )
                result[key] = entities
            except Exception as exc:
                logger.warning(
                    "Failed to query entities of type '%s' for profile '%s': %s",
                    entity_def.name,
                    profile.profile_name,
                    exc,
                )
                result[key] = []
        return result

    # -- Responder operations --------------------------------------------------

    async def generate_response(self, ctx: ActionContext) -> ResponseProposal:
        """Stub -- Phase E implementation."""
        ...
