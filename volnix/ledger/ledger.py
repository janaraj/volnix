"""Core Ledger implementation.

The Ledger provides an append-only audit trail for all significant
operations within the Volnix framework.  Entries are typed, immutable,
and queryable.

Receives a :class:`Database` via dependency injection -- does NOT create
its own ``SQLiteDatabase``.  The database lifecycle is managed externally
by :class:`ConnectionManager`.
"""

from __future__ import annotations

from typing import Any

from volnix.ledger.config import LedgerConfig
from volnix.ledger.entries import LedgerEntry, deserialize_entry
from volnix.ledger.query import LedgerQuery
from volnix.persistence.append_log import AppendOnlyLog
from volnix.persistence.database import Database


class Ledger:
    """Append-only audit ledger for Volnix operations.

    Parameters:
        config: Ledger configuration controlling storage, retention, and
                which entry types are enabled.
        db: A :class:`Database` instance (provided via DI, not created here).
    """

    COLUMNS = [
        ("entry_type", "TEXT NOT NULL"),
        ("timestamp", "TEXT NOT NULL"),
        ("actor_id", "TEXT"),
        ("engine_name", "TEXT"),
        # PMF Plan Phase 4C Step 6 — platform Session correlation.
        # Nullable: pre-session entries (engine_lifecycle, etc.) and
        # runs outside a session both persist NULL.
        ("session_id", "TEXT"),
        # PMF Plan Phase 4C Step 8 — activation correlation for
        # ReplayLLMProvider journal lookup. Nullable: entries not
        # tied to an activation (e.g., state_mutation) persist NULL.
        # Indexed on initialize() for O(log N) replay lookups.
        ("activation_id", "TEXT"),
        ("payload", "TEXT NOT NULL"),
    ]

    def __init__(
        self,
        config: LedgerConfig,
        db: Database,
        *,
        redactor: Any = None,  # Callable[[LedgerEntry], LedgerEntry] | None
        ephemeral: bool = False,
    ) -> None:
        self._config = config
        self._db = db
        self._log = AppendOnlyLog(db=db, table_name="ledger_log", columns=self.COLUMNS)
        # None = all types enabled; non-empty set = only those types
        # An empty list in config means "all types" (None), not "no types"
        self._entry_types_enabled: set[str] | None = (
            set(config.entry_types_enabled) if config.entry_types_enabled else None
        )
        # PMF Plan Phase 4C Step 14 — privacy hooks.
        # ``redactor``: optional callable run before every append
        # so products can strip sensitive fields. Injected via DI
        # (NOT imported from volnix.privacy) so Ledger stays
        # domain-neutral. Post-impl audit H5: validate callability
        # at DI time so misinjection surfaces at boot rather than
        # at first ``append``.
        # ``ephemeral``: when True, append() returns -1 and writes
        # nothing. Guards disk writes for no-persistence sessions.
        if redactor is not None and not callable(redactor):
            raise TypeError(
                f"Ledger redactor must be callable or None, got {type(redactor).__name__}"
            )
        self._redactor: Any = redactor
        self._ephemeral: bool = ephemeral

    async def initialize(self) -> None:
        """Open the backing store and ensure the schema exists."""
        await self._log.initialize()
        await self._log.create_index("entry_type")
        await self._log.create_index("timestamp")
        await self._log.create_index("actor_id")
        # PMF Plan Phase 4C Step 6 — session_id filter primary index.
        await self._log.create_index("session_id")
        # PMF Plan Phase 4C Step 8 — activation_id index for
        # ReplayLLMProvider journal lookups.
        await self._log.create_index("activation_id")

    async def shutdown(self) -> None:
        """No-op -- Database lifecycle is managed by ConnectionManager."""
        pass

    async def append(self, entry: LedgerEntry) -> int:
        """Append an entry to the ledger.

        Args:
            entry: The ledger entry to persist.

        Returns:
            The auto-assigned entry ID, or -1 if the entry type is disabled.
        """
        if self._entry_types_enabled and entry.entry_type not in self._entry_types_enabled:
            return -1
        # PMF Plan Phase 4C Step 14 — ephemeral mode suppresses
        # disk writes entirely so a consumer running a private
        # session never accidentally persists the ledger.
        if self._ephemeral:
            return -1
        # PMF Plan Phase 4C Step 14 — run the redactor BEFORE
        # extracting indexed columns so redaction on fields like
        # ``actor_id`` / ``session_id`` propagates to the SQL
        # columns too. Returning None from a redactor is a
        # programming error — refuse loudly rather than writing a
        # NoneType payload.
        if self._redactor is not None:
            _original_type = entry.entry_type
            # Post-impl audit H4: a buggy redactor can mutate the
            # input entry via ``object.__setattr__`` and bypass
            # ``frozen=True``. Pass a deep copy so the caller's
            # reference is never touched; the redactor gets full
            # freedom to mutate its private copy OR return a
            # fresh model — either path is safe.
            entry = self._redactor(entry.model_copy(deep=True))
            if entry is None:
                raise TypeError(
                    "Ledger redactor returned None; the hook must "
                    "return a LedgerEntry. Fix the ledger_redactor "
                    "registered in VolnixConfig.privacy."
                )
            # Post-impl audit H2: the type filter above has already
            # run. A redactor that rewrote ``entry_type`` would
            # sneak a disabled type past the gate — refuse loudly
            # so the contract ("redactor doesn't change type") is
            # machine-enforced, not documented-only.
            if entry.entry_type != _original_type:
                raise TypeError(
                    f"Ledger redactor changed entry_type from "
                    f"{_original_type!r} to {entry.entry_type!r}. "
                    f"Redactors MUST preserve entry_type — the "
                    f"type filter runs before the redactor, so a "
                    f"rewrite would bypass the consumer's allowlist."
                )
        return await self._log.append(
            {
                "entry_type": entry.entry_type,
                "timestamp": entry.timestamp.isoformat(),
                "actor_id": _extract_actor_id(entry),
                "engine_name": _extract_engine_name(entry),
                "session_id": _extract_session_id(entry),
                "activation_id": _extract_activation_id(entry),
                "payload": entry.model_dump_json(),
            }
        )

    async def query(self, filters: LedgerQuery) -> list[LedgerEntry]:
        """Query the ledger with structured filters.

        ALL filtering is pushed to SQL for performance:
        - entry_type, actor_id, engine_name → equality filters
        - start_time, end_time → range filters on timestamp column
        - limit, offset → SQL LIMIT/OFFSET

        Args:
            filters: Query parameters specifying type, time range,
                     actor, engine, and pagination.

        Returns:
            Ordered list of matching ledger entries.
        """
        # Equality filters → SQL WHERE col = ?
        sql_filters: dict = {}
        if filters.entry_type:
            sql_filters["entry_type"] = filters.entry_type
        if filters.actor_id:
            sql_filters["actor_id"] = str(filters.actor_id)
        if filters.engine_name:
            sql_filters["engine_name"] = filters.engine_name
        # PMF Plan Phase 4C Step 6 — session_id equality filter.
        if filters.session_id:
            sql_filters["session_id"] = str(filters.session_id)
        # PMF Plan Phase 4C Step 8 — activation_id equality filter.
        if filters.activation_id:
            sql_filters["activation_id"] = str(filters.activation_id)

        # Range filters → SQL WHERE col >= ? AND col <= ?
        range_filters: list[tuple[str, str, str]] = []
        if filters.start_time:
            range_filters.append(("timestamp", ">=", filters.start_time.isoformat()))
        if filters.end_time:
            range_filters.append(("timestamp", "<=", filters.end_time.isoformat()))

        rows = await self._log.query(
            from_sequence=0,
            filters=sql_filters if sql_filters else None,
            range_filters=range_filters if range_filters else None,
            limit=filters.limit,
            offset=filters.offset if filters.offset is not None else None,
        )

        # Typed deserialization via entry registry
        return [deserialize_entry(row) for row in rows]

    async def get_count(self, entry_type: str | None = None) -> int:
        """Return the total number of ledger entries.

        Args:
            entry_type: If provided, count only entries of this type.

        Returns:
            Number of matching entries.
        """
        filters = {"entry_type": entry_type} if entry_type else None
        return await self._log.count(filters)


def _extract_actor_id(entry: LedgerEntry) -> str:
    """Extract actor_id from an entry if it has one."""
    val = getattr(entry, "actor_id", None)
    return str(val) if val else ""


def _extract_engine_name(entry: LedgerEntry) -> str:
    """Extract engine_name from an entry if it has one."""
    return getattr(entry, "engine_name", None) or ""


def _extract_session_id(entry: LedgerEntry) -> str | None:
    """Extract ``session_id`` from an entry if it has one
    (PMF Plan Phase 4C Step 6). Module-level function matching the
    existing ``_extract_actor_id`` / ``_extract_engine_name``
    helpers (audit-fold C2 — not an instance method).

    Returns ``None`` (not empty string) so a NULL column value
    signals "no session" — enabling consumers to query
    ``WHERE session_id IS NULL`` for unsessioned entries.
    """
    raw = getattr(entry, "session_id", None)
    if raw is None:
        return None
    return str(raw)


def _extract_activation_id(entry: LedgerEntry) -> str | None:
    """Extract ``activation_id`` from an entry if it has one
    (PMF Plan Phase 4C Step 8). Same module-level pattern as
    ``_extract_session_id``. Feeds the ``activation_id`` indexed
    column that ``ReplayLLMProvider`` uses to look up utterance
    rows for a specific activation.

    Returns ``None`` for entries without an ``activation_id``
    field (most; only ``LLMUtteranceEntry`` / ``ToolLoopStepEntry`` /
    ``ActivationCompleteEntry`` carry it).
    """
    raw = getattr(entry, "activation_id", None)
    if raw is None:
        return None
    return str(raw)
