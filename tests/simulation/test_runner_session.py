"""Phase 4C Step 6 — SimulationRunner session-awareness tests.

Step 6 adds ``session_id`` + ``initial_tick`` kwargs to
``SimulationRunner.__init__`` and exposes them via read-only
properties. This file locks the surface the Step 8 replay
provider + Step 10 observation query depend on.

Negative ratio: 5/8 = 62%.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from volnix.core.envelope import ActionEnvelope
from volnix.core.events import Event
from volnix.core.types import ActionSource, ActorId, SessionId, Timestamp
from volnix.simulation.event_queue import EventQueue
from volnix.simulation.runner import SimulationRunner


def _make_runner(*, session_id=None, initial_tick=0):
    async def _noop_executor(envelope):
        return None

    return SimulationRunner(
        event_queue=EventQueue(),
        pipeline_executor=_noop_executor,
        session_id=session_id,
        initial_tick=initial_tick,
    )


# ─── Field defaults (audit L3 + L4) ────────────────────────────────


async def test_negative_event_base_session_id_defaults_to_none() -> None:
    """Audit-fold L3: Step 6 adds ``session_id: SessionId | None = None``
    to the frozen ``Event`` base. A wrong default (required, or a
    non-None sentinel) would break every existing event-construction
    site in the codebase. Lock the default."""
    evt = Event(
        event_type="t",
        timestamp=Timestamp(
            world_time=datetime.now(UTC),
            wall_time=datetime.now(UTC),
            tick=0,
        ),
    )
    assert evt.session_id is None


async def test_negative_action_envelope_session_id_defaults_to_none() -> None:
    """Audit-fold L4: parity with Event — ``ActionEnvelope.session_id``
    defaults to None on construction."""
    env = ActionEnvelope(
        actor_id=ActorId("a-1"),
        source=ActionSource.INTERNAL,
        action_type="t",
    )
    assert env.session_id is None


# ─── Runner kwargs + properties ───────────────────────────────────


async def test_negative_default_session_id_is_none() -> None:
    runner = _make_runner()
    assert runner.session_id is None


async def test_negative_default_initial_tick_is_zero() -> None:
    runner = _make_runner()
    assert runner.current_tick == 0


async def test_negative_session_id_property_has_no_setter() -> None:
    """Audit-fold H3: ``session_id`` is read-only post-construction.
    The property has no setter, so assignment raises
    ``AttributeError``. Future refactors that silently break this
    contract get caught."""
    runner = _make_runner(session_id=SessionId("s-1"))
    with pytest.raises(AttributeError):
        runner.session_id = SessionId("other")  # type: ignore[misc]


async def test_positive_session_id_accessible_via_property() -> None:
    runner = _make_runner(session_id=SessionId("sess-123"))
    assert runner.session_id == SessionId("sess-123")


async def test_positive_initial_tick_seeds_current_tick() -> None:
    """Cross-run tick continuity: the next run inherits the prior
    run's end tick via ``initial_tick``."""
    runner = _make_runner(initial_tick=42)
    assert runner.current_tick == 42


async def test_positive_current_tick_property_reflects_internal_state() -> None:
    """The ``current_tick`` property MUST reflect the live
    ``_current_tick`` attribute; a stale cached copy would lie
    about progress to outside observers."""
    runner = _make_runner(initial_tick=5)
    # Runner increments _current_tick during run(); we simulate by
    # touching the attribute directly — the property must not be a
    # frozen snapshot.
    runner._current_tick = 17
    assert runner.current_tick == 17
