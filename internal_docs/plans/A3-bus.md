# Phase A3: Event Bus Module Implementation

## Context

**Phase:** A3 (third implementation phase)
**Module:** `terrarium/bus/`
**Depends on:** A1 (persistence — BusPersistence uses SQLiteDatabase)
**Goal:** A working async event bus — the nervous system connecting all engines. Pub/sub with topic routing, SQLite persistence, replay, middleware, and back-pressure.

**Bigger picture:** The bus is THE communication backbone. Per DESIGN_PRINCIPLES.md: "All inter-engine communication flows through typed events. Engines never call each other directly." Every engine calls `self._bus.publish(event)` and receives events via `self._bus.subscribe(event_type, callback)`. The bus persists every event **before** fanout (the log is never behind). Replay enables debugging, counterfactual analysis, and crash recovery. Without a working bus, engines are isolated silos that can't talk.

**After A3:** We have persistence (A1) + config (A2) + bus (A3). The foundation for A4 (ledger) and all engine communication. An engine can publish an event, subscribers receive it, events are persisted to SQLite, and we can replay them.

---

## Key Design Decisions

1. **BusPersistence receives `Database` via DI** — does NOT create its own SQLiteDatabase. The ConnectionManager from A1 provides the database. Per DESIGN_PRINCIPLES: "DO use the persistence module for all database operations — never create standalone SQLite connections."
2. **Shared `AppendOnlyLog` base** — both bus persistence (A3) and ledger (A4) share the same append-only log infrastructure. This avoids duplicate SQL code and ensures consistent patterns. The base handles table creation, append, query, count. Subclasses handle serialization.
3. **Persist BEFORE fanout** — the spec says the log is never behind in-memory state. If fanout fails, the event is still persisted.
4. **Back-pressure: drop oldest** — when a subscriber queue is full, drop the oldest unprocessed event. The SQLite log preserves everything for replay.
5. **Consumer tasks (Actor-model isolation)** — each subscriber gets a background `asyncio.Task` that drains its own `asyncio.Queue`. Failures in one subscriber don't affect others. Slow subscribers don't block fast ones.
6. **Wildcard subscriptions** — subscribing to `"*"` receives ALL events. Used by dashboard, metrics, debugging.
7. **Event serialization** — Pydantic `model_dump_json()` for storage. Store `event_type` as a column for filtered queries. Deserialization returns base `Event` (typed deserialization via registry in Phase C+).
8. **Middleware: Chain of Responsibility** — before_publish can transform or drop events. after_publish is fire-and-forget (exceptions suppressed).

## Bus vs Ledger Boundary (designed together, implemented separately)

| | **Bus (A3)** | **Ledger (A4)** |
|---|---------|-----------|
| **Purpose** | Real-time inter-engine communication | Audit trail / flight recorder |
| **Content** | Domain events (WorldEvent, PolicyBlockEvent...) | Operational entries (PipelineStepEntry, LLMCallEntry...) |
| **Consumers** | Engines that subscribed to event types | Reporter, dashboard, debugging tools |
| **Written when** | During publish, BEFORE fanout | During each operation (pipeline step, LLM call, etc.) |
| **Replay** | Re-deliver events to subscribers | Reconstruct what the system did |
| **Shared infra** | `AppendOnlyLog` from `persistence/` | Same `AppendOnlyLog` from `persistence/` |

Both receive a `Database` from `ConnectionManager`. Both use `AppendOnlyLog`. Both are append-only. The difference is what they record and who consumes it.

## Design Patterns

```
EventBus (Mediator)
    │
    ├── TopicFanout (Observer)
    │   ├── topic subscriptions (observer registry)
    │   ├── wildcard subscriptions (catch-all)
    │   └── per-subscriber Queue + Task (Actor-model isolation)
    │
    ├── BusPersistence (Event Sourcing)
    │   └── AppendOnlyLog (shared infra, DI'd Database)
    │
    ├── ReplayEngine (Event Replay)
    │   └── reads from persistence, delivers to fanout or callback
    │
    └── MiddlewareChain (Chain of Responsibility)
        ├── before_publish: transform or drop
        └── after_publish: observe (fire-and-forget)
```

---

## Architecture

```
EventBus.publish(event)
    │
    ├── 1. MiddlewareChain.process_before(event)
    │       → may transform event or drop (return None)
    │
    ├── 2. BusPersistence.persist(event)  [if enabled]
    │       → SQLiteDatabase.execute(INSERT INTO event_log ...)
    │       → returns sequence_id
    │       → THIS HAPPENS BEFORE FANOUT
    │
    ├── 3. TopicFanout.fanout(event)
    │       → find all Subscriptions matching event.event_type
    │       → find all wildcard ("*") Subscriptions
    │       → for each: put event in subscriber's asyncio.Queue
    │       → if queue full: drop oldest, put new (back-pressure)
    │
    └── 4. MiddlewareChain.process_after(event)
            → logging, metrics, etc.

Each subscriber has:
    Subscription {
        event_type: str
        callback: async (Event) -> None
        queue: asyncio.Queue[Event]
        task: asyncio.Task  ← background consumer
    }

Consumer task (per subscriber):
    while True:
        event = await queue.get()
        try:
            await callback(event)
        except Exception:
            pass  # subscriber failures don't crash the bus
```

## Event Log Schema (SQLite)

```sql
CREATE TABLE IF NOT EXISTS event_log (
    sequence_id  INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id     TEXT UNIQUE NOT NULL,
    event_type   TEXT NOT NULL,
    timestamp    TEXT NOT NULL,
    caused_by    TEXT,
    payload      TEXT NOT NULL,    -- JSON serialized Event
    created_at   TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_event_type ON event_log(event_type);
CREATE INDEX IF NOT EXISTS idx_timestamp ON event_log(timestamp);
CREATE INDEX IF NOT EXISTS idx_event_id ON event_log(event_id);
```

---

## Implementation Order

### Step 1: `bus/types.py` — Fix and implement

The Subscription dataclass has `queue: asyncio.Queue = asyncio.Queue(maxsize=1000)` which is a mutable default (broken). Fix with `field(default_factory=...)`:

```python
@dataclass
class Subscription:
    event_type: str
    callback: Subscriber
    queue: asyncio.Queue[Event] = field(default_factory=lambda: asyncio.Queue(maxsize=1000))
    task: asyncio.Task[None] | None = None
```

BusMetrics is already a frozen Pydantic model — verify it works.

### Step 2: `persistence/append_log.py` — Shared AppendOnlyLog (NEW file in persistence/)

Both bus (A3) and ledger (A4) need an append-only SQLite log. Create the shared base in the persistence module where it belongs:

```python
"""Append-only log backed by SQLite. Shared by bus event log and ledger audit log."""

class AppendOnlyLog:
    def __init__(self, db: Database, table_name: str, columns: list[tuple[str, str]]):
        """
        Args:
            db: Database instance from ConnectionManager (DI).
            table_name: SQL table name (e.g., "event_log", "ledger_log").
            columns: List of (column_name, column_type) tuples beyond the
                     auto-generated sequence_id and created_at.
        """
        self._db = db
        self._table = table_name
        self._columns = columns

    async def initialize(self) -> None:
        """Create table + indexes if not exists."""
        cols = ", ".join(f"{name} {typ}" for name, typ in self._columns)
        await self._db.execute(f"""
            CREATE TABLE IF NOT EXISTS {self._table} (
                sequence_id INTEGER PRIMARY KEY AUTOINCREMENT,
                {cols},
                created_at TEXT NOT NULL DEFAULT (datetime('now'))
            )
        """)

    async def append(self, values: dict[str, Any]) -> int:
        """Append a record. Returns sequence_id."""
        col_names = ", ".join(values.keys())
        placeholders = ", ".join("?" for _ in values)
        await self._db.execute(
            f"INSERT INTO {self._table} ({col_names}) VALUES ({placeholders})",
            tuple(values.values())
        )
        row = await self._db.fetchone("SELECT last_insert_rowid() as seq")
        return row["seq"]

    async def query(self, from_sequence: int = 0, filters: dict | None = None,
                    limit: int | None = None) -> list[dict]:
        """Query records with optional filters."""
        sql = f"SELECT * FROM {self._table} WHERE sequence_id >= ?"
        params: list = [from_sequence]
        if filters:
            for col, val in filters.items():
                if isinstance(val, list):
                    placeholders = ",".join("?" for _ in val)
                    sql += f" AND {col} IN ({placeholders})"
                    params.extend(val)
                else:
                    sql += f" AND {col} = ?"
                    params.append(val)
        sql += " ORDER BY sequence_id ASC"
        if limit:
            sql += " LIMIT ?"
            params.append(limit)
        return await self._db.fetchall(sql, tuple(params))

    async def count(self, filters: dict | None = None) -> int:
        sql = f"SELECT COUNT(*) as cnt FROM {self._table}"
        params: list = []
        if filters:
            conditions = []
            for col, val in filters.items():
                conditions.append(f"{col} = ?")
                params.append(val)
            if conditions:
                sql += " WHERE " + " AND ".join(conditions)
        row = await self._db.fetchone(sql, tuple(params))
        return row["cnt"]

    async def latest_sequence(self) -> int:
        row = await self._db.fetchone(f"SELECT MAX(sequence_id) as seq FROM {self._table}")
        return row["seq"] if row and row["seq"] is not None else 0
```

This goes in `terrarium/persistence/append_log.py` and is added to persistence `__init__.py` exports. Tests go in `tests/persistence/test_append_log.py`.

### Step 3: `bus/persistence.py` — Event-specific wrapper around AppendOnlyLog

Receives `Database` via DI. Uses `AppendOnlyLog` for storage. Handles event serialization/deserialization.

```python
class BusPersistence:
    EVENT_COLUMNS = [
        ("event_id", "TEXT UNIQUE NOT NULL"),
        ("event_type", "TEXT NOT NULL"),
        ("timestamp", "TEXT NOT NULL"),
        ("caused_by", "TEXT"),
        ("payload", "TEXT NOT NULL"),
    ]

    def __init__(self, db: Database):  # DI — receives Database, not db_path
        self._log = AppendOnlyLog(db, "event_log", self.EVENT_COLUMNS)

    async def initialize(self) -> None:
        await self._log.initialize()
        # Add indexes for common query patterns
        await self._log._db.execute(
            "CREATE INDEX IF NOT EXISTS idx_event_type ON event_log(event_type)")
        await self._log._db.execute(
            "CREATE INDEX IF NOT EXISTS idx_timestamp ON event_log(timestamp)")

    async def shutdown(self) -> None:
        pass  # Database lifecycle managed by ConnectionManager, not here

    async def persist(self, event: Event) -> int:
        return await self._log.append({
            "event_id": str(event.event_id),
            "event_type": event.event_type,
            "timestamp": str(event.timestamp),
            "caused_by": str(event.caused_by) if event.caused_by else None,
            "payload": event.model_dump_json(),
        })

    async def query(self, from_sequence=0, event_types=None, limit=None) -> list[Event]:
        filters = {}
        if event_types:
            filters["event_type"] = event_types  # list → IN clause
        rows = await self._log.query(from_sequence, filters, limit)
        return [Event.model_validate_json(r["payload"]) for r in rows]

    async def get_count(self) -> int:
        return await self._log.count()

    async def get_latest_sequence(self) -> int:
        return await self._log.latest_sequence()
```

**Key: `shutdown()` is a no-op.** The Database lifecycle is managed by ConnectionManager, not by BusPersistence. This is correct per DI — the consumer doesn't own the resource it's given.

**Event deserialization note:** `Event.model_validate_json()` returns base Event. Payload preserves all fields. Typed deserialization via registry added in Phase C+. Documented as known limitation.

### Step 3: `bus/fanout.py` — Topic-based dispatcher

```python
class TopicFanout:
    def __init__(self):
        self._subscriptions: dict[str, list[Subscription]] = {}
        self._wildcard: list[Subscription] = []

    def add_subscriber(self, event_type: str, entry: Subscription):
        if event_type == "*":
            self._wildcard.append(entry)
        else:
            self._subscriptions.setdefault(event_type, []).append(entry)

    def remove_subscriber(self, event_type: str, callback: Subscriber):
        target = self._wildcard if event_type == "*" else self._subscriptions.get(event_type, [])
        target[:] = [s for s in target if s.callback is not callback]

    async def fanout(self, event: Event):
        targets = list(self._subscriptions.get(event.event_type, []))
        targets.extend(self._wildcard)
        for sub in targets:
            try:
                sub.queue.put_nowait(event)
            except asyncio.QueueFull:
                # Back-pressure: drop oldest, put new
                try:
                    sub.queue.get_nowait()
                except asyncio.QueueEmpty:
                    pass
                try:
                    sub.queue.put_nowait(event)
                except asyncio.QueueFull:
                    pass  # truly stuck, skip

    def get_subscriber_count(self, event_type=None):
        if event_type is None:
            total = sum(len(subs) for subs in self._subscriptions.values())
            return total + len(self._wildcard)
        if event_type == "*":
            return len(self._wildcard)
        return len(self._subscriptions.get(event_type, []))
```

### Step 4: `bus/middleware.py` — Middleware chain

BusMiddleware protocol + MiddlewareChain + LoggingMiddleware + MetricsMiddleware.

```python
class MiddlewareChain:
    def __init__(self):
        self._middleware: list[BusMiddleware] = []

    def add(self, middleware: BusMiddleware):
        self._middleware.append(middleware)

    async def process_before(self, event: Event) -> Event | None:
        current = event
        for mw in self._middleware:
            result = await mw.before_publish(current)
            if result is None:
                return None  # dropped
            current = result
        return current

    async def process_after(self, event: Event):
        for mw in self._middleware:
            try:
                await mw.after_publish(event)
            except Exception:
                pass  # after-publish failures are non-fatal

class LoggingMiddleware:
    def __init__(self):
        self.log: list[str] = []  # simple in-memory log for now

    async def before_publish(self, event):
        self.log.append(f"before:{event.event_type}:{event.event_id}")
        return event

    async def after_publish(self, event):
        self.log.append(f"after:{event.event_type}:{event.event_id}")

class MetricsMiddleware:
    def __init__(self):
        self.before_count = 0
        self.after_count = 0

    async def before_publish(self, event):
        self.before_count += 1
        return event

    async def after_publish(self, event):
        self.after_count += 1
```

### Step 6: `bus/bus.py` — EventBus (the orchestrator)

Wires together persistence + fanout + middleware. Receives `Database` via DI for persistence.

```python
class EventBus:
    def __init__(self, config: BusConfig, db: Database | None = None):
        """
        Args:
            config: BusConfig from the config system.
            db: Database instance from ConnectionManager. If None and
                persistence_enabled, raises ValueError.
        """
        self._config = config
        self._db = db
        self._fanout = TopicFanout()
        self._persistence: BusPersistence | None = None
        self._middleware = MiddlewareChain()
        self._metrics = {"published": 0, "delivered": 0, "dropped": 0, "persistence_errors": 0}

    async def initialize(self):
        if self._config.persistence_enabled:
            if self._db is None:
                raise ValueError("persistence_enabled=True but no Database provided")
            self._persistence = BusPersistence(self._db)
            await self._persistence.initialize()

    async def shutdown(self):
        # Cancel all subscriber consumer tasks
        # ... iterate through fanout subscriptions, cancel tasks
        # NOTE: we do NOT close self._db — ConnectionManager owns it

    async def subscribe(self, event_type, callback, queue_size=None):
        qs = queue_size or self._config.queue_size
        sub = Subscription(event_type=event_type, callback=callback,
                          queue=asyncio.Queue(maxsize=qs))
        sub.task = asyncio.create_task(self._consumer(sub))
        self._fanout.add_subscriber(event_type, sub)

    async def unsubscribe(self, event_type, callback):
        self._fanout.remove_subscriber(event_type, callback)

    async def publish(self, event):
        # 1. Middleware before
        processed = await self._middleware.process_before(event)
        if processed is None:
            return  # dropped by middleware

        # 2. Persist BEFORE fanout
        if self._persistence:
            try:
                await self._persistence.persist(processed)
            except Exception:
                self._metrics["persistence_errors"] += 1

        # 3. Fanout
        await self._fanout.fanout(processed)
        self._metrics["published"] += 1

        # 4. Middleware after
        await self._middleware.process_after(processed)

    async def replay(self, from_sequence=0, event_types=None, callback=None):
        if not self._persistence:
            return []
        events = await self._persistence.query(from_sequence, event_types)
        if callback:
            for e in events:
                await callback(e)
            return []
        return events

    async def get_event_count(self):
        if not self._persistence:
            return 0
        return await self._persistence.get_count()

    async def get_metrics(self):
        return BusMetrics(
            events_published=self._metrics["published"],
            events_delivered=self._metrics["delivered"],
            events_dropped=self._metrics["dropped"],
            persistence_errors=self._metrics["persistence_errors"],
        )

    @staticmethod
    async def _consumer(sub: Subscription):
        while True:
            event = await sub.queue.get()
            try:
                await sub.callback(event)
            except Exception:
                pass  # subscriber failures don't crash the bus
```

### Step 6: `bus/replay.py` — ReplayEngine

```python
class ReplayEngine:
    def __init__(self, persistence: BusPersistence, fanout: TopicFanout):
        self._persistence = persistence
        self._fanout = fanout

    async def replay_range(self, from_sequence, to_sequence=None, event_types=None):
        events = await self._persistence.query(from_sequence, event_types)
        if to_sequence is not None:
            events = [e for e in events if ...]  # need sequence tracking
        count = 0
        for event in events:
            await self._fanout.fanout(event)
            count += 1
        return count

    async def replay_timerange(self, start, end):
        # Query by timestamp range
        ...

    async def replay_to_callback(self, callback, from_sequence=0, event_types=None):
        events = await self._persistence.query(from_sequence, event_types)
        for event in events:
            await callback(event)
        return len(events)
```

**Note:** replay_timerange needs timestamp-based query in BusPersistence. Add a `query_by_time()` method or extend `query()` with time params.

---

## Files to Modify / Create

| File | Action | Notes |
|------|--------|-------|
| `terrarium/persistence/append_log.py` | **CREATE** | Shared AppendOnlyLog base (used by bus + ledger) |
| `terrarium/persistence/__init__.py` | **UPDATE** | Add AppendOnlyLog to exports |
| `terrarium/bus/types.py` | **FIX + IMPLEMENT** | Fix Subscription mutable default, verify BusMetrics |
| `terrarium/bus/persistence.py` | **IMPLEMENT** | Event log wrapper over AppendOnlyLog. Receives Database via DI. |
| `terrarium/bus/fanout.py` | **IMPLEMENT** | Topic routing + wildcard + back-pressure |
| `terrarium/bus/middleware.py` | **IMPLEMENT** | Chain + LoggingMiddleware + MetricsMiddleware |
| `terrarium/bus/bus.py` | **IMPLEMENT** | Orchestrator. Receives Database via DI. middleware → persist → fanout |
| `terrarium/bus/replay.py` | **IMPLEMENT** | Replay from persistence to fanout or callback |
| `terrarium/bus/config.py` | **VERIFY** | Already has defaults |
| `terrarium/bus/__init__.py` | **VERIFY** | Re-exports correct |
| `tests/persistence/test_append_log.py` | **CREATE** | ~6 tests for shared AppendOnlyLog |
| `tests/bus/test_bus.py` | **IMPLEMENT** | ~12 tests |
| `tests/bus/test_fanout.py` | **IMPLEMENT** | ~8 tests |
| `tests/bus/test_persistence.py` | **IMPLEMENT** | ~8 tests |
| `tests/bus/test_replay.py` | **IMPLEMENT** | ~6 tests |
| `tests/bus/test_middleware.py` | **IMPLEMENT** | ~7 tests |
| `tests/bus/test_integration.py` | **CREATE** | ~3 tests: bus + real persistence E2E |
| `IMPLEMENTATION_STATUS.md` | **UPDATE** | Flip bus to done, session log |
| `plans/A3-bus.md` | **CREATE** | Save plan to project |

---

## Tests

### test_persistence.py (~8 tests)
- test_persistence_initialize — creates event_log table
- test_persistence_persist_event — stores event, returns sequence_id
- test_persistence_query_all — retrieves all events in order
- test_persistence_query_by_type — filters by event_type
- test_persistence_query_range — from_sequence filtering
- test_persistence_query_limit — respects limit param
- test_persistence_get_count — correct count
- test_persistence_get_latest_sequence — returns max sequence_id

### test_fanout.py (~8 tests)
- test_fanout_add_subscriber — adds to correct topic
- test_fanout_remove_subscriber — removes by callback reference
- test_fanout_delivers_to_matching — only matching event_type receives
- test_fanout_wildcard — wildcard receives all events
- test_fanout_subscriber_count — counts per-type and total
- test_fanout_multiple_subscribers_same_type — all receive same event
- test_fanout_back_pressure_drop_oldest — full queue drops oldest
- test_fanout_no_subscribers_no_error — publishing to unsubscribed type is fine

### test_middleware.py (~7 tests)
- test_middleware_chain_before — transforms event
- test_middleware_chain_after — called after publish
- test_middleware_drop_event — before_publish returns None, event dropped
- test_middleware_chain_order — middleware runs in add order
- test_logging_middleware — records before/after
- test_metrics_middleware — counts before/after
- test_middleware_after_failure_nonfatal — after_publish exception doesn't crash

### test_bus.py (~10 tests)
- test_bus_initialize — persistence created when enabled
- test_bus_initialize_no_persistence — works with persistence_enabled=False
- test_bus_publish_subscribe — publish event, subscriber receives it
- test_bus_wildcard_subscription — wildcard subscriber gets all events
- test_bus_multiple_subscribers — two subscribers for same type both receive
- test_bus_unsubscribe — removed subscriber stops receiving
- test_bus_event_persisted — published event is in persistence
- test_bus_persist_before_fanout — persistence happens before subscriber callback
- test_bus_event_count — get_event_count matches published count
- test_bus_metrics — get_metrics returns correct counts
- test_bus_subscriber_error_nonfatal — subscriber exception doesn't crash bus
- test_bus_middleware_integration — middleware + publish + subscribe E2E

### test_replay.py (~6 tests)
- test_replay_range — replays events in sequence range
- test_replay_to_callback — delivers events to callback
- test_replay_filter_by_type — only specified types replayed
- test_replay_empty — no events returns 0
- test_replay_from_bus — bus.replay() delegates correctly
- test_replay_preserves_order — events replayed in original order

### test_bus_integration.py (NEW — cross-module)
- test_bus_with_real_persistence — EventBus + SQLiteDatabase from A1, full lifecycle
- test_publish_persist_replay_cycle — publish → persist → replay → verify identical

---

## Completion Criteria (Zero Stubs)

| File | Methods | All Implemented? | All Tested? |
|------|---------|-----------------|-------------|
| `persistence/append_log.py` | initialize, append, query, count, latest_sequence | ✅ 5 methods | ✅ 6 tests |
| `bus/types.py` | Subscriber, Subscription (fixed), BusMetrics | ✅ | ✅ via usage |
| `bus/persistence.py` | initialize, shutdown, persist, query, get_count, get_latest_sequence | ✅ 6 methods | ✅ 8 tests |
| `bus/fanout.py` | add_subscriber, remove_subscriber, fanout, get_subscriber_count | ✅ 4 methods | ✅ 8 tests |
| `bus/middleware.py` | MiddlewareChain (3), LoggingMiddleware (2), MetricsMiddleware (2) | ✅ 7 methods | ✅ 7 tests |
| `bus/bus.py` | initialize, shutdown, subscribe, unsubscribe, publish, replay, get_event_count, get_metrics, _consumer | ✅ 9 methods | ✅ 12 tests |
| `bus/replay.py` | replay_range, replay_timerange, replay_to_callback | ✅ 3 methods | ✅ 6 tests |
| `bus/config.py` | BusConfig fields | ✅ already done | ✅ via schema tests |
| `bus/__init__.py` | re-exports | ✅ | ✅ import test |

**0 stubs remaining in bus/ AND persistence/append_log.py. ~55 tests total across 8 test files.**

**After A3, A1-A3 should work seamlessly:**
- A1 (persistence): Database ABC, SQLiteDatabase, ConnectionManager, MigrationRunner, SnapshotStore, **AppendOnlyLog** ← NEW
- A2 (config): ConfigLoader, TerrariumConfig, ConfigRegistry, TunableRegistry, ConfigValidator
- A3 (bus): EventBus, TopicFanout, BusPersistence (uses AppendOnlyLog from A1), ReplayEngine, MiddlewareChain
- All using DI — bus receives Database from ConnectionManager, not creating its own

---

## Known Limitation (documented, not a bug)

**Event deserialization:** `Event.model_validate_json()` deserializes to the base `Event` class, not to specific subtypes (WorldEvent, PolicyBlockEvent, etc.). The full payload is preserved in JSON, so no data is lost. Typed deserialization will be added when the event type registry is implemented (Phase C+). This is documented in `IMPLEMENTATION_STATUS.md` under Known Issues.

---

## Post-Implementation Tasks

### 1. Save plan
Copy to `plans/A3-bus.md` in the project repo.

### 2. Update IMPLEMENTATION_STATUS.md

**Current Focus:**
```
**Phase:** A — Foundation Modules
**Item:** A3 bus/ ✅ COMPLETE → Next: A4 ledger/
**Status:** Bus module fully implemented. Pub/sub, persistence, replay, middleware.
```

**Flip these rows to ✅ done:**
- Bus — bus
- Bus — fanout
- Bus — persistence
- Bus — replay
- Bus — middleware

**Session log entry with:** implementations, test count, coverage, decisions, known limitation.

---

## Verification

1. `.venv/bin/python -m pytest tests/bus/ -v` — ALL pass
2. `.venv/bin/python -m pytest tests/persistence/test_append_log.py -v` — ALL pass (new shared infra)
3. `.venv/bin/python -m pytest tests/bus/ tests/persistence/ --cov=terrarium/bus --cov=terrarium/persistence --cov-report=term-missing` — >90% coverage for both
4. `grep -rn "^\s*\.\.\.$" terrarium/bus/*.py terrarium/persistence/append_log.py` — 0 results
5. **DI verification** — bus does NOT import SQLiteDatabase directly. Only receives `Database` ABC:
   ```bash
   grep -n "SQLiteDatabase" terrarium/bus/*.py  # should be 0 results
   ```
6. **A1-A3 integration smoke test:**
   ```python
   from terrarium.persistence import ConnectionManager, PersistenceConfig
   from terrarium.bus import EventBus, BusConfig
   from terrarium.core.events import Event

   # A1: persistence provides the database
   mgr = ConnectionManager(PersistenceConfig(base_dir="/tmp/test"))
   await mgr.initialize()
   db = await mgr.get_connection("bus_events")

   # A3: bus receives the database via DI
   bus = EventBus(BusConfig(persistence_enabled=True), db=db)
   await bus.initialize()

   # Publish, subscribe, persist, replay — all work
   received = []
   await bus.subscribe("test", lambda e: received.append(e))
   await bus.publish(Event(...))
   assert len(received) == 1
   replayed = await bus.replay()
   assert len(replayed) == 1

   await bus.shutdown()
   await mgr.shutdown()
   ```
7. **ALL previous tests still pass:** `.venv/bin/python -m pytest tests/ -q` — 446+ passed, 0 failed
8. `plans/A3-bus.md` exists in project repo
9. `IMPLEMENTATION_STATUS.md` updated with bus → done + session log + known limitation (event deserialization)
