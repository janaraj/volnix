"""Persistent store for held actions awaiting approval.

Uses the Volnix ``Database`` abstraction (``volnix.persistence.database``)
so that all low-level SQLite access stays inside the persistence layer.
Stores the full action context needed to re-execute through the pipeline
on approval.
"""

from __future__ import annotations

import json
import logging
import time
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from volnix.persistence.database import Database

logger = logging.getLogger(__name__)

_CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS holds (
    hold_id TEXT PRIMARY KEY,
    actor_id TEXT NOT NULL,
    service_id TEXT NOT NULL,
    action TEXT NOT NULL,
    input_data TEXT NOT NULL,
    approver_role TEXT NOT NULL,
    policy_id TEXT NOT NULL,
    created_at REAL NOT NULL,
    expires_at REAL NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    resolved_by TEXT,
    resolved_at REAL,
    resolution_reason TEXT,
    run_id TEXT
)
"""


class HoldStore:
    """Persistent store for held pipeline actions.

    Accepts a ``Database`` instance (from the persistence layer) so that
    all raw SQLite access remains confined to ``volnix/persistence/``.
    """

    def __init__(self, db: Database) -> None:
        self._db = db

    async def initialize(self) -> None:
        """Create schema tables."""
        await self._db.execute(_CREATE_TABLE)

    async def close(self) -> None:
        """Close the underlying database connection."""
        await self._db.close()

    async def store(
        self,
        hold_id: str,
        actor_id: str,
        service_id: str,
        action: str,
        input_data: dict[str, Any],
        approver_role: str,
        policy_id: str,
        timeout_seconds: float,
        run_id: str | None = None,
    ) -> None:
        """Persist a held action."""
        now = time.time()
        await self._db.execute(
            """INSERT OR REPLACE INTO holds
               (hold_id, actor_id, service_id, action, input_data,
                approver_role, policy_id, created_at, expires_at, status, run_id)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending', ?)""",
            (
                hold_id,
                actor_id,
                service_id,
                action,
                json.dumps(input_data),
                approver_role,
                policy_id,
                now,
                now + timeout_seconds,
                run_id,
            ),
        )

    async def get(self, hold_id: str) -> dict[str, Any] | None:
        """Retrieve a held action."""
        return await self._db.fetchone("SELECT * FROM holds WHERE hold_id = ?", (hold_id,))

    async def resolve(
        self, hold_id: str, approved: bool, approver: str, reason: str = ""
    ) -> dict[str, Any] | None:
        """Mark hold as approved/rejected. Returns stored action data."""
        existing = await self.get(hold_id)
        if existing is None or existing["status"] != "pending":
            return None
        status = "approved" if approved else "rejected"
        await self._db.execute(
            """UPDATE holds SET status = ?, resolved_by = ?,
               resolved_at = ?, resolution_reason = ?
               WHERE hold_id = ? AND status = 'pending'""",
            (status, approver, time.time(), reason, hold_id),
        )
        return existing

    async def list_pending(
        self,
        approver_role: str | None = None,
        run_id: str | None = None,
    ) -> list[dict[str, Any]]:
        """List pending holds."""
        query = "SELECT * FROM holds WHERE status = 'pending'"
        params: list[Any] = []
        if approver_role:
            query += " AND approver_role = ?"
            params.append(approver_role)
        if run_id:
            query += " AND run_id = ?"
            params.append(run_id)
        query += " ORDER BY created_at DESC"
        return await self._db.fetchall(query, tuple(params))

    async def expire_stale(self, now_epoch: float) -> list[str]:
        """Mark expired holds as rejected."""
        rows = await self._db.fetchall(
            "SELECT hold_id FROM holds WHERE status = 'pending' AND expires_at <= ?",
            (now_epoch,),
        )
        expired_ids = [r["hold_id"] for r in rows]
        if expired_ids:
            placeholders = ",".join("?" * len(expired_ids))
            await self._db.execute(
                f"""UPDATE holds SET status = 'expired', resolved_at = ?,
                    resolution_reason = 'timeout'
                    WHERE hold_id IN ({placeholders})""",
                (now_epoch, *expired_ids),
            )
        return expired_ids
