"""Architecture guards for volnix/core/*.

G2 of the Phase 4B gap analysis: ``volnix/core/*`` must not import
from ``volnix/engines/*``. This test fails CI on any regression
(the first draft of Phase 4B tried to do exactly this, hence the
guard).
"""

from __future__ import annotations

import pytest

from tests.architecture.helpers import PRODUCT_ROOT, find_import_offenders, rel_repo_path

pytestmark = pytest.mark.architecture


def _core_file_importing_engines(module: str) -> bool:
    return module.startswith("volnix.engines.")


def test_core_does_not_import_from_engines() -> None:
    """Every file under volnix/core/* must not import from
    volnix/engines/*. Engines depend on core, never the reverse —
    otherwise a circular dependency forms and core becomes
    load-bearing for every engine that core happens to reference.
    """
    core_dir = PRODUCT_ROOT / "core"
    offenders = find_import_offenders(core_dir, _core_file_importing_engines)
    assert not offenders, (
        "volnix/core/* must not import from volnix/engines/*:\n"
        + "\n".join(
            f"  {path}: {', '.join(mods)}" for path, mods in sorted(offenders.items())
        )
    )


def test_core_protocols_only_imports_core() -> None:
    """Stricter guard specifically for ``core/protocols.py`` — it is
    imported by every engine, so any engine import here makes every
    consumer transitively depend on that engine. Only core siblings
    are permitted.
    """
    from tests.architecture.helpers import imported_modules

    protocols_file = PRODUCT_ROOT / "core" / "protocols.py"
    mods = imported_modules(protocols_file)
    offenders = sorted(m for m in mods if m.startswith("volnix.") and not m.startswith("volnix.core"))
    assert not offenders, (
        f"{rel_repo_path(protocols_file)} imports from non-core volnix modules: "
        f"{offenders}. Protocol types must live in volnix.core.*."
    )
