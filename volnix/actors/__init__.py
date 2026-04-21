"""Actor personality system -- definitions, personalities, and generation.

Actors are the agents, humans, and systems that populate a Volnix world.
Each actor has an identity, role, permissions, and optionally a personality
or friction profile that governs how they behave during simulation.

Re-exports the primary public API surface::

    from volnix.actors import ActorDefinition, Personality, ActorRegistry
"""

from volnix.actors.behavioral_signature import BehavioralSignature
from volnix.actors.character import CharacterDefinition
from volnix.actors.character_loader import CharacterCatalogError, CharacterLoader
from volnix.actors.config import ActorConfig
from volnix.actors.definition import ActorDefinition
from volnix.actors.generator import ActorPersonalityGenerator
from volnix.actors.personality import AdversarialProfile, FrictionProfile, Personality
from volnix.actors.registry import ActorRegistry
from volnix.actors.replay import ReplayEntry, ReplayLog
from volnix.actors.simple_generator import SimpleActorGenerator
from volnix.actors.slot_binding import SlotBinding
from volnix.actors.state import ActorBehaviorTraits, ActorState, ScheduledAction, WaitingFor
from volnix.actors.trait_extractor import (
    TraitExtractorHookError,
    resolve_extractor_hook,
)

__all__ = [
    "ActorBehaviorTraits",
    "ActorConfig",
    "ActorDefinition",
    "ActorPersonalityGenerator",
    "ActorRegistry",
    "ActorState",
    "AdversarialProfile",
    # Phase 4C Step 11 / 12 — character catalog + behavioral signature.
    # Re-exported from the sub-package so ``from volnix.actors import
    # CharacterDefinition`` works (mirrors ``ActorDefinition`` and
    # closes the Step-11 audit M8 asymmetry).
    "BehavioralSignature",
    "CharacterCatalogError",
    "CharacterDefinition",
    "CharacterLoader",
    "FrictionProfile",
    "Personality",
    "ReplayEntry",
    "ReplayLog",
    "ScheduledAction",
    "SimpleActorGenerator",
    "SlotBinding",
    "TraitExtractorHookError",
    "WaitingFor",
    "resolve_extractor_hook",
]
