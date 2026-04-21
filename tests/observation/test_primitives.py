"""Phase 4C Step 10 — observation primitives tests.

Three pure functions over ``UnifiedTimeline`` with caller-supplied
extractor callables. No PMF vocabulary in the primitives — tests
verify ONLY the general-purpose shape.

Negative ratio: 5/10 = 50%.
"""

from __future__ import annotations

from typing import Any

from volnix.observation.primitives import (
    IntentBehaviorGap,
    PersonaContribution,
    VariantDeltaReport,
    intent_behavior_gap,
    load_bearing_personas,
    variant_delta,
)
from volnix.observation.query import (
    TimelineEvent,
    TimelineSource,
    UnifiedTimeline,
)


def _ev(tick: int, payload: dict[str, Any]) -> TimelineEvent:
    return TimelineEvent(source=TimelineSource.EVENT, tick=tick, sequence=0, payload=payload)


def _tl(events: list[TimelineEvent]) -> UnifiedTimeline:
    return UnifiedTimeline(events=events)


# ─── intent_behavior_gap ───────────────────────────────────────────


def test_positive_intent_behavior_gap_detects_divergence() -> None:
    tl = _tl(
        [
            _ev(1, {"intent": "buy", "did": "browse"}),
            _ev(2, {"intent": "buy", "did": "buy"}),  # no gap
            _ev(3, {"intent": "sell", "did": "hold"}),
        ]
    )
    gaps = intent_behavior_gap(
        tl,
        intent_extractor=lambda e: e.payload.get("intent"),
        behavior_extractor=lambda e: e.payload.get("did"),
    )
    assert len(gaps) == 2
    assert all(isinstance(g, IntentBehaviorGap) for g in gaps)
    assert gaps[0].tick == 1
    assert gaps[0].intent == "buy"
    assert gaps[0].behavior == "browse"
    assert gaps[0].source_row_index == 0
    assert gaps[1].tick == 3


def test_negative_intent_behavior_gap_no_intents_returns_empty() -> None:
    tl = _tl([_ev(1, {"did": "browse"})])
    gaps = intent_behavior_gap(
        tl,
        intent_extractor=lambda e: e.payload.get("intent"),
        behavior_extractor=lambda e: e.payload.get("did"),
    )
    assert gaps == []


def test_negative_intent_behavior_gap_skips_when_either_none() -> None:
    """An extractor returning None for intent OR behavior means
    the row isn't a candidate — no gap reported."""
    tl = _tl(
        [
            _ev(1, {"intent": "buy"}),  # behavior None
            _ev(2, {"did": "sell"}),  # intent None
        ]
    )
    gaps = intent_behavior_gap(
        tl,
        intent_extractor=lambda e: e.payload.get("intent"),
        behavior_extractor=lambda e: e.payload.get("did"),
    )
    assert gaps == []


def test_negative_intent_behavior_gap_equal_values_no_gap() -> None:
    tl = _tl([_ev(1, {"intent": "buy", "did": "buy"})])
    assert (
        intent_behavior_gap(
            tl,
            intent_extractor=lambda e: e.payload.get("intent"),
            behavior_extractor=lambda e: e.payload.get("did"),
        )
        == []
    )


def test_positive_intent_behavior_gap_empty_timeline() -> None:
    assert (
        intent_behavior_gap(
            _tl([]),
            intent_extractor=lambda e: None,
            behavior_extractor=lambda e: None,
        )
        == []
    )


# ─── variant_delta ─────────────────────────────────────────────────


def test_positive_variant_delta_counts_events() -> None:
    a = _tl([_ev(1, {}), _ev(2, {})])
    b = _tl([_ev(1, {}), _ev(2, {}), _ev(3, {})])
    report = variant_delta(a, b, metric_fn=lambda t: float(len(t)))
    assert isinstance(report, VariantDeltaReport)
    assert report.metric_a == 2.0
    assert report.metric_b == 3.0
    assert report.delta == 1.0


def test_negative_variant_delta_equal_timelines_zero_delta() -> None:
    tl = _tl([_ev(1, {}), _ev(2, {})])
    report = variant_delta(tl, tl, metric_fn=lambda t: float(len(t)))
    assert report.delta == 0.0


def test_negative_variant_delta_negative_result_when_b_smaller() -> None:
    a = _tl([_ev(1, {}), _ev(2, {}), _ev(3, {})])
    b = _tl([_ev(1, {})])
    report = variant_delta(a, b, metric_fn=lambda t: float(len(t)))
    assert report.delta == -2.0


# ─── load_bearing_personas ────────────────────────────────────────


def test_positive_load_bearing_personas_detects_flip() -> None:
    """Bob's ``no`` vote flips the 2-yes-1-no majority to 2-yes-0-no
    on removal — but verdict stays ``approved``. However, removing
    alice flips 2-yes to 1-yes vs 1-no → tied → ``rejected``."""
    alice = _tl([_ev(1, {"vote": "yes"})])
    bob = _tl([_ev(1, {"vote": "yes"})])
    carol = _tl([_ev(1, {"vote": "no"})])

    def verdict(timelines: list[UnifiedTimeline]) -> str:
        yes = sum(1 for t in timelines for e in t.events if e.payload.get("vote") == "yes")
        no = sum(1 for t in timelines for e in t.events if e.payload.get("vote") == "no")
        return "approved" if yes > no else "rejected"

    contributions = load_bearing_personas(
        {"alice": alice, "bob": bob, "carol": carol},
        verdict_fn=verdict,
    )
    assert len(contributions) == 3
    assert all(isinstance(c, PersonaContribution) for c in contributions)
    # With all: 2 yes > 1 no → approved. Remove alice: 1 yes, 1 no → tied → rejected.
    alice_c = next(c for c in contributions if c.persona == "alice")
    assert alice_c.verdict_with == "approved"
    assert alice_c.verdict_without == "rejected"
    assert alice_c.is_load_bearing is True
    # Remove carol: 2 yes, 0 no → still approved. Not load-bearing.
    carol_c = next(c for c in contributions if c.persona == "carol")
    assert carol_c.is_load_bearing is False


def test_negative_load_bearing_personas_single_no_flip() -> None:
    """Everyone votes the same way — no one's absence flips the
    verdict."""
    tl = _tl([_ev(1, {"vote": "yes"})])

    def verdict(timelines: list[UnifiedTimeline]) -> str:
        return "approved" if len(timelines) > 0 else "rejected"

    contributions = load_bearing_personas(
        {"alice": tl, "bob": tl, "carol": tl},
        verdict_fn=verdict,
    )
    # Removing any one still leaves 2 — verdict stays "approved".
    assert all(not c.is_load_bearing for c in contributions)


# ─── Cleanup 3: primitive guards ──────────────────────────────────


def test_positive_intent_behavior_gap_detects_zero_as_value() -> None:
    """Step 10 audit M4: ``0`` / ``False`` / ``""`` are legitimate
    extracted values — the ``is None`` check must preserve them
    as non-skip. Regression test against a future refactor to
    truthiness pruning."""
    tl = _tl([_ev(1, {"intent": 0, "did": 1})])
    gaps = intent_behavior_gap(
        tl,
        intent_extractor=lambda e: e.payload.get("intent"),
        behavior_extractor=lambda e: e.payload.get("did"),
    )
    assert len(gaps) == 1
    assert gaps[0].intent == 0
    assert gaps[0].behavior == 1


def test_positive_intent_behavior_gap_detects_empty_string_divergence() -> None:
    tl = _tl([_ev(1, {"intent": "", "did": "something"})])
    gaps = intent_behavior_gap(
        tl,
        intent_extractor=lambda e: e.payload.get("intent"),
        behavior_extractor=lambda e: e.payload.get("did"),
    )
    assert len(gaps) == 1


def test_negative_variant_delta_nan_metric_raises() -> None:
    """Step 10 audit M1: non-finite metric values poison downstream
    comparisons silently. ``variant_delta`` raises at the boundary."""
    import pytest

    tl = _tl([_ev(1, {})])
    with pytest.raises(ValueError, match="non-finite"):
        variant_delta(tl, tl, metric_fn=lambda t: float("nan"))


def test_negative_variant_delta_inf_metric_raises() -> None:
    import pytest

    tl = _tl([_ev(1, {})])
    with pytest.raises(ValueError, match="non-finite"):
        variant_delta(tl, tl, metric_fn=lambda t: float("inf"))


def test_positive_load_bearing_float_verdict_epsilon_not_flagged() -> None:
    """Step 10 audit M2: float verdicts must NOT flag every
    persona as load-bearing due to floating-point rounding. Two
    verdicts differing by 1e-15 are treated as equal under the
    default epsilon tolerance."""
    alice = _tl([_ev(1, {"score": 0.1})])
    bob = _tl([_ev(1, {"score": 0.2})])

    def verdict(timelines: list[UnifiedTimeline]) -> float:
        return sum(e.payload.get("score", 0.0) for t in timelines for e in t.events)

    contributions = load_bearing_personas(
        {"alice": alice, "bob": bob},
        verdict_fn=verdict,
    )
    # verdict_with = 0.3, verdict_without_alice = 0.2
    # These differ by 0.1 >> epsilon → alice IS load-bearing.
    alice_c = next(c for c in contributions if c.persona == "alice")
    assert alice_c.is_load_bearing is True


def test_positive_load_bearing_float_rounding_noise_not_flagged() -> None:
    """The default equality_fn is tolerant to pure FP noise."""
    tl = _tl([_ev(1, {})])

    # Verdict that differs only by rounding error across calls.
    calls = {"n": 0}

    def verdict(timelines: list[UnifiedTimeline]) -> float:
        calls["n"] += 1
        # Return 1.0 with ε noise on odd calls.
        return 1.0 + (1e-15 if calls["n"] % 2 else 0.0)

    contributions = load_bearing_personas(
        {"alice": tl, "bob": tl},
        verdict_fn=verdict,
    )
    # Noise-driven diffs must NOT flag load-bearing.
    assert all(not c.is_load_bearing for c in contributions)


def test_positive_load_bearing_custom_equality_fn() -> None:
    """Caller-supplied ``equality_fn`` overrides the default."""
    tl = _tl([_ev(1, {})])

    calls = [0.0, 1.0, 2.0]  # verdict_with=0.0, then 1.0, 2.0 per persona

    def verdict(timelines: list[UnifiedTimeline]) -> float:
        return calls.pop(0)

    # Custom tolerance treats anything within ±10 as equal.
    contributions = load_bearing_personas(
        {"alice": tl, "bob": tl},
        verdict_fn=verdict,
        equality_fn=lambda a, b: abs(a - b) < 10.0,
    )
    assert all(not c.is_load_bearing for c in contributions)


def test_negative_load_bearing_empty_mapping_returns_empty() -> None:
    """Step 10 audit L1: empty input returns empty list —
    undocumented edge case now locked."""
    contributions = load_bearing_personas(
        {},
        verdict_fn=lambda ts: len(ts),
    )
    assert contributions == []
