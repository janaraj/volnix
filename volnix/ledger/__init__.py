"""Audit Trail -- append-only ledger for all Volnix operations.

This package provides a structured audit log that records pipeline steps,
state mutations, LLM calls, gateway requests, validation outcomes, engine
lifecycle transitions, and snapshots.

Re-exports the primary public API surface so downstream code can do::

    from volnix.ledger import Ledger, LedgerConfig, LedgerEntry
"""

from volnix.ledger.config import LedgerConfig
from volnix.ledger.entries import (
    ENTRY_REGISTRY,
    EngineLifecycleEntry,
    GatewayRequestEntry,
    LedgerEntry,
    LLMCallEntry,
    PipelineStepEntry,
    SnapshotEntry,
    StateMutationEntry,
    UnknownLedgerEntry,
    ValidationEntry,
    deserialize_entry,
)
from volnix.ledger.export import LedgerExporter
from volnix.ledger.ledger import Ledger
from volnix.ledger.query import LedgerAggregation, LedgerQuery, LedgerQueryBuilder

__all__ = [
    # Public API
    "EngineLifecycleEntry",
    "GatewayRequestEntry",
    "Ledger",
    "LedgerAggregation",
    "LedgerConfig",
    "LedgerEntry",
    "LedgerExporter",
    "LedgerQuery",
    "LedgerQueryBuilder",
    "LLMCallEntry",
    "PipelineStepEntry",
    "SnapshotEntry",
    "StateMutationEntry",
    "UnknownLedgerEntry",
    "ValidationEntry",
    # Internal (exported for advanced use / testing)
    "ENTRY_REGISTRY",
    "deserialize_entry",
]
