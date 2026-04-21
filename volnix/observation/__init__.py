"""Observation API — PMF Plan Phase 4C Step 10.

Domain-neutral observation primitives for products that embed
Volnix. ``ObservationQuery`` merges events, utterances, trajectory
points, and ledger entries into a ``UnifiedTimeline`` that the three
caller-extractor-driven primitives
(:func:`intent_behavior_gap`, :func:`variant_delta`,
:func:`load_bearing_personas`) operate on.

No PMF- or vertical-specific vocabulary — products layer their own
signal primitives on top (e.g. Rehearse's ``rehearse.signals.pmf``).
"""

from volnix.observation.primitives import (
    IntentBehaviorGap,
    PersonaContribution,
    VariantDeltaReport,
    intent_behavior_gap,
    load_bearing_personas,
    variant_delta,
)
from volnix.observation.query import (
    ObservationQuery,
    TimelineEvent,
    TimelineSource,
    UnifiedTimeline,
)

__all__ = [
    "ObservationQuery",
    "UnifiedTimeline",
    "TimelineEvent",
    "TimelineSource",
    "IntentBehaviorGap",
    "PersonaContribution",
    "VariantDeltaReport",
    "intent_behavior_gap",
    "load_bearing_personas",
    "variant_delta",
]
