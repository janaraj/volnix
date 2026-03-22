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
        limit: Maximum number of entries to return (default 100).
        offset: Number of entries to skip before returning results.
    """

    entry_type: str | None = None
    start_time: datetime | None = None
    end_time: datetime | None = None
    actor_id: ActorId | None = None
    engine_name: str | None = None
    limit: int = 100  # default; callers can override per-query
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
        self._entry_type: str | None = None
        self._start_time: datetime | None = None
        self._end_time: datetime | None = None
        self._actor_id: ActorId | None = None
        self._engine_name: str | None = None
        self._limit: int = 100
        self._offset: int = 0
        self._aggregation: LedgerAggregation | None = None

    def filter_type(self, entry_type: str) -> Self:
        """Filter by entry type.

        Args:
            entry_type: The entry type string to filter on.

        Returns:
            This builder for chaining.
        """
        self._entry_type = entry_type
        return self

    def filter_time(self, start: datetime | None = None, end: datetime | None = None) -> Self:
        """Filter by time range.

        Args:
            start: Start of the time range (inclusive).
            end: End of the time range (inclusive).

        Returns:
            This builder for chaining.
        """
        if start is not None:
            self._start_time = start
        if end is not None:
            self._end_time = end
        return self

    def filter_actor(self, actor_id: ActorId) -> Self:
        """Filter by actor.

        Args:
            actor_id: The actor to filter on.

        Returns:
            This builder for chaining.
        """
        self._actor_id = actor_id
        return self

    def filter_engine(self, engine_name: str) -> Self:
        """Filter by engine name.

        Args:
            engine_name: The engine name to filter on.

        Returns:
            This builder for chaining.
        """
        self._engine_name = engine_name
        return self

    def limit(self, limit: int) -> Self:
        """Set the maximum number of entries to return.

        Args:
            limit: Maximum entries.

        Returns:
            This builder for chaining.
        """
        self._limit = limit
        return self

    def offset(self, offset: int) -> Self:
        """Set the number of entries to skip.

        Args:
            offset: Entries to skip.

        Returns:
            This builder for chaining.
        """
        self._offset = offset
        return self

    def aggregate(self, group_by: str, metric: str) -> Self:
        """Set aggregation parameters.

        Note: Aggregation is stored but not yet applied at the query level.
        The Ledger.query() method returns raw entries; aggregation is applied
        by the caller (e.g., Reporter in Phase F3).

        Args:
            group_by: The field to group results by.
            metric: The aggregation function (``"count"``, ``"sum"``, ``"avg"``).

        Returns:
            This builder for chaining.
        """
        self._aggregation = LedgerAggregation(group_by=group_by, metric=metric)
        return self

    def build(self) -> LedgerQuery:
        """Build and return the :class:`LedgerQuery`.

        Returns:
            The constructed query object.
        """
        return LedgerQuery(
            entry_type=self._entry_type,
            start_time=self._start_time,
            end_time=self._end_time,
            actor_id=self._actor_id,
            engine_name=self._engine_name,
            limit=self._limit,
            offset=self._offset,
        )
