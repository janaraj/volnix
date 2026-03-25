## G4: Feedback Engine — Self-Improving Loop

**Spec reference**: `internal_docs/terrarium-full-spec.md` Section 14, `internal_docs/terrarium-architecture.md` lines 232-279

Split into:
- **G4a**: Annotations + Service Capture + Tier Promotion + Pack Compile/Verify + 5 CLI commands
- **G4b**: External Source Sync (Context Hub/OpenAPI drift detection) + Ecosystem Signals (aggregate intelligence)

This plan covers **G4a**.

---

### Context

The Feedback Engine is the self-improving loop (Spec §14): "It collects signals from simulation runs and feeds them back into the system." Currently 100% stub — all methods are `...`. Five CLI commands are deferred. The engine is registered in composition.py and subscribed to `["capability_gap", "world", "simulation"]` events but does nothing.

**Promotion ladder** (Spec §14 lines 1090-1104):
```
Bootstrapped → capture behavioral rules from runs → community review → Tier 2 (Curated Profile)
Bootstrapped → capture + compile-pack → deterministic logic → Tier 1 (Verified Pack)
Tier 2 (Curated Profile) → critical path → compile-pack → Tier 1 (Verified Pack)
```

**Foundation already in place** (from G2):
- `ProfileSchema` with `fidelity_source` field (bootstrapped | curated_profile) at `terrarium/packs/profile_schema.py:80`
- `ProfileLoader.save()` persists profiles at `terrarium/packs/profile_loader.py:76-92`
- `ProfileRegistry` shared between compiler/responder/adapter
- `GapAnalyzer` produces structured gap records at `terrarium/engines/reporter/capability_gaps.py`
- `ArtifactStore` saves run reports/event_logs at `terrarium/runs/artifacts.py`

---

### G4a vs G4b — Clear Boundary

| G4a (this plan) | G4b (future) |
|-----------------|-------------|
| AnnotationStore (SQLite, per-service) | ExternalSyncChecker (Context Hub drift, OpenAPI version check) |
| ServiceCapture (extract surface from run) | Ecosystem Signals (most requested services, common failures) |
| TierPromoter (evaluate + promote) | Auto-sync jobs (propose profile updates) |
| PackCompiler (generate Tier 1 scaffold) | Community contribution workflow |
| PackVerifier (validate pack correctness) | |
| FeedbackEngine (wire + bus events + ledger) | |
| 5 CLI commands (annotate, capture, promote, compile-pack, verify-pack) | |
| Test harness (conftest + unit + integration) | |

G4b depends on G4a — it uses the AnnotationStore and promotion pipeline as foundation.

---

### Deliverables

#### NEW files
| File | Purpose |
|------|---------|
| `terrarium/engines/feedback/models.py` | Pydantic models: CapturedSurface, PromotionEvaluation, PromotionResult, etc. |
| `terrarium/engines/feedback/capture.py` | ServiceCapture — extract behavioral fingerprint from run event log |
| `terrarium/engines/feedback/pack_compiler.py` | PackCompiler — generate Tier 1 pack scaffold from Tier 2 profile |
| `terrarium/engines/feedback/pack_verifier.py` | PackVerifier — validate pack structure and correctness |
| `tests/engines/feedback/conftest.py` | Test harness: reusable fixtures for all feedback tests |
| `tests/engines/feedback/test_annotations.py` | AnnotationStore unit tests |
| `tests/engines/feedback/test_capture.py` | ServiceCapture unit tests |
| `tests/engines/feedback/test_promotion.py` | TierPromoter unit tests |
| `tests/engines/feedback/test_pack_compiler.py` | PackCompiler unit tests |
| `tests/engines/feedback/test_pack_verifier.py` | PackVerifier unit tests |
| `tests/engines/feedback/test_engine.py` | FeedbackEngine integration tests |
| `internal_docs/plans/G4a-feedback-promotion.md` | Saved implementation plan |

#### REWRITE files (stubs → real)
| File | What changes |
|------|-------------|
| `terrarium/engines/feedback/engine.py` | Full FeedbackEngine with _on_initialize, _handle_event, public API |
| `terrarium/engines/feedback/annotations.py` | AnnotationStore with AppendOnlyLog pattern |
| `terrarium/engines/feedback/promotion.py` | TierPromoter with evaluate + promote logic |

#### MODIFY files
| File | What changes |
|------|-------------|
| `terrarium/engines/feedback/config.py` | Add promotion thresholds, auto_annotate_gaps |
| `terrarium/ledger/entries.py` | Add AnnotationEntry + PromotionEntry to ENTRY_REGISTRY |
| `terrarium/runs/artifacts.py` | Add `captured_surface` to _ALLOWED_ARTIFACT_TYPES |
| `terrarium/app.py` | Wire feedback deps in _inject_cross_engine_deps |
| `terrarium/terrarium.toml` | Add feedback config fields |
| `terrarium/cli.py` | Replace 5 deferred stubs with real implementations |
| `IMPLEMENTATION_STATUS.md` | Update to reflect G4a completion + current test count |
| `tests/engines/test_feedback.py` | DELETE old stub file (tests move to subdirectory) |

---

### Component 1: Models (`models.py` — NEW)

All frozen Pydantic models used across the feedback pipeline.

```python
class ObservedOperation(BaseModel, frozen=True):
    """An API operation observed during a run."""
    name: str
    call_count: int
    parameter_keys: list[str]       # which params were used
    response_keys: list[str]        # which fields appeared in responses
    error_count: int = 0

class ObservedMutation(BaseModel, frozen=True):
    """An entity state change observed during a run."""
    entity_type: str
    operation: str                   # create/update/delete
    count: int

class ObservedError(BaseModel, frozen=True):
    """An error pattern observed during a run."""
    error_type: str
    count: int
    context: str                     # when/why

class CapturedSurface(BaseModel, frozen=True):
    """Behavioral fingerprint of a service extracted from a completed run."""
    service_name: str
    run_id: str
    captured_at: str                              # ISO timestamp
    operations_observed: list[ObservedOperation]
    entity_mutations: list[ObservedMutation]
    error_patterns: list[ObservedError]
    annotations: list[dict[str, Any]]
    behavioral_rules: list[str]                   # extracted from annotations + patterns
    source_profile: str | None                    # original profile name if any
    fidelity_source: str                          # bootstrapped | curated_profile

class PromotionEvaluation(BaseModel, frozen=True):
    """Result of evaluating a service for tier promotion."""
    service_name: str
    eligible: bool
    current_fidelity: str
    proposed_fidelity: str
    criteria_met: list[str]
    criteria_missing: list[str]
    recommendation: str
    annotation_count: int
    run_count: int

class PromotionResult(BaseModel, frozen=True):
    """Outcome of executing a promotion."""
    service_name: str
    previous_fidelity: str
    new_fidelity: str
    profile_path: str
    version: str

class PackCompileResult(BaseModel, frozen=True):
    """Outcome of generating a pack scaffold."""
    service_name: str
    output_dir: str
    files_generated: list[str]
    handler_stubs: int

class VerificationCheck(BaseModel, frozen=True):
    """A single verification check result."""
    name: str
    passed: bool
    message: str

class VerificationResult(BaseModel, frozen=True):
    """Full pack verification outcome."""
    service_name: str
    passed: bool
    checks: list[VerificationCheck]
    errors: list[str]
    warnings: list[str]
```

---

### Component 2: AnnotationStore (`annotations.py` — REWRITE)

Uses `AppendOnlyLog` from `terrarium/persistence/append_log.py` (same pattern as bus persistence at `terrarium/bus/persistence.py:27-44` and ledger at `terrarium/ledger/ledger.py:30-36`).

**Table schema** (`annotations` table):
- `sequence_id` (auto), `created_at` (auto)
- `service_id TEXT NOT NULL`
- `text TEXT NOT NULL`
- `author TEXT NOT NULL` — "user", "agent:{id}", "system"
- `tag TEXT` — optional category
- `run_id TEXT` — optional: which run

**Methods:**
- `__init__(self, db: Database)`
- `async initialize()` — AppendOnlyLog.initialize() + create_index("service_id")
- `async add(service_id, text, author, tag=None, run_id=None) -> int`
- `async get_by_service(service_id) -> list[dict]`
- `async get_by_run(run_id) -> list[dict]`
- `async search(query) -> list[dict]` — SQL LIKE on text column
- `async count_by_service(service_id) -> int`

---

### Component 3: ServiceCapture (`capture.py` — NEW)

Extracts a service's behavioral fingerprint from a completed run.

**Input**: `run_id` + `service_name` → loads event_log from ArtifactStore
**Output**: `CapturedSurface`

**Logic in `capture()`:**
1. Load event_log artifact via ArtifactStore
2. Filter events where `service_id == service_name`
3. Count operations (group by action name, count calls, collect param/response keys)
4. Count entity mutations (group by entity_type + operation)
5. Count errors (from pipeline short-circuits or error events)
6. Load annotations for this run from AnnotationStore
7. Build `CapturedSurface`

**`capture_to_profile_draft(captured, llm_router) -> ServiceProfileData`:**
- Uses LLM to formalize observations into a curated profile
- Takes captured operations → generates proper response_schemas
- Takes captured mutations → generates state machines
- Takes annotations → generates behavioral_notes
- Sets `fidelity_source = "curated_profile"`
- Uses existing `profile_infer` routing key for LLM calls

---

### Component 4: TierPromoter (`promotion.py` — REWRITE)

**Constructor**: receives AnnotationStore, ProfileRegistry, ProfileLoader, config (thresholds from FeedbackConfig)

**`evaluate_candidate(service_name, captured) -> PromotionEvaluation`:**

Promotion criteria (configurable via FeedbackConfig):
1. `promotion_min_runs` (default 3) — service used in N+ runs
2. `promotion_min_annotations` (default 1) — at least one human review
3. No unresolved capability gaps in captured surface
4. Profile has >= 3 operations

Returns PromotionEvaluation with `eligible`, `criteria_met/missing`, `recommendation`.

**`promote(service_name, new_profile) -> PromotionResult`:**
1. Update `fidelity_source` to `"curated_profile"` on the profile
2. Increment version (e.g., "0.1.0" → "1.0.0")
3. Save via ProfileLoader
4. Register in ProfileRegistry
5. Return PromotionResult

**`get_promotion_candidates() -> list[dict]`:**
- List all profiles where `fidelity_source == "bootstrapped"`
- For each, count annotations, return readiness info

---

### Component 5: PackCompiler (`pack_compiler.py` — NEW)

Generates Tier 1 pack scaffold from a Tier 2 profile. Output is file templates, NOT a fully working pack — developer fills in deterministic handlers.

**`compile(profile, output_dir=None) -> PackCompileResult`:**

Generates to `terrarium/packs/verified/{service}/`:
```
{service}/
  __init__.py         — empty module
  pack.py             — ServicePack subclass with tool defs + entity schemas
  schemas.py          — Entity schemas + tool params (from profile.entities/operations)
  handlers.py         — One async handler per operation (body = raise NotImplementedError)
  state_machines.py   — State machine definitions (from profile.state_machines)
```

Templates use existing verified pack structure as reference (e.g., `terrarium/packs/verified/email/`).

---

### Component 6: PackVerifier (`pack_verifier.py` — NEW)

Validates a Tier 1 pack directory.

**Checks:**
1. **Structure**: pack.py, schemas.py, handlers.py, state_machines.py exist
2. **Importable**: pack module can be imported, has `ServicePack` subclass
3. **Tools**: `get_tools()` returns non-empty list
4. **Entities**: `get_entity_schemas()` returns valid schemas
5. **Handlers**: every tool name has a handler in handlers.py
6. **State machines**: transition states reference valid enum values
7. **No stubs**: no `NotImplementedError` or `...` in handler bodies (warning, not error)

Returns `VerificationResult` with pass/fail + check details.

---

### Component 7: FeedbackEngine (`engine.py` — REWRITE)

**`_on_initialize()`:**
```python
# 1. Get DB connection
conn_mgr = self._config.get("_conn_mgr")
if conn_mgr:
    db = await conn_mgr.get_connection("annotations")
    self._annotation_store = AnnotationStore(db)
    await self._annotation_store.initialize()

# 2. Get injected dependencies
artifact_store = self._config.get("_artifact_store")
profile_registry = self._config.get("_profile_registry")
profile_loader = self._config.get("_profile_loader")

# 3. Create business logic components
self._capture = ServiceCapture(artifact_store, self._annotation_store)
self._promoter = TierPromoter(
    annotation_store=self._annotation_store,
    profile_registry=profile_registry,
    profile_loader=profile_loader,
    config=FeedbackConfig(**{k: v for k, v in self._config.items() if not k.startswith("_")}),
)
```

**`_handle_event()`:**
- `capability_gap` → if `auto_annotate_gaps` enabled, auto-add annotation: "Capability gap: agent {actor_id} requested tool {tool} which is not available"
- `simulation.complete` → log completion (for run count tracking)

**Public API** (called by CLI commands and other engines):
```python
async def add_annotation(service_id, text, author, tag=None, run_id=None) -> int
async def get_annotations(service_id) -> list[dict]
async def capture_service(run_id, service_name) -> CapturedSurface
async def evaluate_promotion(service_name, captured) -> PromotionEvaluation
async def promote_service(service_name, new_profile) -> PromotionResult
async def get_promotion_candidates() -> list[dict]
```

All operations record in ledger via `self._ledger.append(entry)`.

---

### Component 8: Config + TOML + Ledger + Artifacts

**FeedbackConfig** (`config.py`):
```python
class FeedbackConfig(BaseModel, frozen=True):
    annotations_db_path: str = "data/annotations.db"
    external_sync_enabled: bool = False
    auto_annotate_gaps: bool = True
    promotion_min_runs: int = 3
    promotion_min_annotations: int = 1
```

**terrarium.toml**:
```toml
[feedback]
annotations_db_path = "data/annotations.db"
external_sync_enabled = false
auto_annotate_gaps = true
promotion_min_runs = 3
promotion_min_annotations = 1
```

**Ledger entries** (`ledger/entries.py`):
- `AnnotationEntry(entry_type="feedback.annotation", service_id, text, author)`
- `PromotionEntry(entry_type="feedback.promotion", service_name, previous_fidelity, new_fidelity, version)`
- `CaptureEntry(entry_type="feedback.capture", service_name, run_id, operations_count)`

**Artifact types** (`runs/artifacts.py`): add `"captured_surface"` to `_ALLOWED_ARTIFACT_TYPES`

---

### Component 9: App Wiring (`app.py`)

In `_inject_cross_engine_deps()`:
```python
feedback = self._registry.get("feedback")
feedback._config["_conn_mgr"] = self._conn_mgr
feedback._ledger = self._ledger
feedback._config["_artifact_store"] = self._artifact_store
feedback._config["_profile_registry"] = getattr(responder, "_profile_registry", None)
feedback._config["_profile_loader"] = getattr(responder, "_profile_loader", None)
```

---

### Component 10: Five CLI Commands (`cli.py`)

Replace deferred stubs with async implementations. Each loads app, gets feedback engine, calls the appropriate method.

1. **`terrarium annotate <service> -m "text" [--tag tag] [--run run_id]`** → `feedback.add_annotation()`
2. **`terrarium capture <service> [--run run_id]`** → `feedback.capture_service()` → print summary table
3. **`terrarium promote <service> [--submit-pr]`** → evaluate → if eligible, generate draft → promote → print result
4. **`terrarium compile-pack <service> <from_source>`** → `PackCompiler.compile()` → print files
5. **`terrarium verify-pack <service>`** → `PackVerifier.verify()` → print checks table → exit code 0/1

---

### Component 11: Test Harness

**`tests/engines/feedback/conftest.py`** — Reusable fixtures:

```python
# Follows pattern from tests/engines/reporter/conftest.py

@pytest.fixture
async def annotation_db(tmp_path):
    """Temporary SQLite database for annotation tests."""
    db = SQLiteDatabase(str(tmp_path / "annotations.db"))
    await db.connect()
    yield db
    await db.close()

@pytest.fixture
async def annotation_store(annotation_db):
    """Initialized AnnotationStore with temp DB."""
    store = AnnotationStore(annotation_db)
    await store.initialize()
    return store

@pytest.fixture
def sample_captured_surface():
    """Factory for CapturedSurface with sensible defaults."""
    def _make(service_name="twilio", **overrides): ...
    return _make

@pytest.fixture
def sample_profile():
    """Factory for ServiceProfileData with bootstrapped fidelity."""
    def _make(service_name="twilio", fidelity_source="bootstrapped", **overrides): ...
    return _make

@pytest.fixture
def mock_artifact_store():
    """Mock ArtifactStore returning canned event_log."""
    store = AsyncMock()
    store.load_artifact = AsyncMock(return_value=[...])  # sample events
    return store

@pytest.fixture
def mock_profile_registry():
    """Mock ProfileRegistry with register/get/list methods."""
    ...

@pytest.fixture
def mock_profile_loader(tmp_path):
    """Real ProfileLoader writing to tmp_path."""
    return ProfileLoader(tmp_path / "profiles")

@pytest.fixture
async def feedback_engine(annotation_db, mock_event_bus, mock_ledger):
    """Fully wired FeedbackEngine for integration tests."""
    ...
```

**Test files** (one per component, clear separation):

| File | Tests | What |
|------|-------|------|
| `test_annotations.py` | 5 | add, get_by_service, get_by_run, search, count |
| `test_capture.py` | 4 | capture from events, includes annotations, empty run, capture_to_profile_draft |
| `test_promotion.py` | 5 | evaluate eligible/not, promote updates fidelity, get candidates, version increment |
| `test_pack_compiler.py` | 3 | generates files, handlers match ops, schemas from entities |
| `test_pack_verifier.py` | 3 | valid pack passes, missing files fail, stub handlers warn |
| `test_engine.py` | 4 | initializes components, auto-annotate gap, add annotation records ledger, full promotion flow |
| **Total** | **24** | |

---

### Component 12: Documentation Updates

**`internal_docs/plans/G4a-feedback-promotion.md`** — Save this plan to the docs folder.

**`IMPLEMENTATION_STATUS.md`** — Update:
- Change "Current Focus" from D4b to reflect current state
- Update test count (2088+)
- Mark G4a as complete
- Update the G4 gap section
- Add G1 (6 packs, 87 tools), G2 (Tier 2 profiles, Context Hub), Agency Engine, H1 CLI to done sections

---

### Implementation Order

```
Phase 1 — Models + Storage (no cross-deps):
  1. models.py
  2. annotations.py (AnnotationStore)
  3. config.py (FeedbackConfig update)
  4. terrarium.toml update

Phase 2 — Business Logic (depends on Phase 1):
  5. capture.py (ServiceCapture)
  6. promotion.py (TierPromoter)
  7. pack_compiler.py (PackCompiler)
  8. pack_verifier.py (PackVerifier)

Phase 3 — Wiring (depends on Phase 2):
  9. engine.py (FeedbackEngine)
  10. app.py (inject deps)
  11. ledger/entries.py (new entry types)
  12. runs/artifacts.py (new artifact type)

Phase 4 — CLI (depends on Phase 3):
  13. cli.py (5 commands)

Phase 5 — Test Harness + Tests:
  14. tests/engines/feedback/conftest.py (harness)
  15. tests/engines/feedback/test_annotations.py
  16. tests/engines/feedback/test_capture.py
  17. tests/engines/feedback/test_promotion.py
  18. tests/engines/feedback/test_pack_compiler.py
  19. tests/engines/feedback/test_pack_verifier.py
  20. tests/engines/feedback/test_engine.py
  21. Delete old tests/engines/test_feedback.py

Phase 6 — Documentation:
  22. Save plan to internal_docs/plans/G4a-feedback-promotion.md
  23. Update IMPLEMENTATION_STATUS.md
```

---

### Verification

1. `uv run pytest tests/engines/feedback/ -v` — all 24 tests pass
2. `uv run pytest tests/ --ignore=tests/live --ignore=tests/integration -q` — 2100+ passed, no regressions
3. CLI smoke tests:
   - `uv run terrarium annotate stripe -m "Refunds on charges >180 days should fail"`
   - `uv run terrarium verify-pack email` (validates existing Tier 1 pack)
   - `uv run terrarium compile-pack test-svc terrarium/packs/profiles/jira.profile.yaml` (generates scaffold)
4. `uv run ruff check terrarium/engines/feedback/ tests/engines/feedback/`
