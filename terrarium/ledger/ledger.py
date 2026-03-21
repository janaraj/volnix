"""Core Ledger implementation.

The Ledger provides an append-only audit trail for all significant
operations within the Terrarium framework.  Entries are typed, immutable,
and queryable.
"""

from __future__ import annotations

from terrarium.ledger.config import LedgerConfig
from terrarium.ledger.entries import LedgerEntry
from terrarium.ledger.query import LedgerQuery


class Ledger:
    """Append-only audit ledger for Terrarium operations.

    Parameters:
        config: Ledger configuration controlling storage, retention, and
                which entry types are enabled.
    """

    def __init__(self, config: LedgerConfig) -> None:
        ...

    async def initialize(self) -> None:
        """Open the backing store and ensure the schema exists."""
        ...

    async def shutdown(self) -> None:
        """Flush pending writes and close the backing store."""
        ...

    async def append(self, entry: LedgerEntry) -> int:
        """Append an entry to the ledger.

        Args:
            entry: The ledger entry to persist.

        Returns:
            The auto-assigned entry ID.
        """
        ...

    async def query(self, filters: LedgerQuery) -> list[LedgerEntry]:
        """Query the ledger with structured filters.

        Args:
            filters: Query parameters specifying type, time range,
                     actor, engine, and pagination.

        Returns:
            Ordered list of matching ledger entries.
        """
        ...

    async def get_count(self, entry_type: str | None = None) -> int:
        """Return the total number of ledger entries.

        Args:
            entry_type: If provided, count only entries of this type.

        Returns:
            Number of matching entries.
        """
        ...
