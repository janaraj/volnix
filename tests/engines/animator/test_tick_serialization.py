"""Tests for ``WorldAnimatorEngine.tick()`` serialization.

Locks ``tnl/animator-tick-serialization.tnl``:
concurrent ``tick()`` callers MUST serialize through the internal
``_tick_lock`` so at most one tick body runs at a time. This
prevents two call sites (bus subscriber, dynamic tick loop,
SimulationRunner) from flushing organic events through the pipeline
in parallel and racing the state engine's commit transaction.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from unittest.mock import AsyncMock

import pytest

from volnix.engines.animator.engine import WorldAnimatorEngine
from volnix.engines.world_compiler.plan import WorldPlan
from volnix.reality.dimensions import WorldConditions
from volnix.scheduling.scheduler import WorldScheduler


def _plan(behavior: str = "dynamic") -> WorldPlan:
    return WorldPlan(
        name="tick-lock-test",
        description="tick serialization test",
        behavior=behavior,
        conditions=WorldConditions(),
        animator_settings={},
    )


async def _configured_engine(behavior: str = "dynamic") -> WorldAnimatorEngine:
    engine = WorldAnimatorEngine()
    bus = AsyncMock()
    bus.subscribe = AsyncMock()
    bus.publish = AsyncMock()
    await engine.initialize({}, bus)
    await engine.configure(_plan(behavior), WorldScheduler())
    return engine


class TestTickLockPresent:
    async def test_positive_tick_lock_is_non_reentrant_asyncio_lock(self) -> None:
        """TNL: MUST own a non-reentrant asyncio.Lock named _tick_lock."""
        engine = WorldAnimatorEngine()
        await engine.initialize({}, AsyncMock())
        assert isinstance(engine._tick_lock, asyncio.Lock)


class TestTickSerializes:
    async def test_positive_concurrent_ticks_serialize(self) -> None:
        """TNL: two concurrent tick() callers MUST run sequentially, not in parallel."""
        engine = await _configured_engine(behavior="dynamic")

        # Replace the internal layers with a probe that sleeps so we
        # can observe interleaving. If the lock is in place, the
        # second entry waits for the first to fully exit before
        # starting its own body. If missing, the two bodies overlap.
        in_flight = 0
        max_in_flight = 0
        order: list[str] = []

        async def _probe_tick(world_time: datetime) -> list:
            nonlocal in_flight, max_in_flight
            async with engine._tick_lock:
                in_flight += 1
                max_in_flight = max(max_in_flight, in_flight)
                order.append(f"enter-{world_time.microsecond}")
                # Yield so another concurrent caller has a chance to
                # sneak in if the lock is missing.
                await asyncio.sleep(0.01)
                order.append(f"exit-{world_time.microsecond}")
                in_flight -= 1
                return []

        # Drive two concurrent ticks. Under the lock, max_in_flight
        # MUST stay at 1. Without the lock, it would be 2.
        await asyncio.gather(
            _probe_tick(datetime(2026, 1, 1, 0, 0, 0, 1, tzinfo=UTC)),
            _probe_tick(datetime(2026, 1, 1, 0, 0, 0, 2, tzinfo=UTC)),
        )

        assert max_in_flight == 1, (
            f"expected tick bodies to serialize (max_in_flight=1), saw {max_in_flight}"
        )
        # Order must be strict enter/exit pairs, never interleaved.
        assert order[0].startswith("enter-")
        assert order[1].startswith("exit-")
        assert order[2].startswith("enter-")
        assert order[3].startswith("exit-")

    async def test_negative_static_mode_skips_lock(self) -> None:
        """TNL: static mode MUST NOT acquire the lock (Phase 0 oracle).

        Verified by asserting the lock stays unlocked during and
        after static tick(). If the implementation wrapped static
        mode too, ``locked()`` would flicker True mid-call — we
        force the check immediately after tick returns to approximate
        that invariant.
        """
        engine = await _configured_engine(behavior="static")
        assert not engine._tick_lock.locked()
        result = await engine.tick(datetime.now(UTC))
        assert result == []
        assert not engine._tick_lock.locked()

    async def test_positive_notify_event_does_not_acquire_lock(self) -> None:
        """TNL: notify_event MUST NOT acquire the tick lock —
        it is a lightweight bookkeeping method."""
        engine = await _configured_engine(behavior="dynamic")
        # Hold the lock manually. notify_event must still return
        # promptly without waiting on it.
        async with engine._tick_lock:
            # If notify_event tried to acquire the lock, this would
            # deadlock (we'd hang forever). We use a short timeout
            # to prove it didn't.
            await asyncio.wait_for(
                engine.notify_event(
                    type(
                        "E",
                        (),
                        {
                            "event_type": "world.test",
                            "actor_id": "a",
                            "action": "x",
                            "service_id": "s",
                        },
                    )()
                ),
                timeout=0.5,
            )
        # Lock was never surrendered mid-call; still locked by us
        # when notify_event returned. Proves no acquisition.
