# Phase F4-F5: Run Management + Governed vs Ungoverned Diff

## Context

The simulation runs but there's no lifecycle management — no way to tag runs, compare governed vs ungoverned, save artifacts, or replay. The `runs/` module has well-defined API contracts (all stubbed with `...`) and the low-level persistence (SnapshotStore, Ledger) is already implemented. We need to fill in the stubs and wire everything together.

## Key Concepts — Answers to "How Does This Work?"

### What is a Snapshot?

A **snapshot** is a full binary backup of the SQLite world state database at a point in time.

- **Storage:** `{base_dir}/snapshots/{snapshot_id}.db` (SQLite backup) + `{snapshot_id}.json` (metadata)
- **ID format:** `snap_{run_id}_{label}_{8-char-uuid}`
- **What it captures:** EVERYTHING — all entities, event logs, causal graph state
- **Who creates it:** `StateEngine.snapshot(label)` → calls `SnapshotStore.save_snapshot()` → records `SnapshotEntry` to ledger
- **Already fully implemented** in `terrarium/persistence/snapshot.py` (save, load, list, delete, metadata)
- **SnapshotManager** in `runs/snapshot.py` is a run-aware wrapper — delegates to SnapshotStore + StateEngine

### Same World, Different Mode — How?

The spec says: *"Same seed + same world definition = same initial state. This is essential for counterfactual diffs."*

**The workflow:**
```
1. Compile world ONCE → initial snapshot captured automatically
   (WorldCompilerEngine.generate_world() calls StateEngine.snapshot("initial_world"))

2. Run 1 (governed):
   - create_run(world_def, config, mode="governed", tag="gov")
   - start_run(run_id) → agent acts → pipeline enforces governance
   - end_run(run_id) → save report, scorecard, event_log as artifacts
   - Snapshot: auto-snapshot on complete (RunConfig.snapshot_on_complete=True)

3. Run 2 (ungoverned):
   - Restore from initial_world snapshot (SAME starting state)
   - create_run(world_def, config, mode="ungoverned", tag="ungov")
   - start_run(run_id) → agent acts → pipeline logs but doesn't enforce
   - end_run(run_id) → save report, scorecard, event_log as artifacts

4. Compare:
   - diff_runs(["gov", "ungov"])
   - Loads saved scorecards + event logs from ArtifactStore
   - Produces the spec comparison table
```

**Key:** Both runs start from the SAME compiled world. The world is compiled once, snapshotted, then each run restores from that snapshot. Governance mode only affects RUNTIME enforcement — the same policies are EVALUATED in both modes, but in ungoverned mode enforcement is overridden to LOG.

### How Are 2 Reports Compared?

**Data flow:**
```
ArtifactStore.load_artifact(run_1, "scorecard") → scorecard_1
ArtifactStore.load_artifact(run_1, "event_log") → events_1
ArtifactStore.load_artifact(run_2, "scorecard") → scorecard_2
ArtifactStore.load_artifact(run_2, "event_log") → events_2
                          ↓
RunComparator.compare([run_1, run_2]):
  ├─ compare_scores()     → metric-by-metric deltas (uses saved scorecards)
  ├─ compare_events()     → event type distribution diffs (uses saved event logs)
  ├─ compare_entity_states() → entity count/state diffs
  └─ _extract_governance_metrics() → spec table metrics from event logs:
       - PolicyBlockEvent count → "Actions actually blocked"
       - PolicyHoldEvent count → "Approval requests created"
       - BudgetExhaustedEvent count → "Budget exceeded"
       - PermissionDeniedEvent count → "Unauthorized data access"
       - Total world.* events → "Actions that hit policy"
       - overall_score from scorecard → "Governance Score"
```

**Two comparison levels:**
1. **Generic `compare(run_ids)`** — scorecard deltas + event diffs (works for any N runs)
2. **Specialized `compare_governed_ungoverned(gov_id, ungov_id)`** — produces the SPEC TABLE format with governance-specific metrics extracted from event logs

### Framework vs One-Off?

All stubs follow the SAME dependency injection pattern:
- Constructor: `__init__(self, config: RunConfig, persistence: ConnectionManager)`
- All methods async
- Use typed IDs (RunId, SnapshotId) from `terrarium.core.types`
- Config via Pydantic model (RunConfig) wired through TerrariumConfig
- No hardcoded paths — everything from RunConfig.data_dir

## What Exists (REUSE)

| Component | File | Status |
|-----------|------|--------|
| `RunManager` class | `terrarium/runs/manager.py` | ⚠️ Stub — `__init__(config: RunConfig, persistence: ConnectionManager)` |
| `RunConfig` model | `terrarium/runs/config.py` | ✅ `data_dir`, `snapshot_on_complete`, `snapshot_interval_ticks`, `retention_days` |
| `SnapshotManager` class | `terrarium/runs/snapshot.py` | ⚠️ Stub — `__init__(config: RunConfig, persistence: ConnectionManager)` |
| `ArtifactStore` class | `terrarium/runs/artifacts.py` | ⚠️ Stub — `__init__(config: RunConfig)` |
| `RunComparator` class | `terrarium/runs/comparison.py` | ⚠️ Stub — no `__init__` (6 methods) |
| `RunReplayer` class | `terrarium/runs/replay.py` | ⚠️ Stub — `__init__(config: RunConfig, persistence: ConnectionManager)` |
| `SnapshotStore` | `terrarium/persistence/snapshot.py` | ✅ FULL (save, load, list, delete via SQLite backup) |
| `CounterfactualDiffer` | `terrarium/engines/reporter/diff.py` | ✅ score_diff, event_diff, entity_state_diff |
| `ScorecardComputer` | `terrarium/engines/reporter/scorecard.py` | ✅ 8 per-actor + 2 collective + overall_score |
| `SnapshotEntry` | `terrarium/ledger/entries.py` | ✅ Defined |
| `RunId`, `SnapshotId`, `WorldMode` | `terrarium/core/types.py` | ✅ Defined |
| `StateEngine.snapshot()` | `terrarium/engines/state/engine.py` | ✅ Creates snapshot + ledger entry |
| `TerrariumConfig.runs` | `terrarium/config/schema.py:82` | ✅ Wired as `runs: RunConfig` |
| Test stubs | `tests/runs/test_*.py` | ⚠️ 16 stub tests with `...` bodies |

## Implementation Details

### 1. RunManager (`terrarium/runs/manager.py`)

**PRESERVE** existing constructor signature: `__init__(self, config: RunConfig, persistence: ConnectionManager)`.
Add `tag` parameter to `create_run`. Add internal state + disk persistence + tag resolution.

```python
class RunManager:
    """Manages run lifecycle: created → running → completed/failed."""

    def __init__(self, config: RunConfig, persistence: ConnectionManager) -> None:
        self._config = config
        self._persistence = persistence
        self._data_dir = Path(config.data_dir)
        self._data_dir.mkdir(parents=True, exist_ok=True)
        self._runs: dict[str, dict[str, Any]] = {}  # run_id → metadata
        self._active_run: str | None = None
        self._tags: dict[str, str] = {}  # tag → run_id
        # Load existing runs from disk on init
        self._load_existing_runs()

    async def create_run(
        self, world_def: dict, config_snapshot: dict,
        mode: str = "governed", reality_preset: str = "messy",
        fidelity_mode: str = "auto", tag: str | None = None,
    ) -> RunId:
        run_id = RunId(f"run_{uuid4().hex[:12]}")
        self._runs[str(run_id)] = {
            "run_id": str(run_id), "status": "created", "mode": mode,
            "reality_preset": reality_preset, "fidelity_mode": fidelity_mode,
            "tag": tag,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "started_at": None, "completed_at": None,
            "world_def": world_def, "config_snapshot": config_snapshot,
        }
        if tag:
            self._tags[tag] = str(run_id)
        self._save_run_metadata(run_id)
        return run_id

    async def start_run(self, run_id: RunId) -> None:
        run = self._get_or_raise(run_id)
        run["status"] = "running"
        run["started_at"] = datetime.now(timezone.utc).isoformat()
        self._active_run = str(run_id)
        self._save_run_metadata(run_id)

    async def complete_run(self, run_id: RunId, status: str = "completed") -> None:
        run = self._get_or_raise(run_id)
        run["status"] = status
        run["completed_at"] = datetime.now(timezone.utc).isoformat()
        if self._active_run == str(run_id):
            self._active_run = None
        self._save_run_metadata(run_id)

    async def fail_run(self, run_id: RunId, error: str) -> None:
        run = self._get_or_raise(run_id)
        run["status"] = "failed"
        run["error"] = error
        run["completed_at"] = datetime.now(timezone.utc).isoformat()
        if self._active_run == str(run_id):
            self._active_run = None
        self._save_run_metadata(run_id)

    async def get_run(self, run_id: RunId) -> dict | None:
        rid = self._resolve_id(run_id)
        return self._runs.get(rid)

    async def list_runs(self, limit: int = 50) -> list[dict]:
        runs = sorted(self._runs.values(), key=lambda r: r["created_at"], reverse=True)
        return runs[:limit]

    async def get_active_run(self) -> RunId | None:
        if self._active_run:
            return RunId(self._active_run)
        return None

    # ── Private helpers ──

    def _resolve_id(self, run_id_or_tag: str | RunId) -> str:
        """Resolve tag → run_id, 'last' → most recent, or pass through."""
        s = str(run_id_or_tag)
        if s in self._tags:
            return self._tags[s]
        if s == "last":
            runs = sorted(self._runs.values(), key=lambda r: r["created_at"], reverse=True)
            return runs[0]["run_id"] if runs else ""
        return s

    def _get_or_raise(self, run_id: RunId) -> dict:
        rid = self._resolve_id(run_id)
        run = self._runs.get(rid)
        if run is None:
            raise KeyError(f"Run not found: {run_id}")
        return run

    def _save_run_metadata(self, run_id: RunId) -> None:
        run_dir = self._data_dir / str(run_id)
        run_dir.mkdir(parents=True, exist_ok=True)
        meta_path = run_dir / "metadata.json"
        meta_path.write_text(json.dumps(self._runs[str(run_id)], indent=2, default=str))

    def _load_existing_runs(self) -> None:
        """Reload runs from disk (for restart resilience)."""
        if not self._data_dir.exists():
            return
        for meta_path in self._data_dir.glob("*/metadata.json"):
            try:
                data = json.loads(meta_path.read_text())
                rid = data["run_id"]
                self._runs[rid] = data
                if data.get("tag"):
                    self._tags[data["tag"]] = rid
                if data.get("status") == "running":
                    self._active_run = rid
            except (json.JSONDecodeError, KeyError):
                continue
```

### 2. ArtifactStore (`terrarium/runs/artifacts.py`)

**PRESERVE** existing constructor: `__init__(self, config: RunConfig)`.
Save methods return `str` (file path) per stub contract.

```python
class ArtifactStore:
    def __init__(self, config: RunConfig) -> None:
        self._config = config
        self._data_dir = Path(config.data_dir)

    async def save_report(self, run_id: RunId, report: dict) -> str:
        return self._write_artifact(run_id, "report", report)

    async def save_scorecard(self, run_id: RunId, scorecard: dict) -> str:
        return self._write_artifact(run_id, "scorecard", scorecard)

    async def save_event_log(self, run_id: RunId, events: list) -> str:
        serialized = [self._serialize_event(e) for e in events]
        return self._write_artifact(run_id, "event_log", serialized)

    async def save_config(self, run_id: RunId, config: dict) -> str:
        return self._write_artifact(run_id, "config", config)

    async def list_artifacts(self, run_id: RunId) -> list[dict]:
        run_dir = self._data_dir / str(run_id)
        if not run_dir.exists():
            return []
        results = []
        for f in sorted(run_dir.glob("*.json")):
            if f.stem == "metadata":
                continue
            stat = f.stat()
            results.append({
                "type": f.stem,
                "path": str(f),
                "size_bytes": stat.st_size,
            })
        return results

    async def load_artifact(self, run_id: RunId, artifact_type: str) -> Any:
        path = self._data_dir / str(run_id) / f"{artifact_type}.json"
        if not path.exists():
            return None
        return json.loads(path.read_text())

    # ── Private ──

    def _write_artifact(self, run_id: RunId, name: str, data: Any) -> str:
        run_dir = self._data_dir / str(run_id)
        run_dir.mkdir(parents=True, exist_ok=True)
        path = run_dir / f"{name}.json"
        path.write_text(json.dumps(data, indent=2, default=str))
        return str(path)

    def _serialize_event(self, event: Any) -> dict:
        if hasattr(event, "model_dump"):
            return event.model_dump(mode="json")
        if isinstance(event, dict):
            return event
        return {"event_type": str(getattr(event, "event_type", "")), "data": str(event)}
```

### 3. SnapshotManager (`terrarium/runs/snapshot.py`)

**PRESERVE** existing constructor: `__init__(self, config: RunConfig, persistence: ConnectionManager)`.
Internally gets SnapshotStore from persistence and delegates to StateEngine.

```python
class SnapshotManager:
    def __init__(self, config: RunConfig, persistence: ConnectionManager) -> None:
        self._config = config
        self._persistence = persistence
        self._snapshot_store: SnapshotStore | None = None
        self._tick_counter: dict[str, int] = {}  # run_id → tick of last snapshot

    def _get_store(self) -> SnapshotStore:
        """Lazy-init SnapshotStore from persistence config."""
        if self._snapshot_store is None:
            from terrarium.persistence.snapshot import SnapshotStore
            from terrarium.persistence.config import PersistenceConfig
            snapshot_dir = self._config.data_dir  # reuse runs data_dir for snapshots
            self._snapshot_store = SnapshotStore(PersistenceConfig(base_dir=snapshot_dir))
        return self._snapshot_store

    async def take_snapshot(self, run_id: RunId, label: str, tick: int) -> SnapshotId:
        """Create snapshot via StateEngine (which handles DB backup + ledger recording)."""
        # Get state engine's database and use SnapshotStore directly
        store = self._get_store()
        db = await self._persistence.get_connection("state")
        snapshot_id = await store.save_snapshot(run_id, f"{label}_t{tick}", db)
        self._tick_counter[str(run_id)] = tick
        return snapshot_id

    async def restore_snapshot(self, snapshot_id: SnapshotId) -> None:
        """Restore state from a previously taken snapshot."""
        store = self._get_store()
        await store.load_snapshot(snapshot_id)

    async def list_snapshots(self, run_id: RunId) -> list[dict]:
        store = self._get_store()
        return await store.list_snapshots(run_id=run_id)

    async def auto_snapshot(self, run_id: RunId, tick: int) -> SnapshotId | None:
        """Take snapshot if interval has elapsed since last one."""
        interval = self._config.snapshot_interval_ticks
        if interval <= 0:
            return None
        last = self._tick_counter.get(str(run_id), 0)
        if tick - last >= interval:
            return await self.take_snapshot(run_id, "auto", tick)
        return None
```

### 4. RunComparator (`terrarium/runs/comparison.py`)

**CRITICAL:** Must implement ALL 6 stub methods. Uses ArtifactStore to load saved data.
`compare_governed_ungoverned()` must produce the SPEC TABLE with governance-specific metrics.

```python
class RunComparator:
    """Compares metrics and state across multiple evaluation runs.

    Reads from ArtifactStore — does NOT recompute. Comparison is post-hoc.
    """

    def __init__(self, artifact_store: ArtifactStore) -> None:
        self._artifacts = artifact_store

    async def compare(self, run_ids: list[RunId]) -> dict:
        """Comprehensive comparison: scores + events + entity states."""
        scores = await self.compare_scores(run_ids)
        events = await self.compare_events(run_ids)
        entities = await self.compare_entity_states(run_ids)
        labels = scores.get("labels", [str(r) for r in run_ids])
        return {
            "labels": labels,
            "run_count": len(run_ids),
            "scores": scores,
            "events": events,
            "entity_states": entities,
        }

    async def compare_scores(self, run_ids: list[RunId]) -> dict:
        """Compare scorecard metrics across runs. Returns per-metric deltas."""
        scorecards = []
        labels = []
        for rid in run_ids:
            sc = await self._artifacts.load_artifact(rid, "scorecard") or {}
            meta = await self._artifacts.load_artifact(rid, "metadata")
            scorecards.append(sc)
            labels.append(meta.get("tag", str(rid)) if meta else str(rid))

        # Collect all collective metric keys
        all_keys: set[str] = set()
        for sc in scorecards:
            all_keys.update(sc.get("collective", sc).keys())

        metrics: dict[str, dict] = {}
        for key in sorted(all_keys):
            row: dict[str, Any] = {}
            values: list[float] = []
            for i, sc in enumerate(scorecards):
                collective = sc.get("collective", sc)
                val = collective.get(key)
                row[labels[i]] = val
                if isinstance(val, (int, float)):
                    values.append(val)
            if len(values) >= 2:
                row["delta"] = round(values[-1] - values[0], 2)
            metrics[key] = row

        return {"labels": labels, "metrics": metrics}

    async def compare_events(self, run_ids: list[RunId]) -> dict:
        """Compare event distributions across runs."""
        labels = []
        event_logs = []
        for rid in run_ids:
            events = await self._artifacts.load_artifact(rid, "event_log") or []
            meta = await self._artifacts.load_artifact(rid, "metadata")
            event_logs.append(events)
            labels.append(meta.get("tag", str(rid)) if meta else str(rid))

        counts = [len(log) for log in event_logs]
        by_type: dict[str, dict] = {}
        for i, log in enumerate(event_logs):
            type_counts: dict[str, int] = {}
            for event in log:
                et = event.get("event_type", "unknown") if isinstance(event, dict) else str(getattr(event, "event_type", "unknown"))
                type_counts[et] = type_counts.get(et, 0) + 1
            for et, count in type_counts.items():
                if et not in by_type:
                    by_type[et] = {}
                by_type[et][labels[i]] = count

        return {"labels": labels, "total_counts": dict(zip(labels, counts)), "by_type": by_type}

    async def compare_entity_states(self, run_ids: list[RunId]) -> dict:
        """Compare final entity states across runs (from saved reports)."""
        labels = []
        reports = []
        for rid in run_ids:
            report = await self._artifacts.load_artifact(rid, "report") or {}
            meta = await self._artifacts.load_artifact(rid, "metadata")
            reports.append(report)
            labels.append(meta.get("tag", str(rid)) if meta else str(rid))

        entity_counts: dict[str, Any] = {}
        for i, report in enumerate(reports):
            entities = report.get("entities", {})
            for etype, elist in entities.items():
                if etype not in entity_counts:
                    entity_counts[etype] = {}
                entity_counts[etype][labels[i]] = len(elist) if isinstance(elist, list) else 0

        return {"labels": labels, "entity_counts": entity_counts}

    def format_comparison(self, comparison: dict) -> str:
        """Human-readable comparison table matching spec format."""
        labels = comparison.get("labels", [])
        scores = comparison.get("scores", {}).get("metrics", {})
        gov_metrics = comparison.get("governance_metrics", {})

        lines = ["GOVERNED vs. UNGOVERNED COMPARISON"]
        lines.append("=" * 60)
        header = f"{'Metric':<35}" + "".join(f"{l:>12}" for l in labels)
        lines.append(header)
        lines.append("-" * 60)

        # Governance-specific metrics first (from spec table)
        if gov_metrics:
            for metric, row in gov_metrics.items():
                vals = "".join(f"{row.get(l, 'N/A'):>12}" for l in labels)
                lines.append(f"{metric:<35}{vals}")
            lines.append("-" * 60)

        # Scorecard metrics
        for metric, row in scores.items():
            vals = "".join(f"{str(row.get(l, 'N/A')):>12}" for l in labels)
            lines.append(f"{metric:<35}{vals}")

        lines.append("=" * 60)
        return "\n".join(lines)

    async def compare_governed_ungoverned(
        self, governed_run_id: RunId, ungoverned_run_id: RunId
    ) -> dict[str, Any]:
        """Specialized comparison producing the SPEC TABLE format.

        Extracts governance-specific metrics from event logs:
        - Actions that hit policy (total policy-evaluated events)
        - Actions actually blocked (PolicyBlockEvent count)
        - Approval requests created (PolicyHoldEvent count)
        - Budget exceeded (BudgetExhaustedEvent count)
        - Unauthorized data access (PermissionDeniedEvent count)
        - Governance Score (overall_score from scorecard)
        """
        # Base comparison (scores, events, entities)
        result = await self.compare([governed_run_id, ungoverned_run_id])
        result["comparison_type"] = "governed_vs_ungoverned"

        # Extract governance-specific metrics from event logs
        gov_metrics: dict[str, dict[str, Any]] = {}
        labels = result["labels"]

        for i, rid in enumerate([governed_run_id, ungoverned_run_id]):
            events = await self._artifacts.load_artifact(rid, "event_log") or []
            label = labels[i]

            # Count governance events by type
            policy_block = 0
            policy_hold = 0
            policy_trigger = 0
            budget_exhausted = 0
            permission_denied = 0
            total_actions = 0

            for event in events:
                et = event.get("event_type", "") if isinstance(event, dict) else ""
                if et.startswith("world."):
                    total_actions += 1
                if "policy_block" in et or "PolicyBlock" in str(event.get("__class__", "")):
                    policy_block += 1
                    policy_trigger += 1
                elif "policy_hold" in et or "PolicyHold" in str(event.get("__class__", "")):
                    policy_hold += 1
                    policy_trigger += 1
                elif "policy" in et.lower():
                    policy_trigger += 1
                if "budget_exhausted" in et or "BudgetExhausted" in str(event.get("__class__", "")):
                    budget_exhausted += 1
                if "permission_denied" in et or "PermissionDenied" in str(event.get("__class__", "")):
                    permission_denied += 1

            gov_metrics.setdefault("Actions that hit policy", {})[label] = policy_trigger
            gov_metrics.setdefault("Actions actually blocked", {})[label] = policy_block
            gov_metrics.setdefault("Approval requests created", {})[label] = policy_hold
            gov_metrics.setdefault("Budget exceeded", {})[label] = budget_exhausted
            gov_metrics.setdefault("Unauthorized data access", {})[label] = permission_denied

        # Add governance scores from scorecards
        for i, rid in enumerate([governed_run_id, ungoverned_run_id]):
            sc = await self._artifacts.load_artifact(rid, "scorecard") or {}
            label = labels[i]
            overall = sc.get("collective", {}).get("overall_score", 0)
            gov_metrics.setdefault("Governance Score", {})[label] = overall

        result["governance_metrics"] = gov_metrics
        return result
```

### 5. RunReplayer (`terrarium/runs/replay.py`)

**PRESERVE** existing constructor: `__init__(self, config: RunConfig, persistence: ConnectionManager)`.
Uses ArtifactStore (loaded lazily from config) for event log access.

```python
class RunReplayer:
    def __init__(self, config: RunConfig, persistence: ConnectionManager) -> None:
        self._config = config
        self._persistence = persistence
        self._active_run_id: RunId | None = None
        self._paused: bool = False
        self._speed: float = 1.0
        self._current_tick: int = 0
        self._events: list[dict] = []
        self._artifact_store: ArtifactStore | None = None

    def _get_artifact_store(self) -> ArtifactStore:
        if self._artifact_store is None:
            self._artifact_store = ArtifactStore(self._config)
        return self._artifact_store

    async def start_replay(self, run_id: RunId, speed: float = 1.0) -> None:
        store = self._get_artifact_store()
        events = await store.load_artifact(run_id, "event_log")
        self._events = events or []
        self._active_run_id = run_id
        self._current_tick = 0
        self._paused = False
        self._speed = speed

    async def pause_replay(self) -> None:
        self._paused = True

    async def resume_replay(self) -> None:
        self._paused = False

    async def seek_to_tick(self, tick: int) -> None:
        self._current_tick = tick

    async def stop_replay(self) -> None:
        self._active_run_id = None
        self._events = []
        self._current_tick = 0
        self._paused = False

    async def get_replay_state(self) -> dict:
        events_up_to_tick = [e for e in self._events if (e.get("tick", 0) if isinstance(e, dict) else 0) <= self._current_tick]
        return {
            "run_id": str(self._active_run_id) if self._active_run_id else None,
            "tick": self._current_tick,
            "paused": self._paused,
            "speed": self._speed,
            "status": "paused" if self._paused else ("replaying" if self._active_run_id else "idle"),
            "total_events": len(self._events),
            "events_at_tick": len(events_up_to_tick),
        }
```

### 6. Wire into TerrariumApp (`terrarium/app.py`)

Add to `__init__()`:
```python
self._run_manager: Any = None
self._artifact_store: Any = None
self._run_snapshot_mgr: Any = None
```

Add to `start()` after step 9 (Health), before step 10 (Gateway):
```python
# 9.5. Run management
from terrarium.runs.manager import RunManager
from terrarium.runs.artifacts import ArtifactStore
from terrarium.runs.snapshot import SnapshotManager as RunSnapshotManager

self._run_manager = RunManager(config=self._config.runs, persistence=self._conn_mgr)
self._artifact_store = ArtifactStore(config=self._config.runs)
self._run_snapshot_mgr = RunSnapshotManager(
    config=self._config.runs, persistence=self._conn_mgr,
)
```

Add new methods:
```python
async def create_run(
    self, plan: Any, mode: str = "governed", tag: str | None = None
) -> RunId:
    """Create a run record, compile the world, start the run."""
    run_id = await self._run_manager.create_run(
        world_def=plan.model_dump(mode="json") if hasattr(plan, "model_dump") else {},
        config_snapshot={"seed": plan.seed, "behavior": plan.behavior, "mode": getattr(plan, "mode", mode)},
        mode=mode,
        reality_preset=getattr(plan, "reality_preset", ""),
        fidelity_mode=getattr(plan, "fidelity", "auto"),
        tag=tag,
    )
    # Compile + configure
    result = await self.compile_and_run(plan)
    # Start run
    await self._run_manager.start_run(run_id)
    # Save config artifact
    await self._artifact_store.save_config(run_id, result)
    return run_id

async def end_run(self, run_id: RunId) -> dict:
    """Complete a run: generate report, save artifacts, optional snapshot."""
    reporter = self._registry.get("reporter")
    report = await reporter.generate_full_report()
    scorecard = await reporter.generate_scorecard()

    await self._artifact_store.save_report(run_id, report)
    await self._artifact_store.save_scorecard(run_id, scorecard)

    # Save event log from state engine timeline
    state = self._registry.get("state")
    events = await state.get_timeline()
    await self._artifact_store.save_event_log(run_id, events)

    # Auto-snapshot on complete (if configured)
    if self._config.runs.snapshot_on_complete:
        try:
            await state.snapshot(f"run_complete_{run_id}")
        except Exception as e:
            logger.warning("Auto-snapshot failed for run %s: %s", run_id, e)

    await self._run_manager.complete_run(run_id)
    return {"run_id": str(run_id), "report": report, "scorecard": scorecard}

async def diff_runs(self, run_ids: list[str]) -> dict:
    """Compare multiple runs using saved artifacts."""
    from terrarium.runs.comparison import RunComparator
    comparator = RunComparator(self._artifact_store)
    typed_ids = [RunId(rid) for rid in run_ids]
    return await comparator.compare(typed_ids)

async def diff_governed_ungoverned(self, gov_tag: str, ungov_tag: str) -> dict:
    """Specialized governed vs ungoverned comparison."""
    from terrarium.runs.comparison import RunComparator
    comparator = RunComparator(self._artifact_store)
    # Resolve tags to run IDs
    gov_run = await self._run_manager.get_run(RunId(gov_tag))
    ungov_run = await self._run_manager.get_run(RunId(ungov_tag))
    if not gov_run or not ungov_run:
        raise ValueError(f"Could not resolve run tags: {gov_tag}, {ungov_tag}")
    return await comparator.compare_governed_ungoverned(
        RunId(gov_run["run_id"]), RunId(ungov_run["run_id"])
    )

@property
def run_manager(self) -> Any:
    return self._run_manager

@property
def artifact_store(self) -> Any:
    return self._artifact_store
```

### 7. HTTP API Endpoints (`terrarium/engines/adapter/protocols/http_rest.py`)

Add run management endpoints alongside existing routes:

```python
# ── Run Management ──
@app.post("/api/v1/runs")
async def create_run_endpoint(body: dict):
    run_mgr = gateway._app.run_manager
    run_id = await run_mgr.create_run(**body)
    return {"run_id": str(run_id)}

@app.get("/api/v1/runs")
async def list_runs_endpoint(limit: int = 20):
    return await gateway._app.run_manager.list_runs(limit=limit)

@app.get("/api/v1/runs/{run_id}")
async def get_run_endpoint(run_id: str):
    result = await gateway._app.run_manager.get_run(RunId(run_id))
    if result is None:
        raise HTTPException(status_code=404, detail=f"Run not found: {run_id}")
    return result

@app.post("/api/v1/runs/{run_id}/complete")
async def complete_run_endpoint(run_id: str):
    return await gateway._app.end_run(RunId(run_id))

@app.get("/api/v1/runs/{run_id}/artifacts")
async def list_artifacts_endpoint(run_id: str):
    return await gateway._app.artifact_store.list_artifacts(RunId(run_id))

@app.get("/api/v1/runs/{run_id}/artifacts/{artifact_type}")
async def get_artifact_endpoint(run_id: str, artifact_type: str):
    result = await gateway._app.artifact_store.load_artifact(RunId(run_id), artifact_type)
    if result is None:
        raise HTTPException(status_code=404, detail=f"Artifact not found: {artifact_type}")
    return result

@app.get("/api/v1/diff")
async def diff_runs_endpoint(runs: str = Query(..., description="Comma-separated run IDs or tags")):
    run_ids = [r.strip() for r in runs.split(",")]
    return await gateway._app.diff_runs(run_ids)

@app.get("/api/v1/diff/governed")
async def diff_governed_endpoint(gov: str = Query(...), ungov: str = Query(...)):
    return await gateway._app.diff_governed_ungoverned(gov, ungov)
```

## Files to Modify/Create

| File | Action | Key Changes |
|------|--------|-------------|
| `terrarium/runs/manager.py` | **IMPLEMENT** | Fill stubs, add tag resolution, disk persistence, _load_existing_runs() |
| `terrarium/runs/artifacts.py` | **IMPLEMENT** | Fill stubs, save returns `str` path, list returns metadata dicts |
| `terrarium/runs/snapshot.py` | **IMPLEMENT** | Fill stubs, delegate to SnapshotStore, auto_snapshot interval logic |
| `terrarium/runs/comparison.py` | **IMPLEMENT** | ALL 6 methods, governance_metrics extraction, format_comparison |
| `terrarium/runs/replay.py` | **IMPLEMENT** | Fill stubs, lazy ArtifactStore, replay state management |
| `terrarium/app.py` | **UPDATE** | create_run(), end_run(), diff_runs(), diff_governed_ungoverned(), wiring in start() |
| `terrarium/engines/adapter/protocols/http_rest.py` | **UPDATE** | Run + artifact + diff API endpoints |
| `tests/runs/test_manager.py` | **REWRITE** | 8 real tests (see below) |
| `tests/runs/test_artifacts.py` | **REWRITE** | 6 real tests |
| `tests/runs/test_snapshot.py` | **REWRITE** | 4 real tests |
| `tests/runs/test_comparison.py` | **REWRITE** | 6 real tests |
| `tests/runs/test_replay.py` | **REWRITE** | 4 real tests |
| `tests/integration/test_governed_vs_ungoverned.py` | **CREATE** | E2E governed vs ungoverned comparison |

## Test Scenarios

### RunManager Tests (`tests/runs/test_manager.py` — 8 tests)
- `test_create_run_returns_run_id` — returns RunId starting with "run_"
- `test_create_run_with_tag` — tag resolves to run_id via get_run
- `test_start_run_transitions_status` — status changes to "running"
- `test_complete_run_transitions_status` — status changes to "completed"
- `test_fail_run_records_error` — status "failed" + error field set
- `test_list_runs_newest_first` — two runs, newest first
- `test_get_run_resolves_tag` — get_run("gov") resolves to tagged run_id
- `test_get_active_run` — returns RunId while running, None after complete
- `test_metadata_persisted_to_disk` — metadata.json exists in tmp_path after create

### ArtifactStore Tests (`tests/runs/test_artifacts.py` — 6 tests)
- `test_save_load_report_roundtrip` — save_report → load_artifact("report") matches
- `test_save_load_scorecard_roundtrip` — same for scorecard
- `test_save_load_event_log_roundtrip` — same for event_log (with model_dump serialization)
- `test_list_artifacts_returns_saved_types` — list shows "report", "scorecard" after saving both
- `test_load_nonexistent_returns_none` — load unknown type returns None
- `test_save_returns_file_path` — save_report returns str path that exists on disk

### SnapshotManager Tests (`tests/runs/test_snapshot.py` — 4 tests)
- `test_take_snapshot_returns_snapshot_id` — delegates to SnapshotStore
- `test_list_snapshots_by_run` — filtered by run_id
- `test_auto_snapshot_respects_interval` — tick 0 → snapshot, tick 1 → None (interval=5), tick 5 → snapshot
- `test_auto_snapshot_disabled` — interval=0 → always None

### RunComparator Tests (`tests/runs/test_comparison.py` — 6 tests)
- `test_compare_scores_with_deltas` — two scorecards → metric deltas computed
- `test_compare_events_by_type` — event log distribution breakdown
- `test_compare_governed_ungoverned_governance_metrics` — extracts blocked/hold/denied counts
- `test_format_comparison_produces_table` — output contains spec table headers
- `test_compare_missing_scorecard_handled` — empty scorecard → no crash
- `test_compare_entity_states` — entity count comparison from reports

### RunReplayer Tests (`tests/runs/test_replay.py` — 4 tests)
- `test_start_replay_loads_events` — events loaded from artifact store
- `test_pause_resume` — state toggles correctly
- `test_seek_to_tick` — current_tick updates
- `test_get_replay_state_structure` — returns correct keys (run_id, tick, paused, speed, status)

### Integration: Governed vs Ungoverned (`tests/integration/test_governed_vs_ungoverned.py` — 3 tests)
Using `app_with_mock_llm` fixture from existing `tests/integration/conftest.py`:
- `test_governed_run_saves_artifacts` — create_run + end_run → artifacts on disk
- `test_ungoverned_run_saves_artifacts` — same in ungoverned mode
- `test_diff_governed_ungoverned_produces_comparison` — diff shows governance_metrics with expected structure

## Verification

1. `pytest tests/runs/ -q` — all 28 tests pass
2. `pytest tests/integration/test_governed_vs_ungoverned.py -q` — all 3 pass
3. `pytest tests/ -q` — full suite passes (was 1314 passed, should be ~1342+)
4. `grep -rn "\.\.\." terrarium/runs/` — ZERO ellipsis stubs remaining
5. Artifacts are real JSON files in `data/runs/{run_id}/` (metadata.json, report.json, scorecard.json, event_log.json)
6. `RunComparator.format_comparison()` output matches spec table format

## Post-Implementation
1. Save plan to `internal_docs/plans/F4-F5-runs.md`
2. Update IMPLEMENTATION_STATUS.md — flip F4, F5 rows to done, add session entry
3. Principal engineer review
