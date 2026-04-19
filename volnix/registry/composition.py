"""Composition root for the Volnix framework.

This is the **only** module that imports concrete engine classes.  All other
code depends on abstract protocols and the engine registry.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from volnix.registry.registry import EngineRegistry

if TYPE_CHECKING:
    from volnix.engines.agency.npc_activator import NPCActivator


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
