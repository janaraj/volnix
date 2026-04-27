"""Tests for ``VolnixApp.llm_router`` public property.

Locks ``tnl/volnix-app-public-llm-router.tnl``: the property
exposes the same instance held at ``_llm_router``, mirrors the
existing public-property convention (no guard, optimistic typing),
and is purely additive (the underscore field stays accessible).
"""

from __future__ import annotations

from pathlib import Path

from volnix.app import VolnixApp
from volnix.config.schema import VolnixConfig
from volnix.engines.state.config import StateConfig
from volnix.llm.config import LLMConfig, LLMProviderEntry
from volnix.llm.router import LLMRouter
from volnix.persistence.config import PersistenceConfig


def _volnix_config(tmp_path: Path) -> VolnixConfig:
    """Build a minimal VolnixConfig pointed at tmp persistence with
    a mock LLM provider (the router is only constructed when
    ``llm.providers`` is non-empty — see ``_initialize_llm`` in
    ``volnix/app.py``)."""
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
        }
    )
    return cfg


class TestLLMRouterProperty:
    def test_positive_property_exists_on_class(self) -> None:
        """TNL: ``VolnixApp`` MUST expose ``llm_router`` as a
        ``@property``. Class-level ``isinstance(..., property)`` is
        the precise check — captures it as a descriptor, not a
        regular attribute."""
        assert isinstance(getattr(VolnixApp, "llm_router", None), property), (
            "VolnixApp.llm_router must be a @property"
        )

    def test_negative_property_returns_none_before_start(self, tmp_path: Path) -> None:
        """TNL: pre-start access MUST NOT raise. Returns ``None``
        because ``_llm_router`` starts at ``None`` and is only
        wired during ``_initialize_llm()`` (step 4 of ``start()``).
        Matches every other public property on ``VolnixApp``."""
        app = VolnixApp(config=_volnix_config(tmp_path))
        # No await app.start() — verifying pre-start behavior.
        assert app.llm_router is None

    async def test_positive_property_returns_router_after_start(self, tmp_path: Path) -> None:
        """TNL: after ``start()``, the property returns the same
        instance internal callers see at ``_llm_router``."""
        app = VolnixApp(config=_volnix_config(tmp_path))
        try:
            await app.start()
            assert app.llm_router is not None
            assert isinstance(app.llm_router, LLMRouter)
            # Same instance, not a copy/proxy.
            assert app.llm_router is app._llm_router
        finally:
            await app.stop()

    async def test_positive_underscore_attribute_remains_accessible(self, tmp_path: Path) -> None:
        """TNL: the new property is additive — ``_llm_router``
        MUST remain present so internal callers continue to work
        (e.g., ``runtime._llm_router = self._llm_router`` at
        app.py:1119)."""
        app = VolnixApp(config=_volnix_config(tmp_path))
        try:
            await app.start()
            # Underscore name still works; not removed/renamed.
            assert hasattr(app, "_llm_router")
            assert app._llm_router is app.llm_router
        finally:
            await app.stop()
