"""Phase 4C Step 5 — slot-pinning lifecycle tests.

Exercises ``SessionManager.pin_slot``, ``slots_for_session``, and
the ``SlotManager.restore_assignment`` path that ``resume()``
triggers.

Negative ratio: 3/6 = 50%.
"""

from __future__ import annotations

import pytest

from volnix.actors.definition import ActorDefinition
from volnix.actors.registry import ActorRegistry
from volnix.actors.slot_manager import SlotManager
from volnix.core.types import ActorId, ActorType, SessionId, WorldId
from volnix.persistence.manager import create_database
from volnix.sessions.manager import SessionManager
from volnix.sessions.store import SessionStore


def _make_actor(actor_id: str, role: str = "exec") -> ActorDefinition:
    return ActorDefinition(
        id=ActorId(actor_id),
        type=ActorType.AGENT,
        role=role,
    )


async def _make_manager_with_slot_manager() -> tuple[SessionManager, SlotManager, ActorRegistry]:
    db = await create_database(":memory:", wal_mode=False)
    store = SessionStore(db)
    await store.initialize()
    registry = ActorRegistry()
    slot_manager = SlotManager(actor_registry=registry)
    mgr = SessionManager(store=store, slot_manager=slot_manager)
    return mgr, slot_manager, registry


async def test_negative_pin_slot_without_slot_manager_raises() -> None:
    """``SessionManager`` with ``slot_manager=None`` rejects
    ``pin_slot`` loudly — Step 6 wires the SlotManager; callers
    that pin before then are a configuration bug."""
    db = await create_database(":memory:", wal_mode=False)
    store = SessionStore(db)
    await store.initialize()
    mgr = SessionManager(store=store, slot_manager=None)
    s = await mgr.start(WorldId("w-1"), world_seed=1)
    with pytest.raises(RuntimeError, match="SlotManager"):
        await mgr.pin_slot(s.session_id, ActorId("a-1"), "ceo")


async def test_negative_pin_slot_for_unknown_session_raises() -> None:
    from volnix.core.errors import SessionNotFoundError

    mgr, _, registry = await _make_manager_with_slot_manager()
    registry.register(_make_actor("a-1"))
    with pytest.raises(SessionNotFoundError):
        await mgr.pin_slot(SessionId("sess-nope"), ActorId("a-1"), "ceo")


async def test_negative_restore_assignment_idempotent() -> None:
    """Audit-fold H2: ``restore_assignment`` must be idempotent —
    two calls with the same token for the same actor yield the
    same in-memory state (no duplicate tokens)."""
    mgr, slot_manager, registry = await _make_manager_with_slot_manager()
    registry.register(_make_actor("a-1"))

    slot_manager.restore_assignment(
        actor_id=ActorId("a-1"),
        agent_name="ceo",
        token="tok-fixed",
    )
    slot_manager.restore_assignment(
        actor_id=ActorId("a-1"),
        agent_name="ceo",
        token="tok-fixed",
    )
    # Only one (actor, token) mapping in either direction.
    assert slot_manager.resolve_token("tok-fixed") == ActorId("a-1")
    assert slot_manager._actor_tokens["a-1"] == "tok-fixed"
    # And the binding reports the slot claimed (audit H2).
    assert slot_manager._binding.is_slot_claimed(ActorId("a-1")) is True


async def test_positive_pin_slot_persists_assignment() -> None:
    mgr, slot_manager, registry = await _make_manager_with_slot_manager()
    registry.register(_make_actor("a-1"))
    s = await mgr.start(WorldId("w-1"), world_seed=1)
    token = await mgr.pin_slot(s.session_id, ActorId("a-1"), "ceo")
    assert token  # non-empty
    # Persisted in the store.
    assignments = await mgr.slots_for_session(s.session_id)
    assert len(assignments) == 1
    assert assignments[0].actor_id == ActorId("a-1")
    assert assignments[0].token == token


async def test_positive_slots_for_session_lists_in_pin_order() -> None:
    mgr, slot_manager, registry = await _make_manager_with_slot_manager()
    registry.register(_make_actor("a-1"))
    registry.register(_make_actor("a-2"))
    s = await mgr.start(WorldId("w-1"), world_seed=1)
    await mgr.pin_slot(s.session_id, ActorId("a-1"), "ceo")
    await mgr.pin_slot(s.session_id, ActorId("a-2"), "cto")
    assignments = await mgr.slots_for_session(s.session_id)
    names = [a.slot_name for a in assignments]
    assert names == ["ceo", "cto"]


async def test_positive_restore_assignment_re_claims_slot_binding() -> None:
    """Audit-fold H2: after ``restore_assignment``,
    ``SlotBinding.is_slot_claimed`` reports the actor's slot as
    claimed — preventing a second agent from stealing it via
    ``register``."""
    _, slot_manager, registry = await _make_manager_with_slot_manager()
    registry.register(_make_actor("a-1"))
    slot_manager.restore_assignment(
        actor_id=ActorId("a-1"),
        agent_name="ceo",
        token="tok-restored",
    )
    # A second register attempt must fail — slot is already claimed.
    second = slot_manager.register(ActorId("a-1"), "attacker")
    assert second is None  # claim refused
