"""Phase 4C Step 6 — AppendOnlyLog migration-on-connect tests.

Locks the D6b + audit-C1 behaviour: ``initialize()`` runs a
``PRAGMA table_info`` diff against declared columns and
``ALTER TABLE ADD COLUMN`` for any missing entries. The
``_column_names`` set is updated so subsequent ``append()`` calls
recognise the new column.

Negative ratio: 3/4 = 75%.
"""

from __future__ import annotations

from volnix.persistence.append_log import AppendOnlyLog
from volnix.persistence.manager import create_database


async def test_negative_missing_column_added_on_reconnect() -> None:
    """Simulates a schema upgrade: create the table with column
    set A, then reopen with column set A+new and assert the new
    column is added via ALTER TABLE."""
    db = await create_database(":memory:", wal_mode=False)

    v1 = AppendOnlyLog(db=db, table_name="t", columns=[("a", "TEXT")])
    await v1.initialize()
    await v1.append({"a": "x"})

    v2 = AppendOnlyLog(
        db=db,
        table_name="t",
        columns=[("a", "TEXT"), ("b", "TEXT")],
    )
    await v2.initialize()
    # Live table must have the new column.
    rows = await db.fetchall("PRAGMA table_info(t)")
    col_names = {row["name"] for row in rows}
    assert "b" in col_names
    # The v2 instance's _column_names must include "b" so append
    # with the new column succeeds (audit-fold C1).
    await v2.append({"a": "y", "b": "z"})


async def test_negative_existing_column_not_duplicated() -> None:
    """A column already present in the live table MUST NOT trigger
    another ``ALTER TABLE``. SQLite would reject a duplicate-column
    ADD; a defensive migration pass must detect and skip."""
    db = await create_database(":memory:", wal_mode=False)
    log = AppendOnlyLog(db=db, table_name="t", columns=[("a", "TEXT"), ("b", "TEXT")])
    await log.initialize()
    # Running initialize again must not raise.
    await log.initialize()
    rows = await db.fetchall("PRAGMA table_info(t)")
    names = [row["name"] for row in rows]
    # No duplicates.
    assert names.count("b") == 1


async def test_negative_alter_strips_not_null_and_default() -> None:
    """Audit-fold M1: ``ALTER TABLE ADD COLUMN`` cannot carry
    NOT NULL without a DEFAULT; ``initialize()`` strips those
    modifiers via ``col_type.split()[0]``. A column declared
    ``"TEXT NOT NULL DEFAULT 'x'"`` should land as plain ``TEXT``
    on an existing table, with NULL values for pre-existing rows."""
    db = await create_database(":memory:", wal_mode=False)

    v1 = AppendOnlyLog(db=db, table_name="t", columns=[("a", "TEXT")])
    await v1.initialize()
    await v1.append({"a": "row1"})

    v2 = AppendOnlyLog(
        db=db,
        table_name="t",
        columns=[
            ("a", "TEXT"),
            ("b", "TEXT NOT NULL DEFAULT 'x'"),
        ],
    )
    await v2.initialize()
    # Pre-existing row has NULL (not 'x') because ADD COLUMN
    # cannot carry DEFAULT.
    rows = await db.fetchall("SELECT a, b FROM t")
    assert rows[0]["b"] is None


async def test_positive_migration_noop_for_fresh_db() -> None:
    """A fresh DB: ``CREATE TABLE IF NOT EXISTS`` creates the
    table with all columns present, so the ALTER pass runs zero
    statements. Regression guard against a future refactor that
    would re-apply ALTER on every connect."""
    db = await create_database(":memory:", wal_mode=False)
    log = AppendOnlyLog(db=db, table_name="t", columns=[("a", "TEXT"), ("b", "TEXT")])
    await log.initialize()
    rows = await db.fetchall("PRAGMA table_info(t)")
    names = {row["name"] for row in rows}
    assert "a" in names and "b" in names
