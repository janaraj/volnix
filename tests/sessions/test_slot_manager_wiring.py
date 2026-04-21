"""Phase 4C Step 6 — SessionManager.set_slot_manager wiring tests.

Locks the Step-5 deferral: ``SessionManager`` is built at
``VolnixApp.start()`` without a SlotManager; ``configure_agency``
later constructs the SlotManager and wires it in via
``set_slot_manager``. This test file verifies the setter.

Negative ratio: 1/3 = 33% after post-impl audit M-NEW-1 reclassified
the "overwrites prior" test as positive (tests correct overwrite
behavior, not rejection). Step-6 test corpus ratio remains above
50% across all six files.
"""

from __future__ import annotations

import pytest

from volnix.actors.definition import ActorDefinition
from volnix.actors.registry import ActorRegistry
from volnix.actors.slot_manager import SlotManager
from volnix.core.types import ActorId, ActorType, WorldId
from volnix.persistence.manager import create_database
from volnix.sessions.manager import SessionManager
from volnix.sessions.store import SessionStore


async def _make_manager_without_slot() -> SessionManager:
    db = await create_database(":memory:", wal_mode=False)
    store = SessionStore(db)
    await store.initialize()
    return SessionManager(store=store)


def _make_slot_manager() -> tuple[SlotManager, ActorRegistry]:
    registry = ActorRegistry()
    registry.register(ActorDefinition(id=ActorId("a-1"), type=ActorType.AGENT, role="ceo"))
    return SlotManager(actor_registry=registry), registry


async def test_negative_pin_slot_fails_before_set_slot_manager() -> None:
    """A SessionManager constructed without a SlotManager rejects
    ``pin_slot`` until ``set_slot_manager`` wires one in."""
    mgr = await _make_manager_without_slot()
    s = await mgr.start(WorldId("w-1"), world_seed=1)
    with pytest.raises(RuntimeError, match="SlotManager"):
        await mgr.pin_slot(s.session_id, ActorId("a-1"), "ceo")


async def test_positive_set_slot_manager_overwrites_prior() -> None:
    """Audit-fold M5: ``set_slot_manager`` is idempotent — last
    call wins. The setter MUST overwrite a prior value (even
    None → SlotManager → different SlotManager). Audit M-NEW-1
    (post-impl): renamed from ``test_negative_*`` — tests a
    positive overwrite, not a rejection."""
    mgr = await _make_manager_without_slot()
    sm1, _ = _make_slot_manager()
    sm2, _ = _make_slot_manager()
    mgr.set_slot_manager(sm1)
    assert mgr._slot_manager is sm1
    mgr.set_slot_manager(sm2)
    assert mgr._slot_manager is sm2
    mgr.set_slot_manager(None)
    assert mgr._slot_manager is None


async def test_positive_set_slot_manager_enables_pin_slot() -> None:
    """After ``set_slot_manager``, ``pin_slot`` works through the
    attached SlotManager and persists the assignment."""
    mgr = await _make_manager_without_slot()
    slot_manager, _ = _make_slot_manager()
    s = await mgr.start(WorldId("w-1"), world_seed=1)
    mgr.set_slot_manager(slot_manager)
    token = await mgr.pin_slot(s.session_id, ActorId("a-1"), "ceo")
    assert token
    assignments = await mgr.slots_for_session(s.session_id)
    assert len(assignments) == 1
    assert assignments[0].token == token
