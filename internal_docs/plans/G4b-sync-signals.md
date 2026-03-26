## G4b: External Source Sync + Local Signals

**Spec reference**: `terrarium-full-spec.md` §14 lines 1106-1121, `terrarium-architecture.md` lines 259-279

**Depends on**: G4a (AnnotationStore, ProfileRegistry, ProfileLoader, ServiceCapture, FeedbackEngine — all done)

---

### Context

G4a built the core feedback pipeline: annotations, capture, promotion, pack compile/verify. G4b completes the self-improving loop with two features:

1. **External Source Sync** — detect when real-world API docs (Context Hub, OpenAPI specs) have changed since a profile was created, propose updates
2. **Local Signals** — aggregate intelligence across the USER'S OWN runs: most used services, common failures, capability gaps, popular templates

**Important scope decision**: The spec mentions "ecosystem signals across thousands of simulations." But for a local open-source install, there is no global ecosystem — just one user's run history. So we implement **local signals only**: aggregate YOUR runs to show YOUR priorities. No telemetry, no central server, no community aggregation. Useful from day 1 for any user.

From the spec: "As external knowledge sources update, Terrarium profiles can auto-detect drift... This keeps profiles current without requiring manual tracking of every API changelog."

**What this solves for a user:**
- "My Stripe profile is 3 months old — is it still accurate?" → Sync checks Context Hub/OpenAPI
- "Which of my services need the most work?" → Local signals show your priorities
- "My agents keep asking for tools that don't exist" → Gap analysis across your runs
- "Which world definitions work best?" → Template insights from your history

---

### G4b Scope — Everything Deferred from G4a

| Component | Spec Source | Description |
|-----------|------------|-------------|
| **ExternalSyncChecker** | §14 lines 1106-1112 | Drift detection: Context Hub docs, OpenAPI version, MCP manifest |
| **DriftDetector** | architecture lines 270-279 | Compare profile operations vs latest external spec |
| **ProfileUpdateProposer** | architecture line 275 | Generate proposed profile updates from drift |
| **LocalSignalAggregator** | §14 lines 1114-1121 | Aggregate stats across user's own runs |
| **Most Used Services** | §14 line 1118 | Track which services user uses most |
| **Bootstrapping Failures** | §14 line 1119 | Track user's bootstrapped services with issues |
| **Template Insights** | §14 line 1120 | Track which world definitions work best |
| **Capability Gap Summary** | §14 line 1121 | Track most-requested missing tools in user's runs |
| **CLI: `terrarium sync`** | — | Check + propose profile updates |
| **CLI: `terrarium signals`** | — | Display local signals dashboard |

---

### Component 1: DriftDetector (`engines/feedback/drift.py` — NEW)

Compares a service profile against the latest external documentation to detect what has changed.

**Drift types:**
- `operations_added` — external spec has new endpoints not in profile
- `operations_removed` — profile has endpoints no longer in external spec
- `operations_changed` — parameters or response schema differ
- `version_changed` — API version in external spec is newer
- `docs_updated` — Context Hub content has changed (hash comparison)

```python
# ── Models ────────────────────────────────────────────────────
class DriftReport(BaseModel, frozen=True):
    """Result of comparing a profile against one external source."""
    service_name: str
    checked_at: str                              # ISO timestamp
    source: str                                  # "context_hub" | "openapi"
    has_drift: bool
    profile_version: str
    external_version: str | None
    operations_added: list[str] = Field(default_factory=list)
    operations_removed: list[str] = Field(default_factory=list)
    operations_changed: list[str] = Field(default_factory=list)
    content_hash_changed: bool = False
    summary: str = ""


# ── Protocol: each drift source implements this ───────────────
class DriftSource(Protocol):
    """Protocol for a drift detection source.

    To add a new source (e.g., MCP manifest):
    1. Create a class implementing this protocol
    2. Register it in DRIFT_SOURCE_REGISTRY
    """
    source_name: str

    async def check(
        self, profile: ServiceProfileData
    ) -> DriftReport | None:
        """Check profile against this source. None if no drift."""
        ...


# ── Built-in sources ─────────────────────────────────────────
class ContextHubDriftSource:
    """Detects drift by comparing profile against Context Hub docs."""
    source_name = "context_hub"

    def __init__(self, provider: ContextHubProvider) -> None: ...

    async def check(self, profile: ServiceProfileData) -> DriftReport | None:
        """1. Fetch latest docs via chub
        2. Hash content → compare against stored hash
        3. Parse markdown for operation hints (HTTP method + path patterns)
        4. Diff against profile operations
        """

class OpenAPIDriftSource:
    """Detects drift by comparing profile against OpenAPI spec."""
    source_name = "openapi"

    def __init__(self, provider: OpenAPIProvider) -> None: ...

    async def check(self, profile: ServiceProfileData) -> DriftReport | None:
        """1. Fetch spec → get structured operations + version
        2. Compare version
        3. Diff operations by name: added, removed, changed
        """


# ── Registry ─────────────────────────────────────────────────
DRIFT_SOURCE_REGISTRY: dict[str, type[DriftSource]] = {
    "context_hub": ContextHubDriftSource,
    "openapi": OpenAPIDriftSource,
}


# ── Detector: runs all sources ────────────────────────────────
class DriftDetector:
    """Runs all registered drift sources against a profile.

    To add MCP manifest drift: create class, add to registry.
    """

    def __init__(
        self,
        context_hub: ContextHubProvider | None,
        openapi_provider: OpenAPIProvider | None,
    ) -> None:
        self._sources: list[DriftSource] = []
        if context_hub:
            self._sources.append(ContextHubDriftSource(context_hub))
        if openapi_provider:
            self._sources.append(OpenAPIDriftSource(openapi_provider))

    async def check(
        self, profile: ServiceProfileData
    ) -> list[DriftReport]:
        """Check profile against ALL registered sources.
        Returns list of DriftReports (one per source that found drift).
        """

    @staticmethod
    def _diff_operations(
        profile_ops: list[str], external_ops: list[str]
    ) -> tuple[list[str], list[str]]:
        """Return (added, removed) operation names."""
```

**Why this design:**
- Adding MCP manifest drift = one new class + one line in DRIFT_SOURCE_REGISTRY
- Same plugin pattern as signals
- Each source independently testable

---

### Component 2: ProfileUpdateProposer (`engines/feedback/proposer.py` — NEW)

Given a DriftReport, proposes concrete profile updates.

```python
class ProfileUpdateProposal(BaseModel, frozen=True):
    """A proposed update to a service profile based on drift detection."""
    service_name: str
    drift_report: DriftReport
    proposed_changes: list[ProposedChange]
    auto_applicable: bool              # can be applied without LLM
    requires_review: bool              # needs human review

class ProposedChange(BaseModel, frozen=True):
    """A single proposed change to a profile."""
    change_type: str                   # "add_operation" | "remove_operation" | "update_schema" | "update_version"
    target: str                        # operation name or field path
    description: str                   # human-readable
    new_value: dict[str, Any] | None   # the proposed new data


class ProfileUpdateProposer:
    """Generates profile update proposals from drift reports."""

    def __init__(self, llm_router: Any | None = None) -> None: ...

    async def propose(
        self, profile: ServiceProfileData, drift: DriftReport
    ) -> ProfileUpdateProposal:
        """Generate a proposal from drift report.

        For structural changes (added/removed ops): deterministic
        For schema changes: may use LLM if available
        """

    async def apply(
        self, profile: ServiceProfileData, proposal: ProfileUpdateProposal
    ) -> ServiceProfileData:
        """Apply a proposal to create an updated profile.

        Returns a new ServiceProfileData (frozen copy with updates).
        Does NOT save to disk — caller decides whether to save.
        """
```

---

### Component 3: Signal Framework (`engines/feedback/signals.py` — NEW)

**Design principle**: Each signal is a **plugin** implementing a protocol. Adding a new signal = define one class + register it. The framework handles run iteration, artifact loading, result collection.

```python
# ── Protocol: every signal implements this ────────────────────
class SignalCollector(Protocol):
    """Protocol for a single signal type.

    To add a new signal:
    1. Create a class implementing this protocol
    2. Register it in SIGNAL_REGISTRY
    3. Enable it in FeedbackConfig.enabled_signals (or enabled by default)
    """
    signal_name: str

    async def collect(self, context: SignalContext) -> SignalResult:
        """Compute this signal from the shared context."""
        ...


# ── Shared context: loaded ONCE, shared across all signals ────
class SignalContext(BaseModel, frozen=True):
    """Pre-loaded data shared across all signal collectors.

    The framework loads this once, then passes it to every
    registered collector — no duplicate artifact loading.
    """
    runs: list[dict[str, Any]]               # from RunManager.list_runs()
    event_logs: dict[str, list[dict]]        # run_id → events (lazy-loaded)
    annotation_counts: dict[str, int]        # service_name → count
    profile_fidelities: dict[str, str]       # service_name → fidelity_source


# ── Result: each signal returns one of these ──────────────────
class SignalResult(BaseModel, frozen=True):
    """Output from a single signal collector."""
    signal_name: str
    entries: list[dict[str, Any]]            # signal-specific data rows
    summary: str                             # human-readable one-liner


# ── Aggregate output ──────────────────────────────────────────
class LocalSignals(BaseModel, frozen=True):
    """All signal results combined."""
    computed_at: str
    total_runs: int
    signals: dict[str, SignalResult]         # signal_name → result


# ── Built-in signal collectors ────────────────────────────────

class ServiceUsageSignal:
    """Tracks which services the user uses most across runs."""
    signal_name = "service_usage"
    async def collect(self, ctx: SignalContext) -> SignalResult: ...

class BootstrapFailureSignal:
    """Tracks bootstrapped services with high error/gap rates."""
    signal_name = "bootstrap_failures"
    async def collect(self, ctx: SignalContext) -> SignalResult: ...

class CapabilityGapSignal:
    """Tracks most-requested missing tools across runs."""
    signal_name = "capability_gaps"
    async def collect(self, ctx: SignalContext) -> SignalResult: ...

class TemplateInsightSignal:
    """Tracks which world definitions the user reuses most."""
    signal_name = "template_insights"
    async def collect(self, ctx: SignalContext) -> SignalResult: ...


# ── Registry: add new signals here ────────────────────────────
SIGNAL_REGISTRY: dict[str, type[SignalCollector]] = {
    "service_usage": ServiceUsageSignal,
    "bootstrap_failures": BootstrapFailureSignal,
    "capability_gaps": CapabilityGapSignal,
    "template_insights": TemplateInsightSignal,
}


# ── Framework: orchestrates everything ────────────────────────
class SignalAggregator:
    """Runs all registered signal collectors against user's run history.

    Usage:
        aggregator = SignalAggregator(run_manager, artifact_store, ...)
        signals = await aggregator.compute()
        # signals.signals["service_usage"].entries → [...]

    To add a new signal:
        1. Define class implementing SignalCollector
        2. Add to SIGNAL_REGISTRY
        3. Done — framework handles the rest
    """

    def __init__(
        self,
        run_manager: Any,
        artifact_store: Any,
        annotation_store: AnnotationStore,
        profile_registry: Any,
        config: FeedbackConfig,
    ) -> None: ...

    async def compute(
        self,
        signal_names: list[str] | None = None,
    ) -> LocalSignals:
        """Compute signals. If signal_names is None, run all registered.

        1. Build SignalContext (load runs, event logs, annotation counts)
        2. For each registered signal: call collect(context)
        3. Return LocalSignals with all results
        """

    async def _build_context(self) -> SignalContext:
        """Load all shared data once."""
```

**Why this design:**
- Adding a 5th signal = one new class + one line in SIGNAL_REGISTRY
- No changes to the framework, engine, CLI, or config
- Shared context means artifact loading happens once, not per-signal
- Each signal is independently testable
- Config can enable/disable individual signals via `enabled_signals: list[str]`

---

### Component 4: ExternalSyncChecker (`engines/feedback/sync.py` — REWRITE stub)

The orchestrator that ties DriftDetector + ProfileUpdateProposer together. Called by the FeedbackEngine and CLI.

```python
class ExternalSyncChecker:
    """Checks all profiled services for external API drift."""

    def __init__(
        self,
        drift_detector: DriftDetector,
        proposer: ProfileUpdateProposer,
        profile_registry: Any,
        annotation_store: AnnotationStore,
    ) -> None: ...

    async def check_drift(
        self, service_name: str
    ) -> DriftReport | None:
        """Check a single service for drift."""

    async def check_all(self) -> list[DriftReport]:
        """Check ALL profiled services for drift. Returns list of reports."""

    async def propose_update(
        self, service_name: str
    ) -> ProfileUpdateProposal | None:
        """Check drift + propose update for a service."""

    async def apply_update(
        self, service_name: str, proposal: ProfileUpdateProposal
    ) -> ServiceProfileData:
        """Apply a proposed update and save the new profile."""
```

---

### Component 5: FeedbackEngine Extensions (`engines/feedback/engine.py` — MODIFY)

Add sync + signals methods to the public API:

```python
# New public methods:
async def check_sync(self, service_name: str) -> DriftReport | None
async def check_sync_all(self) -> list[DriftReport]
async def propose_sync_update(self, service_name: str) -> ProfileUpdateProposal | None
async def apply_sync_update(self, service_name: str, proposal: ProfileUpdateProposal) -> ServiceProfileData
async def get_local_signals(self, signal_names: list[str] | None = None) -> LocalSignals
```

Lazy-initialize `_sync_checker` and `_signal_aggregator` in `_ensure_initialized()` when `external_sync_enabled` is True.

---

### Component 6: FeedbackConfig Extensions (`engines/feedback/config.py` — MODIFY)

```python
class FeedbackConfig(BaseModel, frozen=True):
    # ... existing G4a fields ...
    # G4b fields:
    external_sync_enabled: bool = False        # already exists
    sync_check_on_startup: bool = False        # check all profiles on app start
    sync_max_concurrent: int = 5               # concurrent drift checks
    signals_enabled: bool = True               # enable signal computation
    signals_max_runs: int = 100                # max runs to scan
    signals_include_event_logs: bool = True     # load event logs (heavier but more data)
    enabled_signals: list[str] = Field(        # which signals to compute
        default_factory=lambda: [
            "service_usage",
            "bootstrap_failures",
            "capability_gaps",
            "template_insights",
        ]
    )
```

---

### Component 7: Ledger Entry Types (`ledger/entries.py` — MODIFY)

```python
class FeedbackSyncEntry(LedgerEntry):
    """Records an external sync drift check."""
    entry_type: str = "feedback.sync"
    service_name: str = ""
    source: str = ""               # "context_hub" | "openapi"
    has_drift: bool = False
    operations_added: int = 0
    operations_removed: int = 0

class FeedbackSyncUpdateEntry(LedgerEntry):
    """Records an applied sync update."""
    entry_type: str = "feedback.sync_update"
    service_name: str = ""
    changes_applied: int = 0
    new_version: str = ""
```

Register both in `ENTRY_REGISTRY`.

---

### Component 8: CLI Commands (`cli.py` — MODIFY)

**`terrarium sync <service> [--all] [--apply]`**
```
terrarium sync stripe          # Check drift for stripe
terrarium sync --all           # Check all profiled services
terrarium sync stripe --apply  # Check + apply proposed updates
```

**`terrarium signals [--format json|table]`**
```
terrarium signals              # Show local signals dashboard
terrarium signals --format json # Machine-readable output
```

---

### Component 9: TOML Config (`terrarium.toml` — MODIFY)

```toml
[feedback]
external_sync_enabled = false
sync_check_on_startup = false
sync_max_concurrent = 5
signals_include_event_logs = true
signals_max_runs = 100
# ... existing G4a fields unchanged
```

---

### Component 10: Test Harness + Tests

**`tests/engines/feedback/conftest.py` — EXTEND** with new fixtures:
- `mock_context_hub` — returns canned docs with known operations
- `mock_openapi_provider` — returns canned spec with known version + operations
- `make_drift_report` — factory for DriftReport
- `make_local_signals` — factory for LocalSignals
- `sample_run_history` — list of mock run metadata dicts

**Test files:**

| File | Tests | What |
|------|-------|------|
| `test_drift.py` | 6 | detect added/removed ops, version change, no drift, context hub drift, openapi drift |
| `test_proposer.py` | 4 | propose add op, propose remove op, apply proposal, no-op for no drift |
| `test_signals.py` | 7 | framework runs all collectors, individual signal results, custom signal registration, empty runs, config controls which signals run, signal context built once, enabled_signals filter |
| `test_sync.py` | 4 | check single, check all, propose update, apply update |
| `test_engine_g4b.py` | 3 | engine sync methods, engine signals method, sync disabled returns empty |
| **Total** | **24** | |

**Live E2E test** (`tests/live/test_g4b_sync.py`):
```
1. Start app with codex-acp
2. Load jira profile (curated, known operations)
3. Fetch latest Context Hub docs for jira
4. Check drift → report if ops have changed
5. Compute local signals from existing run history
6. Verify signal aggregation produces non-empty results
```

---

### Implementation Order

```
Phase 1 — Models + Detector (no deps):
  1. drift.py — DriftReport model + DriftDetector
  2. proposer.py — ProfileUpdateProposal + ProfileUpdateProposer
  3. signals.py — LocalSignals models + Aggregator

Phase 2 — Wiring:
  4. sync.py — ExternalSyncChecker (REWRITE stub)
  5. engine.py — Add sync + signals methods
  6. config.py — Add new config fields
  7. terrarium.toml — Add config values

Phase 3 — Ledger + CLI:
  8. ledger/entries.py — FeedbackSyncEntry, FeedbackSyncUpdateEntry
  9. cli.py — sync + signals commands

Phase 4 — Tests:
  10. conftest.py — Extend with new fixtures
  11. test_drift.py
  12. test_proposer.py
  13. test_signals.py
  14. test_sync.py
  15. test_engine_g4b.py

Phase 5 — Live E2E:
  16. tests/live/test_g4b_sync.py

Phase 6 — Documentation:
  17. Save plan to internal_docs/plans/G4b-sync-signals.md
```

---

### Verification

1. `uv run pytest tests/engines/feedback/ -v` — all 55 tests pass (31 G4a + 24 G4b)
2. `uv run pytest tests/ --ignore=tests/live --ignore=tests/integration -q` — 2139+ passed
3. CLI: `uv run terrarium sync jira` — shows drift report
4. CLI: `uv run terrarium signals` — shows local signals dashboard
5. Live: `GOOGLE_API_KEY=dummy uv run pytest tests/live/test_g4b_sync.py -v -s`
6. `uv run ruff check terrarium/engines/feedback/`

---

### All Files

| File | Action | What |
|------|--------|------|
| `terrarium/engines/feedback/drift.py` | **NEW** | DriftDetector + DriftReport |
| `terrarium/engines/feedback/proposer.py` | **NEW** | ProfileUpdateProposer + Proposal models |
| `terrarium/engines/feedback/signals.py` | **NEW** | LocalSignalAggregator + Signal models |
| `terrarium/engines/feedback/sync.py` | **REWRITE** | ExternalSyncChecker orchestrator |
| `terrarium/engines/feedback/engine.py` | **MODIFY** | Add sync + signals public API |
| `terrarium/engines/feedback/config.py` | **MODIFY** | Add sync config fields |
| `terrarium/ledger/entries.py` | **MODIFY** | Add 2 new entry types |
| `terrarium/terrarium.toml` | **MODIFY** | Add sync config |
| `terrarium/cli.py` | **MODIFY** | Add sync + signals commands |
| `tests/engines/feedback/conftest.py` | **MODIFY** | Add G4b fixtures |
| `tests/engines/feedback/test_drift.py` | **NEW** | 6 tests |
| `tests/engines/feedback/test_proposer.py` | **NEW** | 4 tests |
| `tests/engines/feedback/test_signals.py` | **NEW** | 5 tests |
| `tests/engines/feedback/test_sync.py` | **NEW** | 4 tests |
| `tests/engines/feedback/test_engine_g4b.py` | **NEW** | 3 tests |
| `tests/live/test_g4b_sync.py` | **NEW** | Live E2E test |
| `internal_docs/plans/G4b-sync-signals.md` | **NEW** | Saved plan |
