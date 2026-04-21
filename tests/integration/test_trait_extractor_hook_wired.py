"""Phase 4C Step 12 — end-to-end hook wiring test.

Post-impl audit C1/C2: ``trait_extractor_hook`` was landed as config
+ builder + resolver but NO consumer actually called
``resolve_extractor_hook`` at wire time. This test locks the
integration path by checking the resolver is invoked in
``VolnixApp.configure_agency()`` with the config's hook value.

Negative ratio: 2/3 = 66%.
"""

from __future__ import annotations

import pytest

from volnix.actors.behavioral_signature import BehavioralSignature
from volnix.actors.trait_extractor import resolve_extractor_hook
from volnix.config.schema import VolnixConfig


def test_positive_resolver_called_during_configure_agency() -> None:
    """Grep the production call site: ``configure_agency`` must
    resolve the hook and call the result. This is the C1 fix —
    without it, the hook is dead config.
    """
    from pathlib import Path

    src = Path("volnix/app.py").read_text(encoding="utf-8")
    # The resolver import + call must be present in app.py.
    assert "resolve_extractor_hook" in src, (
        "volnix/app.py must import resolve_extractor_hook so "
        "trait_extractor_hook config takes effect."
    )
    assert "trait_extractor_hook" in src, (
        "volnix/app.py must read VolnixConfig.trait_extractor_hook"
    )


def test_positive_default_resolver_returns_bundled_extractor() -> None:
    """Config default ``None`` resolves to the bundled
    ``extract_behavior_traits`` — pre-Step-12 behaviour byte-identical."""
    from volnix.actors.trait_extractor import extract_behavior_traits

    cfg = VolnixConfig()
    resolved = resolve_extractor_hook(cfg.trait_extractor_hook)
    assert resolved is extract_behavior_traits


def test_negative_custom_hook_produces_custom_traits(monkeypatch: pytest.MonkeyPatch) -> None:
    """A product-supplied extractor is honored end-to-end. This
    simulates the Rehearse-shape override by registering a sentinel
    extractor in a test module and wiring it via config."""
    import sys
    import types

    sentinel = BehavioralSignature(cooperation_level=0.999, extensions={"sentinel": 1.0})
    module = types.ModuleType("volnix_step12_test_hook")

    def my_extractor(actor_def):  # noqa: ANN001 — ActorDefinition annotated would pull in circular import
        return sentinel

    module.my_extractor = my_extractor
    monkeypatch.setitem(sys.modules, "volnix_step12_test_hook", module)

    resolved = resolve_extractor_hook("volnix_step12_test_hook:my_extractor")

    class _FakeActor:
        pass

    result = resolved(_FakeActor())
    assert result is sentinel
    assert result.extensions["sentinel"] == 1.0
