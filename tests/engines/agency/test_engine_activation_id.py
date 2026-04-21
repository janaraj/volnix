"""Phase 4C Step 8 — AgencyEngine lead-actor activation_id tests.

Locks the Step-8 rewrite of the lead-actor uuid4 generation site
at ``engine.py:1603``: when a session_id is wired via
``set_session_id``, the tool-loop entry MUST derive
``activation_id`` deterministically via ``generate_activation_id``
so ``ReplayLLMProvider`` can reproduce the run.

Negative ratio: 1/2 = 50%.
"""

from __future__ import annotations

from pathlib import Path


def test_negative_uuid4_removed_from_lead_actor_path() -> None:
    """The pre-Step-8 site at ``engine.py:1603`` used
    ``uuid.uuid4().hex[:12]`` directly. Step 8 swapped it for
    ``generate_activation_id`` — a source grep confirms the old
    call is gone so the deterministic derivation cannot regress
    silently.
    """
    src = Path("volnix/engines/agency/engine.py").read_text(encoding="utf-8")
    # No raw uuid4 literal truncated to 12 chars in the file at all.
    assert "uuid.uuid4()" not in src, (
        "AgencyEngine.engine.py must not call uuid.uuid4() directly; "
        "use volnix.core.types.generate_activation_id instead."
    )


def test_positive_generate_activation_id_imported_in_engine() -> None:
    """Locks the replacement: ``generate_activation_id`` is now
    the source of activation IDs on the lead-actor path."""
    src = Path("volnix/engines/agency/engine.py").read_text(encoding="utf-8")
    assert "generate_activation_id" in src, (
        "AgencyEngine.engine.py must import + use generate_activation_id"
    )
    assert "set_session_id" in src, (
        "AgencyEngine must expose set_session_id setter for SimulationRunner"
    )
