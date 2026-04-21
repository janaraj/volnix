"""Phase 4C Step 6 — SimulationRunner/Session wiring integration test.

Step 6 exposes ``session_id`` + ``current_tick`` on the
SimulationRunner so upstream callers (engines, activators) can
read the session context when constructing events and envelopes.
The runner does NOT mutate envelopes — ``ActionEnvelope`` is
frozen. This test locks the "runner exposes, upstream stamps"
contract (audit-fold M4 — renamed from the misleading
``test_session_runner_stamping.py``).

Negative ratio: 1/2 = 50%.
"""

from __future__ import annotations

from volnix.core.envelope import ActionEnvelope
from volnix.core.types import ActionSource, ActorId, SessionId
from volnix.simulation.event_queue import EventQueue
from volnix.simulation.runner import SimulationRunner


async def _noop_executor(envelope):
    return None


async def test_negative_runner_without_session_exposes_none() -> None:
    """A runner constructed without ``session_id`` reports
    ``None`` — callers stamping envelopes must not assume a
    session is active just because a runner exists."""
    runner = SimulationRunner(
        event_queue=EventQueue(),
        pipeline_executor=_noop_executor,
    )
    assert runner.session_id is None


async def test_positive_runner_exposes_session_id_for_upstream_stampers() -> None:
    """The runner exposes ``session_id`` via a read-only property.
    Upstream code (AgencyEngine.activate, Animator.generate_event)
    reads this value and passes it into the frozen
    ``ActionEnvelope`` constructor — the runner never mutates
    envelopes itself."""
    sid = SessionId("sess-wire-1")
    runner = SimulationRunner(
        event_queue=EventQueue(),
        pipeline_executor=_noop_executor,
        session_id=sid,
    )
    # Upstream code reads the runner's session and stamps it onto
    # a fresh envelope at construction. Verify the stamping path
    # produces a correctly-correlated envelope.
    env = ActionEnvelope(
        actor_id=ActorId("a-1"),
        source=ActionSource.INTERNAL,
        action_type="test",
        session_id=runner.session_id,
    )
    assert env.session_id == sid
