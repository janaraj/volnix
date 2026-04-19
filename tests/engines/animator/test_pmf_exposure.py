"""Tests for the Phase-3 PMF exposure opt-in on :class:`WorldAnimatorEngine`.

The contract this pins:

* With no ``animator_settings.pmf`` block: zero ``NPCExposureEvent``
  publishes across any number of ticks. This is the regression-safety
  gate — every existing blueprint falls under it.
* With ``expose_rate > 0``, ``candidate_npcs`` populated, and
  ``features`` populated: ticks probabilistically emit
  ``NPCExposureEvent`` on the bus. The RNG is seeded from
  ``world_time`` so the sequence is reproducible.
* Invalid config (missing candidates, missing features, rate=0) is
  a no-op — the code defends against partial config rather than
  crashing.
"""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock

import pytest

from volnix.core.events import NPCExposureEvent
from volnix.engines.animator.engine import WorldAnimatorEngine
from volnix.engines.world_compiler.plan import WorldPlan
from volnix.reality.dimensions import WorldConditions
from volnix.scheduling.scheduler import WorldScheduler


def _tick_time(minute_offset: int = 0) -> datetime:
    return datetime(2026, 4, 15, 12, minute_offset, 0, tzinfo=UTC)


def _plan(animator_settings: dict | None = None) -> WorldPlan:
    return WorldPlan(
        name="test",
        description="test world",
        behavior="dynamic",
        conditions=WorldConditions(),
        animator_settings=animator_settings or {},
    )


async def _engine(animator_settings: dict | None = None) -> tuple[WorldAnimatorEngine, AsyncMock]:
    engine = WorldAnimatorEngine()
    bus = AsyncMock()
    bus.subscribe = AsyncMock()
    bus.publish = AsyncMock()
    await engine.initialize({}, bus)
    await engine.configure(_plan(animator_settings), WorldScheduler())
    return engine, bus


def _exposure_publishes(bus: AsyncMock) -> list[NPCExposureEvent]:
    """Extract NPCExposureEvent instances from the mock bus."""
    events: list[NPCExposureEvent] = []
    for call in bus.publish.await_args_list:
        arg = call.args[0] if call.args else None
        if isinstance(arg, NPCExposureEvent):
            events.append(arg)
    return events


# -- regression safety -------------------------------------------------------


class TestNoExposureByDefault:
    @pytest.mark.asyncio
    async def test_absent_pmf_block_never_publishes_exposure(self) -> None:
        """Every existing blueprint's animator_settings omits ``pmf``.
        The tick loop must publish ZERO ``NPCExposureEvent`` in that case.
        """
        engine, bus = await _engine(animator_settings={})
        for i in range(10):
            await engine.tick(_tick_time(minute_offset=i))
        assert _exposure_publishes(bus) == []

    @pytest.mark.asyncio
    async def test_rate_zero_never_publishes(self) -> None:
        engine, bus = await _engine(
            animator_settings={
                "pmf": {
                    "expose_rate": 0.0,
                    "candidate_npcs": ["npc-1"],
                    "features": ["drop_flare"],
                }
            }
        )
        for i in range(5):
            await engine.tick(_tick_time(minute_offset=i))
        assert _exposure_publishes(bus) == []

    @pytest.mark.asyncio
    async def test_missing_candidates_is_noop(self) -> None:
        engine, bus = await _engine(
            animator_settings={"pmf": {"expose_rate": 1.0, "features": ["drop_flare"]}}
        )
        await engine.tick(_tick_time())
        assert _exposure_publishes(bus) == []

    @pytest.mark.asyncio
    async def test_missing_features_is_noop(self) -> None:
        engine, bus = await _engine(
            animator_settings={"pmf": {"expose_rate": 1.0, "candidate_npcs": ["npc-1"]}}
        )
        await engine.tick(_tick_time())
        assert _exposure_publishes(bus) == []

    @pytest.mark.asyncio
    async def test_malformed_rate_coerced_to_zero(self) -> None:
        engine, bus = await _engine(
            animator_settings={
                "pmf": {
                    "expose_rate": "not-a-number",
                    "candidate_npcs": ["npc-1"],
                    "features": ["drop_flare"],
                }
            }
        )
        await engine.tick(_tick_time())
        assert _exposure_publishes(bus) == []


# -- active generation -------------------------------------------------------


class TestExposurePublishing:
    @pytest.mark.asyncio
    async def test_rate_one_publishes_every_tick(self) -> None:
        engine, bus = await _engine(
            animator_settings={
                "pmf": {
                    "expose_rate": 1.0,
                    "candidate_npcs": ["npc-1", "npc-2"],
                    "features": ["drop_flare", "enter_pocket"],
                }
            }
        )
        await engine.tick(_tick_time(1))
        await engine.tick(_tick_time(2))
        await engine.tick(_tick_time(3))
        events = _exposure_publishes(bus)
        assert len(events) == 3

    @pytest.mark.asyncio
    async def test_event_targets_a_configured_npc_and_feature(self) -> None:
        engine, bus = await _engine(
            animator_settings={
                "pmf": {
                    "expose_rate": 1.0,
                    "candidate_npcs": ["npc-1", "npc-2"],
                    "features": ["drop_flare", "enter_pocket"],
                }
            }
        )
        await engine.tick(_tick_time(7))
        events = _exposure_publishes(bus)
        assert len(events) == 1
        ev = events[0]
        assert str(ev.npc_id) in {"npc-1", "npc-2"}
        assert ev.feature_id in {"drop_flare", "enter_pocket"}
        assert ev.source == "animator"
        assert ev.event_type == "npc.exposure"
        # intended_for targets the specific NPC — the E2E test relies
        # on this to pass the ``notify``-level activation gate.
        assert ev.input_data.get("intended_for") == [str(ev.npc_id)]

    @pytest.mark.asyncio
    async def test_determinism_same_time_same_choice(self) -> None:
        """Rerunning at identical world_time produces identical events.

        Seeded from ``int(world_time.timestamp() * 1000)``, so two
        engines ticking at the same moment pick the same npc+feature.
        """
        settings = {
            "pmf": {
                "expose_rate": 1.0,
                "candidate_npcs": ["a", "b", "c", "d"],
                "features": ["f1", "f2", "f3", "f4"],
            }
        }
        e1, bus1 = await _engine(animator_settings=settings)
        e2, bus2 = await _engine(animator_settings=settings)
        t = _tick_time(17)
        await e1.tick(t)
        await e2.tick(t)
        ev1 = _exposure_publishes(bus1)[0]
        ev2 = _exposure_publishes(bus2)[0]
        assert str(ev1.npc_id) == str(ev2.npc_id)
        assert ev1.feature_id == ev2.feature_id
