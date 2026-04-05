"""Tests for volnix.ledger.query -- fluent query builder for ledger entries."""
import pytest
from datetime import datetime, timezone

from volnix.core.types import ActorId
from volnix.ledger.query import LedgerAggregation, LedgerQuery, LedgerQueryBuilder


def test_ledger_query_defaults():
    """LedgerQuery should have sensible defaults."""
    q = LedgerQuery()
    assert q.entry_type is None
    assert q.start_time is None
    assert q.end_time is None
    assert q.actor_id is None
    assert q.engine_name is None
    assert q.limit == 100
    assert q.offset == 0


def test_query_builder_filter_type():
    """filter_type should set entry_type on the built query."""
    q = LedgerQueryBuilder().filter_type("pipeline_step").build()
    assert q.entry_type == "pipeline_step"


def test_query_builder_filter_time():
    """filter_time should set start_time and end_time."""
    start = datetime(2025, 1, 1, tzinfo=timezone.utc)
    end = datetime(2025, 12, 31, tzinfo=timezone.utc)
    q = LedgerQueryBuilder().filter_time(start=start, end=end).build()
    assert q.start_time == start
    assert q.end_time == end


def test_query_builder_filter_time_partial():
    """filter_time with only start or end should set just that field."""
    start = datetime(2025, 6, 1, tzinfo=timezone.utc)
    q = LedgerQueryBuilder().filter_time(start=start).build()
    assert q.start_time == start
    assert q.end_time is None


def test_query_builder_filter_actor():
    """filter_actor should set actor_id on the built query."""
    q = LedgerQueryBuilder().filter_actor(ActorId("actor-1")).build()
    assert q.actor_id == ActorId("actor-1")


def test_query_builder_chain():
    """Builder methods should be chainable."""
    start = datetime(2025, 1, 1, tzinfo=timezone.utc)
    q = (
        LedgerQueryBuilder()
        .filter_type("llm_call")
        .filter_time(start=start)
        .filter_actor(ActorId("actor-2"))
        .filter_engine("reasoning")
        .limit(50)
        .offset(10)
        .build()
    )
    assert q.entry_type == "llm_call"
    assert q.start_time == start
    assert q.actor_id == ActorId("actor-2")
    assert q.engine_name == "reasoning"
    assert q.limit == 50
    assert q.offset == 10


def test_query_builder_build():
    """build() should produce a LedgerQuery with all defaults when no filters set."""
    q = LedgerQueryBuilder().build()
    assert isinstance(q, LedgerQuery)
    assert q.entry_type is None
    assert q.limit == 100
    assert q.offset == 0


def test_ledger_aggregation_model():
    """LedgerAggregation should accept group_by and metric."""
    agg = LedgerAggregation(group_by="entry_type", metric="count")
    assert agg.group_by == "entry_type"
    assert agg.metric == "count"


def test_query_builder_immutable():
    """Each build() call should produce an independent LedgerQuery."""
    builder = LedgerQueryBuilder()
    q1 = builder.filter_type("llm_call").build()
    q2 = builder.filter_type("pipeline_step").build()
    # q2 should overwrite q1's entry_type
    assert q1.entry_type == "llm_call"
    assert q2.entry_type == "pipeline_step"
