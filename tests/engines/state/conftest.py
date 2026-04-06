"""Shared fixtures for state engine tests."""

import pytest

from volnix.engines.state.causal_graph import CausalGraph
from volnix.engines.state.event_log import EventLog
from volnix.engines.state.migrations import STATE_MIGRATIONS
from volnix.engines.state.store import EntityStore
from volnix.persistence.migrations import MigrationRunner
from volnix.persistence.sqlite import SQLiteDatabase


@pytest.fixture
async def db(tmp_path):
    """Fresh SQLite database with state engine schema applied via migrations."""
    database = SQLiteDatabase(str(tmp_path / "test_state.db"))
    await database.connect()
    runner = MigrationRunner(database)
    for m in STATE_MIGRATIONS:
        runner.register(m)
    await runner.migrate_up()
    yield database
    await database.close()


@pytest.fixture
def store(db):
    return EntityStore(db)


@pytest.fixture
def event_log(db):
    return EventLog(db)


@pytest.fixture
def graph(db):
    return CausalGraph(db)
