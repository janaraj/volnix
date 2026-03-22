# Phase C3: WIRE — Full Pipeline E2E

## Context

**Phase:** C3 (final Phase C item — proves the architecture end-to-end)
**Depends on:** Everything built so far (A1-A4, B1-B4, C1-C2)
**Goal:** One `email_send` action flows through all 7 pipeline steps. State committed. Event logged. Bus delivers. Ledger records. Side effects processed. Testable both manually and via automated tests.

**Why C3 is the most important phase:** It proves the entire architecture works — not just individual modules in isolation, but the full flow: config → registry → wiring → pipeline → pack dispatch → state commit → event publish → ledger audit. If C3 works, every future phase is incremental (add governance rules, add more packs, add more protocols).

**Key implementation principles for this phase:**
1. **TerrariumApp is the reusable framework** — NOT one-off wiring code. Every test, every CLI command, every future integration uses TerrariumApp.start() → app.handle_action(). This is the standard boot path.
2. **Pass-through engines are explicitly marked** — Code comments, docstrings, and IMPLEMENTATION_STATUS.md all say "PASS-THROUGH (Phase F)". Agents implementing Phase F know exactly what to replace.
3. **Drift-prevention test harness** — Architectural tests verify: (a) all 7 steps execute, (b) ledger records everything, (c) bus delivers events, (d) state persists. These tests MUST NOT be removed when governance is added — they verify the wire stays intact.
4. **Real-data E2E** — Tests simulate an agent sending a real email_send action through the full system, then verify the response, the stored entity, the event log, the ledger entries, and the bus delivery. This is the "act as an agent" test.
5. **Replay verification** — Test that events in the bus log can be replayed to reconstruct the action timeline.

---

## The Full Wire

```
handle_action("agent-1", "email", "email_send", {from_addr, to_addr, subject, body})
    ↓
ActionContext created
    ↓
PipelineDAG.execute(ctx) — 7 sequential steps:
    ↓
① PermissionEngine.execute(ctx) → ALLOW (pass-through, Phase F2)
    ↓
② PolicyEngine.execute(ctx) → ALLOW (pass-through, Phase F1)
    ↓
③ BudgetEngine.execute(ctx) → ALLOW (pass-through, Phase F2)
    ↓
④ AdapterEngine.execute(ctx) → ALLOW (pass-through, Phase E1)
    ↓
⑤ WorldResponderEngine.execute(ctx)  ← THE KEY IMPLEMENTATION
    → Tier1Dispatcher.dispatch(ctx, world_state)
      → PackRuntime.execute("email_send", input_data, state)
        → EmailPack.handle_action("email_send", input, state)
        → ResponseProposal(response_body, proposed_state_deltas)
    → ctx.response_proposal = proposal
    → ALLOW
    ↓
⑥ ValidationStep.execute(ctx)  ← NEW WRAPPER
    → Validate ctx.response_proposal against pack schemas + state machines
    → ALLOW
    ↓
⑦ StateEngine.execute(ctx)  ← ALREADY DONE (C1)
    → Apply StateDelta(create email entity) in transaction
    → Persist WorldEvent to event log
    → Record causal edges
    → Record StateMutationEntry to ledger
    → Publish WorldEvent to bus
    → ALLOW
    ↓
PipelineDAG records 7 PipelineStepEntry to ledger
PipelineDAG publishes step events to bus
SideEffectProcessor processes any side effects
    ↓
Return response_body to caller
```

---

## Implementation Order (6 steps)

### Step 1: Pass-Through Engine Steps (4 engines)

**Why pass-through, not stubs:** These are the correct Phase C behavior — all governance passes. The pipeline DAG doesn't care what each step does internally. Phase F replaces ALLOW with real logic. Pass-throughs should:
- Log at DEBUG that they're allowing
- Return proper StepResult with step_name and verdict
- Implement `_handle_event` as a debug logger (not `...`)

**Files:**
- `terrarium/engines/permission/engine.py`
- `terrarium/engines/policy/engine.py`
- `terrarium/engines/budget/engine.py`
- `terrarium/engines/adapter/engine.py`

**CRITICAL: Every pass-through method MUST have this exact docstring pattern:**
```python
async def execute(self, ctx: ActionContext) -> StepResult:
    """PASS-THROUGH (Phase F2): Returns ALLOW without checks.

    This is the correct Phase C behavior. When Phase F2 implements
    real governance, replace this method body with actual logic.
    The method signature and return type MUST NOT change.
    """
    logger.debug("%s: allowing action '%s' for actor '%s' (pass-through)",
                 self.step_name, ctx.action, ctx.actor_id)
    return StepResult(step_name=self.step_name, verdict=StepVerdict.ALLOW,
                      message="pass-through")

async def _handle_event(self, event: Event) -> None:
    """PASS-THROUGH (Phase F2): Logs event without processing."""
    logger.debug("%s: received event %s (pass-through)", self.engine_name, event.event_type)
```

**The "pass-through" message in StepResult.message is intentional** — E2E tests can verify that governance stubs are correctly identified. When Phase F replaces these, the message will change and tests confirm the new implementation is active.

**Imports needed per file:** Add `logging`, `StepVerdict`, `StepResult`, `Event`. Add `logger = logging.getLogger(__name__)`.

**OTHER STUB METHODS** (all other methods on these 4 engines besides execute and _handle_event) should keep their `...` bodies but add a docstring: `"""Stub — Phase F1/F2 implementation."""`. Do NOT implement them — they are genuinely future work. Only execute() and _handle_event() get real implementations.

### Step 2: WorldResponderEngine.execute() — THE KEY IMPLEMENTATION

**File:** `terrarium/engines/responder/engine.py`

This is the bridge between packs and the pipeline. It must:
1. Initialize with Tier1Dispatcher (create during `_on_initialize`)
2. Build world state from StateEngine for the pack
3. Call Tier1Dispatcher.dispatch(ctx, state)
4. Set ctx.response_proposal = proposal
5. Return StepResult(ALLOW)

```python
class WorldResponderEngine(BaseEngine):
    engine_name = "responder"
    dependencies = ["state"]
    subscriptions = []

    async def _on_initialize(self):
        # Get state engine reference (injected by wire_engines)
        # Create PackRegistry, discover packs, create PackRuntime, create Tier1Dispatcher
        from terrarium.packs.registry import PackRegistry
        from terrarium.packs.runtime import PackRuntime
        from terrarium.packs.loader import discover_packs
        from terrarium.engines.responder.tier1 import Tier1Dispatcher
        from pathlib import Path

        self._pack_registry = PackRegistry()
        # Discover packs from the verified directory
        verified_dir = self._config.get("verified_packs_dir")
        if verified_dir:
            self._pack_registry.discover(verified_dir)
        else:
            # Default: discover from package path
            pack_base = Path(__file__).resolve().parents[1] / "packs" / "verified"
            if pack_base.is_dir():
                self._pack_registry.discover(str(pack_base))

        self._pack_runtime = PackRuntime(self._pack_registry)
        self._tier1 = Tier1Dispatcher(self._pack_runtime)

    async def execute(self, ctx: ActionContext) -> StepResult:
        # Check if we have a Tier 1 pack for this action
        if not self._tier1.has_pack_for_tool(ctx.action):
            return StepResult(
                step_name="responder",
                verdict=StepVerdict.ERROR,
                message=f"No pack found for action '{ctx.action}'",
            )

        # Build world state for the pack
        state = await self._build_state_for_pack(ctx)

        # Dispatch to Tier 1 pack
        proposal = await self._tier1.dispatch(ctx, state=state)

        # Set on context for downstream steps (validation, commit)
        ctx.response_proposal = proposal

        return StepResult(
            step_name="responder",
            verdict=StepVerdict.ALLOW,
            metadata={"fidelity_tier": proposal.fidelity.tier if proposal.fidelity else None},
        )

    async def _build_state_for_pack(self, ctx: ActionContext) -> dict:
        """Fetch relevant entity state from StateEngine for the pack."""
        state_engine = self._dependencies.get("state")
        if state_engine is None:
            return {}

        # Query entities of all types the pack manages
        pack = self._pack_registry.get_pack_for_tool(ctx.action)
        entity_types = list(pack.get_entity_schemas().keys())

        result = {}
        for etype in entity_types:
            try:
                entities = await state_engine.query_entities(etype)
                result[f"{etype}s"] = entities  # email → emails
            except Exception:
                result[f"{etype}s"] = []
        return result

    async def _handle_event(self, event):
        logger.debug("Responder received event: %s", event.event_type)
```

**Key design:** The responder discovers packs during `_on_initialize()`. It uses the existing PackRegistry.discover() to find all verified packs. The `_build_state_for_pack` method queries the StateEngine for entities of all types the pack manages.

### Step 3: ValidationStep Wrapper

**File:** `terrarium/validation/step.py` (NEW)

Wraps the existing `ValidationPipeline` as a `PipelineStep` so the DAG can call it.

```python
"""Validation pipeline step — wraps ValidationPipeline as a PipelineStep."""
from __future__ import annotations
import logging
from terrarium.core.context import ActionContext, StepResult
from terrarium.core.types import StepVerdict
from terrarium.pipeline.step import BasePipelineStep
from terrarium.validation.schema import SchemaValidator
from terrarium.validation.state_machine import StateMachineValidator

logger = logging.getLogger(__name__)

class ValidationStep(BasePipelineStep):
    """Pipeline step that validates the ResponseProposal."""

    step_name = "validation"

    def __init__(self):
        self._schema_validator = SchemaValidator()
        self._sm_validator = StateMachineValidator()

    async def execute(self, ctx: ActionContext) -> StepResult:
        if ctx.response_proposal is None:
            return self._make_result(StepVerdict.ALLOW, message="No proposal to validate")

        # Get entity schemas and state machines from the pack that generated the proposal
        # These are embedded in the fidelity metadata source
        errors = []
        proposal = ctx.response_proposal

        # Validate entity deltas against schemas (if available on context)
        # For now: basic validation that deltas have required fields
        for delta in (proposal.proposed_state_deltas or []):
            if not delta.entity_type:
                errors.append("StateDelta missing entity_type")
            if not delta.entity_id:
                errors.append("StateDelta missing entity_id")
            if delta.operation not in ("create", "update", "delete"):
                errors.append(f"Unknown operation: {delta.operation}")

        if errors:
            return self._make_result(StepVerdict.ERROR, message="; ".join(errors))

        return self._make_result(StepVerdict.ALLOW)
```

**Note:** Full schema+state-machine validation is already done by PackRuntime (step 5). The validation step is a safety net that catches any malformed proposals that bypass the runtime. More sophisticated validation (cross-entity consistency, temporal checks) will be added in Phase F.

### Step 4: Register ValidationStep in Pipeline

**Problem:** The pipeline builder resolves steps from `EngineRegistry.get_pipeline_steps()`. But `ValidationStep` is not an engine — it's a standalone step. We need to include it in the step registry.

**Solution:** After `create_default_registry()` and before `build_pipeline_from_config()`, manually register the ValidationStep:

```python
steps = registry.get_pipeline_steps()  # Gets 6 engine steps
steps["validation"] = ValidationStep()  # Add the standalone validation step
dag = build_pipeline_from_config(config.pipeline, steps)
```

This keeps ValidationStep out of the engine registry (it's not an engine) while making it available to the pipeline builder.

### Step 5: TerrariumApp Bootstrap

**File:** `terrarium/app.py` (NEW)

This is the orchestration layer that ties everything together for both production use and testing:

```python
"""TerrariumApp — bootstrap and orchestration for the full system."""
from __future__ import annotations
import logging
import uuid
from datetime import datetime, timezone
from typing import Any

from terrarium.bus.bus import EventBus
from terrarium.config.loader import ConfigLoader
from terrarium.config.schema import TerrariumConfig
from terrarium.core.context import ActionContext
from terrarium.core.types import ActorId, ServiceId, Timestamp
from terrarium.ledger.ledger import Ledger
from terrarium.persistence.manager import ConnectionManager
from terrarium.pipeline.builder import build_pipeline_from_config
from terrarium.pipeline.dag import PipelineDAG
from terrarium.registry.composition import create_default_registry
from terrarium.registry.health import HealthAggregator
from terrarium.registry.registry import EngineRegistry
from terrarium.registry.wiring import wire_engines, shutdown_engines
from terrarium.validation.step import ValidationStep

logger = logging.getLogger(__name__)


class TerrariumApp:
    """Full Terrarium system bootstrap and lifecycle manager."""

    def __init__(self, config: TerrariumConfig | None = None):
        self._config = config or TerrariumConfig()
        self._conn_mgr: ConnectionManager | None = None
        self._bus: EventBus | None = None
        self._ledger: Ledger | None = None
        self._registry: EngineRegistry | None = None
        self._pipeline: PipelineDAG | None = None
        self._health: HealthAggregator | None = None
        self._started = False

    async def start(self) -> None:
        """Bootstrap the full system: persistence, bus, ledger, engines, pipeline."""
        # 1. Persistence
        self._conn_mgr = ConnectionManager(self._config.persistence)
        await self._conn_mgr.initialize()

        # 2. Event bus
        bus_db = await self._conn_mgr.get_connection("bus")
        self._bus = EventBus(self._config.bus, db=bus_db)
        await self._bus.initialize()

        # 3. Ledger
        ledger_db = await self._conn_mgr.get_connection("ledger")
        self._ledger = Ledger(self._config.ledger, ledger_db)
        await self._ledger.initialize()

        # 4. Engine registry + wiring
        self._registry = create_default_registry()
        # Inject ledger into state engine config
        state_config = self._config.state.model_dump()
        state_config["_ledger"] = self._ledger
        # Override the state config on the TerrariumConfig (frozen, so rebuild)
        # Actually: wire_engines extracts config via getattr, so we need to
        # inject _ledger differently. Simplest: set it after wiring.
        await wire_engines(self._registry, self._bus, self._config)

        # Inject ledger into state engine post-wiring
        state_engine = self._registry.get("state")
        state_engine._ledger = self._ledger

        # 5. Build pipeline
        steps = self._registry.get_pipeline_steps()
        steps["validation"] = ValidationStep()  # Add standalone validation step
        self._pipeline = build_pipeline_from_config(self._config.pipeline, steps)
        self._pipeline._bus = self._bus      # Inject bus for event publishing
        self._pipeline._ledger = self._ledger  # Inject ledger for step recording

        # 6. Health
        self._health = HealthAggregator(self._registry)

        self._started = True
        logger.info("TerrariumApp started with %d engines", len(self._registry.list_engines()))

    async def stop(self) -> None:
        """Graceful shutdown in reverse order."""
        if self._registry:
            await shutdown_engines(self._registry)
        if self._bus:
            await self._bus.shutdown()
        if self._conn_mgr:
            await self._conn_mgr.shutdown()
        self._started = False

    async def handle_action(
        self,
        actor_id: str,
        service_id: str,
        action: str,
        input_data: dict[str, Any],
        **overrides: Any,
    ) -> dict[str, Any]:
        """Execute a single action through the full 7-step pipeline.

        This is the primary entry point for all agent interactions.

        Returns:
            The response body from the pack (or error dict on failure).
        """
        now = datetime.now(timezone.utc)
        ctx = ActionContext(
            request_id=f"req-{uuid.uuid4().hex[:12]}",
            actor_id=ActorId(actor_id),
            service_id=ServiceId(service_id),
            action=action,
            input_data=input_data,
            world_time=overrides.get("world_time", now),
            wall_time=now,
            tick=overrides.get("tick", 0),
        )

        await self._pipeline.execute(ctx)

        if ctx.short_circuited:
            step = ctx.short_circuit_step
            return {"error": f"Pipeline short-circuited at step '{step}'", "step": step}

        if ctx.response_proposal:
            return ctx.response_proposal.response_body
        return {"error": "No response produced"}

    @property
    def registry(self) -> EngineRegistry:
        return self._registry

    @property
    def bus(self) -> EventBus:
        return self._bus

    @property
    def ledger(self) -> Ledger:
        return self._ledger

    @property
    def pipeline(self) -> PipelineDAG:
        return self._pipeline
```

### Step 6: E2E Tests

**File:** `tests/integration/test_wire.py` (NEW — THE MAIN E2E TEST FILE)

```python
@pytest.fixture
async def app(tmp_path):
    """Fully bootstrapped TerrariumApp with tmp databases."""
    from terrarium.config.schema import TerrariumConfig
    from terrarium.persistence.config import PersistenceConfig

    config = TerrariumConfig()
    # Override persistence to use tmp_path
    config = config.model_copy(update={
        "persistence": PersistenceConfig(base_dir=str(tmp_path / "data")),
        "state": config.state.model_copy(update={"db_path": str(tmp_path / "state.db")}),
    })

    app = TerrariumApp(config)
    await app.start()
    yield app
    await app.stop()
```

### Test Categories

**Category A: Real-Data E2E Tests (Agent Simulation)**
These simulate a real agent interacting with Terrarium. Real data goes in, real data comes out.

| # | Test | What an agent does | What we verify |
|---|------|-------|-------|
| A1 | `test_agent_sends_email` | Agent-1 calls email_send with real payload | Response has email_id, status="delivered", thread_id |
| A2 | `test_agent_reads_email` | Agent-1 sends email, then reads it | Response has full email data, status transitions to "read" |
| A3 | `test_agent_replies_to_email` | Agent-1 sends, Agent-2 replies | Reply has in_reply_to, same thread_id, correct subject |
| A4 | `test_agent_lists_inbox` | Agent-1 sends 3 emails to Agent-2, Agent-2 lists | List returns 3 emails in correct order |
| A5 | `test_agent_full_conversation` | send → read → reply → reply → list — multi-turn | All 4 emails in timeline, correct thread linking |

**Category B: Infrastructure Verification Tests (Wire Integrity)**
These verify the infrastructure works. They MUST NOT be removed when governance is added.

| # | Test | Verifies |
|---|------|----------|
| B1 | `test_all_7_steps_execute` | All 7 PipelineStepEntry in ledger with correct step_names in order |
| B2 | `test_all_steps_return_allow` | Every step verdict is ALLOW for a valid email_send |
| B3 | `test_state_committed_to_store` | Entity exists in StateEngine.get_entity() after pipeline |
| B4 | `test_event_persisted_to_log` | WorldEvent in StateEngine event log with correct fields |
| B5 | `test_event_published_to_bus` | Bus subscriber receives the WorldEvent |
| B6 | `test_ledger_has_state_mutation` | StateMutationEntry with entity_type, operation, before/after |
| B7 | `test_fidelity_metadata_tier1` | FidelityMetadata: tier=VERIFIED, deterministic=True, benchmark_grade=True |

**Category C: Replay + Audit Tests (Data Integrity)**

| # | Test | Verifies |
|---|------|----------|
| C1 | `test_bus_event_replay` | Events from bus log can be replayed in order |
| C2 | `test_ledger_query_by_actor` | Ledger entries filterable by actor_id |
| C3 | `test_state_timeline` | StateEngine.get_timeline() returns events in correct order |
| C4 | `test_causal_chain_through_pipeline` | Two linked actions have causal edges in CausalGraph |

**Category D: Drift Prevention Tests (Architectural Guards)**
These prevent future implementations from breaking the architecture.

| # | Test | Guards against |
|---|------|----------------|
| D1 | `test_pass_through_steps_marked` | All 4 governance steps have message="pass-through" — when Phase F replaces them, this test changes to verify real governance |
| D2 | `test_unknown_action_fails_gracefully` | action="nonexistent" → error response (not crash) |
| D3 | `test_pipeline_short_circuit` | Inject a DENY step → pipeline stops, only N steps in ledger |
| D4 | `test_terrarium_app_lifecycle` | start() → handle_action() → stop() without resource leaks |
| D5 | `test_concurrent_actions_safe` | Two actions in parallel both succeed (basic concurrency) |

**Total: ~20 E2E tests across 4 categories**

---

## Files to Modify / Create

| File | Action | Notes |
|------|--------|-------|
| `engines/permission/engine.py` | **IMPLEMENT** | execute() + _handle_event pass-through |
| `engines/policy/engine.py` | **IMPLEMENT** | execute() + _handle_event pass-through |
| `engines/budget/engine.py` | **IMPLEMENT** | execute() + _handle_event pass-through |
| `engines/adapter/engine.py` | **IMPLEMENT** | execute() + _handle_event pass-through |
| `engines/responder/engine.py` | **IMPLEMENT** | execute() with Tier1Dispatcher + state building |
| `validation/step.py` | **CREATE** | ValidationStep wrapping existing validators |
| `app.py` | **CREATE** | TerrariumApp bootstrap + handle_action |
| `tests/integration/test_wire.py` | **CREATE** | ~20 E2E tests (4 categories) |
| `tests/integration/conftest.py` | **CREATE/UPDATE** | TerrariumApp fixture |
| `IMPLEMENTATION_STATUS.md` | **UPDATE** | Flip C3 rows, session log |
| `plans/C3-wire.md` | **CREATE** | Save plan |

---

## Verification

1. `pytest tests/integration/test_wire.py -v` — ALL ~20 pass
2. `pytest tests/ -q` — 803 + ~20 = ~823 passed, 0 failures
3. Manual E2E test:
```python
import asyncio
from terrarium.app import TerrariumApp
async def main():
    app = TerrariumApp()
    await app.start()
    result = await app.handle_action(
        "agent-1", "email", "email_send",
        {"from_addr": "alice@test.com", "to_addr": "bob@test.com",
         "subject": "Hello", "body": "World"},
    )
    print(result)
    # → {"email_id": "email-xxx", "status": "delivered", "thread_id": "thread-xxx", ...}
    await app.stop()
asyncio.run(main())
```
4. Ledger verification:
```python
entries = await app.ledger.query(...)
assert len([e for e in entries if e.entry_type == "pipeline_step"]) == 7
```

---

## Design Compliance

| Principle | How C3 follows it |
|-----------|------------------|
| **Pipeline is the law** | ALL actions flow through 7-step DAG |
| **No direct SDK calls** | Responder uses PackRuntime, not pack.handle_action directly |
| **Bus for inter-engine comms** | StateEngine publishes WorldEvent to bus |
| **Ledger audits everything** | 7 PipelineStepEntry + StateMutationEntry |
| **Config-driven** | Pipeline steps from terrarium.toml, pack discovery from filesystem |
| **Engine isolation** | Each engine only accesses deps via registry injection |
| **Pass-through is correct** | Governance stubs return ALLOW — the architecture supports this |

---

## Post-Implementation

1. Save plan to `plans/C3-wire.md`
2. Update `IMPLEMENTATION_STATUS.md`:
   - Flip responder, permission, policy, budget, adapter step rows to done
   - Add session log
   - Update focus: `C3 WIRE ✅ → Phase C COMPLETE → Next: D1 reality/`
3. **Phase C COMPLETE** — first vertical slice proven end-to-end
