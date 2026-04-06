"""Configuration model for the audit ledger.

Provides a Pydantic model that centralises all tuneable parameters for
the ledger subsystem, including storage path, retention policy, and
entry type filtering.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class LedgerConfig(BaseModel):
    model_config = ConfigDict(frozen=True)
    """Configuration for the Volnix audit ledger.

    Attributes:
        db_path: Filesystem path for the SQLite ledger database.
        retention_days: Number of days to retain entries before pruning.
        entry_types_enabled: List of entry type strings that are enabled.
                             An empty list means all types are enabled.
        flush_interval_ms: Interval in milliseconds between flush cycles.
    """

    db_path: str = "volnix_ledger.db"
    retention_days: int = 90
    entry_types_enabled: list[str] = Field(default_factory=list)
    flush_interval_ms: int = 1000
