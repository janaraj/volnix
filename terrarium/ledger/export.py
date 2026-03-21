"""Ledger export utilities.

Provides export functionality for writing ledger entries to JSON, CSV,
or a replay-compatible format.
"""

from __future__ import annotations

from terrarium.ledger.query import LedgerQuery


class LedgerExporter:
    """Exports ledger entries to various file formats."""

    async def export_json(self, query: LedgerQuery, output_path: str) -> int:
        """Export matching ledger entries to a JSON file.

        Args:
            query: Query filters to select which entries to export.
            output_path: Filesystem path for the output JSON file.

        Returns:
            Number of entries exported.
        """
        ...

    async def export_csv(self, query: LedgerQuery, output_path: str) -> int:
        """Export matching ledger entries to a CSV file.

        Args:
            query: Query filters to select which entries to export.
            output_path: Filesystem path for the output CSV file.

        Returns:
            Number of entries exported.
        """
        ...

    async def export_replay(self, query: LedgerQuery, output_path: str) -> int:
        """Export matching ledger entries in a replay-compatible format.

        Args:
            query: Query filters to select which entries to export.
            output_path: Filesystem path for the output replay file.

        Returns:
            Number of entries exported.
        """
        ...
