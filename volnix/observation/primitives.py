"""Domain-neutral observation primitives (PMF Plan Phase 4C Step 10).

Three pure functions on :class:`UnifiedTimeline`. No PMF-,
Rehearse-, or vertical-specific vocabulary — each primitive takes
caller-supplied extractor callables so the observer-domain stays
product-side.

- :func:`intent_behavior_gap` — where did declared intent diverge
  from observed behavior?
- :func:`variant_delta` — what's the metric delta between two runs?
- :func:`load_bearing_personas` — leave-one-out: whose absence
  would flip the verdict?
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any

from pydantic import BaseModel, ConfigDict

from volnix.observation.query import TimelineEvent, UnifiedTimeline

# ---------------------------------------------------------------------------
# Result value objects
# ---------------------------------------------------------------------------


class IntentBehaviorGap(BaseModel):
    """One location on a timeline where intent and behavior diverge."""

    model_config = ConfigDict(frozen=True)

    tick: int
    intent: Any
    behavior: Any
    source_row_index: int
    """Index into the input timeline's ``events`` list — lets
    consumers pull the originating ``TimelineEvent`` for context."""


class VariantDeltaReport(BaseModel):
    """Scalar delta of a caller-supplied metric across two timelines."""

    model_config = ConfigDict(frozen=True)

    metric_a: float
    metric_b: float
    delta: float
    """``metric_b - metric_a``. Positive = B scored higher."""


class PersonaContribution(BaseModel):
    """One persona's influence on the aggregate verdict. Emitted
    by :func:`load_bearing_personas` when removing that persona's
    timeline would flip the aggregate."""

    model_config = ConfigDict(frozen=True)

    persona: str
    verdict_with: Any
    verdict_without: Any
    is_load_bearing: bool


# ---------------------------------------------------------------------------
# Primitives
# ---------------------------------------------------------------------------


def intent_behavior_gap(
    timeline: UnifiedTimeline,
    *,
    intent_extractor: Callable[[TimelineEvent], Any],
    behavior_extractor: Callable[[TimelineEvent], Any],
) -> list[IntentBehaviorGap]:
    """Scan the timeline for rows where the declared intent
    differs from the observed behavior.

    Both extractors receive the same ``TimelineEvent`` and return
    either the extracted value or ``None`` (skip row). A gap is
    reported when BOTH extractors return a non-``None`` value and
    those values are not equal.

    Pure — no side effects, no state.
    """
    gaps: list[IntentBehaviorGap] = []
    for idx, row in enumerate(timeline.events):
        intent = intent_extractor(row)
        behavior = behavior_extractor(row)
        if intent is None or behavior is None:
            continue
        if intent == behavior:
            continue
        gaps.append(
            IntentBehaviorGap(
                tick=row.tick,
                intent=intent,
                behavior=behavior,
                source_row_index=idx,
            )
        )
    return gaps


def variant_delta(
    timeline_a: UnifiedTimeline,
    timeline_b: UnifiedTimeline,
    *,
    metric_fn: Callable[[UnifiedTimeline], float],
) -> VariantDeltaReport:
    """Compute ``metric_fn(b) - metric_fn(a)`` and return the
    triple. Caller supplies any reducer (count, mean, sum, etc.)
    via ``metric_fn``.
    """
    m_a = float(metric_fn(timeline_a))
    m_b = float(metric_fn(timeline_b))
    return VariantDeltaReport(metric_a=m_a, metric_b=m_b, delta=m_b - m_a)


def load_bearing_personas(
    timelines_by_persona: Mapping[str, UnifiedTimeline],
    *,
    verdict_fn: Callable[[list[UnifiedTimeline]], Any],
) -> list[PersonaContribution]:
    """Leave-one-out: for each persona, compute the verdict with
    and without their timeline. Identify personas whose removal
    would flip (or change) the verdict.

    Args:
        timelines_by_persona: Mapping of persona id → their
            timeline. One entry per persona.
        verdict_fn: Aggregator over the list of timelines.
            Returns any comparable value (bool, float, str, etc.).

    Returns:
        One ``PersonaContribution`` per persona. Personas whose
        ``verdict_without`` differs from ``verdict_with`` have
        ``is_load_bearing=True``.
    """
    all_personas = list(timelines_by_persona.keys())
    all_timelines = list(timelines_by_persona.values())
    verdict_with = verdict_fn(all_timelines)

    results: list[PersonaContribution] = []
    for i, persona in enumerate(all_personas):
        without = [t for j, t in enumerate(all_timelines) if j != i]
        verdict_without = verdict_fn(without)
        results.append(
            PersonaContribution(
                persona=persona,
                verdict_with=verdict_with,
                verdict_without=verdict_without,
                is_load_bearing=(verdict_with != verdict_without),
            )
        )
    return results
