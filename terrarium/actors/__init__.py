"""Actor personality system -- definitions, personalities, and generation.

Actors are the agents, humans, and systems that populate a Terrarium world.
Each actor has an identity, role, permissions, and optionally a personality
or friction profile that governs how they behave during simulation.

Re-exports the primary public API surface::

    from terrarium.actors import ActorDefinition, Personality, ActorRegistry
"""

from terrarium.actors.config import ActorConfig
from terrarium.actors.definition import ActorDefinition
from terrarium.actors.generator import ActorPersonalityGenerator
from terrarium.actors.personality import AdversarialProfile, FrictionProfile, Personality
from terrarium.actors.registry import ActorRegistry
from terrarium.actors.replay import ReplayEntry, ReplayLog
from terrarium.actors.simple_generator import SimpleActorGenerator
from terrarium.actors.slot_binding import SlotBinding
from terrarium.actors.state import ActorBehaviorTraits, ActorState, ScheduledAction, WaitingFor

__all__ = [
    "ActorBehaviorTraits",
    "ActorConfig",
    "ActorDefinition",
    "ActorPersonalityGenerator",
    "ActorState",
    "AdversarialProfile",
    "FrictionProfile",
    "Personality",
    "ActorRegistry",
    "ReplayEntry",
    "ReplayLog",
    "ScheduledAction",
    "SimpleActorGenerator",
    "SlotBinding",
    "WaitingFor",
]
