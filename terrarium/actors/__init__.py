"""Actor personality system -- definitions, personalities, and generation.

Actors are the agents, humans, and systems that populate a Terrarium world.
Each actor has an identity, role, permissions, and optionally a personality
or adversarial profile that governs how they behave during simulation.

Re-exports the primary public API surface::

    from terrarium.actors import ActorDefinition, Personality, ActorRegistry
"""

from terrarium.actors.definition import ActorDefinition
from terrarium.actors.personality import AdversarialProfile, Personality
from terrarium.actors.registry import ActorRegistry
from terrarium.actors.generator import ActorGenerator

__all__ = [
    "ActorDefinition",
    "Personality",
    "AdversarialProfile",
    "ActorRegistry",
    "ActorGenerator",
]
