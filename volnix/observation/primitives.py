"""Domain-neutral observation primitives (PMF Plan Phase 4C Step 10).

Three pure functions on :class:`UnifiedTimeline`. No PMF-,
product-, or vertical-specific vocabulary — each primitive takes
caller-supplied extractor callables so the observer-domain stays
product-side.

- :func:`intent_behavior_gap` — where did declared intent diverge
  from observed behavior?
- :func:`variant_delta` — what's the metric delta between two runs?
- :func:`load_bearing_personas` — leave-one-out: whose absence
  would flip the verdict?

**Contracts each primitive expects of its callable arguments:**

- ``extractor`` callables MUST return ``None`` to signal "skip this
  row." Any non-``None`` value is compared — `0`, `""`, `False`,
  and empty collections are legitimate values (the ``is None``
  check, not truthiness).
- ``metric_fn`` MUST return a finite float. ``NaN`` / ``inf``
  propagate into ``VariantDeltaReport.delta`` where they break
  downstream comparisons silently; :func:`variant_delta` guards
  against this at the boundary.
- ``verdict_fn`` MUST be deterministic and side-effect-free —
  :func:`load_bearing_personas` calls it N+1 times for N personas.
  A stochastic verdict would produce false "load-bearing" signals
  purely from its own noise.
"""

from __future__ import annotations

import math
from collections.abc import Callable, Mapping
from typing import Any

from pydantic import BaseModel, ConfigDict

from volnix.observation.query import TimelineEvent, UnifiedTimeline

# Default tolerance for float-verdict equality in
# :func:`load_bearing_personas`. Caller-overridable via the
# ``equality_fn`` kwarg when different semantics apply.
_FLOAT_VERDICT_TOLERANCE: float = 1e-9


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

    **Falsy values are legitimate signals** (``0``, ``""``,
    ``False``, empty collections). Only ``None`` means "skip" —
    the ``is None`` check prevents accidental truthiness pruning.

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

    **Non-finite guard** (Step 10 audit M1): ``metric_fn`` is
    REQUIRED to return a finite float. ``NaN`` and ``inf`` raise
    :class:`ValueError` at the boundary so downstream
    comparisons can't propagate silently. A consumer whose
    reducer legitimately yields NaN for empty input should
    handle that case before calling this primitive.
    """
    m_a = float(metric_fn(timeline_a))
    m_b = float(metric_fn(timeline_b))
    if not math.isfinite(m_a):
        raise ValueError(
            f"variant_delta: metric_fn returned non-finite value "
            f"{m_a!r} for timeline_a. Guard your reducer against "
            f"empty-input or divide-by-zero before calling."
        )
    if not math.isfinite(m_b):
        raise ValueError(
            f"variant_delta: metric_fn returned non-finite value {m_b!r} for timeline_b."
        )
    return VariantDeltaReport(metric_a=m_a, metric_b=m_b, delta=m_b - m_a)


def load_bearing_personas(
    timelines_by_persona: Mapping[str, UnifiedTimeline],
    *,
    verdict_fn: Callable[[list[UnifiedTimeline]], Any],
    equality_fn: Callable[[Any, Any], bool] | None = None,
) -> list[PersonaContribution]:
    """Leave-one-out: for each persona, compute the verdict with
    and without their timeline. Identify personas whose removal
    would flip (or change) the verdict.

    **``verdict_fn`` MUST be deterministic and side-effect-free.**
    It is called ``len(timelines_by_persona) + 1`` times — once
    for the full set plus once per persona with that persona
    removed. A stochastic ``verdict_fn`` (randomness, LLM call,
    stateful accumulator) will produce false "load-bearing"
    signals from its own noise.

    **Float-verdict tolerance** (Step 10 audit M2): float verdict
    values default to epsilon-tolerance equality (``abs(a-b) <
    1e-9``) so floating-point rounding in the aggregator doesn't
    flag every persona as load-bearing. Caller overrides via
    ``equality_fn`` for domain-specific tolerance or non-numeric
    verdict types that need custom comparison.

    Args:
        timelines_by_persona: Mapping of persona id → their
            timeline. One entry per persona.
        verdict_fn: Aggregator over the list of timelines.
            Returns any comparable value (bool, float, str, etc.).
        equality_fn: Optional custom equality predicate. Default
            uses ``==`` for non-float types and epsilon-tolerance
            for floats.

    Returns:
        One ``PersonaContribution`` per persona. Personas whose
        ``verdict_without`` differs from ``verdict_with`` have
        ``is_load_bearing=True``.
    """
    cmp = equality_fn if equality_fn is not None else _default_equality
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
                is_load_bearing=not cmp(verdict_with, verdict_without),
            )
        )
    return results


def _default_equality(a: Any, b: Any) -> bool:
    """Tolerance-aware equality: epsilon-compare for floats,
    strict ``==`` for everything else. Catches the FP-rounding
    false-positive flagged in Step 10 audit M2 without forcing
    consumers to wrap their verdict_fn."""
    # bool is a subclass of int / float — don't treat as numeric.
    if (
        isinstance(a, float)
        and isinstance(b, float)
        and not isinstance(a, bool)
        and not isinstance(b, bool)
    ):
        return math.isclose(a, b, abs_tol=_FLOAT_VERDICT_TOLERANCE)
    return a == b
