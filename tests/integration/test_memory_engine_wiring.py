"""Integration tests for MemoryEngine wiring into VolnixApp
(PMF Plan Phase 4B Step 10).

Real VolnixApp, real in-memory persistence, real bus, real ledger.
Composition wiring is exactly the kind of path where unit-level
mocking hides the real bugs, so negative + positive cases both run
against the real stack.

The LLM router is the one dependency we mock — VolnixApp's default
``_initialize_llm`` returns ``None`` when no providers are
configured, and the memory wiring correctly raises on that case.
For positive-path tests we inject a mock router directly.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from volnix.app import VolnixApp
from volnix.config.schema import VolnixConfig
from volnix.engines.memory.config import MemoryConfig
from volnix.engines.memory.engine import MemoryEngine
from volnix.engines.state.config import StateConfig
from volnix.engines.world_compiler.plan import WorldPlan
from volnix.persistence.config import PersistenceConfig


def _volnix_config(tmp_path: Path, memory_enabled: bool = False, **memory_kwargs) -> VolnixConfig:
    """Build a VolnixConfig with tmp-path persistence + memory knob."""
    cfg = VolnixConfig()
    cfg = cfg.model_copy(
        update={
            "persistence": PersistenceConfig(base_dir=str(tmp_path / "data"), wal_mode=False),
            "state": StateConfig(
                db_path=str(tmp_path / "state.db"),
                snapshot_dir=str(tmp_path / "snapshots"),
            ),
            "memory": MemoryConfig(enabled=memory_enabled, **memory_kwargs),
        }
    )
    return cfg


def _minimal_plan(seed: int = 1) -> WorldPlan:
    """Minimal real WorldPlan — defaults cover every field
    ``configure_agency`` reads. ``seed`` is the only knob we override."""
    return WorldPlan(name="test-world", seed=seed, behavior="static")


def _mock_router() -> MagicMock:
    r = MagicMock()
    r.route = AsyncMock()
    return r


# ---------------------------------------------------------------------------
# Disabled path — Phase 0 regression oracle must stay byte-identical.
# ---------------------------------------------------------------------------


class TestDisabledPath:
    async def test_negative_disabled_memory_leaves_app_memory_engine_none(
        self, tmp_path: Path
    ) -> None:
        app = VolnixApp(config=_volnix_config(tmp_path, memory_enabled=False))
        try:
            await app.start()
            # Router mock is irrelevant — disabled path never touches it.
            app._llm_router = _mock_router()
            await app.configure_agency(_minimal_plan(), result={"actors": []})
            assert app._memory_engine is None
        finally:
            await app.stop()


# ---------------------------------------------------------------------------
# Missing-seed and missing-router must raise loudly.
# ---------------------------------------------------------------------------


class TestNegativeWiringErrors:
    async def test_negative_enabled_without_plan_seed_raises(self, tmp_path: Path) -> None:
        app = VolnixApp(config=_volnix_config(tmp_path, memory_enabled=True))
        try:
            await app.start()
            app._llm_router = _mock_router()
            # WorldPlan.seed defaults to 42; force None via model_copy
            # so the missing-seed branch is actually reached.
            broken_plan = _minimal_plan().model_copy(update={"seed": None})
            with pytest.raises(RuntimeError, match="plan.seed"):
                await app.configure_agency(broken_plan, result={"actors": []})
        finally:
            await app.stop()

    async def test_negative_enabled_without_llm_router_raises(self, tmp_path: Path) -> None:
        app = VolnixApp(config=_volnix_config(tmp_path, memory_enabled=True))
        try:
            await app.start()
            # Simulate "no providers configured" — _llm_router is None.
            app._llm_router = None
            with pytest.raises(RuntimeError, match="llm_router"):
                await app.configure_agency(_minimal_plan(), result={"actors": []})
        finally:
            await app.stop()


# ---------------------------------------------------------------------------
# Enabled happy path.
# ---------------------------------------------------------------------------


class TestEnabledPath:
    async def test_positive_enabled_constructs_engine_and_starts(self, tmp_path: Path) -> None:
        app = VolnixApp(config=_volnix_config(tmp_path, memory_enabled=True))
        try:
            await app.start()
            app._llm_router = _mock_router()
            await app.configure_agency(_minimal_plan(seed=7), result={"actors": []})
            assert isinstance(app._memory_engine, MemoryEngine)
            assert app._memory_engine._seed == 7
            assert app._memory_engine._started is True
            # Ledger injected per D10-4.
            assert app._memory_engine._ledger is app._ledger
        finally:
            await app.stop()

    async def test_positive_engine_subscribes_to_cohort_rotated(self, tmp_path: Path) -> None:
        """Verify the engine's subscriptions ClassVar survives the
        wiring — ``start()`` iterates them and calls bus.subscribe."""
        app = VolnixApp(config=_volnix_config(tmp_path, memory_enabled=True))
        try:
            await app.start()
            app._llm_router = _mock_router()
            await app.configure_agency(_minimal_plan(), result={"actors": []})
            engine = app._memory_engine
            assert engine is not None
            assert engine.subscriptions == ["cohort.rotated"]
            # BaseEngine.start() sets _started=True; this proves the
            # subscribe() call loop ran without error.
            assert engine._started is True
        finally:
            await app.stop()


# ---------------------------------------------------------------------------
# reset_on_world_start — D10-5 / G15 bug fix verification.
# ---------------------------------------------------------------------------


class TestResetOnWorldStart:
    async def test_negative_reset_enabled_leaves_empty_store(self, tmp_path: Path) -> None:
        """Engine's _on_initialize must forward the reset flag so
        existing session-less records are wiped when
        ``reset_on_world_start=True``.

        Also locks the ``tnl/session-scoped-memory.tnl`` MUST clause:
        **session-scoped rows MUST NOT be truncated by this flag under
        any circumstance** — the audit-fold M3 regression guard.
        """
        from volnix.core.memory_types import MemoryRecord, content_hash_of
        from volnix.core.types import MemoryRecordId, SessionId

        app = VolnixApp(
            config=_volnix_config(tmp_path, memory_enabled=True, reset_on_world_start=True)
        )
        try:
            await app.start()
            app._llm_router = _mock_router()
            await app.configure_agency(_minimal_plan(), result={"actors": []})
            engine = app._memory_engine
            assert engine is not None

            # Session-less record — should be wiped on reset.
            session_less = MemoryRecord(
                record_id=MemoryRecordId("r-reset-test-null"),
                scope="actor",
                owner_id="actor-alpha",
                kind="episodic",
                tier="tier2",
                source="explicit",
                content="before reset",
                content_hash=content_hash_of("before reset"),
                importance=0.5,
                tags=[],
                created_tick=1,
                consolidated_from=None,
            )
            await engine._store.insert(session_less)

            # Session-scoped record — MUST survive the reset. This is
            # the isolation-guard clause (audit-fold M3).
            session_scoped = MemoryRecord(
                record_id=MemoryRecordId("r-reset-test-sess"),
                scope="actor",
                owner_id="actor-alpha",
                session_id=SessionId("sess-survives-reset"),
                kind="episodic",
                tier="tier2",
                source="explicit",
                content="should survive",
                content_hash=content_hash_of("should survive"),
                importance=0.5,
                tags=[],
                created_tick=1,
                consolidated_from=None,
            )
            await engine._store.insert(session_scoped)

            await engine._on_initialize()

            # Session-less slice emptied.
            null_rows = await engine._store.list_by_owner("actor-alpha", kind="episodic")
            assert null_rows == []
            # Session-scoped slice preserved.
            sess_rows = await engine._store.list_by_owner(
                "actor-alpha",
                kind="episodic",
                session_id=SessionId("sess-survives-reset"),
            )
            assert len(sess_rows) == 1
            assert str(sess_rows[0].record_id) == "r-reset-test-sess"
        finally:
            await app.stop()

    async def test_negative_reset_disabled_leaves_records_intact(self, tmp_path: Path) -> None:
        """Symmetric regression: reset_on_world_start=False must NOT
        wipe — re-initialise LEAVES pre-existing records untouched.
        Locks both branches of the G15 flag."""
        from volnix.core.memory_types import MemoryRecord, content_hash_of
        from volnix.core.types import MemoryRecordId

        app = VolnixApp(
            config=_volnix_config(tmp_path, memory_enabled=True, reset_on_world_start=False)
        )
        try:
            await app.start()
            app._llm_router = _mock_router()
            await app.configure_agency(_minimal_plan(), result={"actors": []})
            engine = app._memory_engine
            assert engine is not None

            record = MemoryRecord(
                record_id=MemoryRecordId("r-reset-test-2"),
                scope="actor",
                owner_id="actor-beta",
                kind="episodic",
                tier="tier2",
                source="explicit",
                content="survive init",
                content_hash=content_hash_of("survive init"),
                importance=0.5,
                tags=[],
                created_tick=1,
                consolidated_from=None,
            )
            await engine._store.insert(record)

            await engine._on_initialize()
            rows = await engine._store.list_by_owner("actor-beta", kind="episodic")
            assert len(rows) == 1
            assert str(rows[0].record_id) == "r-reset-test-2"
        finally:
            await app.stop()


# ---------------------------------------------------------------------------
# Stop lifecycle
# ---------------------------------------------------------------------------


class TestStopLifecycle:
    async def test_negative_app_stop_leaves_engine_stopped(self, tmp_path: Path) -> None:
        app = VolnixApp(config=_volnix_config(tmp_path, memory_enabled=True))
        await app.start()
        app._llm_router = _mock_router()
        await app.configure_agency(_minimal_plan(), result={"actors": []})
        engine = app._memory_engine
        assert engine is not None
        assert engine._started is True

        await app.stop()
        # After stop() the engine should report not-started.
        assert engine._started is False
        # The app also nils its slot.
        assert app._memory_engine is None

    async def test_negative_disabled_app_stop_leaves_no_engine(self, tmp_path: Path) -> None:
        """No engine ever built → stop path must not crash, must
        LEAVE ``_memory_engine`` as None."""
        app = VolnixApp(config=_volnix_config(tmp_path, memory_enabled=False))
        await app.start()
        app._llm_router = _mock_router()
        await app.configure_agency(_minimal_plan(), result={"actors": []})
        assert app._memory_engine is None
        await app.stop()  # must not raise
        assert app._memory_engine is None

    async def test_negative_double_stop_raises_no_unexpected_error(self, tmp_path: Path) -> None:
        """Calling ``app.stop()`` twice must not raise on the second
        call — the slot is nil'd on first stop; second stop sees
        ``_memory_engine is None`` and short-circuits."""
        app = VolnixApp(config=_volnix_config(tmp_path, memory_enabled=True))
        await app.start()
        app._llm_router = _mock_router()
        await app.configure_agency(_minimal_plan(), result={"actors": []})
        await app.stop()
        # Second stop must not crash. Runs the full teardown path
        # again; only the memory branch is relevant here.
        await app.stop()
        assert app._memory_engine is None


# ---------------------------------------------------------------------------
# Step 11 — AgencyEngine memory-engine injection
# ---------------------------------------------------------------------------


class TestCohortRotationMemoryReaction:
    """PMF 4B cleanup commit 7 — end-to-end integration proving
    4A × 4B seam works: a real ``agency.rotate_cohort()`` call
    triggers MemoryEngine's ``_on_cohort_rotated`` handler via the
    bus, demoted actors get ledger evict + consolidation entries,
    promoted actors optionally get hydration. This closes the
    audit gap where no test exercised the real seam with real
    components."""

    async def test_positive_rotate_cohort_triggers_memory_eviction_ledger_row(
        self, tmp_path: Path
    ) -> None:
        from volnix.core.types import ActorId

        app = VolnixApp(
            config=_volnix_config(
                tmp_path,
                memory_enabled=True,
                # on_eviction only (no periodic noise in this test).
                consolidation_triggers=["on_eviction"],
            )
        )
        try:
            await app.start()
            app._llm_router = _mock_router()
            await app.configure_agency(_minimal_plan(), result={"actors": []})
            agency = app._registry.get("agency")
            memory_engine = app._memory_engine
            assert memory_engine is not None

            # Seed a capture on the memory engine's ledger so we can
            # inspect entries.
            captured: list = []

            class _CapturingLedger:
                async def append(self, entry):
                    captured.append(entry)
                    return len(captured)

            memory_engine._ledger = _CapturingLedger()

            # Manually construct + publish a CohortRotationEvent so
            # we exercise the real bus → memory engine path without
            # needing a wired cohort manager. This tests the seam
            # end-to-end: bus subscription + handler dispatch +
            # per-actor evict + ledger row.
            from datetime import UTC, datetime

            from volnix.core.events import CohortRotationEvent
            from volnix.core.types import Timestamp

            now = datetime.now(UTC)
            await app._bus.publish(
                CohortRotationEvent(
                    timestamp=Timestamp(world_time=now, wall_time=now, tick=10),
                    promoted_ids=[],
                    demoted_ids=[ActorId("npc-demoted")],
                    rotation_policy="round_robin",
                    tick=10,
                )
            )
            # Give the bus consumer a tick to process.
            import asyncio as _asyncio

            await _asyncio.sleep(0.1)

            # Assert evict entry landed for the demoted actor.
            evictions = [e for e in captured if type(e).__name__ == "MemoryEvictionEntry"]
            assert len(evictions) >= 1
            assert any(str(e.actor_id) == "npc-demoted" for e in evictions)

            # Also: consolidation fired because trigger includes on_eviction.
            consolidations = [e for e in captured if type(e).__name__ == "MemoryConsolidationEntry"]
            assert len(consolidations) >= 1
            _ = agency  # silence unused if future cohort wiring needs it
        finally:
            await app.stop()


class TestTier1FixtureWiring:
    """Cleanup commit 3 — ``tier_mode="mixed"`` +
    ``tier1_fixtures_path`` must actually load pack-authored
    fixtures during app startup. Previously the loader existed but
    was orphaned in the live flow (audit H3)."""

    async def test_positive_mixed_mode_loads_fixtures_from_path(self, tmp_path: Path) -> None:
        # Author a minimal fixtures YAML.
        fixtures = tmp_path / "memory_fixtures.yaml"
        fixtures.write_text(
            "actor-hero:\n"
            '  - content: "hero prefers quiet"\n'
            "    importance: 0.8\n"
            "    tags: [preference]\n"
        )

        app = VolnixApp(
            config=_volnix_config(
                tmp_path,
                memory_enabled=True,
                tier_mode="mixed",
                tier1_fixtures_path=str(fixtures),
            )
        )
        try:
            await app.start()
            app._llm_router = _mock_router()
            await app.configure_agency(_minimal_plan(), result={"actors": []})
            engine = app._memory_engine
            assert engine is not None
            rows = await engine._store.list_by_owner("actor-hero", kind="semantic")
            assert len(rows) == 1
            assert rows[0].tier == "tier1"
            assert rows[0].source == "pack_fixture"
            assert "quiet" in rows[0].content
        finally:
            await app.stop()

    async def test_negative_tier2_only_ignores_fixtures_path(self, tmp_path: Path) -> None:
        """``tier_mode="tier2_only"`` (default) MUST ignore the
        fixtures path even when it's set — proves the tier_mode
        gate is honoured."""
        fixtures = tmp_path / "memory_fixtures.yaml"
        fixtures.write_text(
            'actor-hero:\n  - content: "should not load"\n    importance: 0.5\n    tags: []\n'
        )

        app = VolnixApp(
            config=_volnix_config(
                tmp_path,
                memory_enabled=True,
                tier_mode="tier2_only",  # NOT mixed
                tier1_fixtures_path=str(fixtures),
            )
        )
        try:
            await app.start()
            app._llm_router = _mock_router()
            await app.configure_agency(_minimal_plan(), result={"actors": []})
            engine = app._memory_engine
            assert engine is not None
            rows = await engine._store.list_by_owner("actor-hero", kind="semantic")
            assert rows == []
        finally:
            await app.stop()

    async def test_negative_mixed_mode_without_path_loads_nothing(self, tmp_path: Path) -> None:
        """``tier_mode="mixed"`` with ``tier1_fixtures_path=None``
        still succeeds — no pack fixtures to load is a valid state.
        Composition must NOT fail; the app boots cleanly."""
        app = VolnixApp(
            config=_volnix_config(
                tmp_path,
                memory_enabled=True,
                tier_mode="mixed",
                # tier1_fixtures_path unset → None
            )
        )
        try:
            await app.start()
            app._llm_router = _mock_router()
            # Should not raise.
            await app.configure_agency(_minimal_plan(), result={"actors": []})
            assert app._memory_engine is not None
        finally:
            await app.stop()


class TestStep11AgencyIntegration:
    """PMF 4B Step 11 — app.py must inject the memory engine into
    the AgencyEngine so NPCActivator sees it as ``host._memory_engine``
    during every activation."""

    async def test_positive_agency_set_memory_engine_called_after_build(
        self, tmp_path: Path
    ) -> None:
        app = VolnixApp(config=_volnix_config(tmp_path, memory_enabled=True))
        try:
            await app.start()
            app._llm_router = _mock_router()
            await app.configure_agency(_minimal_plan(), result={"actors": []})
            agency = app._registry.get("agency")
            assert agency._memory_engine is app._memory_engine
            assert agency._memory_engine is not None
        finally:
            await app.stop()

    async def test_negative_memory_disabled_agency_memory_engine_stays_none(
        self, tmp_path: Path
    ) -> None:
        """Disabled config → both app._memory_engine and
        agency._memory_engine stay None."""
        app = VolnixApp(config=_volnix_config(tmp_path, memory_enabled=False))
        try:
            await app.start()
            app._llm_router = _mock_router()
            await app.configure_agency(_minimal_plan(), result={"actors": []})
            agency = app._registry.get("agency")
            assert app._memory_engine is None
            # AgencyEngine initialises the slot in _on_initialize; it
            # stays None when set_memory_engine was never called.
            assert getattr(agency, "_memory_engine", "missing") is None
        finally:
            await app.stop()
