"""Phase 4C Step 5 — session continuity tests.

Locks the "server-restart survival" contract: a session persisted
before a `SessionManager` is torn down must be fully resumable by
a freshly-constructed `SessionManager` pointing at the same
database. Locks the `slot_manager` re-hydration path too.

Negative ratio: 2/4 = 50%.
"""

from __future__ import annotations

import pytest

from volnix.actors.definition import ActorDefinition
from volnix.actors.registry import ActorRegistry
from volnix.actors.slot_manager import SlotManager
from volnix.core.session import SessionStatus
from volnix.core.types import ActorId, ActorType, WorldId
from volnix.persistence.manager import create_database
from volnix.sessions.manager import SessionManager
from volnix.sessions.store import SessionStore


async def _make_store():
    # Use a shared aiosqlite connection via file mode so two
    # SessionManager instances built on the same path observe the
    # same data. We use a tmp_path-managed file in test bodies.
    pass


async def test_negative_terminated_session_resume_raises() -> None:
    """A completed / abandoned session cannot be resumed — the
    status transition guard rejects it even after store round-trip."""
    db = await create_database(":memory:", wal_mode=False)
    store = SessionStore(db)
    await store.initialize()
    mgr = SessionManager(store=store)
    s = await mgr.start(WorldId("w-1"), world_seed=1)
    await mgr.end(s.session_id)
    with pytest.raises(ValueError, match="cannot resume"):
        await mgr.resume(s.session_id)


async def test_negative_resume_replays_slots_without_duplication(
    tmp_path,
) -> None:
    """Audit-fold H2 continuity: on resume, every persisted slot
    assignment is replayed INTO the slot manager exactly once. A
    duplicate restore would mint conflicting binding state."""
    db_path = str(tmp_path / "sessions.db")
    db = await create_database(db_path, wal_mode=False)
    store = SessionStore(db)
    await store.initialize()

    registry = ActorRegistry()
    registry.register(ActorDefinition(id=ActorId("a-1"), type=ActorType.AGENT, role="ceo"))
    slot_manager = SlotManager(actor_registry=registry)
    mgr = SessionManager(store=store, slot_manager=slot_manager)

    s = await mgr.start(WorldId("w-1"), world_seed=1)
    token = await mgr.pin_slot(s.session_id, ActorId("a-1"), "ceo")
    await mgr.pause(s.session_id)
    await mgr.resume(s.session_id)

    # After resume the token still resolves to the actor AND the
    # binding reports claimed. No "token2" duplication.
    assert slot_manager.resolve_token(token) == ActorId("a-1")
    assert slot_manager._actor_tokens["a-1"] == token
    assert slot_manager._binding.is_slot_claimed(ActorId("a-1")) is True


async def test_positive_session_survives_session_manager_reconstruction(
    tmp_path,
) -> None:
    """The ship goal: a session persisted by one ``SessionManager``
    instance is fully readable by a FRESHLY-constructed
    ``SessionManager`` that opens the same database file —
    simulates the process-restart scenario."""
    db_path = str(tmp_path / "sessions.db")
    db1 = await create_database(db_path, wal_mode=False)
    store1 = SessionStore(db1)
    await store1.initialize()
    mgr1 = SessionManager(store=store1)
    original = await mgr1.start(WorldId("w-1"), world_seed=42)
    await mgr1.pause(original.session_id)
    await db1.close()

    # Simulate process restart: brand-new ConnectionManager /
    # SessionManager / SessionStore pointed at the same file.
    db2 = await create_database(db_path, wal_mode=False)
    store2 = SessionStore(db2)
    await store2.initialize()
    mgr2 = SessionManager(store=store2)
    recovered = await mgr2.get_session(original.session_id)
    assert recovered.status is SessionStatus.PAUSED
    assert recovered.world_id == original.world_id
    assert recovered.seed == original.seed


async def test_positive_resume_after_restart_rehydrates_slot_manager(
    tmp_path,
) -> None:
    """End-to-end continuity: pin a slot, pause, restart, build
    a new manager + slot manager, resume → the slot manager's
    in-memory dicts reflect the persisted pinning."""
    db_path = str(tmp_path / "sessions.db")

    # Phase 1: pin + pause.
    db1 = await create_database(db_path, wal_mode=False)
    store1 = SessionStore(db1)
    await store1.initialize()
    registry1 = ActorRegistry()
    registry1.register(ActorDefinition(id=ActorId("a-1"), type=ActorType.AGENT, role="ceo"))
    slot_manager1 = SlotManager(actor_registry=registry1)
    mgr1 = SessionManager(store=store1, slot_manager=slot_manager1)
    session = await mgr1.start(WorldId("w-1"), world_seed=1)
    persisted_token = await mgr1.pin_slot(session.session_id, ActorId("a-1"), "ceo")
    await mgr1.pause(session.session_id)
    await db1.close()

    # Phase 2: fresh manager + slot manager, resume.
    db2 = await create_database(db_path, wal_mode=False)
    store2 = SessionStore(db2)
    await store2.initialize()
    registry2 = ActorRegistry()
    # NOTE: registry2 is empty — restore trusts persisted data
    # without re-checking the registry.
    slot_manager2 = SlotManager(actor_registry=registry2)
    mgr2 = SessionManager(store=store2, slot_manager=slot_manager2)
    await mgr2.resume(session.session_id)

    # The new slot manager has the original token+actor wired up.
    assert slot_manager2.resolve_token(persisted_token) == ActorId("a-1")
