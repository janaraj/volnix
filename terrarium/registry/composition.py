"""Composition root for the Terrarium framework.

This is the **only** module that imports concrete engine classes.  All other
code depends on abstract protocols and the engine registry.
"""

from __future__ import annotations

from terrarium.registry.registry import EngineRegistry


def create_default_registry() -> EngineRegistry:
    """Create an :class:`EngineRegistry` pre-populated with default engines.

    This is the composition root -- the single place where concrete engine
    implementations are imported and instantiated.  All downstream code
    retrieves engines by name or protocol from the registry.

    Returns:
        A fully populated :class:`EngineRegistry` with the default engine set.
    """
    from terrarium.engines.adapter.engine import AgentAdapterEngine
    from terrarium.engines.animator.engine import WorldAnimatorEngine
    from terrarium.engines.budget.engine import BudgetEngine
    from terrarium.engines.feedback.engine import FeedbackEngine
    from terrarium.engines.permission.engine import PermissionEngine
    from terrarium.engines.policy.engine import PolicyEngine
    from terrarium.engines.reporter.engine import ReportGeneratorEngine
    from terrarium.engines.responder.engine import WorldResponderEngine
    from terrarium.engines.state.engine import StateEngine
    from terrarium.engines.world_compiler.engine import WorldCompilerEngine

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
    return registry
