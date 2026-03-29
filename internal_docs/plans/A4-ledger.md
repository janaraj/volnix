# Phase A4: Ledger Module Implementation

## Context

**Phase:** A4 (fourth and final foundation phase)
**Module:** `terrarium/ledger/`
**Depends on:** A1 (persistence — Ledger uses AppendOnlyLog + Database via DI)
**Goal:** A working audit ledger — the flight recorder. Append-only, queryable, exportable. Records pipeline steps, state mutations, LLM calls, gateway requests, validations, engine lifecycle, and snapshots.

**Bigger picture:** Per DESIGN_PRINCIPLES.md: *"DO record every significant action in the ledger. The ledger is the flight recorder. If it did not produce a ledger entry, it did not happen."* Every engine will write to the ledger. The pipeline (B2) will record each step. The LLM tracker (B3) will record each call. The gateway (E1) will record each request. The reporter (F3) will READ the ledger to generate scorecards and two-direction observation reports. Without a working ledger, we have no audit trail, no observability, no compliance.

**Bus vs Ledger:** The bus carries domain events between engines (reactive communication). The ledger records what the system did (audit trail). Same infrastructure (AppendOnlyLog from A1), different concerns, different consumers.

**After A4:** Foundation complete (A1-A4). We have persistence, config, bus, AND ledger. Ready for Phase B (pipeline, validation, LLM, registry).

---

## Key Design Decisions

1. **Ledger receives `Database` via DI** — same pattern as BusPersistence. ConnectionManager owns lifecycle.
2. **Uses `AppendOnlyLog` from persistence/** — shared infrastructure, no duplicate SQL.
3. **Typed entry deserialization** — Unlike bus (which returns base `Event`), ledger stores `entry_type` and uses a registry to reconstruct the correct `LedgerEntry` subclass. We solve the deserialization problem HERE, not Phase C+.
4. **LedgerQuery drives filtering** — structured query model, not ad-hoc dicts. The `LedgerQueryBuilder` provides a fluent interface.
5. **Export to JSON/CSV** — writes query results to files for debugging, compliance, sharing.
6. **Entry type filtering** — config can enable/disable specific entry types (performance tuning).
7. **`shutdown()` is a no-op** — Database lifecycle managed by ConnectionManager (same as BusPersistence).

---

## Architecture

```
Ledger (implements LedgerProtocol)
    │
    ├── LedgerPersistence (wraps AppendOnlyLog)
    │   └── AppendOnlyLog (from persistence/ via DI)
    │       └── Database (from ConnectionManager)
    │
    ├── Entry Type Registry
    │   ├── "pipeline_step" → PipelineStepEntry
    │   ├── "state_mutation" → StateMutationEntry
    │   ├── "llm_call" → LLMCallEntry
    │   ├── "gateway_request" → GatewayRequestEntry
    │   ├── "validation" → ValidationEntry
    │   ├── "engine_lifecycle" → EngineLifecycleEntry
    │   └── "snapshot" → SnapshotEntry
    │
    ├── LedgerQuery + LedgerQueryBuilder (query model)
    │
    └── LedgerExporter (JSON, CSV, replay)
```

**Entry Type Registry** — The key difference from bus persistence. Each entry is stored as JSON with its `entry_type` string. On query, we look up the type in the registry and deserialize to the correct subclass:

```python
ENTRY_REGISTRY: dict[str, type[LedgerEntry]] = {
    "pipeline_step": PipelineStepEntry,
    "state_mutation": StateMutationEntry,
    "llm_call": LLMCallEntry,
    "gateway_request": GatewayRequestEntry,
    "validation": ValidationEntry,
    "engine_lifecycle": EngineLifecycleEntry,
    "snapshot": SnapshotEntry,
}

def deserialize_entry(row: dict) -> LedgerEntry:
    entry_type = row["entry_type"]
    cls = ENTRY_REGISTRY.get(entry_type, LedgerEntry)
    return cls.model_validate_json(row["payload"])
```

This solves the deserialization problem at the ledger level. The bus can adopt this pattern later (Phase C+) for typed event deserialization.

---

## Reuse from A1-A3 (what we DON'T rebuild)

| What | Built in | Reused by Ledger |
|------|----------|-----------------|
| `AppendOnlyLog` | A3 (persistence/) | Wraps it for ledger_log table — same pattern as BusPersistence |
| `Database` ABC | A1 (persistence/) | Receives via DI — same as BusPersistence |
| `ConnectionManager` | A1 (persistence/) | NOT imported by Ledger. Wiring layer (B4) uses it to get DB, passes to Ledger |
| `SQLiteDatabase` | A1 (persistence/) | NOT imported by Ledger. Only wiring layer and tests use it directly |
| `BusConfig` pattern | A3 (bus/) | Ledger follows identical DI pattern: `__init__(config, db)`, `shutdown()` is no-op |
| Entry serialization | A3 (bus/) | Same pattern: `model_dump_json()` to store, `model_validate_json()` to load |

**New in A4 (not in bus):** Typed deserialization via entry registry. The bus returns base `Event` — the ledger returns the correct subclass (`PipelineStepEntry`, `LLMCallEntry`, etc.) using the `entry_type` discriminator.

## DI Chain (how it all wires together in Phase B4)

```python
# Phase B4 (registry/wiring) will do:
mgr = ConnectionManager(config.persistence)
await mgr.initialize()

bus_db = await mgr.get_connection("bus")       # separate DB file
ledger_db = await mgr.get_connection("ledger") # separate DB file

bus = EventBus(config.bus, db=bus_db)
ledger = Ledger(config.ledger, db=ledger_db)

# Each module receives Database via DI
# Each module uses AppendOnlyLog internally
# ConnectionManager owns all DB lifecycles
# shutdown() on bus/ledger is a no-op — mgr.shutdown() closes everything
```

---

## Implementation Order

### Step 1: Verify `entries.py` — already has 7 entry types + base

The skeleton is complete with real Pydantic models (not stubs). Verify all fields have defaults where appropriate and `entry_type` is populated. **Issue:** The base `LedgerEntry` has `entry_type: str` but no default — subclasses need to set it. Add class-level defaults:

```python
class PipelineStepEntry(LedgerEntry):
    entry_type: str = "pipeline_step"  # discriminator
    ...

class StateMutationEntry(LedgerEntry):
    entry_type: str = "state_mutation"
    ...
```

Each subclass sets its own `entry_type` default so callers don't need to remember the string.

### Step 2: Implement `ledger.py` — Core Ledger

**Critical design: SQL-level filtering.** Store commonly-filtered fields as separate columns (not just in JSON payload). This allows ALL filters to push to SQL — no Python post-filtering needed. This is essential for reporter performance (F3 will query thousands of entries).

```python
class Ledger:
    # Columns extracted from entries for SQL-level filtering
    COLUMNS = [
        ("entry_type", "TEXT NOT NULL"),     # discriminator for typed deserialization
        ("timestamp", "TEXT NOT NULL"),       # ISO format, indexable
        ("actor_id", "TEXT"),                 # extracted from entry for SQL WHERE
        ("engine_name", "TEXT"),              # extracted from entry for SQL WHERE
        ("payload", "TEXT NOT NULL"),         # full JSON for deserialization
    ]

    def __init__(self, config: LedgerConfig, db: Database):
        """Receives Database via DI. ConnectionManager owns lifecycle.
        Same pattern as BusPersistence — Ledger doesn't create connections."""
        self._config = config
        self._db = db
        self._log = AppendOnlyLog(db=db, table_name="ledger_log", columns=self.COLUMNS)
        self._entry_types_enabled = (
            set(config.entry_types_enabled) if config.entry_types_enabled else None
        )

    async def initialize(self) -> None:
        await self._log.initialize()
        # Indexes for common query patterns (reporter will filter by these)
        await self._db.execute(
            "CREATE INDEX IF NOT EXISTS idx_ledger_type ON ledger_log(entry_type)")
        await self._db.execute(
            "CREATE INDEX IF NOT EXISTS idx_ledger_ts ON ledger_log(timestamp)")
        await self._db.execute(
            "CREATE INDEX IF NOT EXISTS idx_ledger_actor ON ledger_log(actor_id)")

    async def shutdown(self) -> None:
        pass  # Database lifecycle managed by ConnectionManager (same as BusPersistence)

    async def append(self, entry: LedgerEntry) -> int:
        if self._entry_types_enabled and entry.entry_type not in self._entry_types_enabled:
            return -1  # entry type disabled in config
        # Extract SQL-filterable fields from entry
        return await self._log.append({
            "entry_type": entry.entry_type,
            "timestamp": entry.timestamp.isoformat(),
            "actor_id": _extract_actor_id(entry),
            "engine_name": _extract_engine_name(entry),
            "payload": entry.model_dump_json(),
        })

    async def query(self, filters: LedgerQuery) -> list[LedgerEntry]:
        """ALL filtering pushed to SQL via AppendOnlyLog.query()."""
        sql_filters: dict = {}
        if filters.entry_type:
            sql_filters["entry_type"] = filters.entry_type
        if filters.actor_id:
            sql_filters["actor_id"] = str(filters.actor_id)
        if filters.engine_name:
            sql_filters["engine_name"] = filters.engine_name

        rows = await self._log.query(
            from_sequence=0,
            filters=sql_filters if sql_filters else None,
            limit=filters.limit,
        )

        # Time-range filtering (extend AppendOnlyLog or filter here)
        # For now, use SQL-level created_at or stored timestamp
        entries = []
        for row in rows:
            entry = _deserialize_entry(row)
            if filters.start_time and entry.timestamp < filters.start_time:
                continue
            if filters.end_time and entry.timestamp > filters.end_time:
                continue
            entries.append(entry)

        if filters.offset:
            entries = entries[filters.offset:]
        return entries

    async def get_count(self, entry_type: str | None = None) -> int:
        filters = {"entry_type": entry_type} if entry_type else None
        return await self._log.count(filters)


def _extract_actor_id(entry: LedgerEntry) -> str | None:
    """Extract actor_id from entry if it has one."""
    return str(getattr(entry, "actor_id", None) or "")

def _extract_engine_name(entry: LedgerEntry) -> str | None:
    """Extract engine_name from entry if it has one."""
    return getattr(entry, "engine_name", None) or ""

def _deserialize_entry(row: dict) -> LedgerEntry:
    """Typed deserialization via entry registry."""
    entry_type = row["entry_type"]
    cls = ENTRY_REGISTRY.get(entry_type, LedgerEntry)
    return cls.model_validate_json(row["payload"])
```

**Why this is better than the bus pattern:** Bus does Python post-filtering for some fields. Ledger pushes actor_id and engine_name to SQL columns and indexes. When the reporter queries "all LLM calls by the responder engine" (thousands of entries in a real run), the SQL index makes it O(log n) not O(n).

**Broader context fit:** F3 (reporter) queries the ledger heavily:
- "All pipeline steps for this run" → `entry_type = "pipeline_step"`
- "All LLM calls by responder engine" → `entry_type = "llm_call" AND engine_name = "responder"`
- "All entries for agent-alpha" → `actor_id = "agent-alpha"`
- "Total LLM cost" → query all LLMCallEntry, sum cost_usd in Python (aggregation not in SQL for v1)

### Step 3: Implement `query.py` — Query models + builder

```python
class LedgerQuery(BaseModel):
    entry_type: str | None = None
    start_time: datetime | None = None
    end_time: datetime | None = None
    actor_id: ActorId | None = None
    engine_name: str | None = None
    limit: int = 100
    offset: int = 0

class LedgerAggregation(BaseModel):
    group_by: str
    metric: str  # "count" | "sum" | "avg"

class LedgerQueryBuilder:
    def __init__(self):
        self._query = LedgerQuery()

    def filter_type(self, entry_type: str) -> LedgerQueryBuilder:
        self._query = self._query.model_copy(update={"entry_type": entry_type})
        return self

    def filter_time(self, start=None, end=None) -> LedgerQueryBuilder:
        updates = {}
        if start: updates["start_time"] = start
        if end: updates["end_time"] = end
        self._query = self._query.model_copy(update=updates)
        return self

    def filter_actor(self, actor_id) -> LedgerQueryBuilder:
        self._query = self._query.model_copy(update={"actor_id": actor_id})
        return self

    def aggregate(self, group_by, metric) -> LedgerQueryBuilder:
        # Store aggregation for future use
        return self

    def build(self) -> LedgerQuery:
        return self._query
```

### Step 4: Implement `export.py` — JSON/CSV/replay export

```python
class LedgerExporter:
    def __init__(self, ledger: Ledger):
        self._ledger = ledger

    async def export_json(self, query: LedgerQuery, output_path: str) -> int:
        entries = await self._ledger.query(query)
        data = [e.model_dump(mode="json") for e in entries]
        Path(output_path).write_text(json.dumps(data, indent=2, default=str))
        return len(data)

    async def export_csv(self, query: LedgerQuery, output_path: str) -> int:
        entries = await self._ledger.query(query)
        if not entries:
            Path(output_path).write_text("")
            return 0
        # Use first entry's fields as CSV headers
        fieldnames = list(entries[0].model_dump().keys())
        with open(output_path, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            for entry in entries:
                writer.writerow({k: str(v) for k, v in entry.model_dump().items()})
        return len(entries)

    async def export_replay(self, query: LedgerQuery, output_path: str) -> int:
        # Replay format: one JSON object per line (JSONL)
        entries = await self._ledger.query(query)
        with open(output_path, "w") as f:
            for entry in entries:
                f.write(entry.model_dump_json() + "\n")
        return len(entries)
```

### Step 5: Verify `config.py` — already has defaults

LedgerConfig has: db_path, retention_days, entry_types_enabled, flush_interval_ms. Verify all defaults are sensible.

---

## Files to Modify / Create

| File | Action | Notes |
|------|--------|-------|
| `terrarium/ledger/entries.py` | **UPDATE** | Add `entry_type` defaults to each subclass + entry registry |
| `terrarium/ledger/ledger.py` | **IMPLEMENT** | Core Ledger with append, query, get_count |
| `terrarium/ledger/query.py` | **IMPLEMENT** | LedgerQuery, LedgerAggregation, LedgerQueryBuilder |
| `terrarium/ledger/export.py` | **IMPLEMENT** | JSON, CSV, JSONL export |
| `terrarium/ledger/config.py` | **VERIFY** | Already has defaults |
| `terrarium/ledger/__init__.py` | **VERIFY** | Re-exports correct |
| `tests/ledger/test_ledger.py` | **IMPLEMENT** | ~12 tests |
| `tests/ledger/test_entries.py` | **IMPLEMENT** | ~10 tests |
| `tests/ledger/test_query.py` | **IMPLEMENT** | ~8 tests |
| `tests/ledger/test_export.py` | **IMPLEMENT** | ~8 tests |
| `tests/ledger/test_integration.py` | **CREATE** | ~4 tests: ledger + bus + persistence E2E |
| `IMPLEMENTATION_STATUS.md` | **UPDATE** | Flip ledger to done, session log |
| `plans/A4-ledger.md` | **CREATE** | Save plan to project |

---

## Tests

### test_entries.py (~10 tests)
- test_ledger_entry_base — base fields (entry_id, entry_type, timestamp, metadata)
- test_pipeline_step_entry — all fields, entry_type default = "pipeline_step"
- test_state_mutation_entry — all fields, before/after dicts
- test_llm_call_entry — all fields, cost/latency
- test_gateway_request_entry — all fields
- test_validation_entry — passed/failed with details
- test_engine_lifecycle_entry — engine_name, event_type
- test_snapshot_entry — snapshot_id, run_id, tick, size
- test_entry_serialization_roundtrip — model_dump_json → model_validate_json preserves all
- test_entry_registry_all_types — every subclass is in the registry

### test_ledger.py (~12 tests)
- test_ledger_initialize — creates ledger_log table + indexes
- test_ledger_append — appends entry, returns sequence_id
- test_ledger_append_multiple_types — append PipelineStep, LLMCall, GatewayRequest
- test_ledger_query_all — retrieves all entries in order
- test_ledger_query_by_type — filter by entry_type
- test_ledger_query_by_time_range — start_time/end_time filtering
- test_ledger_query_by_actor — filter by actor_id
- test_ledger_query_with_limit_offset — pagination
- test_ledger_get_count — total count
- test_ledger_get_count_by_type — filtered count
- test_ledger_typed_deserialization — query returns correct subclass types (not base LedgerEntry)
- test_ledger_entry_type_filtering — disabled entry types return -1

### test_query.py (~8 tests)
- test_ledger_query_defaults — all None/defaults
- test_query_builder_filter_type — chain builder
- test_query_builder_filter_time — start/end time
- test_query_builder_filter_actor — actor_id
- test_query_builder_chain — multiple filters chained
- test_query_builder_build — produces LedgerQuery
- test_ledger_aggregation_model — group_by + metric
- test_query_builder_immutable — chaining doesn't mutate original

### test_export.py (~8 tests)
- test_export_json — valid JSON file, correct entry count
- test_export_json_empty — empty query produces empty array
- test_export_csv — valid CSV with headers, correct rows
- test_export_csv_empty — empty query produces empty file
- test_export_replay — JSONL format, one entry per line
- test_export_replay_parseable — each line is valid JSON
- test_export_json_with_filter — filtered export
- test_export_preserves_entry_types — exported data includes entry_type

### test_integration.py (NEW — ~4 tests)
- test_ledger_with_connection_manager — full lifecycle: ConnectionManager → Database → Ledger
- test_ledger_append_query_cycle — append → query → verify typed deserialization
- test_ledger_and_bus_coexist — both Ledger and EventBus use same ConnectionManager, different databases
- test_foundation_smoke — A1 persistence + A2 config + A3 bus + A4 ledger all working together

---

## Completion Criteria (Zero Stubs)

| File | Methods | All Implemented? | All Tested? |
|------|---------|-----------------|-------------|
| `entries.py` | 7 entry classes + base + registry | ✅ | ✅ 10 tests |
| `ledger.py` | initialize, shutdown, append, query, get_count | ✅ 5 methods | ✅ 12 tests |
| `query.py` | LedgerQuery, LedgerAggregation, LedgerQueryBuilder (6 methods) | ✅ | ✅ 8 tests |
| `export.py` | export_json, export_csv, export_replay | ✅ 3 methods | ✅ 8 tests |
| `config.py` | LedgerConfig fields | ✅ already done | ✅ via schema tests |
| `__init__.py` | re-exports | ✅ | ✅ import test |

**0 stubs remaining in ledger/. ~42 tests across 5 test files.**

**After A4, ALL foundation modules (A1-A4) work seamlessly:**
- A1: persistence/ — Database, SQLiteDatabase, ConnectionManager, AppendOnlyLog
- A2: config/ — ConfigLoader, TerrariumConfig, ConfigRegistry
- A3: bus/ — EventBus, TopicFanout, BusPersistence (via AppendOnlyLog)
- A4: ledger/ — Ledger, LedgerEntry hierarchy, LedgerQuery, LedgerExporter (via AppendOnlyLog)

Both bus and ledger use the same AppendOnlyLog infrastructure, same DI pattern, same ConnectionManager. Different tables, different concerns.

---

## Post-Implementation Tasks

### 1. Save plan
Copy to `plans/A4-ledger.md` in the project repo.

### 2. Update IMPLEMENTATION_STATUS.md

**Current Focus:**
```
**Phase:** A — Foundation Modules ✅ ALL COMPLETE
**Item:** A4 ledger/ ✅ COMPLETE → Next: B1 validation/
**Status:** All 4 foundation modules done. Ready for Phase B.
```

**Flip these rows to ✅ done:**
- Ledger — ledger
- Ledger — entries
- Ledger — query
- Ledger — export

**Session log entry.**

---

## Verification

1. `.venv/bin/python -m pytest tests/ledger/ -v` — ALL pass
2. `.venv/bin/python -m pytest tests/ledger/ --cov=terrarium/ledger --cov-report=term-missing` — >90%
3. `grep -rn "^\s*\.\.\.$" terrarium/ledger/*.py` — 0 results (no stubs)
4. **DI verification:** `grep -n "SQLiteDatabase" terrarium/ledger/*.py` — 0 results
5. **Typed deserialization test:** query returns PipelineStepEntry, LLMCallEntry etc. (not base LedgerEntry)
6. **A1-A4 integration smoke test:**
   ```python
   from terrarium.persistence import ConnectionManager, PersistenceConfig
   from terrarium.bus import EventBus, BusConfig
   from terrarium.ledger import Ledger, LedgerConfig
   from terrarium.ledger.entries import PipelineStepEntry

   mgr = ConnectionManager(PersistenceConfig(base_dir="/tmp/test"))
   await mgr.initialize()

   bus_db = await mgr.get_connection("bus")
   ledger_db = await mgr.get_connection("ledger")

   bus = EventBus(BusConfig(persistence_enabled=True), db=bus_db)
   ledger = Ledger(LedgerConfig(), db=ledger_db)

   await bus.initialize()
   await ledger.initialize()

   # Ledger append + query
   seq = await ledger.append(PipelineStepEntry(
       step_name="permission", request_id="req_1",
       actor_id="agent-alpha", action="email_send", verdict="allow"
   ))
   entries = await ledger.query(LedgerQuery(entry_type="pipeline_step"))
   assert len(entries) == 1
   assert isinstance(entries[0], PipelineStepEntry)  # typed!

   await bus.shutdown()
   await mgr.shutdown()
   ```
7. ALL previous tests: `.venv/bin/python -m pytest tests/ -q` — 483+ passed, 0 failed
8. `plans/A4-ledger.md` exists
9. `IMPLEMENTATION_STATUS.md` updated
