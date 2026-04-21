"""Phase 4C Step 9 — StateEngine.get_trajectory tests.

Locks the historical-value-projection contract:
- Happy path: ordered TrajectoryPoint list reconstructed from
  committed ``WorldEvent.state_deltas`` in tick order, with
  stable ``rowid`` tiebreaker at identical ticks.
- Error path: only MALFORMED ``field_path`` raises
  ``TrajectoryFieldNotFound``. Data absence (no events, field
  never present) returns ``[]`` — so callers doing sliding-window
  queries get consistent shape (audit-fold H1).

Negative ratio: 6/11 = 54%.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest

from volnix.core.errors import TrajectoryFieldNotFound
from volnix.core.events import WorldEvent
from volnix.core.types import ActorId, EntityId, EventId, ServiceId, Timestamp
from volnix.engines.state.engine import _MISSING, StateEngine, _extract_dotted
from volnix.engines.state.trajectory import TrajectoryPoint


def _world_event(
    *,
    tick: int,
    entity_id: str = "entity-a",
    fields: dict[str, Any] | None = None,
    action: str = "mutate",
) -> WorldEvent:
    """Build a committed WorldEvent with one state_delta."""
    delta: dict[str, Any] = {
        "entity_type": "thing",
        "entity_id": entity_id,
        "operation": "update",
        "fields": fields or {},
        "previous_fields": {},
    }
    return WorldEvent(
        event_type=f"world.{action}",
        timestamp=Timestamp(
            world_time=datetime(2026, 1, 15, tzinfo=UTC),
            wall_time=datetime.now(UTC),
            tick=tick,
        ),
        actor_id=ActorId("agent-1"),
        service_id=ServiceId("svc-test"),
        action=action,
        state_deltas=[delta],
    )


def _world_event_multi_delta(*, tick: int, deltas: list[dict[str, Any]]) -> WorldEvent:
    return WorldEvent(
        event_type="world.mutate",
        timestamp=Timestamp(
            world_time=datetime(2026, 1, 15, tzinfo=UTC),
            wall_time=datetime.now(UTC),
            tick=tick,
        ),
        actor_id=ActorId("agent-1"),
        service_id=ServiceId("svc-test"),
        action="mutate",
        state_deltas=deltas,
    )


async def _fresh_engine(db) -> StateEngine:
    """Build a bare StateEngine using the shared db fixture."""
    from volnix.engines.state.causal_graph import CausalGraph
    from volnix.engines.state.event_log import EventLog

    engine = StateEngine()
    engine._db = db
    engine._event_log = EventLog(db)
    engine._causal_graph = CausalGraph(db)
    return engine


# ─── Dotted-path helper ─────────────────────────────────────────────


def test_positive_extract_dotted_flat_key() -> None:
    assert _extract_dotted({"a": 1}, ["a"]) == 1


def test_positive_extract_dotted_nested() -> None:
    assert _extract_dotted({"a": {"b": {"c": 3}}}, ["a", "b", "c"]) == 3


def test_negative_extract_dotted_missing_leaf_returns_sentinel() -> None:
    """Missing leaf returns the MISSING sentinel (which the caller
    treats as empty-list, not exception — audit-fold H1/M1)."""
    assert _extract_dotted({"a": 1}, ["b"]) is _MISSING


def test_negative_extract_dotted_intermediate_not_dict_returns_sentinel() -> None:
    """Path stops being dict mid-walk — no raise, sentinel."""
    assert _extract_dotted({"a": 1}, ["a", "b"]) is _MISSING


def test_negative_extract_dotted_list_index_unsupported() -> None:
    """Numeric segment on a list returns MISSING (Step-9 scope
    limit — plan audit-fold M1)."""
    assert _extract_dotted({"items": ["x"]}, ["items", "0"]) is _MISSING


# ─── get_trajectory — malformed-path rejection ─────────────────────


async def test_negative_empty_field_path_raises(db) -> None:
    engine = await _fresh_engine(db)
    with pytest.raises(TrajectoryFieldNotFound):
        await engine.get_trajectory(EntityId("entity-a"), "")


async def test_negative_whitespace_field_path_raises(db) -> None:
    engine = await _fresh_engine(db)
    with pytest.raises(TrajectoryFieldNotFound):
        await engine.get_trajectory(EntityId("entity-a"), "   ")


async def test_negative_field_path_with_empty_segments_raises(db) -> None:
    """``..`` or leading/trailing dots signal a typo — reject
    loudly so the walk doesn't silently return empty."""
    engine = await _fresh_engine(db)
    for bad in ("a..b", ".a", "a."):
        with pytest.raises(TrajectoryFieldNotFound):
            await engine.get_trajectory(EntityId("entity-a"), bad)


async def test_negative_tick_range_start_after_end_raises(db) -> None:
    engine = await _fresh_engine(db)
    with pytest.raises(ValueError):
        await engine.get_trajectory(EntityId("entity-a"), "budget", tick_range=(10, 5))


# ─── get_trajectory — data-absence returns [] ──────────────────────


async def test_negative_entity_with_no_events_returns_empty(db) -> None:
    engine = await _fresh_engine(db)
    result = await engine.get_trajectory(EntityId("nobody"), "budget")
    assert result == []


async def test_negative_unknown_field_returns_empty(db) -> None:
    """Audit-fold H1: field absent from every delta is NOT an
    error — returns empty list for consistent sliding-window
    behaviour."""
    engine = await _fresh_engine(db)
    await engine._event_log.append(_world_event(tick=1, entity_id="entity-a", fields={"other": 1}))
    result = await engine.get_trajectory(EntityId("entity-a"), "budget")
    assert result == []


# ─── get_trajectory — happy paths ──────────────────────────────────


async def test_positive_linear_trajectory_matches_expectation(db) -> None:
    """Three successive updates to the same field yield three
    trajectory points in tick order."""
    engine = await _fresh_engine(db)
    await engine._event_log.append(_world_event(tick=1, entity_id="alice", fields={"budget": 100}))
    await engine._event_log.append(_world_event(tick=2, entity_id="alice", fields={"budget": 80}))
    await engine._event_log.append(_world_event(tick=3, entity_id="alice", fields={"budget": 50}))
    # Irrelevant event — different entity, same tick.
    await engine._event_log.append(_world_event(tick=2, entity_id="bob", fields={"budget": 999}))
    points = await engine.get_trajectory(EntityId("alice"), "budget")
    assert [p.value for p in points] == [100, 80, 50]
    assert [p.tick for p in points] == [1, 2, 3]
    assert all(isinstance(p, TrajectoryPoint) for p in points)
    assert all(p.entity_id == EntityId("alice") for p in points)
    assert all(p.field_path == "budget" for p in points)


async def test_positive_nested_field_path_extracted(db) -> None:
    engine = await _fresh_engine(db)
    await engine._event_log.append(
        _world_event(
            tick=1,
            entity_id="alice",
            fields={"budget": {"remaining_usd": 100, "spent_usd": 0}},
        )
    )
    await engine._event_log.append(
        _world_event(
            tick=2,
            entity_id="alice",
            fields={"budget": {"remaining_usd": 75, "spent_usd": 25}},
        )
    )
    points = await engine.get_trajectory(EntityId("alice"), "budget.remaining_usd")
    assert [p.value for p in points] == [100, 75]


async def test_positive_multiple_state_changes_at_same_tick_ordered_by_insertion(
    db,
) -> None:
    """Audit-fold C2: within a tick, trajectory points must be
    stably ordered by insertion (rowid), not by non-deterministic
    payload hash."""
    engine = await _fresh_engine(db)
    # Two events at the same tick, different inserted-first order.
    await engine._event_log.append(_world_event(tick=5, entity_id="alice", fields={"budget": 10}))
    await engine._event_log.append(_world_event(tick=5, entity_id="alice", fields={"budget": 20}))
    await engine._event_log.append(_world_event(tick=5, entity_id="alice", fields={"budget": 30}))
    points = await engine.get_trajectory(EntityId("alice"), "budget")
    assert [p.value for p in points] == [10, 20, 30]


async def test_positive_tick_range_bounds_inclusive(db) -> None:
    """``tick_range=(a, b)`` is inclusive on both ends — events at
    exactly ``a`` and ``b`` are included."""
    engine = await _fresh_engine(db)
    for t in (1, 2, 3, 4, 5):
        await engine._event_log.append(
            _world_event(tick=t, entity_id="alice", fields={"budget": t * 10})
        )
    points = await engine.get_trajectory(EntityId("alice"), "budget", tick_range=(2, 4))
    assert [p.value for p in points] == [20, 30, 40]


async def test_positive_value_field_survives_json_round_trip(db) -> None:
    """Audit-fold M2: TrajectoryPoint.value must be JSON-safe so
    downstream product wire-transport works. Locks the frozen-
    model ``model_dump(mode='json')`` path end-to-end."""
    engine = await _fresh_engine(db)
    await engine._event_log.append(
        _world_event(
            tick=1,
            entity_id="alice",
            fields={"payload": {"nested": [1, 2, "three"], "flag": True}},
        )
    )
    points = await engine.get_trajectory(EntityId("alice"), "payload")
    assert len(points) == 1
    dumped = points[0].model_dump(mode="json")
    assert dumped["value"] == {"nested": [1, 2, "three"], "flag": True}
    assert dumped["tick"] == 1


async def test_positive_single_tick_bounds_inclusive(db) -> None:
    """Post-impl audit L2: ``tick_range=(5, 5)`` is the single-
    tick inclusive case. Must return exactly events at tick 5,
    no adjacent ticks leaking."""
    engine = await _fresh_engine(db)
    for t in (4, 5, 5, 6):
        await engine._event_log.append(
            _world_event(tick=t, entity_id="alice", fields={"budget": t})
        )
    points = await engine.get_trajectory(EntityId("alice"), "budget", tick_range=(5, 5))
    assert [p.value for p in points] == [5, 5]
    assert all(p.tick == 5 for p in points)


async def test_positive_null_value_emits_trajectory_point(db) -> None:
    """Post-impl audit L3: a field set to ``None`` IS a trajectory
    point (``_MISSING`` sentinel distinguishes missing-key from
    null-value). Locks the 'when was this cleared?' semantics."""
    engine = await _fresh_engine(db)
    await engine._event_log.append(_world_event(tick=1, entity_id="alice", fields={"budget": None}))
    points = await engine.get_trajectory(EntityId("alice"), "budget")
    assert len(points) == 1
    assert points[0].value is None


def test_negative_non_json_value_rejected_at_construction() -> None:
    """Post-impl audit H3: ``TrajectoryPoint.value`` rejects a
    ``datetime`` (or any non-JSON-native leaf) nested inside a
    dict at CONSTRUCTION via the ``json.dumps`` probe — downstream
    consumers calling ``json.dumps(pt.value)`` are safe."""
    from datetime import UTC
    from datetime import datetime as dt

    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        TrajectoryPoint(
            tick=1,
            value={"expires": dt(2026, 1, 1, tzinfo=UTC)},
            event_id=EventId("evt-1"),
            entity_id=EntityId("alice"),
            field_path="expires",
        )


# ─── Multi-delta per event ─────────────────────────────────────────


async def test_positive_multiple_deltas_per_event_only_matching_entity_counted(
    db,
) -> None:
    """One event with two deltas on different entities — only the
    target entity contributes a trajectory point."""
    engine = await _fresh_engine(db)
    evt = _world_event_multi_delta(
        tick=1,
        deltas=[
            {
                "entity_type": "person",
                "entity_id": "alice",
                "operation": "update",
                "fields": {"budget": 100},
            },
            {
                "entity_type": "person",
                "entity_id": "bob",
                "operation": "update",
                "fields": {"budget": 200},
            },
        ],
    )
    await engine._event_log.append(evt)
    points = await engine.get_trajectory(EntityId("alice"), "budget")
    assert len(points) == 1
    assert points[0].value == 100
