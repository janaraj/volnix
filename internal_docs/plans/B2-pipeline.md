# Phase B2: Pipeline Module Implementation

## Context

**Phase:** B2 (second Phase B item)
**Module:** `terrarium/pipeline/`
**Depends on:** A3 (bus — publishes events), A4 (ledger — records steps), B1 (validation — step 6), core types
**Goal:** The 7-step DAG executor — the LAW of the system. Sequential execution, short-circuit, side effect re-entry, ledger recording, event publishing.

**Bigger picture:** Per DESIGN_PRINCIPLES.md: *"Every action flows through the same 7-step DAG. No bypassing."* Every agent action, every animator event, every side effect enters this pipeline. It's the single path through which ALL state mutations happen. Without it, engines are disconnected pieces. With it, the world has law.

**Who consumes this:**
- **C3 (wire)** — first E2E action flows through the real pipeline
- **E1 (gateway)** — gateway.handle_request() calls pipeline.execute(ctx)
- **G3 (animator)** — animator events enter the pipeline
- **Every engine** — engines are pipeline steps

**After B2:** We have foundation (A1-A4) + validation (B1) + pipeline (B2). The execution backbone is ready. B3 (LLM) and B4 (registry) complete Phase B.

---

## Critical Implementation Note: StepResult.is_terminal

**core/context.py** has `StepResult.is_terminal` as a stub (`...`). This MUST be implemented for the pipeline to work. Terminal verdicts (DENY, HOLD, ESCALATE, ERROR) stop the pipeline. ALLOW continues.

```python
@property
def is_terminal(self) -> bool:
    return self.verdict in (StepVerdict.DENY, StepVerdict.HOLD, StepVerdict.ESCALATE, StepVerdict.ERROR)
```

---

## Architecture

```
PipelineDAG.execute(ctx: ActionContext) -> ActionContext
    │
    for each step in [permission, policy, budget, capability, responder, validation, commit]:
    │
    ├── 1. await step.execute(ctx) → StepResult
    │
    ├── 2. Record on context: ctx.{step_name}_result = result
    │
    ├── 3. Record to ledger: PipelineStepEntry(step_name, verdict, duration_ms)
    │
    ├── 4. Publish events: bus.publish(event) for each event in result.events
    │
    ├── 5. Check short-circuit: if result.is_terminal:
    │       ctx.short_circuited = True
    │       ctx.short_circuit_step = step_name
    │       BREAK (skip remaining steps)
    │
    └── 6. Continue to next step

After pipeline completes (if not short-circuited):
    SideEffectProcessor.enqueue(side_effects from ctx.response_proposal)
```

**Key: "validation" step has no engine.** Create a lightweight `ValidationStep` in pipeline/ that wraps `ValidationPipeline` from B1 and satisfies `PipelineStep` protocol. This is the bridge between validation framework and pipeline execution.

---

## Design Principle Compliance

| Principle | How B2 follows it |
|-----------|------------------|
| **Config-driven** | Step order from PipelineConfig (TOML). timeout_per_step from config. max_depth from config. |
| **Ledger recording** | Every step execution → PipelineStepEntry with step_name, verdict, duration_ms |
| **Event publishing** | Terminal events published to bus (PermissionDenied, PolicyBlock, BudgetExhausted, etc.) |
| **No bypassing** | Pipeline is the only path. SideEffects re-enter the same pipeline. |
| **Protocol-based** | Steps are PipelineStep protocol. Pipeline doesn't know concrete engine types. |
| **DI** | Pipeline receives bus, ledger via constructor. Doesn't create them. |

---

## Reuse from A1-B1

| What | From | Used by |
|------|------|---------|
| `EventBus` | A3 | Pipeline publishes events from step results |
| `Ledger` | A4 | Pipeline records PipelineStepEntry for each step |
| `PipelineStepEntry` | A4 | Entry type for ledger recording |
| `ValidationPipeline` | B1 | Wrapped by ValidationStep for step 6 |
| `ValidationResult` | B1 | ValidationStep converts to StepResult |
| `ActionContext`, `StepResult` | core | Context flows through, results returned |
| `StepVerdict` | core | ALLOW/DENY/HOLD/ESCALATE/ERROR |
| `PipelineStep` protocol | core | All steps implement this |
| `SideEffect` | core | From ResponseProposal, re-enter pipeline |
| `PipelineConfig` | pipeline/config.py | Already implemented with defaults |

---

## Implementation Order

### Step 0: Fix `core/context.py` — StepResult.is_terminal

Implement the property (currently stub):
```python
@property
def is_terminal(self) -> bool:
    return self.verdict in (StepVerdict.DENY, StepVerdict.HOLD, StepVerdict.ESCALATE, StepVerdict.ERROR)
```

### Step 1: `pipeline/step.py` — BasePipelineStep

Base class with timing helper:
```python
class BasePipelineStep(ABC):
    step_name: ClassVar[str]

    @abstractmethod
    async def execute(self, ctx: ActionContext) -> StepResult:
        ...

    def _make_result(self, verdict, message="", events=None, metadata=None, duration_ms=0.0) -> StepResult:
        return StepResult(
            step_name=self.step_name,
            verdict=verdict,
            message=message,
            events=events or [],
            metadata=metadata or {},
            duration_ms=duration_ms,
        )
```

### Step 2: `pipeline/dag.py` — PipelineDAG (the core)

```python
class PipelineDAG:
    def __init__(self, steps: list[PipelineStep], bus: EventBus | None = None, ledger: Any | None = None):
        self._steps = steps
        self._bus = bus
        self._ledger = ledger

    @property
    def step_names(self) -> list[str]:
        return [s.step_name for s in self._steps]

    async def execute(self, ctx: ActionContext) -> ActionContext:
        for step in self._steps:
            start = time.monotonic()
            try:
                result = await step.execute(ctx)
            except Exception as exc:
                result = StepResult(
                    step_name=step.step_name,
                    verdict=StepVerdict.ERROR,
                    message=str(exc),
                    duration_ms=(time.monotonic() - start) * 1000,
                )
            else:
                # Update duration
                result = StepResult(
                    step_name=result.step_name,
                    verdict=result.verdict,
                    message=result.message,
                    events=result.events,
                    metadata=result.metadata,
                    duration_ms=(time.monotonic() - start) * 1000,
                )

            # Record on context
            self._record_result(ctx, step.step_name, result)

            # Record to ledger
            await self._record_to_ledger(ctx, result)

            # Publish events
            for event in result.events:
                await self._publish_event(event)

            # Short-circuit check
            if result.is_terminal:
                ctx.short_circuited = True
                ctx.short_circuit_step = step.step_name
                break

        return ctx

    def _record_result(self, ctx, step_name, result):
        field_map = {
            "permission": "permission_result",
            "policy": "policy_result",
            "budget": "budget_result",
            "capability": "capability_result",
            "validation": "validation_result",
            "commit": "commit_result",
        }
        field = field_map.get(step_name)
        if field:
            setattr(ctx, field, result)

    async def _record_to_ledger(self, ctx, result):
        if self._ledger is None:
            return
        from terrarium.ledger.entries import PipelineStepEntry
        entry = PipelineStepEntry(
            step_name=result.step_name,
            request_id=ctx.request_id,
            actor_id=ctx.actor_id,
            action=ctx.action,
            verdict=result.verdict.value,
            duration_ms=result.duration_ms,
        )
        await self._ledger.append(entry)

    async def _publish_event(self, event):
        if self._bus is not None:
            await self._bus.publish(event)
```

### Step 3: `pipeline/builder.py` — build_pipeline_from_config

```python
def build_pipeline_from_config(config: PipelineConfig, step_registry: dict[str, PipelineStep]) -> PipelineDAG:
    """Build pipeline from config step names + a registry of step implementations.

    Args:
        config: Pipeline configuration with step ordering.
        step_registry: Maps step_name → PipelineStep implementation.
                      In production, this comes from EngineRegistry.get_step().
                      In tests, this can be a plain dict of mock steps.
    """
    steps = []
    for step_name in config.steps:
        step = step_registry.get(step_name)
        if step is None:
            raise ValueError(f"Pipeline step '{step_name}' not found in registry. Available: {list(step_registry.keys())}")
        steps.append(step)
    return PipelineDAG(steps)
```

**Note:** Takes a `dict[str, PipelineStep]` not `EngineRegistry` directly. This decouples from B4 — we can pass a plain dict in tests and the real registry in production. The EngineRegistry (B4) will have a method that produces this dict.

### Step 4: `pipeline/side_effects.py` — SideEffectProcessor

```python
class SideEffectProcessor:
    def __init__(self, pipeline: PipelineDAG, max_depth: int = 10):
        self._pipeline = pipeline
        self._max_depth = max_depth
        self._queue: asyncio.Queue[tuple[SideEffect, ActionContext, int]] = asyncio.Queue()
        self._running = False
        self._task: asyncio.Task | None = None

    async def enqueue(self, side_effect: SideEffect, parent_ctx: ActionContext, depth: int = 0) -> None:
        if depth >= self._max_depth:
            return  # silently drop — max depth reached
        await self._queue.put((side_effect, parent_ctx, depth))

    async def process_all(self) -> int:
        count = 0
        while not self._queue.empty():
            se, parent_ctx, depth = await self._queue.get()
            ctx = self._side_effect_to_context(se, parent_ctx)
            result_ctx = await self._pipeline.execute(ctx)
            count += 1
            # If the side effect itself produced side effects, re-enqueue at depth+1
            if result_ctx.response_proposal and result_ctx.response_proposal.proposed_side_effects:
                for nested_se in result_ctx.response_proposal.proposed_side_effects:
                    await self.enqueue(nested_se, result_ctx, depth + 1)
        return count

    async def start_background(self) -> None:
        self._running = True
        self._task = asyncio.create_task(self._background_loop())

    async def stop(self) -> None:
        self._running = False
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

    async def _background_loop(self) -> None:
        while self._running:
            try:
                se, parent_ctx, depth = await asyncio.wait_for(self._queue.get(), timeout=0.1)
                ctx = self._side_effect_to_context(se, parent_ctx)
                result_ctx = await self._pipeline.execute(ctx)
                if result_ctx.response_proposal and result_ctx.response_proposal.proposed_side_effects:
                    for nested_se in result_ctx.response_proposal.proposed_side_effects:
                        await self.enqueue(nested_se, result_ctx, depth + 1)
            except asyncio.TimeoutError:
                continue
            except asyncio.CancelledError:
                break

    @staticmethod
    def _side_effect_to_context(se: SideEffect, parent_ctx: ActionContext) -> ActionContext:
        import uuid
        return ActionContext(
            request_id=f"se_{uuid.uuid4().hex[:8]}",
            actor_id=parent_ctx.actor_id,
            service_id=se.target_service or parent_ctx.service_id,
            action=se.effect_type,
            input_data=se.parameters,
            target_entity=se.target_entity,
            world_time=parent_ctx.world_time,
            wall_time=parent_ctx.wall_time,
            tick=parent_ctx.tick,
            run_id=parent_ctx.run_id,
        )
```

---

## Files to Modify / Create

| File | Action | Notes |
|------|--------|-------|
| `terrarium/core/context.py` | **UPDATE** | Implement StepResult.is_terminal property |
| `terrarium/pipeline/step.py` | **IMPLEMENT** | BasePipelineStep with timing helper |
| `terrarium/pipeline/dag.py` | **IMPLEMENT** | PipelineDAG: execute, record, publish, short-circuit |
| `terrarium/pipeline/builder.py` | **IMPLEMENT** | build_pipeline_from_config with dict registry |
| `terrarium/pipeline/side_effects.py` | **IMPLEMENT** | SideEffectProcessor: queue, process, depth bound |
| `terrarium/pipeline/config.py` | **VERIFY** | Already has defaults |
| `terrarium/pipeline/__init__.py` | **VERIFY** | Re-exports correct |
| `tests/pipeline/test_dag.py` | **IMPLEMENT** | ~14 tests |
| `tests/pipeline/test_step.py` | **IMPLEMENT** | ~5 tests |
| `tests/pipeline/test_builder.py` | **IMPLEMENT** | ~5 tests |
| `tests/pipeline/test_side_effects.py` | **IMPLEMENT** | ~8 tests |
| `tests/pipeline/test_integration.py` | **CREATE** | ~5 tests: pipeline + bus + ledger E2E |
| `IMPLEMENTATION_STATUS.md` | **UPDATE** | Flip pipeline to done, session log |
| `plans/B2-pipeline.md` | **CREATE** | Save plan to project |

---

## Test Strategy: Mock Steps

B2 tests use **mock pipeline steps** (not real engines — those are Phase C+). Each mock step returns a configurable StepResult.

```python
class MockStep:
    """Test step with configurable verdict."""
    def __init__(self, name: str, verdict: StepVerdict = StepVerdict.ALLOW, events=None):
        self._name = name
        self._verdict = verdict
        self._events = events or []

    @property
    def step_name(self) -> str:
        return self._name

    async def execute(self, ctx: ActionContext) -> StepResult:
        return StepResult(step_name=self._name, verdict=self._verdict, events=self._events)
```

This pattern lets us test every flow without real engines: all-allow, deny-at-permission, hold-at-policy, error-at-any-step, etc.

---

## Tests

### test_dag.py (~16 tests)
- test_execute_all_allow — 7 mock allow steps → ctx not short-circuited, all results recorded
- test_execute_short_circuit_deny — deny at step 2 → steps 3-7 skipped
- test_execute_short_circuit_hold — hold at step 2 → steps 3-7 skipped
- test_execute_short_circuit_escalate — escalate → pipeline stops
- test_execute_short_circuit_error — error → pipeline stops
- test_step_names_property — returns ordered list matching input
- test_record_result_on_context — permission_result, policy_result, budget_result etc. set correctly
- test_short_circuit_flags — ctx.short_circuited=True, ctx.short_circuit_step set to failing step name
- test_exception_in_step — step raises Exception → ERROR result auto-generated, pipeline stops
- test_duration_tracking — result.duration_ms > 0 for each step
- test_ledger_recording — each step produces PipelineStepEntry (uses real Ledger from A4)
- test_event_publishing — events from step results published to bus (uses real EventBus from A3)
- test_empty_pipeline — zero steps → ctx returned unchanged, not short-circuited
- test_allow_continues_all_steps — all 7 steps execute when all ALLOW
- test_pipeline_without_bus — bus=None, pipeline still works, no events published
- test_pipeline_without_ledger — ledger=None, pipeline still works, no entries recorded

### test_step.py (~5 tests)
- test_base_step_is_abstract — can't instantiate BasePipelineStep
- test_make_result — helper creates StepResult with correct fields
- test_make_result_defaults — default message, events, metadata
- test_step_name_property — returns ClassVar value
- test_step_result_is_terminal — DENY/HOLD/ESCALATE/ERROR are terminal, ALLOW is not

### test_builder.py (~5 tests)
- test_build_from_config — config steps map to registry entries
- test_build_missing_step_raises — unknown step name raises ValueError
- test_build_preserves_order — steps in DAG match config order
- test_build_empty_steps — empty config.steps produces empty DAG
- test_build_partial_registry — only needed steps must be in registry

### test_side_effects.py (~8 tests)
- test_enqueue_and_process — enqueue 1 SE, process → 1 action through pipeline
- test_process_multiple — enqueue 3 SEs, process → 3 actions
- test_max_depth_enforced — depth >= max_depth → SE silently dropped
- test_nested_side_effects — SE produces another SE → processed at depth+1
- test_nested_depth_limit — nested SEs stop at max_depth
- test_side_effect_to_context — converts SideEffect to ActionContext correctly
- test_process_all_returns_count — returns number processed
- test_empty_queue_returns_zero — nothing enqueued → 0

### test_integration.py (NEW — ~5 tests)
- test_pipeline_with_real_bus — pipeline publishes events to EventBus
- test_pipeline_with_real_ledger — pipeline records PipelineStepEntry to Ledger
- test_pipeline_bus_and_ledger — both bus + ledger receive correct data
- test_side_effect_full_cycle — SE re-enters pipeline, bus + ledger record both
- test_all_verdict_types — ALLOW, DENY, HOLD, ERROR each recorded correctly

---

## Completion Criteria (Zero Stubs)

| File | Methods | All Implemented? | All Tested? |
|------|---------|-----------------|-------------|
| `core/context.py` | StepResult.is_terminal | ✅ fixed | ✅ test_step.py |
| `pipeline/step.py` | BasePipelineStep, _make_result | ✅ | ✅ 5 tests |
| `pipeline/dag.py` | execute, step_names, _record_result, _record_to_ledger, _publish_event | ✅ 5 methods | ✅ 14 tests |
| `pipeline/builder.py` | build_pipeline_from_config | ✅ 1 function | ✅ 5 tests |
| `pipeline/side_effects.py` | enqueue, process_all, start_background, stop, _side_effect_to_context | ✅ 5 methods | ✅ 8 tests |
| `pipeline/config.py` | PipelineConfig | ✅ already done | ✅ via config tests |
| `pipeline/__init__.py` | re-exports | ✅ | ✅ import test |

**0 stubs remaining in pipeline/ or core/context.py. ~37 tests across 5 test files.**

---

## Post-Implementation Tasks

### 1. Save plan
Copy to `plans/B2-pipeline.md` in the project repo.

### 2. Update IMPLEMENTATION_STATUS.md

**Current Focus:**
```
**Phase:** B — Core Infrastructure
**Item:** B2 pipeline/ ✅ COMPLETE → Next: B3 llm/
**Status:** Pipeline DAG implemented. 7-step execution, short-circuit, side effects, ledger + bus integration.
```

**Flip these rows to ✅ done:**
- Pipeline — dag
- Pipeline — step
- Pipeline — builder
- Pipeline — side_effects

**Session log entry.**

---

## Verification

1. `.venv/bin/python -m pytest tests/pipeline/ -v` — ALL pass
2. `.venv/bin/python -m pytest tests/pipeline/ --cov=terrarium/pipeline --cov-report=term-missing` — >90%
3. `grep -rn "^\s*\.\.\.$" terrarium/pipeline/*.py` — 0 results
4. **StepResult.is_terminal works:**
   ```python
   from terrarium.core.context import StepResult
   from terrarium.core.types import StepVerdict
   r = StepResult(step_name="test", verdict=StepVerdict.DENY)
   assert r.is_terminal == True
   r = StepResult(step_name="test", verdict=StepVerdict.ALLOW)
   assert r.is_terminal == False
   ```
5. **Short-circuit works:** publish DENY at step 2, verify steps 3-7 never execute
6. **Ledger integration:** pipeline produces PipelineStepEntry for each step
7. **Bus integration:** events from step results published to bus
8. ALL previous tests: `.venv/bin/python -m pytest tests/ -q` — 556+ passed, 0 failed
9. `plans/B2-pipeline.md` exists
10. `IMPLEMENTATION_STATUS.md` updated
