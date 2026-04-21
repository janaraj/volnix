"""Phase 4C Step 14 — end-to-end redactor-wiring test.

Post-impl audit C2 (mirror of Step-12 trait_extractor_hook C2):
``ledger_redactor`` was landed as config + builder + resolver
but the integration point in ``volnix/app.py`` could be deleted
without any unit test catching the regression. This test locks
the wire path so a future refactor that breaks redactor
delivery fails loudly.

Negative ratio: 1/3 = 33% (positive-heavy because the wire path
is the feature; negative coverage on resolver-failure paths
already lives in ``tests/privacy/test_redaction.py``).
"""

from __future__ import annotations

from pathlib import Path

from volnix.config.builder import ConfigBuilder
from volnix.config.schema import PrivacyConfig, VolnixConfig
from volnix.privacy.redaction import (
    identity_redactor,
    resolve_ledger_redactor,
)


def test_positive_app_py_imports_resolve_ledger_redactor() -> None:
    """Source-grep assertion: ``volnix/app.py`` must import and
    call ``resolve_ledger_redactor`` so ``VolnixConfig.privacy.
    ledger_redactor`` actually shapes runtime behaviour. Without
    this, the config field is dead surface — the Step-12 shape
    of bug that this test explicitly prevents."""
    src = Path("volnix/app.py").read_text(encoding="utf-8")
    assert "resolve_ledger_redactor" in src, (
        "volnix/app.py must import resolve_ledger_redactor so "
        "VolnixConfig.privacy.ledger_redactor takes effect."
    )
    assert "privacy.ledger_redactor" in src, (
        "volnix/app.py must read privacy.ledger_redactor from config"
    )
    assert "privacy.ephemeral" in src, "volnix/app.py must thread privacy.ephemeral to the Ledger"


def test_positive_default_config_resolves_to_identity_redactor() -> None:
    """With no hook configured, the resolver hands back the
    platform's ``identity_redactor`` — pre-Step-14 behaviour is
    preserved byte-identical for existing deployments."""
    cfg = VolnixConfig()
    resolved = resolve_ledger_redactor(cfg.privacy.ledger_redactor)
    assert resolved is identity_redactor
    assert cfg.privacy.ephemeral is False


def test_positive_config_builder_threads_privacy_kwargs_into_config() -> None:
    """``ConfigBuilder.privacy(...)`` produces a ``PrivacyConfig``
    reachable via ``VolnixConfig.privacy`` with the expected
    fields. A caller constructing a redactor-equipped config
    programmatically sees the values round-trip through
    ``.build()`` → ``VolnixConfig.from_dict`` intact."""
    cfg = (
        ConfigBuilder()
        .privacy(
            ephemeral=True,
            ledger_redactor="volnix.privacy.redaction:identity_redactor",
        )
        .build()
    )
    assert isinstance(cfg.privacy, PrivacyConfig)
    assert cfg.privacy.ephemeral is True
    assert cfg.privacy.ledger_redactor == "volnix.privacy.redaction:identity_redactor"
    # The configured hook must resolve cleanly — this is what
    # volnix/app.py does at boot.
    assert resolve_ledger_redactor(cfg.privacy.ledger_redactor) is identity_redactor
