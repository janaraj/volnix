"""Phase 0 regression oracle: passive-NPC shape across shipped blueprints.

This test freezes a deterministic, compile-time view of every blueprint
that declares passive NPCs (``type: internal`` actors). The Active-NPC
feature (Plan Phase 1 onward) adds an optional ``activation_profile``
field to ``ActorDefinition``. Existing blueprints must NOT silently gain
that field — any such drift is a regression unless the snapshot is
intentionally regenerated in the same commit.

Why a compile-time invariant, not a full-run event-log hash:

Volnix compilation uses the LLM for entity generation, personality
generation, seed expansion, visibility rules, and subscriptions. Even
at a fixed world seed, real LLM calls are non-deterministic. Mock-LLM
runs avoid the flake but do not represent production behavior. A
runtime gate (``test_passive_human_actor_not_registered_as_state``)
belongs next to the code that could break it — Plan Phase 2 wires that
test alongside the ``app.py`` actor-loading change.

This test only needs ``yaml`` and the filesystem — it stays
deterministic and unblocks the whole plan.
"""

from __future__ import annotations

import json
from pathlib import Path

import yaml

# -- Paths --------------------------------------------------------------------

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
_BLUEPRINTS_DIR = _REPO_ROOT / "volnix" / "blueprints" / "official"
# Kept beside the test file rather than under any directory named
# ``snapshots/`` — the repo's top-level ``.gitignore:21`` excludes
# ``snapshots/`` everywhere (intended for runtime world snapshots),
# which would silently drop the regression oracle from version control.
_SNAPSHOT_PATH = Path(__file__).parent / "passive_npc_baseline.json"


# -- Inventory ----------------------------------------------------------------
#
# Blueprints that declare passive NPCs (``type: internal`` actors inside
# ``world.actors``). Determined by:
#     grep -l "type: internal" volnix/blueprints/official/*.yaml
#
# Kept explicit (not glob-derived) so that adding a new blueprint with
# passive NPCs forces a code edit here — which forces a PR reviewer to
# notice that the new blueprint is entering the regression gate.

_BLUEPRINTS_WITH_HUMAN: tuple[str, ...] = (
    "customer_support.yaml",
    "dynamic_support_center.yaml",
    "hubspot_sales_pipeline.yaml",
    "incident_response.yaml",
    "support_ticket_triage.yaml",
    "trading_competition.yaml",
)


# -- Shape capture ------------------------------------------------------------


def _capture_actor_shape(blueprint_yaml: dict) -> list[dict]:
    """Deterministic per-actor shape — the fields that decide active vs. passive.

    We capture ``role``, ``type``, ``count``, and the presence of the
    ``activation_profile`` key. We deliberately omit ``budget`` and
    ``permissions``: those are orthogonal to the passive/active decision
    and may legitimately change for unrelated reasons.
    """
    actors = blueprint_yaml.get("world", {}).get("actors", [])
    return [
        {
            "role": a.get("role"),
            "type": a.get("type", "external"),
            "count": a.get("count", 1),
            "has_activation_profile": "activation_profile" in a,
        }
        for a in actors
    ]


def _current_shapes() -> dict[str, list[dict]]:
    return {
        name: _capture_actor_shape(yaml.safe_load((_BLUEPRINTS_DIR / name).read_text()))
        for name in _BLUEPRINTS_WITH_HUMAN
    }


# -- Tests --------------------------------------------------------------------


def test_blueprint_inventory_covers_all_passive_npc_blueprints() -> None:
    """Every blueprint containing ``type: internal`` must be in the regression list.

    If a new blueprint lands with passive NPCs, this test fails until the
    reviewer adds it to ``_BLUEPRINTS_WITH_HUMAN`` — ensuring nothing
    silently slips past the Phase 0 gate.
    """
    on_disk = tuple(
        sorted(
            path.name
            for path in _BLUEPRINTS_DIR.glob("*.yaml")
            if "type: internal" in path.read_text()
        )
    )
    assert on_disk == _BLUEPRINTS_WITH_HUMAN, (
        "Blueprint inventory drift.\n"
        f"  Filesystem: {on_disk}\n"
        f"  Regression list: {_BLUEPRINTS_WITH_HUMAN}\n"
        "Add new blueprints with `type: internal` actors to "
        "_BLUEPRINTS_WITH_HUMAN in this file."
    )


def test_passive_npc_shape_matches_baseline_snapshot() -> None:
    """Passive-NPC shape must be byte-identical to the locked baseline.

    Fails if a blueprint silently gained (or lost) an ``activation_profile``,
    ``role``, ``type``, or ``count`` field. If the change is intentional,
    regenerate the snapshot in the same commit:

        python tests/integration/test_passive_npc_regression.py --regenerate
    """
    assert _SNAPSHOT_PATH.exists(), (
        f"Baseline snapshot missing at {_SNAPSHOT_PATH}. Run with --regenerate to bootstrap it."
    )
    baseline = json.loads(_SNAPSHOT_PATH.read_text())
    current = _current_shapes()
    assert current == baseline, (
        "Passive-NPC shape drift detected.\n"
        f"  Current:  {json.dumps(current, indent=2, sort_keys=True)}\n"
        f"  Baseline: {json.dumps(baseline, indent=2, sort_keys=True)}\n"
        "If intentional, regenerate the snapshot in the same commit."
    )


# -- Regeneration entry point (manual, explicit) ------------------------------

if __name__ == "__main__":
    import sys

    if "--regenerate" not in sys.argv:
        print(
            "Usage: python tests/integration/test_passive_npc_regression.py --regenerate",
            file=sys.stderr,
        )
        sys.exit(2)

    _SNAPSHOT_PATH.parent.mkdir(parents=True, exist_ok=True)
    _SNAPSHOT_PATH.write_text(json.dumps(_current_shapes(), indent=2, sort_keys=True) + "\n")
    print(f"Wrote baseline snapshot to {_SNAPSHOT_PATH}")
