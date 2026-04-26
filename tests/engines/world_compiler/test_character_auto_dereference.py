"""Tests for ``WorldPlan.dereference_characters`` + the compiler's
auto-dereference hook + the ``VolnixApp.set_character_catalog``
setter (``tnl/world-plan-character-auto-dereference.tnl``).
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from volnix.actors.character import CharacterDefinition
from volnix.app import VolnixApp
from volnix.config.schema import VolnixConfig
from volnix.core.errors import WorldPlanValidationError
from volnix.engines.state.config import StateConfig
from volnix.engines.world_compiler.engine import WorldCompilerEngine
from volnix.engines.world_compiler.plan import WorldPlan
from volnix.kernel.registry import SemanticRegistry
from volnix.packs.registry import PackRegistry
from volnix.persistence.config import PersistenceConfig


def _character(cid: str, role: str = "interviewer") -> CharacterDefinition:
    """Build a minimal CharacterDefinition for tests."""
    return CharacterDefinition(
        id=cid,
        name=cid.replace("-", " ").title(),
        role=role,
        persona="A test character.",
    )


# ─── WorldPlan.dereference_characters helper ───────────────────────


class TestDereferenceCharactersHelper:
    """Value-object level tests — no compiler/app involved."""

    def test_positive_empty_characters_is_noop(self) -> None:
        """TNL: empty ``characters`` returns ``self`` unchanged."""
        plan = WorldPlan(name="x", characters=[])
        result = plan.dereference_characters({})
        assert result is plan  # identity preserved (no copy)

    def test_positive_appends_actor_specs_and_clears_characters(self) -> None:
        """TNL: returns NEW plan with ``actor_specs`` appended and
        ``characters=[]``."""
        catalog = {"interviewer": _character("interviewer")}
        plan = WorldPlan(name="x", characters=["interviewer"], actor_specs=[])
        result = plan.dereference_characters(catalog)
        assert result is not plan  # new instance
        assert result.characters == []
        assert len(result.actor_specs) == 1
        assert result.actor_specs[0]["id"] == "interviewer"

    def test_positive_preserves_existing_actor_specs(self) -> None:
        """Pre-existing ``actor_specs`` entries MUST persist;
        catalog dereferences APPEND, not replace."""
        catalog = {"interviewer": _character("interviewer")}
        existing = {"id": "manual-actor", "role": "user"}
        plan = WorldPlan(
            name="x",
            characters=["interviewer"],
            actor_specs=[existing],
        )
        result = plan.dereference_characters(catalog)
        assert len(result.actor_specs) == 2
        ids = {spec["id"] for spec in result.actor_specs}
        assert ids == {"manual-actor", "interviewer"}

    def test_negative_dangling_reference_lists_all(self) -> None:
        """TNL: dangling refs MUST raise ``WorldPlanValidationError``
        listing EVERY missing id (not just the first)."""
        catalog = {"interviewer": _character("interviewer")}
        plan = WorldPlan(
            name="x",
            characters=["interviewer", "missing-1", "missing-2"],
        )
        with pytest.raises(WorldPlanValidationError) as exc_info:
            plan.dereference_characters(catalog)
        msg = str(exc_info.value)
        assert "missing-1" in msg
        assert "missing-2" in msg

    def test_negative_id_collision_with_existing_actor_specs(self) -> None:
        """TNL: when a catalog character's ``to_actor_spec()`` id
        collides with an existing ``actor_specs`` entry, raise
        ``WorldPlanValidationError`` listing the conflicts."""
        catalog = {"interviewer": _character("interviewer")}
        plan = WorldPlan(
            name="x",
            characters=["interviewer"],
            actor_specs=[{"id": "interviewer", "role": "manual"}],
        )
        with pytest.raises(WorldPlanValidationError, match="interviewer"):
            plan.dereference_characters(catalog)


# ─── VolnixApp.set_character_catalog setter ───────────────────────


def _volnix_config(tmp_path: Path) -> VolnixConfig:
    return VolnixConfig().model_copy(
        update={
            "persistence": PersistenceConfig(base_dir=str(tmp_path / "data"), wal_mode=False),
            "state": StateConfig(
                db_path=str(tmp_path / "state.db"),
                snapshot_dir=str(tmp_path / "snapshots"),
            ),
        }
    )


class TestSetCharacterCatalogSetter:
    def test_positive_default_catalog_is_none(self, tmp_path: Path) -> None:
        """TNL: ``_character_catalog`` initialized to ``None`` so
        existing callers (no setter call) get byte-identical behavior."""
        app = VolnixApp(config=_volnix_config(tmp_path))
        assert app._character_catalog is None

    def test_positive_setter_stores_catalog(self, tmp_path: Path) -> None:
        app = VolnixApp(config=_volnix_config(tmp_path))
        catalog = {"interviewer": _character("interviewer")}
        app.set_character_catalog(catalog)
        assert app._character_catalog is catalog

    def test_positive_setter_idempotent(self, tmp_path: Path) -> None:
        """TNL: second call replaces silently."""
        app = VolnixApp(config=_volnix_config(tmp_path))
        app.set_character_catalog({"a": _character("a")})
        app.set_character_catalog({"b": _character("b")})
        assert "a" not in app._character_catalog
        assert "b" in app._character_catalog

    def test_positive_setter_clears_with_none(self, tmp_path: Path) -> None:
        app = VolnixApp(config=_volnix_config(tmp_path))
        app.set_character_catalog({"a": _character("a")})
        app.set_character_catalog(None)
        assert app._character_catalog is None

    async def test_negative_setter_after_start_raises(self, tmp_path: Path) -> None:
        """TNL: late-wired catalogs raise to prevent silent miss."""
        app = VolnixApp(config=_volnix_config(tmp_path))
        try:
            await app.start()
            with pytest.raises(RuntimeError, match="set_character_catalog must be called before"):
                app.set_character_catalog({"a": _character("a")})
        finally:
            await app.stop()


# ─── Compiler-side auto-dereference hook ──────────────────────────


async def _make_compiler(*, character_catalog: dict | None = None) -> WorldCompilerEngine:
    """Construct a compiler engine with optional character catalog."""
    kernel = SemanticRegistry()
    await kernel.initialize()
    engine = WorldCompilerEngine()
    config = {
        "default_seed": 42,
        "max_entities_per_type": 100,
        "_kernel": kernel,
        "_pack_registry": PackRegistry(),
        "_llm_router": None,  # lightweight path doesn't need it
        "_character_catalog": character_catalog,
    }
    bus = AsyncMock()
    await engine.initialize(config, bus)
    return engine


class TestCompilerAutoDereference:
    """The compiler's ``generate_world`` hook MUST call
    ``plan.dereference_characters`` when the catalog is wired AND
    ``plan.characters`` is non-empty. Both heavy and lightweight
    paths share the entry-point hook."""

    @pytest.mark.asyncio
    async def test_positive_lightweight_with_catalog_dereferences(self) -> None:
        """Catalog-wired + ``characters`` populated → compiler
        auto-dereferences. Asserts at the actor LIST level (not
        actor.id, since SimpleActorGenerator hash-suffixes ids
        downstream of the dereference)."""
        catalog = {"interviewer": _character("interviewer", role="panelist")}
        engine = await _make_compiler(character_catalog=catalog)
        plan = WorldPlan(name="x", lightweight=True, characters=["interviewer"])
        result = await engine.generate_world(plan)
        # One catalog entry → one actor in the result.
        assert len(result["actors"]) == 1
        # Role flows through the dereference + generator chain
        # unchanged, so it's the load-bearing assertion that the
        # dereference actually fed into actor expansion.
        assert result["actors"][0].role == "panelist"

    @pytest.mark.asyncio
    async def test_negative_no_catalog_warns_and_passes_through(self, caplog) -> None:
        """TNL: without a catalog wired, populating ``characters``
        logs a warning and proceeds unchanged (no auto-dereference,
        no error)."""
        import logging

        engine = await _make_compiler(character_catalog=None)
        plan = WorldPlan(name="x", lightweight=True, characters=["interviewer"])
        with caplog.at_level(logging.WARNING):
            result = await engine.generate_world(plan)
        # Compilation succeeded:
        assert "actors" in result
        # No actors derived from un-dereferenced characters:
        assert result["actors"] == []
        # Warning surfaced:
        assert any("no CharacterLoader catalog wired" in rec.getMessage() for rec in caplog.records)

    @pytest.mark.asyncio
    async def test_positive_empty_characters_no_warning(self, caplog) -> None:
        """TNL: empty ``characters`` MUST NOT trigger the warning."""
        import logging

        engine = await _make_compiler(character_catalog=None)
        plan = WorldPlan(name="x", lightweight=True, characters=[])
        with caplog.at_level(logging.WARNING):
            await engine.generate_world(plan)
        assert not any(
            "no CharacterLoader catalog wired" in rec.getMessage() for rec in caplog.records
        )

    @pytest.mark.asyncio
    async def test_positive_catalog_dangling_ref_raises_via_compiler(
        self,
    ) -> None:
        """Dangling refs in ``characters`` surface through the
        compiler's auto-dereference hook as
        ``WorldPlanValidationError``."""
        catalog = {"interviewer": _character("interviewer")}
        engine = await _make_compiler(character_catalog=catalog)
        plan = WorldPlan(
            name="x",
            lightweight=True,
            characters=["interviewer", "no-such-id"],
        )
        with pytest.raises(WorldPlanValidationError, match="no-such-id"):
            await engine.generate_world(plan)
