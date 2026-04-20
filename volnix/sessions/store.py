"""SQLite persistence for SessionManager (PMF Plan Phase 4C Step 5).

Two tables: ``sessions`` (one row per Session) and
``slot_assignments`` (one row per pinned slot, keyed on
``(session_id, slot_name)``). Schema created idempotently on
``initialize()``; no external migration tooling at this step (a
future step adding a column must drop-and-recreate or add an
ALTER; documented in the plan).

Public surface via ``volnix.sessions``: ``SlotAssignment``. The
``SessionStore`` class itself is package-private.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from volnix.core.session import (
    SeedStrategy,
    Session,
    SessionStatus,
    SessionType,
)
from volnix.core.types import ActorId, SessionId, WorldId

if TYPE_CHECKING:
    from volnix.persistence.sqlite import Database


@dataclass(frozen=True)
class SlotAssignment:
    """One ``(session, slot)`` → ``(actor, token)`` pinning."""

    session_id: SessionId
    slot_name: str
    actor_id: ActorId
    token: str
    pinned_at: datetime


_SCHEMA_SESSIONS = """
CREATE TABLE IF NOT EXISTS sessions (
    session_id     TEXT PRIMARY KEY,
    world_id       TEXT NOT NULL,
    session_type   TEXT NOT NULL,
    status         TEXT NOT NULL,
    seed_strategy  TEXT NOT NULL,
    seed           INTEGER NOT NULL,
    start_tick     INTEGER NOT NULL DEFAULT 0,
    end_tick       INTEGER,
    created_at     TEXT NOT NULL,
    updated_at     TEXT NOT NULL,
    metadata_json  TEXT NOT NULL DEFAULT '{}'
)
"""

_SCHEMA_SLOT_ASSIGNMENTS = """
CREATE TABLE IF NOT EXISTS slot_assignments (
    session_id  TEXT NOT NULL,
    slot_name   TEXT NOT NULL,
    actor_id    TEXT NOT NULL,
    token       TEXT NOT NULL,
    pinned_at   TEXT NOT NULL,
    PRIMARY KEY (session_id, slot_name),
    FOREIGN KEY (session_id) REFERENCES sessions(session_id)
)
"""

_INDICES = (
    "CREATE INDEX IF NOT EXISTS idx_sessions_world_id ON sessions(world_id)",
    "CREATE INDEX IF NOT EXISTS idx_sessions_status ON sessions(status)",
    "CREATE INDEX IF NOT EXISTS idx_slot_assignments_session ON slot_assignments(session_id)",
)


class SessionStore:
    """SQLite-backed persistence for sessions + slot assignments."""

    def __init__(self, db: Database) -> None:
        self._db = db
        self._initialized = False

    async def initialize(self) -> None:
        """Create tables + indices. Safe to call multiple times —
        ``CREATE TABLE IF NOT EXISTS`` makes repeat calls a no-op.
        The instance-level flag short-circuits on the second call to
        avoid repeated round-trips."""
        if self._initialized:
            return
        await self._db.execute(_SCHEMA_SESSIONS)
        await self._db.execute(_SCHEMA_SLOT_ASSIGNMENTS)
        for stmt in _INDICES:
            await self._db.execute(stmt)
        self._initialized = True

    # ── Session CRUD ──────────────────────────────────────────────

    async def insert_session(self, session: Session) -> None:
        await self._db.execute(
            "INSERT INTO sessions (session_id, world_id, session_type, "
            "status, seed_strategy, seed, start_tick, end_tick, "
            "created_at, updated_at, metadata_json) VALUES "
            "(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                str(session.session_id),
                str(session.world_id),
                session.session_type.value,
                session.status.value,
                session.seed_strategy.value,
                session.seed,
                session.start_tick,
                session.end_tick,
                _iso_required(session.created_at),
                _iso_required(session.updated_at),
                json.dumps(session.metadata),
            ),
        )

    async def update_session(self, session: Session) -> None:
        await self._db.execute(
            "UPDATE sessions SET status=?, end_tick=?, updated_at=?, "
            "metadata_json=? WHERE session_id=?",
            (
                session.status.value,
                session.end_tick,
                _iso_required(session.updated_at),
                json.dumps(session.metadata),
                str(session.session_id),
            ),
        )

    async def get_session(self, session_id: SessionId) -> Session | None:
        rows = await self._db.fetchall(
            "SELECT session_id, world_id, session_type, status, "
            "seed_strategy, seed, start_tick, end_tick, created_at, "
            "updated_at, metadata_json FROM sessions WHERE session_id=?",
            (str(session_id),),
        )
        if not rows:
            return None
        return _row_to_session(rows[0])

    async def list_sessions(
        self, *, world_id: WorldId | None = None, limit: int = 100
    ) -> list[Session]:
        if world_id is None:
            rows = await self._db.fetchall(
                "SELECT session_id, world_id, session_type, status, "
                "seed_strategy, seed, start_tick, end_tick, created_at, "
                "updated_at, metadata_json FROM sessions "
                "ORDER BY created_at DESC LIMIT ?",
                (limit,),
            )
        else:
            rows = await self._db.fetchall(
                "SELECT session_id, world_id, session_type, status, "
                "seed_strategy, seed, start_tick, end_tick, created_at, "
                "updated_at, metadata_json FROM sessions WHERE "
                "world_id=? ORDER BY created_at DESC LIMIT ?",
                (str(world_id), limit),
            )
        return [_row_to_session(r) for r in rows]

    # ── Slot assignment CRUD ──────────────────────────────────────

    async def pin_slot(self, assignment: SlotAssignment) -> None:
        """Insert or replace an ``(session_id, slot_name)`` row.

        Audit-fold M5: ``INSERT OR REPLACE`` drops the prior row
        atomically on re-pin. A product that needs the historical
        "who held slot X at time T?" trail must subscribe to
        session events; this store keeps only the current pinning.
        """
        await self._db.execute(
            "INSERT OR REPLACE INTO slot_assignments "
            "(session_id, slot_name, actor_id, token, pinned_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (
                str(assignment.session_id),
                assignment.slot_name,
                str(assignment.actor_id),
                assignment.token,
                _iso_required(assignment.pinned_at),
            ),
        )

    async def list_slot_assignments(self, session_id: SessionId) -> list[SlotAssignment]:
        rows = await self._db.fetchall(
            "SELECT session_id, slot_name, actor_id, token, pinned_at "
            "FROM slot_assignments WHERE session_id=? "
            "ORDER BY pinned_at ASC",
            (str(session_id),),
        )
        return [_row_to_slot_assignment(r) for r in rows]


# ── Helpers ──────────────────────────────────────────────────────


def _iso_required(dt: datetime | None) -> str:
    """Serialize to ISO-8601 UTC. Raises ``ValueError`` on ``None``
    because the store's ``NOT NULL`` columns require a value; a
    silent ``None``→``"None"`` coercion would pollute the DB
    (audit-fold M4)."""
    if dt is None:
        raise ValueError("datetime required — column is NOT NULL")
    return dt.astimezone(UTC).isoformat()


def _parse_iso(s: str | None) -> datetime | None:
    if s is None:
        return None
    return datetime.fromisoformat(s)


def _row_to_session(row: dict) -> Session:
    """``Database.fetchall`` returns ``list[dict[str, Any]]`` — we
    access by column name (not positional), which is robust to
    future column additions."""
    return Session(
        session_id=SessionId(row["session_id"]),
        world_id=WorldId(row["world_id"]),
        session_type=SessionType(row["session_type"]),
        status=SessionStatus(row["status"]),
        seed_strategy=SeedStrategy(row["seed_strategy"]),
        seed=row["seed"],
        start_tick=row["start_tick"],
        end_tick=row["end_tick"],
        created_at=_parse_iso(row["created_at"]),
        updated_at=_parse_iso(row["updated_at"]),
        metadata=json.loads(row["metadata_json"] or "{}"),
    )


def _row_to_slot_assignment(row: dict) -> SlotAssignment:
    pinned = _parse_iso(row["pinned_at"])
    if pinned is None:
        raise ValueError(
            f"slot_assignments.pinned_at unexpectedly NULL for "
            f"session {row['session_id']!r}/{row['slot_name']!r}"
        )
    return SlotAssignment(
        session_id=SessionId(row["session_id"]),
        slot_name=row["slot_name"],
        actor_id=ActorId(row["actor_id"]),
        token=row["token"],
        pinned_at=pinned,
    )
