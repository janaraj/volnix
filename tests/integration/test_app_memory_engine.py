"""Tests for ``VolnixApp.memory`` public property and
``VolnixApp.enable_memory(world_seed)`` helper.

Locks ``tnl/volnix-app-public-memory-engine.tnl``: explicit
opt-in for the 11th engine without going through
``configure_agency``. Bypasses ``config.memory.enabled`` (the
helper IS the explicit opt-in). Idempotent on the same seed;
seed-mismatch raises.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from volnix.app import VolnixApp
from volnix.config.schema import VolnixConfig
from volnix.engines.memory.config import MemoryConfig
from volnix.engines.memory.engine import MemoryEngine
from volnix.engines.state.config import StateConfig
from volnix.llm.config import LLMConfig, LLMProviderEntry
from volnix.persistence.config import PersistenceConfig


def _volnix_config(tmp_path: Path, *, memory_enabled: bool = False) -> VolnixConfig:
    """Build a minimal VolnixConfig with mock LLM provider so the
    LLM router is constructed during ``start()``. ``memory_enabled``
    governs the ``configure_agency`` auto-path; ``enable_memory``
    bypasses it regardless."""
    cfg = VolnixConfig()
    cfg = cfg.model_copy(
        update={
            "persistence": PersistenceConfig(base_dir=str(tmp_path / "data"), wal_mode=False),
            "state": StateConfig(
                db_path=str(tmp_path / "state.db"),
                snapshot_dir=str(tmp_path / "snapshots"),
            ),
            "llm": LLMConfig(
                defaults=LLMProviderEntry(type="mock", default_model="mock-1"),
                providers={"mock": LLMProviderEntry(type="mock")},
                routing={},
            ),
            "memory": MemoryConfig(enabled=memory_enabled),
        }
    )
    return cfg


# ─── Property descriptor ──────────────────────────────────────────


class TestMemoryPropertyShape:
    def test_positive_memory_property_exists_on_class(self) -> None:
        """TNL: ``VolnixApp.memory`` MUST be a ``@property`` descriptor."""
        assert isinstance(getattr(VolnixApp, "memory", None), property), (
            "VolnixApp.memory must be a @property"
        )

    def test_negative_memory_property_returns_none_before_construction(
        self, tmp_path: Path
    ) -> None:
        """TNL: pre-construction access MUST NOT raise; returns ``None``.
        Memory is optional unlike ``bus`` / ``ledger``."""
        app = VolnixApp(config=_volnix_config(tmp_path))
        # Pre-start — _memory_engine is None.
        assert app.memory is None


# ─── enable_memory helper ─────────────────────────────────────────


class TestEnableMemory:
    async def test_positive_enable_memory_constructs_engine(self, tmp_path: Path) -> None:
        """TNL: happy path — start app, call enable_memory, get a
        ``MemoryEngine`` back; ``app.memory`` is the same instance."""
        app = VolnixApp(config=_volnix_config(tmp_path, memory_enabled=False))
        try:
            await app.start()
            engine = await app.enable_memory(world_seed=42)
            assert isinstance(engine, MemoryEngine)
            assert app.memory is engine
            assert app.memory is app._memory_engine
        finally:
            await app.stop()

    async def test_negative_enable_memory_before_start_raises(self, tmp_path: Path) -> None:
        """TNL: calling before ``start()`` MUST raise ``RuntimeError``
        (no LLM router yet). Error message MUST instruct caller to
        call ``await app.start()`` first."""
        app = VolnixApp(config=_volnix_config(tmp_path))
        # No await app.start() — _llm_router is None.
        with pytest.raises(RuntimeError, match=r"app\.start\(\)"):
            await app.enable_memory(world_seed=42)

    async def test_positive_enable_memory_bypasses_config_memory_enabled(
        self, tmp_path: Path
    ) -> None:
        """TNL: helper MUST construct the engine even when
        ``config.memory.enabled is False``. The helper IS the
        explicit opt-in — caller doesn't have to flip TWO knobs."""
        app = VolnixApp(config=_volnix_config(tmp_path, memory_enabled=False))
        # Sanity: the auto-path config IS off.
        assert app._config.memory.enabled is False
        try:
            await app.start()
            engine = await app.enable_memory(world_seed=42)
            assert engine is not None
            assert isinstance(engine, MemoryEngine)
        finally:
            await app.stop()

    async def test_positive_enable_memory_idempotent_same_seed(self, tmp_path: Path) -> None:
        """TNL: second call with the SAME seed MUST return the
        existing engine (no reconstruction)."""
        app = VolnixApp(config=_volnix_config(tmp_path))
        try:
            await app.start()
            engine1 = await app.enable_memory(world_seed=42)
            engine2 = await app.enable_memory(world_seed=42)
            # Same instance — no reconstruction happened.
            assert engine1 is engine2
            assert app.memory is engine1
        finally:
            await app.stop()

    async def test_negative_enable_memory_different_seed_raises(self, tmp_path: Path) -> None:
        """TNL: second call with a DIFFERENT seed MUST raise
        ``RuntimeError``. Memory is seeded to a single world;
        reseeding mid-run is a wiring bug."""
        app = VolnixApp(config=_volnix_config(tmp_path))
        try:
            await app.start()
            await app.enable_memory(world_seed=42)
            with pytest.raises(RuntimeError, match=r"world_seed=99.*world_seed=42"):
                await app.enable_memory(world_seed=99)
        finally:
            await app.stop()

    async def test_positive_property_returns_engine_after_enable_memory(
        self, tmp_path: Path
    ) -> None:
        """TNL: after ``enable_memory``, ``app.memory`` returns the
        same instance internal callers see at ``_memory_engine``."""
        app = VolnixApp(config=_volnix_config(tmp_path))
        try:
            await app.start()
            await app.enable_memory(world_seed=7)
            assert app.memory is not None
            assert app.memory is app._memory_engine
        finally:
            await app.stop()

    async def test_positive_underscore_attribute_remains_accessible(self, tmp_path: Path) -> None:
        """TNL: ``_memory_engine`` MUST remain present so internal
        callers (configure_agency injection, stop() teardown)
        continue to work."""
        app = VolnixApp(config=_volnix_config(tmp_path))
        try:
            await app.start()
            await app.enable_memory(world_seed=42)
            assert hasattr(app, "_memory_engine")
            assert app._memory_engine is app.memory
        finally:
            await app.stop()


# ─── configure_agency interaction ─────────────────────────────────


class TestConfigureAgencyInteraction:
    """The memory-block of ``configure_agency`` is extracted as
    ``_maybe_setup_memory_engine(plan, agency)`` so the
    already-constructed-engine guard is testable in isolation
    without driving the rest of ``configure_agency``'s setup
    (registry lookups, actor extraction, world-context building)."""

    async def test_positive_setup_after_enable_memory_skips_construction(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """TNL: when ``enable_memory`` ran first and an engine
        already exists, ``_maybe_setup_memory_engine`` MUST skip
        the construction call and proceed directly to the agency-
        injection step.

        Verified via a spy on the build helper: after enable_memory's
        construction, calling the setup MUST NOT invoke
        ``_build_and_start_memory_engine`` again."""
        from unittest.mock import MagicMock

        app = VolnixApp(config=_volnix_config(tmp_path, memory_enabled=True))
        try:
            await app.start()
            engine = await app.enable_memory(world_seed=42)

            # Spy on the helper *after* enable_memory has already
            # constructed the engine.
            call_count = {"n": 0}
            real_helper = app._build_and_start_memory_engine

            async def _spy_helper(*args: object, **kwargs: object) -> object:
                call_count["n"] += 1
                return await real_helper(*args, **kwargs)

            monkeypatch.setattr(app, "_build_and_start_memory_engine", _spy_helper)

            mock_agency = MagicMock()
            mock_agency.set_memory_engine = MagicMock()

            class _Plan:
                seed = 42

            await app._maybe_setup_memory_engine(_Plan(), mock_agency)

            # No reconstruction: engine already existed.
            assert call_count["n"] == 0, (
                f"_maybe_setup_memory_engine invoked the build helper "
                f"{call_count['n']} time(s) despite engine already existing"
            )
            # Engine identity preserved.
            assert app.memory is engine
            # Agency injection STILL happened.
            mock_agency.set_memory_engine.assert_called_once_with(engine)
        finally:
            await app.stop()

    async def test_positive_setup_constructs_when_no_prior_engine(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """TNL Phase 0 oracle: when ``enable_memory`` was NOT called
        and ``config.memory.enabled=True``, the setup MUST construct
        the engine via ``_build_and_start_memory_engine`` (the
        existing auto-path stays byte-identical)."""
        from unittest.mock import MagicMock

        app = VolnixApp(config=_volnix_config(tmp_path, memory_enabled=True))
        try:
            await app.start()
            assert app.memory is None  # No prior enable_memory.

            call_count = {"n": 0}
            real_helper = app._build_and_start_memory_engine

            async def _spy_helper(*args: object, **kwargs: object) -> object:
                call_count["n"] += 1
                return await real_helper(*args, **kwargs)

            monkeypatch.setattr(app, "_build_and_start_memory_engine", _spy_helper)

            mock_agency = MagicMock()
            mock_agency.set_memory_engine = MagicMock()

            class _Plan:
                seed = 42

            await app._maybe_setup_memory_engine(_Plan(), mock_agency)

            assert call_count["n"] == 1, "auto-path MUST construct exactly once"
            assert app.memory is not None
            mock_agency.set_memory_engine.assert_called_once_with(app.memory)
        finally:
            await app.stop()

    async def test_negative_setup_skips_when_config_disabled_and_no_prior_engine(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """TNL Phase 0 oracle: when ``enable_memory`` was NOT called
        AND ``config.memory.enabled=False``, the setup MUST be a
        no-op (no construction, no injection). Existing apps without
        memory keep working byte-identically."""
        from unittest.mock import MagicMock

        app = VolnixApp(config=_volnix_config(tmp_path, memory_enabled=False))
        try:
            await app.start()

            call_count = {"n": 0}
            real_helper = app._build_and_start_memory_engine

            async def _spy_helper(*args: object, **kwargs: object) -> object:
                call_count["n"] += 1
                return await real_helper(*args, **kwargs)

            monkeypatch.setattr(app, "_build_and_start_memory_engine", _spy_helper)

            mock_agency = MagicMock()
            mock_agency.set_memory_engine = MagicMock()

            class _Plan:
                seed = 42

            await app._maybe_setup_memory_engine(_Plan(), mock_agency)

            assert call_count["n"] == 0
            assert app.memory is None
            mock_agency.set_memory_engine.assert_not_called()
        finally:
            await app.stop()
