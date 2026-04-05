"""Tests for volnix.persistence.append_log — shared append-only log."""
import pytest
from volnix.persistence.append_log import AppendOnlyLog
from volnix.persistence.sqlite import SQLiteDatabase


@pytest.fixture
async def db(tmp_path):
    """Create a temporary SQLite database for each test."""
    database = SQLiteDatabase(str(tmp_path / "test.db"))
    await database.connect()
    yield database
    await database.close()


@pytest.fixture
async def log(db):
    """Create an AppendOnlyLog with test columns."""
    alog = AppendOnlyLog(
        db=db,
        table_name="test_log",
        columns=[
            ("name", "TEXT NOT NULL"),
            ("value", "TEXT"),
        ],
    )
    await alog.initialize()
    return alog


async def test_append_log_initialize(db):
    """initialize() should create the table."""
    alog = AppendOnlyLog(
        db=db,
        table_name="my_log",
        columns=[("col1", "TEXT NOT NULL")],
    )
    assert await db.table_exists("my_log") is False
    await alog.initialize()
    assert await db.table_exists("my_log") is True


async def test_append_log_append(log):
    """append() should store a record and return a sequence_id."""
    seq = await log.append({"name": "event1", "value": "data1"})
    assert seq == 1
    seq2 = await log.append({"name": "event2", "value": "data2"})
    assert seq2 == 2


async def test_append_log_query(log):
    """query() should retrieve records in ascending order."""
    await log.append({"name": "a", "value": "1"})
    await log.append({"name": "b", "value": "2"})
    await log.append({"name": "c", "value": "3"})

    rows = await log.query()
    assert len(rows) == 3
    assert rows[0]["name"] == "a"
    assert rows[1]["name"] == "b"
    assert rows[2]["name"] == "c"
    # Verify sequence_id is present and ordered
    assert rows[0]["sequence_id"] < rows[1]["sequence_id"] < rows[2]["sequence_id"]


async def test_append_log_query_with_filters(log):
    """query() should filter by column value."""
    await log.append({"name": "alpha", "value": "x"})
    await log.append({"name": "beta", "value": "y"})
    await log.append({"name": "alpha", "value": "z"})

    rows = await log.query(filters={"name": "alpha"})
    assert len(rows) == 2
    assert all(r["name"] == "alpha" for r in rows)


async def test_append_log_query_with_list_filter(log):
    """query() should support IN clause for list filter values."""
    await log.append({"name": "a", "value": "1"})
    await log.append({"name": "b", "value": "2"})
    await log.append({"name": "c", "value": "3"})

    rows = await log.query(filters={"name": ["a", "c"]})
    assert len(rows) == 2
    names = {r["name"] for r in rows}
    assert names == {"a", "c"}


async def test_append_log_count(log):
    """count() should return the correct total count."""
    assert await log.count() == 0
    await log.append({"name": "x", "value": "1"})
    await log.append({"name": "y", "value": "2"})
    assert await log.count() == 2


async def test_append_log_count_with_filter(log):
    """count() should support filtered counts."""
    await log.append({"name": "a", "value": "1"})
    await log.append({"name": "b", "value": "2"})
    await log.append({"name": "a", "value": "3"})

    assert await log.count(filters={"name": "a"}) == 2
    assert await log.count(filters={"name": "b"}) == 1
    assert await log.count(filters={"name": "c"}) == 0


async def test_append_log_latest_sequence(log):
    """latest_sequence() should return the max sequence_id."""
    assert await log.latest_sequence() == 0  # empty table
    await log.append({"name": "first", "value": "1"})
    assert await log.latest_sequence() == 1
    await log.append({"name": "second", "value": "2"})
    assert await log.latest_sequence() == 2


async def test_append_log_query_from_sequence(log):
    """query(from_sequence=...) should filter rows by sequence_id."""
    await log.append({"name": "a", "value": "1"})
    seq2 = await log.append({"name": "b", "value": "2"})
    await log.append({"name": "c", "value": "3"})

    rows = await log.query(from_sequence=seq2)
    assert len(rows) == 2
    assert rows[0]["name"] == "b"
    assert rows[1]["name"] == "c"


async def test_append_log_query_with_limit(log):
    """query(limit=...) should cap the number of results."""
    for i in range(5):
        await log.append({"name": f"item{i}", "value": str(i)})

    rows = await log.query(limit=3)
    assert len(rows) == 3
    assert rows[0]["name"] == "item0"


async def test_append_log_created_at_populated(log):
    """Rows should have a created_at timestamp auto-populated."""
    await log.append({"name": "test", "value": "val"})
    rows = await log.query()
    assert len(rows) == 1
    assert rows[0]["created_at"] is not None


# --- Range filter tests (added for time-range SQL-level filtering) ---


async def test_append_log_range_filter_gte(db):
    """range_filters with >= operator pushes to SQL."""
    log = AppendOnlyLog(db, "ts_log", [("ts", "TEXT NOT NULL"), ("payload", "TEXT")])
    await log.initialize()
    await log.append({"ts": "2026-01-01", "payload": "jan"})
    await log.append({"ts": "2026-06-15", "payload": "jun"})
    await log.append({"ts": "2026-12-31", "payload": "dec"})

    rows = await log.query(range_filters=[("ts", ">=", "2026-06-01")])
    assert len(rows) == 2
    assert rows[0]["payload"] == "jun"
    assert rows[1]["payload"] == "dec"


async def test_append_log_range_filter_lte(db):
    """range_filters with <= operator pushes to SQL."""
    log = AppendOnlyLog(db, "ts_log2", [("ts", "TEXT NOT NULL"), ("payload", "TEXT")])
    await log.initialize()
    await log.append({"ts": "2026-01-01", "payload": "jan"})
    await log.append({"ts": "2026-06-15", "payload": "jun"})
    await log.append({"ts": "2026-12-31", "payload": "dec"})

    rows = await log.query(range_filters=[("ts", "<=", "2026-06-30")])
    assert len(rows) == 2
    assert rows[0]["payload"] == "jan"
    assert rows[1]["payload"] == "jun"


async def test_append_log_range_filter_combined(db):
    """Multiple range_filters combine with AND."""
    log = AppendOnlyLog(db, "ts_log3", [("ts", "TEXT NOT NULL"), ("payload", "TEXT")])
    await log.initialize()
    await log.append({"ts": "2026-01-01", "payload": "jan"})
    await log.append({"ts": "2026-06-15", "payload": "jun"})
    await log.append({"ts": "2026-12-31", "payload": "dec"})

    rows = await log.query(range_filters=[
        ("ts", ">=", "2026-03-01"),
        ("ts", "<=", "2026-09-01"),
    ])
    assert len(rows) == 1
    assert rows[0]["payload"] == "jun"


async def test_append_log_range_filter_invalid_op(db):
    """Invalid range operator raises ValueError."""
    log = AppendOnlyLog(db, "ts_log4", [("ts", "TEXT")])
    await log.initialize()
    with pytest.raises(ValueError, match="Invalid range operator"):
        await log.query(range_filters=[("ts", "LIKE", "%test%")])


async def test_append_log_query_with_offset(db):
    """SQL OFFSET skips rows at the database level."""
    log = AppendOnlyLog(db, "off_log", [("name", "TEXT NOT NULL")])
    await log.initialize()
    for i in range(5):
        await log.append({"name": f"item{i}"})

    rows = await log.query(limit=2, offset=2)
    assert len(rows) == 2
    assert rows[0]["name"] == "item2"
    assert rows[1]["name"] == "item3"


async def test_append_log_range_with_equality_filters(db):
    """Range filters and equality filters combine correctly."""
    log = AppendOnlyLog(db, "combo_log", [
        ("category", "TEXT NOT NULL"),
        ("ts", "TEXT NOT NULL"),
        ("payload", "TEXT"),
    ])
    await log.initialize()
    await log.append({"category": "a", "ts": "2026-01-01", "payload": "a-jan"})
    await log.append({"category": "b", "ts": "2026-06-15", "payload": "b-jun"})
    await log.append({"category": "a", "ts": "2026-12-31", "payload": "a-dec"})

    rows = await log.query(
        filters={"category": "a"},
        range_filters=[("ts", ">=", "2026-06-01")],
    )
    assert len(rows) == 1
    assert rows[0]["payload"] == "a-dec"
    assert len(rows[0]["created_at"]) > 0
