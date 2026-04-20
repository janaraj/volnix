"""Composition root for the Volnix framework.

This is the **only** module that imports concrete engine classes.  All other
code depends on abstract protocols and the engine registry.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from volnix.registry.registry import EngineRegistry

if TYPE_CHECKING:
    from pathlib import Path

    from volnix.actors.cohort_manager import CohortManager
    from volnix.engines.agency.config import CohortConfig
    from volnix.engines.agency.npc_activator import NPCActivator
    from volnix.engines.memory.config import MemoryConfig
    from volnix.engines.memory.engine import MemoryEngine
    from volnix.llm.router import LLMRouter
    from volnix.persistence.manager import ConnectionManager


def create_default_registry() -> EngineRegistry:
    """Create an :class:`EngineRegistry` pre-populated with default engines.

    This is the composition root -- the single place where concrete engine
    implementations are imported and instantiated.  All downstream code
    retrieves engines by name or protocol from the registry.

    Returns:
        A fully populated :class:`EngineRegistry` with the default engine set.
    """
    from volnix.engines.adapter.engine import AgentAdapterEngine
    from volnix.engines.agency.engine import AgencyEngine
    from volnix.engines.animator.engine import WorldAnimatorEngine
    from volnix.engines.budget.engine import BudgetEngine
    from volnix.engines.feedback.engine import FeedbackEngine
    from volnix.engines.game.orchestrator import GameOrchestrator
    from volnix.engines.permission.engine import PermissionEngine
    from volnix.engines.policy.engine import PolicyEngine
    from volnix.engines.reporter.engine import ReportGeneratorEngine
    from volnix.engines.responder.engine import WorldResponderEngine
    from volnix.engines.state.engine import StateEngine
    from volnix.engines.world_compiler.engine import WorldCompilerEngine

    registry = EngineRegistry()
    registry.register(StateEngine())
    registry.register(PolicyEngine())
    registry.register(PermissionEngine())
    registry.register(BudgetEngine())
    registry.register(WorldResponderEngine())
    registry.register(AgentAdapterEngine())
    registry.register(WorldAnimatorEngine())
    registry.register(ReportGeneratorEngine())
    registry.register(FeedbackEngine())
    registry.register(WorldCompilerEngine())
    registry.register(AgencyEngine())
    # Event-driven game engine. Registered under ``"game"``; the legacy
    # round-based ``GameEngine`` was deleted in Cycle B.10.
    registry.register(GameOrchestrator())
    return registry


def build_npc_activator() -> NPCActivator:
    """Construct the Active-NPC activator with its real dependencies.

    Concrete-class imports (``NPCActivator``, ``NPCPromptBuilder``,
    ``ActivationProfileLoader``) are confined to this composition root
    per DESIGN_PRINCIPLES. App.py asks for the activator by calling
    this function at world-configure time; the returned object
    implements :class:`volnix.core.protocols.NPCActivatorProtocol`.

    Kept as a free function (not wired into ``EngineRegistry``)
    because the activator is not an engine in the BaseEngine sense —
    it has no event-bus lifecycle, no asyncio queue, and is lightweight
    enough to re-create per world configuration.
    """
    from volnix.actors.npc_profiles import ActivationProfileLoader
    from volnix.engines.agency.npc_activator import NPCActivator
    from volnix.engines.agency.npc_prompt_builder import NPCPromptBuilder

    return NPCActivator(
        prompt_builder=NPCPromptBuilder(),
        activation_profile_loader=ActivationProfileLoader(),
    )


def build_cohort_manager(
    cohort_config: CohortConfig,
    world_seed: int,
) -> CohortManager | None:
    """Construct the active-cohort manager when cycling is enabled.

    PMF Plan Phase 4A. Returns ``None`` when ``cohort_config.max_active``
    is ``None`` so callers can short-circuit the ``set_cohort_manager``
    handoff. Concrete-class imports (``CohortManager``) are confined
    here per DESIGN_PRINCIPLES.

    ``world_seed`` flows from ``WorldPlan.seed`` so cohort rotation
    determinism ties to the world, not a module-level default. No
    hardcoded seed anywhere in the 4A code path.
    """
    if cohort_config.max_active is None:
        return None
    from volnix.actors.cohort_manager import CohortManager

    return CohortManager(
        max_active=cohort_config.max_active,
        rotation_policy=cohort_config.rotation_policy,
        rotation_batch_size=cohort_config.rotation_batch_size,
        promote_budget_per_tick=cohort_config.promote_budget_per_tick,
        queue_max_per_npc=cohort_config.queue_max_per_npc,
        inactive_event_policies=cohort_config.inactive_event_policies,  # type: ignore[arg-type]
        seed=world_seed,
    )


async def build_memory_engine(
    memory_config: MemoryConfig,
    world_seed: int,
    llm_router: LLMRouter,
    connection_manager: ConnectionManager,
    *,
    fixtures_path: Path | None = None,
) -> MemoryEngine | None:
    """Construct the 11th engine (MemoryEngine) from config.

    PMF Plan Phase 4B Step 10. Returns ``None`` when
    ``memory_config.enabled`` is false so callers short-circuit the
    wiring (matches the ``build_cohort_manager`` pattern). Concrete-class
    imports (``MemoryEngine``, ``Consolidator``, ``FTS5Embedder``,
    ``SQLiteMemoryStore``, ``Recall``) are confined to this function
    body per DESIGN_PRINCIPLES.

    Args:
        memory_config: The validated ``MemoryConfig``.
        world_seed: From ``WorldPlan.seed``. Ties memory determinism
            to the world, not a module-level default.
        llm_router: Router used by the Consolidator for distillation.
            Must be constructed before this builder fires — app.py
            initialises the router at step 4 of ``start()``, before
            ``configure_agency`` is called.
        connection_manager: Returns the memory DB via
            ``get_connection(cfg.storage_db_name)`` (G5).
        fixtures_path: Unused in 4B (kept in signature so Step 11 /
            Phase 4C can wire pack fixtures without signature churn).

    Raises:
        NotImplementedError: when the config asks for a dense embedder
            (sentence-transformers / openai). Those land in Step 13;
            4B ships FTS5 only. Raising loud beats a silent FTS5
            fallback that the config validator already accepted.
    """
    if not memory_config.enabled:
        return None

    from volnix.engines.memory.consolidation import Consolidator
    from volnix.engines.memory.embedder import FTS5Embedder
    from volnix.engines.memory.engine import MemoryEngine
    from volnix.engines.memory.recall import Recall
    from volnix.engines.memory.store import SQLiteMemoryStore

    scheme, _, _model = memory_config.embedder.partition(":")
    if scheme == "fts5":
        embedder = FTS5Embedder()
    elif scheme == "sentence-transformers":
        # PMF 4B Step 13 — opt-in dense embedder via
        # ``volnix[embeddings]``. ImportError is re-raised from
        # ``SentenceTransformersEmbedder.__init__`` with an install
        # hint when the extras aren't present.
        from volnix.engines.memory.embedder import SentenceTransformersEmbedder

        model_name = _model or "all-MiniLM-L6-v2"
        embedder = SentenceTransformersEmbedder(model_name=model_name)
    else:
        # OpenAI intentionally deferred — no caller asked for it yet
        # (D13-1). Keep this branch loud: silent fallback to FTS5
        # would diverge from what the user configured.
        raise NotImplementedError(
            f"MemoryEngine embedder {scheme!r} is not shipped. Phase 4B "
            f"supports `fts5` (default) and `sentence-transformers` (via "
            f"`volnix[embeddings]`). OpenAI embeddings are a future-phase "
            f"concern. Configured: {memory_config.embedder!r}."
        )

    db = await connection_manager.get_connection(memory_config.storage_db_name)
    store = SQLiteMemoryStore(
        db,
        fts_tokenizer=memory_config.fts_tokenizer,
        embedding_cache_enabled=memory_config.embedder_cache_enabled,
    )

    consolidator = Consolidator(
        store=store,
        llm_router=llm_router,
        use_case=memory_config.distillation_llm_use_case,
        episodic_window=memory_config.consolidation_episodic_window,
        prune_after_consolidation=True,
        distillation_enabled=memory_config.distillation_enabled,
    )

    recall = Recall(store=store, embedder=embedder)

    return MemoryEngine(
        memory_config=memory_config,
        store=store,
        embedder=embedder,
        recall=recall,
        consolidator=consolidator,
        seed=world_seed,
    )
