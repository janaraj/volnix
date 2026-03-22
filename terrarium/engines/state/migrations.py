"""Schema migrations for the state engine database.

Each migration contains exactly ONE SQL statement because
``aiosqlite.Connection.execute()`` wraps ``sqlite3.Cursor.execute()``,
which only executes the first statement in a multi-statement string.
"""

from terrarium.persistence.migrations import Migration

STATE_MIGRATIONS: list[Migration] = [
    # -- entities table -------------------------------------------------------
    Migration(
        version=1,
        name="create_entities_table",
        sql_up="""
            CREATE TABLE IF NOT EXISTS entities (
                entity_type TEXT NOT NULL,
                entity_id   TEXT NOT NULL,
                data        TEXT NOT NULL,
                created_at  TEXT NOT NULL DEFAULT (datetime('now')),
                updated_at  TEXT NOT NULL DEFAULT (datetime('now')),
                UNIQUE(entity_type, entity_id)
            )
        """,
        sql_down="DROP TABLE IF EXISTS entities",
    ),
    Migration(
        version=2,
        name="create_idx_entities_type",
        sql_up="CREATE INDEX IF NOT EXISTS idx_entities_type ON entities(entity_type)",
        sql_down="DROP INDEX IF EXISTS idx_entities_type",
    ),
    Migration(
        version=3,
        name="create_idx_entities_id",
        sql_up="CREATE INDEX IF NOT EXISTS idx_entities_id ON entities(entity_id)",
        sql_down="DROP INDEX IF EXISTS idx_entities_id",
    ),
    # -- events table ---------------------------------------------------------
    Migration(
        version=4,
        name="create_events_table",
        sql_up="""
            CREATE TABLE IF NOT EXISTS events (
                event_id        TEXT PRIMARY KEY,
                event_type      TEXT NOT NULL,
                timestamp_world TEXT,
                timestamp_wall  TEXT,
                tick            INTEGER,
                actor_id        TEXT,
                service_id      TEXT,
                action          TEXT,
                target_entity   TEXT,
                payload         TEXT NOT NULL,
                created_at      TEXT NOT NULL DEFAULT (datetime('now'))
            )
        """,
        sql_down="DROP TABLE IF EXISTS events",
    ),
    Migration(
        version=5,
        name="create_idx_events_ts",
        sql_up="CREATE INDEX IF NOT EXISTS idx_events_ts ON events(timestamp_world)",
        sql_down="DROP INDEX IF EXISTS idx_events_ts",
    ),
    Migration(
        version=6,
        name="create_idx_events_actor",
        sql_up="CREATE INDEX IF NOT EXISTS idx_events_actor ON events(actor_id)",
        sql_down="DROP INDEX IF EXISTS idx_events_actor",
    ),
    Migration(
        version=7,
        name="create_idx_events_target",
        sql_up="CREATE INDEX IF NOT EXISTS idx_events_target ON events(target_entity)",
        sql_down="DROP INDEX IF EXISTS idx_events_target",
    ),
    Migration(
        version=8,
        name="create_idx_events_type",
        sql_up="CREATE INDEX IF NOT EXISTS idx_events_type ON events(event_type)",
        sql_down="DROP INDEX IF EXISTS idx_events_type",
    ),
    Migration(
        version=9,
        name="create_idx_events_tick",
        sql_up="CREATE INDEX IF NOT EXISTS idx_events_tick ON events(tick)",
        sql_down="DROP INDEX IF EXISTS idx_events_tick",
    ),
    # -- causal_edges table ---------------------------------------------------
    Migration(
        version=10,
        name="create_causal_edges_table",
        sql_up="""
            CREATE TABLE IF NOT EXISTS causal_edges (
                cause_id  TEXT NOT NULL,
                effect_id TEXT NOT NULL,
                UNIQUE(cause_id, effect_id)
            )
        """,
        sql_down="DROP TABLE IF EXISTS causal_edges",
    ),
    Migration(
        version=11,
        name="create_idx_causal_cause",
        sql_up="CREATE INDEX IF NOT EXISTS idx_causal_cause ON causal_edges(cause_id)",
        sql_down="DROP INDEX IF EXISTS idx_causal_cause",
    ),
    Migration(
        version=12,
        name="create_idx_causal_effect",
        sql_up="CREATE INDEX IF NOT EXISTS idx_causal_effect ON causal_edges(effect_id)",
        sql_down="DROP INDEX IF EXISTS idx_causal_effect",
    ),
]
