"""Tests for ``VolnixApp.session_manager`` public property.

Locks ``tnl/volnix-app-public-session-manager.tnl``: the property
exposes the same instance held at ``_session_manager``, mirrors the
existing public-property convention (no guard, optimistic typing),
and is purely additive (the underscore field stays accessible).
"""

from __future__ import annotations

from pathlib import Path

from volnix.app import VolnixApp
from volnix.config.schema import VolnixConfig
from volnix.engines.state.config import StateConfig
from volnix.persistence.config import PersistenceConfig
from volnix.sessions.manager import SessionManager


def _volnix_config(tmp_path: Path) -> VolnixConfig:
    """Build a minimal VolnixConfig pointed at tmp persistence."""
    cfg = VolnixConfig()
    cfg = cfg.model_copy(
        update={
            "persistence": PersistenceConfig(base_dir=str(tmp_path / "data"), wal_mode=False),
            "state": StateConfig(
                db_path=str(tmp_path / "state.db"),
                snapshot_dir=str(tmp_path / "snapshots"),
            ),
        }
    )
    return cfg


class TestSessionManagerProperty:
    def test_positive_property_exists_on_class(self) -> None:
        """TNL: ``VolnixApp`` MUST expose ``session_manager`` as a
        ``@property``. Class-level ``isinstance(..., property)`` is the
        precise check — captures it as a descriptor, not a regular
        attribute."""
        assert isinstance(getattr(VolnixApp, "session_manager", None), property), (
            "VolnixApp.session_manager must be a @property"
        )

    def test_negative_property_returns_none_before_start(self, tmp_path: Path) -> None:
        """TNL: pre-start access MUST NOT raise. Returns ``None``
        because ``_session_manager`` starts at ``None`` and is only
        wired during ``start()``. Matches every other public property
        on ``VolnixApp``."""
        app = VolnixApp(config=_volnix_config(tmp_path))
        # No await app.start() — verifying pre-start behavior.
        assert app.session_manager is None

    async def test_positive_property_returns_session_manager_after_start(
        self, tmp_path: Path
    ) -> None:
        """TNL: after ``start()``, the property returns the same
        instance internal callers see at ``_session_manager``."""
        app = VolnixApp(config=_volnix_config(tmp_path))
        try:
            await app.start()
            assert app.session_manager is not None
            assert isinstance(app.session_manager, SessionManager)
            # Same instance, not a copy/proxy.
            assert app.session_manager is app._session_manager
        finally:
            await app.stop()

    async def test_positive_underscore_attribute_remains_accessible(self, tmp_path: Path) -> None:
        """TNL: the new property is additive — ``_session_manager``
        MUST remain present so internal callers continue to work."""
        app = VolnixApp(config=_volnix_config(tmp_path))
        try:
            await app.start()
            # Underscore name still works; not removed/renamed.
            assert hasattr(app, "_session_manager")
            assert app._session_manager is app.session_manager
        finally:
            await app.stop()
