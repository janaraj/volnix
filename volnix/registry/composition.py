"""Composition root for the Volnix framework.

This is the **only** module that imports concrete engine classes.  All other
code depends on abstract protocols and the engine registry.
"""

from __future__ import annotations

from volnix.registry.registry import EngineRegistry


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
    from volnix.engines.game.engine import GameEngine
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
    # Both game implementations coexist during the Cycle B migration:
    # - GameEngine (key ``"game"``) services legacy round-based blueprints
    # - GameOrchestrator (key ``"game_orchestrator"``) services event-driven
    #   blueprints via the Cycle B.5 architecture
    # Cycle B.10 deletes GameEngine and renames the orchestrator to ``"game"``.
    registry.register(GameEngine())
    registry.register(GameOrchestrator())
    return registry
