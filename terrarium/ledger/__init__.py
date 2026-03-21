"""Audit Trail -- append-only ledger for all Terrarium operations.

This package provides a structured audit log that records pipeline steps,
state mutations, LLM calls, gateway requests, validation outcomes, engine
lifecycle transitions, and snapshots.

Re-exports the primary public API surface so downstream code can do::

    from terrarium.ledger import Ledger, LedgerConfig, LedgerEntry
"""

from terrarium.ledger.config import LedgerConfig
from terrarium.ledger.entries import (
    EngineLifecycleEntry,
    GatewayRequestEntry,
    LedgerEntry,
    LLMCallEntry,
    PipelineStepEntry,
    SnapshotEntry,
    StateMutationEntry,
    ValidationEntry,
)
from terrarium.ledger.export import LedgerExporter
from terrarium.ledger.ledger import Ledger
from terrarium.ledger.query import LedgerAggregation, LedgerQuery, LedgerQueryBuilder

__all__ = [
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
    "ValidationEntry",
]
