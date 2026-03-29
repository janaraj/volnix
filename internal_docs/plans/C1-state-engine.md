# Phase C1: State Engine — First Vertical Slice

## Context

**Phase:** C1 (proves architecture end-to-end)
**Module:** `terrarium/engines/state/`
**Depends on:** A1 (persistence — Database, MigrationRunner, SnapshotStore), A3 (bus — EventBus), A4 (ledger — Ledger, StateMutationEntry), B2 (pipeline — DAG, PipelineStep), B4 (registry — EngineRegistry, wire_engines)
**Goal:** Authoritative world-state store with proper integration into bus, ledger, replay, and pipeline.

**Architectural concerns addressed in this plan:**
1. **Schema ownership** — Tables defined via `MigrationRunner` (not scattered CREATE TABLE)
2. **Event bus integration** — Publish events after commit, subscribe to topics
3. **Ledger integration** — Record `StateMutationEntry` for every state change
4. **Replayability** — Event sourcing: rebuild state from event log
5. **Retractability** — Compensating events via `previous_fields` on StateDelta
6. **Component ownership** — Persistence owns schema; engine owns business logic; bus delivers events; ledger audits

---

## Component Ownership Map

```
┌─────────────────────────────────────────────────────────┐
│ terrarium/persistence/ (OWNS: schema, connections, SQL) │
│  ├── migrations.py  — MigrationRunner (versioned DDL)   │
│  ├── database.py    — Database ABC (execute, fetchall)   │
│  ├── sqlite.py      — SQLiteDatabase (WAL, transactions) │
│  └── snapshot.py    — SnapshotStore (backup/restore)     │
├─────────────────────────────────────────────────────────┤
│ terrarium/engines/state/ (OWNS: business logic ONLY)    │
│  ├── migrations.py  — Schema definitions (Migration[])   │
│  │   (defines WHAT tables exist, not HOW to create them) │
│  ├── store.py       — EntityStore (CRUD via Database)    │
│  ├── event_log.py   — EventLog (append/query via DB)    │
│  ├── causal_graph.py— CausalGraph (DAG traversal)       │
│  └── engine.py      — StateEngine (orchestrator)         │
├─────────────────────────────────────────────────────────┤
│ terrarium/bus/ (OWNS: event delivery)                   │
│  └── StateEngine.publish(event) → bus.publish()          │
│      → persist to bus log → fanout to subscribers        │
├─────────────────────────────────────────────────────────┤
│ terrarium/ledger/ (OWNS: audit trail)                   │
│  └── StateEngine records StateMutationEntry after commit │
└─────────────────────────────────────────────────────────┘
```

---

## Implementation Order (7 steps)

### Step 1: `terrarium/engines/state/migrations.py` — Schema Definitions (NEW)

**Why:** Tables should NOT be created via scattered `CREATE TABLE` in each component's `initialize()`. Instead, define migrations using the existing `MigrationRunner` from `terrarium/persistence/migrations.py` (already built in A1, fully tested).

**Pattern:** Each engine defines its `Migration` list. The engine's `_on_initialize()` calls `MigrationRunner.migrate_up()` to apply them. This centralizes schema per-engine and enables versioned schema evolution.

**Reference:** `terrarium/persistence/migrations.py:16-24` — `Migration` dataclass:
```python
@dataclass
class Migration:
    version: int
    name: str
    sql_up: str
    sql_down: str
```

**File content:**
```python
"""Schema migrations for the state engine database."""
from terrarium.persistence.migrations import Migration

STATE_MIGRATIONS: list[Migration] = [
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
            );
            CREATE INDEX IF NOT EXISTS idx_entities_type ON entities(entity_type);
            CREATE INDEX IF NOT EXISTS idx_entities_id ON entities(entity_id);
        """,
        sql_down="DROP TABLE IF EXISTS entities;",
    ),
    Migration(
        version=2,
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
            );
            CREATE INDEX IF NOT EXISTS idx_events_ts ON events(timestamp_world);
            CREATE INDEX IF NOT EXISTS idx_events_actor ON events(actor_id);
            CREATE INDEX IF NOT EXISTS idx_events_target ON events(target_entity);
            CREATE INDEX IF NOT EXISTS idx_events_type ON events(event_type);
            CREATE INDEX IF NOT EXISTS idx_events_tick ON events(tick);
        """,
        sql_down="DROP TABLE IF EXISTS events;",
    ),
    Migration(
        version=3,
        name="create_causal_edges_table",
        sql_up="""
            CREATE TABLE IF NOT EXISTS causal_edges (
                cause_id  TEXT NOT NULL,
                effect_id TEXT NOT NULL,
                UNIQUE(cause_id, effect_id)
            );
            CREATE INDEX IF NOT EXISTS idx_causal_cause ON causal_edges(cause_id);
            CREATE INDEX IF NOT EXISTS idx_causal_effect ON causal_edges(effect_id);
        """,
        sql_down="DROP TABLE IF EXISTS causal_edges;",
    ),
]
```

**Key point:** The `sql_up` strings contain multiple statements. `MigrationRunner.migrate_up()` at `persistence/migrations.py:85-113` calls `self._db.execute(migration.sql_up)` inside a transaction. SQLite's `execute()` handles multi-statement SQL via `executescript()` — BUT we need to verify this works. If not, split into separate migrations per statement.

### Step 2: `terrarium/engines/state/store.py` — EntityStore

**Principle:** EntityStore does NOT create tables. It assumes tables exist (created by MigrationRunner in Step 1). It only does CRUD business logic via `Database` ABC.

**Reference files:**
- `terrarium/persistence/database.py` — Database ABC methods: `execute()`, `fetchone()`, `fetchall()`
- `terrarium/core/errors.py:182-191` — `StateError`, `EntityNotFoundError` (already exist)

**Method implementations:**

```python
"""Entity store — CRUD operations for world entities."""
from __future__ import annotations
import json
import logging
from typing import Any
from terrarium.core.types import EntityId
from terrarium.core.errors import EntityNotFoundError, StateError
from terrarium.persistence.database import Database

logger = logging.getLogger(__name__)

class EntityStore:
    def __init__(self, db: Database) -> None:
        self._db = db

    # NO initialize() that creates tables — migrations handle that

    async def create(self, entity_type: str, entity_id: EntityId, fields: dict[str, Any]) -> None:
        try:
            await self._db.execute(
                "INSERT INTO entities (entity_type, entity_id, data) VALUES (?, ?, ?)",
                (entity_type, str(entity_id), json.dumps(fields)),
            )
        except Exception as exc:
            if "UNIQUE constraint" in str(exc):
                raise StateError(f"Entity already exists: {entity_type}/{entity_id}") from exc
            raise

    async def read(self, entity_type: str, entity_id: EntityId) -> dict[str, Any] | None:
        row = await self._db.fetchone(
            "SELECT data FROM entities WHERE entity_type = ? AND entity_id = ?",
            (entity_type, str(entity_id)),
        )
        if row is None:
            return None
        result = json.loads(row["data"])
        result["_entity_type"] = entity_type
        result["_entity_id"] = str(entity_id)
        return result

    async def update(self, entity_type: str, entity_id: EntityId, fields: dict[str, Any]) -> dict[str, Any]:
        """Update fields (merge semantics). Returns the pre-update state for retractability."""
        existing = await self.read(entity_type, entity_id)
        if existing is None:
            raise EntityNotFoundError(f"Entity not found: {entity_type}/{entity_id}")
        # Capture pre-update state (for StateDelta.previous_fields / retract)
        previous = {k: v for k, v in existing.items() if not k.startswith("_")}
        existing.update(fields)
        # Remove metadata keys before persisting
        data = {k: v for k, v in existing.items() if not k.startswith("_")}
        await self._db.execute(
            "UPDATE entities SET data = ?, updated_at = datetime('now') WHERE entity_type = ? AND entity_id = ?",
            (json.dumps(data), entity_type, str(entity_id)),
        )
        return previous  # caller can use this for StateDelta.previous_fields

    async def delete(self, entity_type: str, entity_id: EntityId) -> dict[str, Any] | None:
        """Delete entity. Returns pre-delete state for retractability, or None if missing."""
        existing = await self.read(entity_type, entity_id)
        await self._db.execute(
            "DELETE FROM entities WHERE entity_type = ? AND entity_id = ?",
            (entity_type, str(entity_id)),
        )
        if existing:
            return {k: v for k, v in existing.items() if not k.startswith("_")}
        return None

    async def query(self, entity_type: str, filters: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        rows = await self._db.fetchall(
            "SELECT entity_id, data FROM entities WHERE entity_type = ?",
            (entity_type,),
        )
        results = []
        for row in rows:
            entity = json.loads(row["data"])
            entity["_entity_type"] = entity_type
            entity["_entity_id"] = row["entity_id"]
            # Python-side filtering (SQLite json_extract optimization in future)
            if filters:
                if all(entity.get(k) == v for k, v in filters.items()):
                    results.append(entity)
            else:
                results.append(entity)
        return results

    async def count(self, entity_type: str) -> int:
        row = await self._db.fetchone(
            "SELECT COUNT(*) as cnt FROM entities WHERE entity_type = ?",
            (entity_type,),
        )
        return row["cnt"] if row else 0
```

**Key design decisions:**
- `update()` returns previous state → enables `StateDelta.previous_fields` for retractability
- `delete()` returns pre-delete state → same reason
- No `initialize()` method — tables created by MigrationRunner

### Step 3: `terrarium/engines/state/event_log.py` — EventLog

**Same principle:** No table creation. Assumes tables exist from migrations.

**Pattern:** Like `BusPersistence` (`bus/persistence.py:52-65`) — store indexed columns + full payload JSON. Reference: `WorldEvent.model_dump_json()` for serialization, `WorldEvent.model_validate_json()` for deserialization.

```python
"""Append-only event log for the state engine."""
from __future__ import annotations
import logging
from datetime import datetime
from typing import Any
from terrarium.core.types import ActorId, EntityId, EventId
from terrarium.core.events import Event, WorldEvent
from terrarium.persistence.database import Database

logger = logging.getLogger(__name__)

class EventLog:
    def __init__(self, db: Database) -> None:
        self._db = db

    async def append(self, event: Event) -> EventId:
        """Append event. Extract indexed fields, store full payload. Never updates."""
        # Extract fields for indexed columns (WorldEvent-specific fields may not exist on base Event)
        actor_id = getattr(event, "actor_id", None)
        service_id = getattr(event, "service_id", None)
        action = getattr(event, "action", None)
        target = getattr(event, "target_entity", None)

        await self._db.execute(
            """INSERT INTO events
               (event_id, event_type, timestamp_world, timestamp_wall, tick,
                actor_id, service_id, action, target_entity, payload)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                str(event.event_id),
                event.event_type,
                event.timestamp.world_time.isoformat() if event.timestamp.world_time else None,
                event.timestamp.wall_time.isoformat() if event.timestamp.wall_time else None,
                event.timestamp.tick,
                str(actor_id) if actor_id else None,
                str(service_id) if service_id else None,
                action,
                str(target) if target else None,
                event.model_dump_json(),
            ),
        )
        return event.event_id

    async def get(self, event_id: EventId) -> Event | None:
        row = await self._db.fetchone(
            "SELECT payload FROM events WHERE event_id = ?", (str(event_id),)
        )
        if row is None:
            return None
        return self._deserialize(row["payload"])

    async def query(
        self,
        start: datetime | None = None,
        end: datetime | None = None,
        actor_id: ActorId | None = None,
        entity_id: EntityId | None = None,
        event_type: str | None = None,
        limit: int | None = None,
    ) -> list[Event]:
        """Query events with optional filters. All filters are AND'd."""
        sql = "SELECT payload FROM events WHERE 1=1"
        params: list[Any] = []
        if start is not None:
            sql += " AND timestamp_world >= ?"
            params.append(start.isoformat())
        if end is not None:
            sql += " AND timestamp_world <= ?"
            params.append(end.isoformat())
        if actor_id is not None:
            sql += " AND actor_id = ?"
            params.append(str(actor_id))
        if entity_id is not None:
            sql += " AND target_entity = ?"
            params.append(str(entity_id))
        if event_type is not None:
            sql += " AND event_type = ?"
            params.append(event_type)
        sql += " ORDER BY timestamp_world ASC, tick ASC"
        if limit is not None:
            sql += " LIMIT ?"
            params.append(limit)
        rows = await self._db.fetchall(sql, tuple(params))
        return [self._deserialize(row["payload"]) for row in rows]

    async def get_by_entity(self, entity_type: str, entity_id: EntityId) -> list[Event]:
        return await self.query(entity_id=entity_id)

    def _deserialize(self, payload: str) -> Event:
        """Deserialize event payload. Try WorldEvent first, fall back to Event."""
        try:
            return WorldEvent.model_validate_json(payload)
        except Exception:
            return Event.model_validate_json(payload)
```

### Step 4: `terrarium/engines/state/causal_graph.py` — CausalGraph

No table creation. BFS traversal for chain walking.

```python
"""Causal graph — DAG tracking cause→effect relationships between events."""
from __future__ import annotations
import logging
from collections import deque
from terrarium.core.types import EventId
from terrarium.persistence.database import Database

logger = logging.getLogger(__name__)

class CausalGraph:
    def __init__(self, db: Database) -> None:
        self._db = db

    async def add_edge(self, cause_id: EventId, effect_id: EventId) -> None:
        await self._db.execute(
            "INSERT OR IGNORE INTO causal_edges (cause_id, effect_id) VALUES (?, ?)",
            (str(cause_id), str(effect_id)),
        )

    async def get_causes(self, event_id: EventId) -> list[EventId]:
        rows = await self._db.fetchall(
            "SELECT cause_id FROM causal_edges WHERE effect_id = ?", (str(event_id),)
        )
        return [EventId(row["cause_id"]) for row in rows]

    async def get_effects(self, event_id: EventId) -> list[EventId]:
        rows = await self._db.fetchall(
            "SELECT effect_id FROM causal_edges WHERE cause_id = ?", (str(event_id),)
        )
        return [EventId(row["effect_id"]) for row in rows]

    async def get_chain(self, event_id: EventId, direction: str = "backward", max_depth: int = 50) -> list[EventId]:
        """BFS traversal. direction="backward" walks causes, "forward" walks effects."""
        visited: set[str] = set()
        result: list[EventId] = []
        queue: deque[tuple[EventId, int]] = deque([(event_id, 0)])
        while queue:
            current, depth = queue.popleft()
            key = str(current)
            if key in visited or depth > max_depth:
                continue
            visited.add(key)
            if current != event_id:
                result.append(current)
            neighbors = await self.get_causes(current) if direction == "backward" else await self.get_effects(current)
            for n in neighbors:
                if str(n) not in visited:
                    queue.append((n, depth + 1))
        return result

    async def get_roots(self, event_id: EventId) -> list[EventId]:
        """Walk backward to root causes (events with no parents)."""
        chain = await self.get_chain(event_id, "backward")
        if not chain:
            return [event_id]
        roots = []
        for eid in chain:
            causes = await self.get_causes(eid)
            if not causes:
                roots.append(eid)
        return roots if roots else [event_id]
```

### Step 5: `terrarium/engines/state/engine.py` — StateEngine

**This is the orchestrator.** Key integration points:
1. Uses `MigrationRunner` for schema (not raw CREATE TABLE)
2. Publishes events to **bus** after commit
3. Records `StateMutationEntry` to **ledger** after commit
4. Supports **replay** via `rebuild_from_events()`
5. Supports **retract** via compensating events with `previous_fields`

**Database access pattern:**
- StateEngine creates `SQLiteDatabase` from config in `_on_initialize()`
- Passes it to Store, EventLog, CausalGraph as `Database` ABC (DI)
- Uses `MigrationRunner` to ensure schema is current

**Ledger access pattern:**
- Ledger is NOT a dependency of StateEngine (no circular deps)
- Instead, the **pipeline DAG** already records `PipelineStepEntry` for each step
- StateEngine additionally records `StateMutationEntry` entries
- Ledger can be injected via config or wiring (passed in `_config["ledger"]`)

**Critical method: `execute()` (pipeline commit step):**
```python
async def execute(self, ctx: ActionContext) -> StepResult:
    """Pipeline commit step: apply deltas, persist event, record to ledger, publish to bus."""
    proposal = ctx.response_proposal
    if proposal is None:
        return StepResult(step_name="commit", verdict=StepVerdict.ERROR, message="No response proposal")

    async with self._db.transaction():
        # 1. Apply state deltas (with previous_fields for retractability)
        applied_deltas: list[StateDelta] = []
        for delta in (proposal.proposed_state_deltas or []):
            if delta.operation == "create":
                await self._store.create(delta.entity_type, delta.entity_id, delta.fields)
                applied_deltas.append(delta)
            elif delta.operation == "update":
                previous = await self._store.update(delta.entity_type, delta.entity_id, delta.fields)
                applied_deltas.append(StateDelta(
                    entity_type=delta.entity_type, entity_id=delta.entity_id,
                    operation="update", fields=delta.fields, previous_fields=previous,
                ))
            elif delta.operation == "delete":
                previous = await self._store.delete(delta.entity_type, delta.entity_id)
                applied_deltas.append(StateDelta(
                    entity_type=delta.entity_type, entity_id=delta.entity_id,
                    operation="delete", fields={}, previous_fields=previous,
                ))

        # 2. Create and persist the world event
        now = datetime.now(timezone.utc)
        event = WorldEvent(
            event_type=f"world.{ctx.action}",
            timestamp=Timestamp(
                world_time=ctx.world_time or now, wall_time=ctx.wall_time or now, tick=ctx.tick or 0,
            ),
            actor_id=ctx.actor_id, service_id=ctx.service_id, action=ctx.action,
            target_entity=ctx.target_entity, input_data=ctx.input_data or {},
        )
        await self._event_log.append(event)

        # 3. Record causal edges
        if event.caused_by:
            await self._causal_graph.add_edge(event.caused_by, event.event_id)
        for cause_id in event.causes:
            await self._causal_graph.add_edge(cause_id, event.event_id)

    # 4. Record to ledger (OUTSIDE transaction — ledger is separate DB)
    if self._ledger is not None:
        for delta in applied_deltas:
            entry = StateMutationEntry(
                entity_type=delta.entity_type, entity_id=str(delta.entity_id),
                operation=delta.operation, fields=delta.fields,
                previous_fields=delta.previous_fields,
                event_id=str(event.event_id), actor_id=str(ctx.actor_id),
            )
            await self._ledger.append(entry)

    # 5. Publish to bus (so other engines react)
    await self.publish(event)

    return StepResult(
        step_name="commit", verdict=StepVerdict.ALLOW,
        events=[event], metadata={"event_id": str(event.event_id), "deltas": len(applied_deltas)},
    )
```

**Retractability: `retract_event()` method:**
```python
async def retract_event(self, event_id: EventId) -> EventId:
    """Create a compensating event that reverses the state changes of the given event.

    Uses previous_fields from the original deltas (stored in ledger) to undo changes.
    This is append-only: the retraction is a NEW event, not deletion of the old one.
    """
    # Query ledger for StateMutationEntry records with this event_id
    # For each mutation, apply the reverse operation using previous_fields
    # Create a new "retract" event and commit it
```

**Rebuild from events (replay):**
```python
async def rebuild_from_events(self) -> int:
    """Rebuild entity state from the event log (event sourcing).

    Clears all entities and replays all events in order.
    Returns the number of events replayed.
    """
    # Clear entities table
    # Query all events ordered by timestamp
    # For each event, extract deltas and apply to store
    # This is the event sourcing reconstruction path
```

**`_on_initialize()` — uses MigrationRunner:**
```python
async def _on_initialize(self) -> None:
    from terrarium.engines.state.migrations import STATE_MIGRATIONS
    from terrarium.persistence.migrations import MigrationRunner

    db_path = self._config.get("db_path", "data/state.db")
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)

    self._db = SQLiteDatabase(db_path, wal_mode=True)
    await self._db.connect()

    # Apply migrations (centralized schema management)
    runner = MigrationRunner(self._db)
    for migration in STATE_MIGRATIONS:
        runner.register(migration)
    await runner.migrate_up()

    # Initialize business logic components (NO table creation here)
    self._store = EntityStore(self._db)
    self._event_log = EventLog(self._db)
    self._causal_graph = CausalGraph(self._db)

    # Snapshot support
    snapshot_dir = self._config.get("snapshot_dir", "snapshots")
    self._snapshot_store = SnapshotStore(PersistenceConfig(base_dir=snapshot_dir))

    # Ledger (optional, injected via config or set by wiring)
    self._ledger = self._config.get("_ledger")  # injected by wiring if available
```

### Step 6: Update `__init__.py` + Wire ledger injection

**`terrarium/engines/state/__init__.py`:**
```python
from terrarium.engines.state.engine import StateEngine
from terrarium.engines.state.store import EntityStore
from terrarium.engines.state.event_log import EventLog
from terrarium.engines.state.causal_graph import CausalGraph
__all__ = ["StateEngine", "EntityStore", "EventLog", "CausalGraph"]
```

**Ledger injection in wiring:** Update `wire_engines()` in `registry/wiring.py` to pass ledger reference to engines that need it. Add to the config dict before passing to engine:
```python
# In wire_engines, after extracting engine_config:
if hasattr(config, 'ledger') and engine_name == "state":
    engine_config["_ledger"] = ledger_instance  # if available
```
This keeps the interface clean — ledger is optional and injected via config.

### Step 7: Tests

*(See test harness section below)*

---

## Integration Flow (End-to-End)

```
1. Agent sends action via gateway
   ↓
2. Pipeline executes 7 steps in order:
   permission → policy → budget → capability → responder → validation → COMMIT
   ↓
3. COMMIT step (StateEngine.execute):
   a. Apply StateDelta(s) to EntityStore (within transaction)
      - update() captures previous_fields for retractability
   b. Create WorldEvent, append to EventLog
   c. Record causal edges in CausalGraph
   d. Record StateMutationEntry to Ledger (audit trail)
   e. Publish WorldEvent to EventBus (other engines react)
   ↓
4. Bus delivers event:
   - Persisted to bus log (BusPersistence) → replayable
   - Fanned out to subscribers (animator, reporter, feedback, etc.)
   ↓
5. Retract if needed:
   - retract_event(id) → reads previous_fields → applies reverse deltas
   - Creates compensating event (append-only, never deletes)
   ↓
6. Replay if needed:
   - rebuild_from_events() → clears entities → replays all events in order
   - Event sourcing reconstruction from the append-only log
```

---

## Files to Modify / Create

| File | Action | Notes |
|------|--------|-------|
| `terrarium/engines/state/migrations.py` | **CREATE** | 3 migrations (entities, events, causal_edges) |
| `terrarium/engines/state/store.py` | **IMPLEMENT** | 6 methods (no initialize — migrations handle schema) |
| `terrarium/engines/state/event_log.py` | **IMPLEMENT** | 5 methods (no initialize) |
| `terrarium/engines/state/causal_graph.py` | **IMPLEMENT** | 6 methods (no initialize) |
| `terrarium/engines/state/engine.py` | **IMPLEMENT** | 14 methods (execute, CRUD, snapshot, replay, retract) |
| `terrarium/engines/state/__init__.py` | **UPDATE** | Export public API |
| `tests/engines/state/conftest.py` | **CREATE** | Shared fixtures (db, store, engine) |
| `tests/engines/state/test_store.py` | **CREATE** | ~12 tests |
| `tests/engines/state/test_event_log.py` | **CREATE** | ~10 tests |
| `tests/engines/state/test_causal_graph.py` | **CREATE** | ~10 tests |
| `tests/engines/state/test_engine.py` | **CREATE** | ~14 tests |
| `tests/engines/state/test_integration.py` | **CREATE** | ~6 tests |
| `IMPLEMENTATION_STATUS.md` | **UPDATE** | Flip state rows to done |
| `plans/C1-state-engine.md` | **CREATE** | Save plan |

---

## Test Harness (~52 tests)

### Shared Fixtures (`conftest.py`)
```python
@pytest.fixture
async def db(tmp_path):
    """Fresh SQLite database with state engine schema applied."""
    from terrarium.persistence.sqlite import SQLiteDatabase
    from terrarium.persistence.migrations import MigrationRunner
    from terrarium.engines.state.migrations import STATE_MIGRATIONS

    database = SQLiteDatabase(str(tmp_path / "test.db"))
    await database.connect()
    runner = MigrationRunner(database)
    for m in STATE_MIGRATIONS:
        runner.register(m)
    await runner.migrate_up()
    yield database
    await database.close()

@pytest.fixture
def store(db): return EntityStore(db)

@pytest.fixture
def event_log(db): return EventLog(db)

@pytest.fixture
def graph(db): return CausalGraph(db)
```

### test_store.py (~12 tests)
| Test | Validates |
|------|-----------|
| `test_create_and_read` | Round-trip: create → read → fields match |
| `test_create_duplicate_raises` | StateError on UNIQUE violation |
| `test_read_missing_none` | Returns None for nonexistent entity |
| `test_update_merges` | Existing fields preserved, new fields added |
| `test_update_returns_previous` | Returns pre-update state for retractability |
| `test_update_missing_raises` | EntityNotFoundError |
| `test_delete_returns_previous` | Returns pre-delete state |
| `test_delete_then_read_none` | Entity gone after delete |
| `test_delete_missing_returns_none` | Idempotent, returns None |
| `test_query_by_type` | Returns all entities of a type |
| `test_query_with_filters` | Python-side filtering works |
| `test_count` | Correct count per type |

### test_event_log.py (~10 tests)
| Test | Validates |
|------|-----------|
| `test_append_and_get` | Round-trip with all fields preserved |
| `test_get_missing_none` | Returns None for unknown event_id |
| `test_query_time_range` | Start/end filtering on timestamp_world |
| `test_query_by_actor` | Filters by actor_id |
| `test_query_by_entity` | Filters by target_entity |
| `test_query_by_event_type` | Filters by event_type |
| `test_query_with_limit` | Respects limit parameter |
| `test_query_empty` | Returns [] when no matches |
| `test_get_by_entity` | Convenience method works |
| `test_events_ordered_by_time` | Results sorted by timestamp |

### test_causal_graph.py (~10 tests)
| Test | Validates |
|------|-----------|
| `test_add_and_get_causes` | Direct parents returned |
| `test_add_and_get_effects` | Direct children returned |
| `test_chain_backward_linear` | A→B→C→D, chain(D,backward)=[C,B,A] |
| `test_chain_forward` | A→B→C, chain(A,forward)=[B,C] |
| `test_chain_branching` | A→C, B→C, chain(C,backward)=[A,B] |
| `test_chain_max_depth` | Stops at max_depth |
| `test_get_roots` | Walks to root causes |
| `test_duplicate_edge_idempotent` | INSERT OR IGNORE |
| `test_unknown_event_empty` | Empty list for nonexistent |
| `test_diamond_pattern` | A→C, A→D, B→C, B→D, both paths found |

### test_engine.py (~14 tests)
| Test | Validates |
|------|-----------|
| `test_on_initialize_migration` | MigrationRunner applies schema, tables exist |
| `test_execute_creates_entity` | Pipeline commit: StateDelta create → entity in store |
| `test_execute_updates_entity` | Pipeline commit: update delta + previous_fields captured |
| `test_execute_deletes_entity` | Pipeline commit: delete delta |
| `test_execute_no_proposal_error` | StepVerdict.ERROR when no proposal |
| `test_execute_publishes_to_bus` | WorldEvent published via bus after commit |
| `test_execute_records_to_ledger` | StateMutationEntry recorded |
| `test_get_entity_found` | Retrieves stored entity |
| `test_get_entity_not_found` | EntityNotFoundError |
| `test_query_entities` | Filters correctly |
| `test_commit_event_persists` | Event in log + causal edges |
| `test_get_causal_chain` | Resolves chain to full events |
| `test_get_timeline` | Time-filtered event query |
| `test_on_stop_closes_db` | Database closed on stop |

### test_integration.py (~6 tests)
| Test | Validates |
|------|-----------|
| `test_full_pipeline_commit` | PipelineDAG with commit step → entity in store, event in log |
| `test_create_then_update` | Two pipeline executions, both events in timeline |
| `test_causal_chain_linked` | Two events with caused_by, chain connects them |
| `test_retractability_previous_fields` | Update captures previous_fields in ledger entry |
| `test_snapshot_creates` | SnapshotStore.save_snapshot returns SnapshotId |
| `test_registry_wiring` | StateEngine wires via create_default_registry + wire_engines |

---

## Verification

1. `pytest tests/engines/state/ -v` — ALL pass
2. `grep -rn "^\s*\.\.\.$" terrarium/engines/state/*.py` — 0 stubs
3. `grep -rn "CREATE TABLE" terrarium/engines/state/` — only in migrations.py (not store/event_log/graph)
4. `grep -rn "from terrarium.engines" terrarium/engines/state/ | grep -v "state"` — 0 cross-engine imports
5. `pytest tests/ -q` — 709 + ~52 = ~761 passed (no regressions)

---

## Post-Implementation

1. Save plan to `plans/C1-state-engine.md`
2. Update `IMPLEMENTATION_STATUS.md`:
   - Flip state engine rows to ✅ done
   - Add session log entry
   - Update current focus: `C1 state engine ✅ → Next: C2 email pack`
