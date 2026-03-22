"""Ledger export utilities.

Provides export functionality for writing ledger entries to JSON, CSV,
or a replay-compatible format.
"""

from __future__ import annotations

import asyncio
import csv
import json
from pathlib import Path
from typing import TYPE_CHECKING

from terrarium.ledger.query import LedgerQuery

if TYPE_CHECKING:
    from terrarium.ledger.ledger import Ledger


class LedgerExporter:
    """Exports ledger entries to various file formats.

    Parameters:
        ledger: The :class:`Ledger` instance to query entries from.
    """

    def __init__(self, ledger: Ledger) -> None:
        self._ledger = ledger

    async def export_json(self, query: LedgerQuery, output_path: str) -> int:
        """Export matching ledger entries to a JSON file.

        Args:
            query: Query filters to select which entries to export.
            output_path: Filesystem path for the output JSON file.

        Returns:
            Number of entries exported.
        """
        entries = await self._ledger.query(query)
        data = [e.model_dump(mode="json") for e in entries]
        parent = Path(output_path).parent
        await asyncio.to_thread(parent.mkdir, parents=True, exist_ok=True)
        json_str = json.dumps(data, indent=2, default=str)
        await asyncio.to_thread(Path(output_path).write_text, json_str)
        return len(data)

    async def export_csv(self, query: LedgerQuery, output_path: str) -> int:
        """Export matching ledger entries to a CSV file.

        Args:
            query: Query filters to select which entries to export.
            output_path: Filesystem path for the output CSV file.

        Returns:
            Number of entries exported.
        """
        entries = await self._ledger.query(query)
        parent = Path(output_path).parent
        await asyncio.to_thread(parent.mkdir, parents=True, exist_ok=True)
        if not entries:
            await asyncio.to_thread(Path(output_path).write_text, "")
            return 0
        all_fields: dict[str, None] = {}  # ordered dict behavior
        for entry in entries:
            for key in entry.model_dump().keys():
                all_fields[key] = None
        fieldnames = list(all_fields.keys())

        def _write_csv() -> None:
            with open(output_path, "w", newline="") as f:
                writer = csv.DictWriter(f, fieldnames=fieldnames)
                writer.writeheader()
                for entry in entries:
                    writer.writerow({k: str(v) for k, v in entry.model_dump().items()})

        await asyncio.to_thread(_write_csv)
        return len(entries)

    async def export_replay(self, query: LedgerQuery, output_path: str) -> int:
        """Export matching ledger entries in a replay-compatible format.

        Each entry is written as a single JSON line (JSONL format).

        Args:
            query: Query filters to select which entries to export.
            output_path: Filesystem path for the output replay file.

        Returns:
            Number of entries exported.
        """
        entries = await self._ledger.query(query)
        parent = Path(output_path).parent
        await asyncio.to_thread(parent.mkdir, parents=True, exist_ok=True)

        def _write_replay() -> None:
            with open(output_path, "w") as f:
                for entry in entries:
                    f.write(entry.model_dump_json() + "\n")

        await asyncio.to_thread(_write_replay)
        return len(entries)
