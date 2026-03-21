"""Ledger query models and builder.

Provides the structured query parameters for filtering ledger entries,
an aggregation descriptor, and a fluent builder for constructing queries.
"""

from __future__ import annotations

from datetime import datetime
from typing import Self

from pydantic import BaseModel

from terrarium.core.types import ActorId


# ---------------------------------------------------------------------------
# Query models
# ---------------------------------------------------------------------------


class LedgerQuery(BaseModel):
    """Structured filter for querying the ledger.

    Attributes:
        entry_type: If set, only return entries of this type.
        start_time: If set, only return entries at or after this time.
        end_time: If set, only return entries at or before this time.
        actor_id: If set, only return entries for this actor.
        engine_name: If set, only return entries from this engine.
        limit: Maximum number of entries to return.
        offset: Number of entries to skip before returning results.
    """

    entry_type: str | None = None
    start_time: datetime | None = None
    end_time: datetime | None = None
    actor_id: ActorId | None = None
    engine_name: str | None = None
    limit: int = 100
    offset: int = 0


class LedgerAggregation(BaseModel):
    """Descriptor for aggregating ledger query results.

    Attributes:
        group_by: The field to group results by.
        metric: The aggregation function to apply (``"count"``,
                ``"sum"``, or ``"avg"``).
    """

    group_by: str
    metric: str  # "count" | "sum" | "avg"


# ---------------------------------------------------------------------------
# Fluent query builder
# ---------------------------------------------------------------------------


class LedgerQueryBuilder:
    """Fluent builder for constructing :class:`LedgerQuery` instances."""

    def __init__(self) -> None:
        ...

    def filter_type(self, entry_type: str) -> Self:
        """Filter by entry type.

        Args:
            entry_type: The entry type string to filter on.

        Returns:
            This builder for chaining.
        """
        ...

    def filter_time(self, start: datetime | None = None, end: datetime | None = None) -> Self:
        """Filter by time range.

        Args:
            start: Start of the time range (inclusive).
            end: End of the time range (inclusive).

        Returns:
            This builder for chaining.
        """
        ...

    def filter_actor(self, actor_id: ActorId) -> Self:
        """Filter by actor.

        Args:
            actor_id: The actor to filter on.

        Returns:
            This builder for chaining.
        """
        ...

    def aggregate(self, group_by: str, metric: str) -> Self:
        """Set aggregation parameters.

        Args:
            group_by: The field to group results by.
            metric: The aggregation function (``"count"``, ``"sum"``, ``"avg"``).

        Returns:
            This builder for chaining.
        """
        ...

    def build(self) -> LedgerQuery:
        """Build and return the :class:`LedgerQuery`.

        Returns:
            The constructed query object.
        """
        ...
