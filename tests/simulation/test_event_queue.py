"""Tests for volnix.simulation.event_queue.EventQueue."""

from __future__ import annotations

from volnix.core.envelope import ActionEnvelope
from volnix.core.types import ActionSource, ActorId, EnvelopePriority, ServiceId
from volnix.simulation.event_queue import EventQueue


def _make_envelope(
    actor_id: str = "actor-1",
    logical_time: float = 0.0,
    priority: EnvelopePriority = EnvelopePriority.INTERNAL,
    action_type: str = "do_something",
    source: ActionSource = ActionSource.INTERNAL,
) -> ActionEnvelope:
    """Helper to build ActionEnvelopes with minimal boilerplate."""
    return ActionEnvelope(
        actor_id=ActorId(actor_id),
        source=source,
        action_type=action_type,
        target_service=ServiceId("svc"),
        logical_time=logical_time,
        priority=priority,
    )


class TestSubmitAndPop:
    """Submission and pop behaviour."""

    def test_submit_and_pop_ordered(self) -> None:
        """Envelopes submitted at different times come out in time order."""
        q = EventQueue()
        e1 = _make_envelope(logical_time=10.0)
        e2 = _make_envelope(logical_time=5.0)
        e3 = _make_envelope(logical_time=15.0)

        q.submit(e1)
        q.submit(e2)
        q.submit(e3)

        assert q.size == 3
        popped = q.pop_next()
        assert popped is not None
        assert popped.logical_time == 5.0

        popped = q.pop_next()
        assert popped is not None
        assert popped.logical_time == 10.0

        popped = q.pop_next()
        assert popped is not None
        assert popped.logical_time == 15.0

    def test_ordering_by_logical_time(self) -> None:
        """Strict ordering by logical_time when priorities are equal."""
        q = EventQueue()
        times = [100.0, 1.0, 50.0, 25.0]
        for t in times:
            q.submit(_make_envelope(logical_time=t))

        result_times = []
        while q.has_pending():
            env = q.pop_next()
            assert env is not None
            result_times.append(env.logical_time)

        assert result_times == sorted(times)


class TestTieBreaking:
    """Tie-breaking behaviour when logical_time is equal."""

    def test_tie_breaking_by_priority(self) -> None:
        """ENVIRONMENT (0) < EXTERNAL (1) < INTERNAL (2) when times are equal."""
        q = EventQueue()

        internal = _make_envelope(
            actor_id="actor-a", logical_time=10.0, priority=EnvelopePriority.INTERNAL
        )
        external = _make_envelope(
            actor_id="actor-a", logical_time=10.0, priority=EnvelopePriority.EXTERNAL
        )
        environment = _make_envelope(
            actor_id="actor-a", logical_time=10.0, priority=EnvelopePriority.ENVIRONMENT
        )

        # Submit in reverse priority order
        q.submit(internal)
        q.submit(external)
        q.submit(environment)

        first = q.pop_next()
        second = q.pop_next()
        third = q.pop_next()
        assert first is not None and second is not None and third is not None
        assert first.priority == EnvelopePriority.ENVIRONMENT
        assert second.priority == EnvelopePriority.EXTERNAL
        assert third.priority == EnvelopePriority.INTERNAL

    def test_tie_breaking_by_actor_id(self) -> None:
        """Same time, same priority -> deterministic ordering by actor_id string."""
        q = EventQueue()
        e_b = _make_envelope(actor_id="beta", logical_time=5.0)
        e_a = _make_envelope(actor_id="alpha", logical_time=5.0)

        q.submit(e_b)
        q.submit(e_a)

        first = q.pop_next()
        second = q.pop_next()
        assert first is not None and second is not None
        assert str(first.actor_id) == "alpha"
        assert str(second.actor_id) == "beta"


class TestSchedule:
    """Scheduling envelopes with a future delay."""

    def test_schedule_with_delay(self) -> None:
        """schedule() offsets envelope logical_time by current_time + delay."""
        q = EventQueue()
        q.current_time = 100.0

        env = _make_envelope(logical_time=0.0)
        q.schedule(env, delay=50.0)

        assert q.size == 1
        popped = q.pop_next()
        assert popped is not None
        assert popped.logical_time == 150.0

    def test_schedule_future_preserves_other_fields(self) -> None:
        """Scheduled envelope keeps all original fields except logical_time."""
        q = EventQueue()
        q.current_time = 10.0

        env = _make_envelope(actor_id="actor-x", action_type="special_action")
        q.schedule(env, delay=20.0)

        popped = q.pop_next()
        assert popped is not None
        assert str(popped.actor_id) == "actor-x"
        assert popped.action_type == "special_action"
        assert popped.logical_time == 30.0


class TestQueueState:
    """State inspection methods."""

    def test_has_pending(self) -> None:
        """has_pending reflects queue emptiness."""
        q = EventQueue()
        assert q.has_pending() is False

        q.submit(_make_envelope())
        assert q.has_pending() is True

        q.pop_next()
        assert q.has_pending() is False

    def test_current_time_advances(self) -> None:
        """current_time advances as envelopes are popped."""
        q = EventQueue()
        assert q.current_time == 0.0

        q.submit(_make_envelope(logical_time=42.0))
        q.pop_next()
        assert q.current_time == 42.0

        # Should not go backwards
        q.submit(_make_envelope(logical_time=10.0))
        q.pop_next()
        assert q.current_time == 42.0

    def test_peek_time(self) -> None:
        """peek_time returns the next logical_time without consuming it."""
        q = EventQueue()
        assert q.peek_time() is None

        q.submit(_make_envelope(logical_time=7.5))
        q.submit(_make_envelope(logical_time=3.0))

        assert q.peek_time() == 3.0
        assert q.size == 2  # nothing consumed

    def test_empty_queue_returns_none(self) -> None:
        """pop_next on an empty queue returns None."""
        q = EventQueue()
        assert q.pop_next() is None

    def test_size(self) -> None:
        """size tracks the number of envelopes in the queue."""
        q = EventQueue()
        assert q.size == 0

        q.submit(_make_envelope())
        q.submit(_make_envelope())
        assert q.size == 2

        q.pop_next()
        assert q.size == 1
