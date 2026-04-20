"""SessionManager — platform-session lifecycle driver (PMF Plan
Phase 4C Step 5).

Sibling of ``RunManager`` / ``WorldManager``. Not an engine.
Orchestrates session start / pause / resume / end; persists state
via ``SessionStore`` so sessions survive process restart; pins
slots through ``SlotManager`` with persistence coordinated via
``slot_assignments``.

Design decisions (from plan §Step 5 + audit-fold):

- **D5a.** Always-construct, opt-in-use. Sessions are always
  available at ``VolnixApp.start()``; unused if no caller invokes
  ``start()``.
- **D5b.** Not a BaseEngine — composition root builds it; no bus
  queue, no engine registry.
- **D5c.** ``end()`` invokes registered callbacks AND publishes
  the bus event. Callbacks awaited sequentially; a raising hook
  rolls the session back to ``ACTIVE`` AND does not append the
  ``SessionEndedEntry`` (audit C3 — ledger and store always
  agree).
- **D5d.** Slot pinning persists via ``SessionStore.pin_slot``;
  ``resume()`` restores pinnings into ``SlotManager`` through
  ``restore_assignment`` (which populates the binding AND the
  token dicts — audit H2).
- **D5e.** Seed derivation: ``INHERIT`` copies world seed;
  ``FRESH`` uses a stable blake2b hash of the session_id XOR
  world_seed; ``EXPLICIT`` records the caller value. ``FRESH``
  uses blake2b (not ``hash()``) so reproducibility holds across
  Python processes (audit C2).
"""

from __future__ import annotations

import hashlib
import logging
import uuid
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from volnix.core.errors import SessionNotFoundError
from volnix.core.events import (
    SessionEndedEvent,
    SessionPausedEvent,
    SessionResumedEvent,
    SessionStartedEvent,
)
from volnix.core.session import (
    SeedStrategy,
    Session,
    SessionCheckpointKind,
    SessionStatus,
    SessionType,
)
from volnix.core.types import ActorId, SessionId, Timestamp, WorldId
from volnix.ledger.entries import (
    SessionCheckpointEntry,
    SessionEndedEntry,
    SessionStartedEntry,
)
from volnix.sessions.store import SessionStore, SlotAssignment

if TYPE_CHECKING:
    from volnix.actors.slot_manager import SlotManager
    from volnix.bus.bus import EventBus
    from volnix.ledger.ledger import Ledger

logger = logging.getLogger(__name__)


SessionEndHook = Callable[[Session], Awaitable[None]]


def _generate_session_id(prefix: str = "sess-") -> SessionId:
    """Generate a 12-char session_id matching the ``run_id`` /
    ``world_id`` pattern. Not seeded — collision probability over
    2^48 is negligible."""
    return SessionId(f"{prefix}{uuid.uuid4().hex[:12]}")


def _stable_hash_u32(value: str) -> int:
    """Stable 32-bit hash independent of ``PYTHONHASHSEED`` — used
    for ``FRESH`` seed derivation so reproducibility holds across
    Python processes (audit-fold C2)."""
    digest = hashlib.blake2b(value.encode("utf-8"), digest_size=4).digest()
    return int.from_bytes(digest, "big")


def _derive_seed(
    strategy: SeedStrategy,
    session_id: SessionId,
    *,
    explicit_seed: int | None,
    world_seed: int | None,
) -> int:
    if strategy is SeedStrategy.EXPLICIT:
        if explicit_seed is None:
            raise ValueError("SeedStrategy.EXPLICIT requires explicit_seed")
        return explicit_seed
    if world_seed is None:
        raise ValueError(f"SeedStrategy.{strategy.name} requires world_seed")
    if strategy is SeedStrategy.INHERIT:
        return world_seed
    if strategy is SeedStrategy.FRESH:
        return world_seed ^ _stable_hash_u32(str(session_id))
    raise ValueError(f"unknown SeedStrategy: {strategy!r}")


def _now() -> datetime:
    return datetime.now(UTC)


def _timestamp(tick: int = 0) -> Timestamp:
    now = _now()
    return Timestamp(world_time=now, wall_time=now, tick=tick)


class SessionManager:
    """Lifecycle driver for platform Sessions."""

    def __init__(
        self,
        *,
        store: SessionStore,
        slot_manager: SlotManager | None = None,
        bus: EventBus | None = None,
        ledger: Ledger | None = None,
    ) -> None:
        self._store = store
        self._slot_manager = slot_manager
        self._bus = bus
        self._ledger = ledger
        self._end_hooks: list[SessionEndHook] = []

    # ── Lifecycle ─────────────────────────────────────────────────

    async def start(
        self,
        world_id: WorldId,
        session_type: SessionType = SessionType.BOUNDED,
        *,
        seed_strategy: SeedStrategy = SeedStrategy.INHERIT,
        seed: int | None = None,
        world_seed: int | None = None,
        start_tick: int = 0,
        metadata: dict[str, object] | None = None,
    ) -> Session:
        """Start a new session against ``world_id``. Returns the
        fully-populated ``Session`` after persisting + emitting
        ledger entry + bus event.

        Raises ``ValueError`` when the seed strategy needs a
        parameter the caller didn't supply (e.g., ``INHERIT``
        without ``world_seed``).
        """
        session_id = _generate_session_id()
        effective_seed = _derive_seed(
            seed_strategy,
            session_id,
            explicit_seed=seed,
            world_seed=world_seed,
        )
        now = _now()
        session = Session(
            session_id=session_id,
            world_id=world_id,
            session_type=session_type,
            status=SessionStatus.ACTIVE,
            seed_strategy=seed_strategy,
            seed=effective_seed,
            start_tick=start_tick,
            end_tick=None,
            created_at=now,
            updated_at=now,
            metadata=metadata or {},
        )
        await self._store.insert_session(session)
        await self._append_ledger(
            SessionStartedEntry(
                session_id=session_id,
                world_id=world_id,
                session_type=session_type.value,
                seed_strategy=seed_strategy.value,
                seed=effective_seed,
            )
        )
        await self._publish(
            SessionStartedEvent(
                timestamp=_timestamp(start_tick),
                session_id=session_id,
                world_id=world_id,
                session_type=session_type.value,
                seed_strategy=seed_strategy.value,
            )
        )
        return session

    async def get_session(self, session_id: SessionId) -> Session:
        session = await self._store.get_session(session_id)
        if session is None:
            raise SessionNotFoundError(str(session_id))
        return session

    async def pause(
        self,
        session_id: SessionId,
        *,
        tick: int = 0,
        note: str = "",
    ) -> Session:
        """Transition ACTIVE → PAUSED. Appends a checkpoint entry
        and publishes ``SessionPausedEvent`` (audit H5 — pause was
        previously ledger-only, breaking bus-consumer symmetry)."""
        session = await self.get_session(session_id)
        if session.status is not SessionStatus.ACTIVE:
            raise ValueError(
                f"cannot pause session {session_id!r} in status {session.status.value!r}"
            )
        updated = session.model_copy(
            update={
                "status": SessionStatus.PAUSED,
                "updated_at": _now(),
            }
        )
        await self._store.update_session(updated)
        await self._append_ledger(
            SessionCheckpointEntry(
                session_id=session_id,
                kind=SessionCheckpointKind.PAUSE,
                tick=tick,
                note=note,
            )
        )
        await self._publish(
            SessionPausedEvent(
                timestamp=_timestamp(tick),
                session_id=session_id,
                world_id=updated.world_id,
                paused_at_tick=tick,
                note=note,
            )
        )
        return updated

    async def resume(
        self,
        session_id: SessionId,
        *,
        tick: int | None = None,
    ) -> Session:
        """Transition PAUSED → ACTIVE + re-hydrate slot assignments
        into the injected ``SlotManager`` (D5d)."""
        session = await self.get_session(session_id)
        if session.status is not SessionStatus.PAUSED:
            raise ValueError(
                f"cannot resume session {session_id!r} in status {session.status.value!r}"
            )
        updated = session.model_copy(
            update={
                "status": SessionStatus.ACTIVE,
                "updated_at": _now(),
            }
        )
        await self._store.update_session(updated)
        # Re-hydrate slot assignments so ``SlotManager``'s in-memory
        # dicts reflect the persisted state after a restart.
        if self._slot_manager is not None:
            assignments = await self._store.list_slot_assignments(session_id)
            for a in assignments:
                self._slot_manager.restore_assignment(
                    actor_id=a.actor_id,
                    agent_name=a.slot_name,
                    token=a.token,
                )
        resumed_at = tick if tick is not None else updated.start_tick
        await self._append_ledger(
            SessionCheckpointEntry(
                session_id=session_id,
                kind=SessionCheckpointKind.RESUME,
                tick=resumed_at,
            )
        )
        await self._publish(
            SessionResumedEvent(
                timestamp=_timestamp(resumed_at),
                session_id=session_id,
                world_id=updated.world_id,
                resumed_at_tick=resumed_at,
            )
        )
        return updated

    async def end(
        self,
        session_id: SessionId,
        *,
        status: SessionStatus = SessionStatus.COMPLETED,
        end_tick: int | None = None,
        reason: str = "",
    ) -> Session:
        """Transition to a terminal status (``COMPLETED`` /
        ``ABANDONED``). On hook failure the session is rolled back
        to its prior status AND the ``SessionEndedEntry`` is NOT
        appended, so the ledger and store always agree
        (audit-fold C3)."""
        if status not in (SessionStatus.COMPLETED, SessionStatus.ABANDONED):
            raise ValueError(f"end() requires terminal status; got {status.value!r}")
        session = await self.get_session(session_id)
        if session.status in (
            SessionStatus.COMPLETED,
            SessionStatus.ABANDONED,
        ):
            raise ValueError(
                f"session {session_id!r} already terminal (status={session.status.value!r})"
            )
        updated = session.model_copy(
            update={
                "status": status,
                "end_tick": end_tick,
                "updated_at": _now(),
            }
        )
        await self._store.update_session(updated)
        # Invoke registered callbacks SEQUENTIALLY. A raising hook
        # propagates AND rolls the session back (audit C3: we
        # also skip appending the ledger entry so ledger + store
        # agree).
        for hook in list(self._end_hooks):
            try:
                await hook(updated)
            except BaseException:
                await self._store.update_session(session)
                raise
        # Append ledger + publish bus AFTER hooks succeed (audit C3).
        await self._append_ledger(
            SessionEndedEntry(
                session_id=session_id,
                world_id=updated.world_id,
                status=status.value,
                end_tick=end_tick,
                reason=reason,
            )
        )
        await self._publish(
            SessionEndedEvent(
                timestamp=_timestamp(end_tick or 0),
                session_id=session_id,
                world_id=updated.world_id,
                status=status.value,
                end_tick=end_tick,
                reason=reason,
            )
        )
        return updated

    async def checkpoint(
        self,
        session_id: SessionId,
        *,
        tick: int = 0,
        note: str = "",
    ) -> None:
        """Append a ``CHECKPOINT`` entry to the ledger. Rejects
        terminated sessions (audit-fold H6) — a checkpoint on a
        completed/abandoned session would pollute the audit
        timeline."""
        session = await self.get_session(session_id)
        if session.status in (
            SessionStatus.COMPLETED,
            SessionStatus.ABANDONED,
        ):
            raise ValueError(
                f"cannot checkpoint session {session_id!r} in terminal "
                f"status {session.status.value!r}"
            )
        await self._append_ledger(
            SessionCheckpointEntry(
                session_id=session_id,
                kind=SessionCheckpointKind.CHECKPOINT,
                tick=tick,
                note=note,
            )
        )

    # ── Slot pinning ─────────────────────────────────────────────

    async def pin_slot(
        self,
        session_id: SessionId,
        actor_id: ActorId,
        agent_name: str,
    ) -> str:
        """Pin a ``(session, slot)`` → ``(actor, token)`` mapping.

        Delegates to ``SlotManager.register`` for in-memory token
        minting then persists to ``slot_assignments`` so
        ``resume()`` can re-hydrate after a process restart.

        Returns the token assigned to the slot.
        """
        await self.get_session(session_id)  # raise if missing
        if self._slot_manager is None:
            raise RuntimeError("pin_slot requires a SlotManager; none was injected")
        result = self._slot_manager.register(actor_id, agent_name)
        if result is None:
            raise RuntimeError(
                f"SlotManager.register returned None for actor {actor_id!r}/agent {agent_name!r}"
            )
        token = result.agent_token  # audit H1 — field is agent_token
        await self._store.pin_slot(
            SlotAssignment(
                session_id=session_id,
                slot_name=agent_name,
                actor_id=actor_id,
                token=token,
                pinned_at=_now(),
            )
        )
        return token

    async def slots_for_session(
        self,
        session_id: SessionId,
    ) -> list[SlotAssignment]:
        """List current slot pinnings for a session in pin-order."""
        return await self._store.list_slot_assignments(session_id)

    # ── End-hook registration ────────────────────────────────────

    def register_on_session_end(self, hook: SessionEndHook) -> None:
        """Register a callback invoked (awaited) when ``end()``
        fires. Hooks run sequentially; a raising hook propagates
        AND rolls the session back to its prior status. No
        unregistration API today — long-lived managers accumulate
        callbacks (documented limitation; acceptable at 0.2.0)."""
        self._end_hooks.append(hook)

    # ── Internals ────────────────────────────────────────────────

    async def _append_ledger(self, entry: object) -> None:
        """Append to ledger when one is injected. Failures
        propagate — ledger writes are the "flight recorder" of the
        system (DESIGN_PRINCIPLES). Audit-fold M3: the prior
        narrow-except pattern silently swallowed ledger failures,
        breaking the "if it didn't produce a ledger entry, it
        didn't happen" invariant."""
        if self._ledger is None:
            return
        await self._ledger.append(entry)

    async def _publish(self, event: object) -> None:
        """Publish to bus when one is injected. Failures are logged
        but don't propagate — bus publish is a notification
        channel; a failed publish shouldn't break the lifecycle
        call path."""
        if self._bus is None:
            return
        try:
            await self._bus.publish(event)
        except (OSError, RuntimeError, ValueError) as exc:
            logger.warning(
                "SessionManager: bus publish failed for %s: %s",
                type(event).__name__,
                exc,
            )


__all__ = ["SessionManager"]
