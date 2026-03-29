# Phase B4: Registry Module Implementation

## Context

**Phase:** B4 (final Phase B item — the DI/orchestration layer)
**Module:** `terrarium/registry/` + `terrarium/core/engine.py` + `terrarium/core/errors.py` + all core tests
**Depends on:** All of Phase A + B1-B3 (673 tests passing)
**Goal:** Engine DI container, topological initialization, bus wiring, health aggregation, composition root. Plus: implement all remaining core/ stubs and their tests.

**Bigger picture:** B4 completes Phase B. After this, Phase C wires the first vertical slice: StateEngine + email pack + full pipeline. The registry creates engine instances, resolves dependency order, injects config + bus, and starts them. Every future phase (C→H) depends on B4.

**What this unlocks for Phase C:**
```
config = ConfigLoader().load()
bus = EventBus(config.bus); await bus.initialize()
registry = create_default_registry()
await wire_engines(registry, bus, config)
steps = registry.get_pipeline_steps()
dag = build_pipeline_from_config(config.pipeline, steps)
# → Full pipeline ready: action flows through 7 steps, state committed, events published
```

---

## Scope Audit: What Must Be Zero-Stub After B4

| File | Current State | After B4 |
|------|--------------|----------|
| `core/types.py` | Fully implemented | No change |
| `core/events.py` | Fully implemented | No change |
| `core/context.py` | Fully implemented | No change |
| `core/protocols.py` | Fully implemented (13 protocols) | No change |
| `core/errors.py` | **Constructors are stubs** (lines 36-37, 75-81) | **IMPLEMENT** |
| `core/engine.py` | **12 methods are stubs** | **IMPLEMENT** |
| `core/__init__.py` | Fully implemented | No change |
| `registry/registry.py` | **7 methods are stubs** | **IMPLEMENT** |
| `registry/wiring.py` | **2 functions are stubs** | **IMPLEMENT** (+ add shutdown_engines) |
| `registry/composition.py` | **1 function is stub** | **IMPLEMENT** |
| `registry/health.py` | **4 methods are stubs** | **IMPLEMENT** |
| `registry/__init__.py` | Fully implemented | Update exports |
| `tests/core/test_engine.py` | 6 stub tests | **IMPLEMENT** (~10 tests) |
| `tests/core/test_errors.py` | 6 stub tests | **IMPLEMENT** (~6 tests) |
| `tests/core/test_context.py` | 5 stub tests | **IMPLEMENT** (~5 tests) |
| `tests/core/test_events.py` | 8 stub tests | **IMPLEMENT** (~10 tests) |
| `tests/core/test_protocols.py` | 4 stub tests | **IMPLEMENT** (~4 tests) |
| `tests/core/test_types.py` | 7 stubs + 4 implemented | **IMPLEMENT** remaining 7 |
| `tests/registry/test_registry.py` | 6 stub tests | **IMPLEMENT** (~15 tests) |
| `tests/registry/test_wiring.py` | 2 stub tests | **IMPLEMENT** (~8 tests) |
| `tests/registry/test_composition.py` | 2 stub tests | **IMPLEMENT** (~5 tests) |
| `tests/registry/test_health.py` | 2 stub tests | **IMPLEMENT** (~7 tests) |

**Total new/implemented tests: ~80**

---

## Implementation Order (6 steps)

### Step 1: `terrarium/core/errors.py` — Error constructors

Lines 36-37 (`TerrariumError.__init__`):
```python
def __init__(self, message: str = "", context: dict[str, Any] | None = None) -> None:
    super().__init__(message)
    self.message = message
    self.context = context or {}
```

Lines 75-81 (`EngineError.__init__`):
```python
def __init__(self, message: str = "", engine_name: str = "", context: dict[str, Any] | None = None) -> None:
    super().__init__(message, context)
    self.engine_name = engine_name
```

Lines 114-119 (`PipelineStepError.__init__` — also a stub):
```python
def __init__(self, message: str = "", step_name: str = "", context: dict[str, Any] | None = None) -> None:
    super().__init__(message, context)
    self.step_name = step_name
```

Lines 163-168 (`ValidationError.__init__` — also a stub):
```python
def __init__(self, message: str = "", validation_type: str = "", context: dict[str, Any] | None = None) -> None:
    super().__init__(message, context)
    self.validation_type = validation_type
```

All `pass` subclasses (ConfigError, EngineInitError, EngineDependencyError, etc.) are correct — they inherit constructors.

### Step 2: `terrarium/core/engine.py` — BaseEngine lifecycle (12 methods)

**Add to `__init__` (line 47):**
```python
def __init__(self) -> None:
    self._bus: Any = None
    self._config: dict[str, Any] = {}
    self._started: bool = False
    self._healthy: bool = False
    self._dependencies: dict[str, Any] = {}
```

**`initialize` (line 57):**
```python
async def initialize(self, config: dict[str, Any], bus: Any) -> None:
    self._config = config
    self._bus = bus
    self._healthy = True
    await self._on_initialize()
```

**`start` (line 66):**
```python
async def start(self) -> None:
    if self._bus is not None:
        for topic in self.subscriptions:
            await self._bus.subscribe(topic, self._dispatch_event)
    self._started = True
    await self._on_start()
```

**`stop` (line 70):**
```python
async def stop(self) -> None:
    self._started = False
    if self._bus is not None:
        for topic in self.subscriptions:
            try:
                await self._bus.unsubscribe(topic, self._dispatch_event)
            except Exception:
                pass  # best-effort unsubscribe during shutdown
    await self._on_stop()
```

**`health_check` (line 74):**
```python
async def health_check(self) -> dict[str, Any]:
    return {
        "engine": self.engine_name,
        "started": self._started,
        "healthy": self._healthy,
    }
```

**`_on_initialize` (line 86):** Default no-op:
```python
async def _on_initialize(self) -> None:
    pass
```

**`_on_start` (line 94):** Default no-op:
```python
async def _on_start(self) -> None:
    pass
```

**`_on_stop` (line 101):** Default no-op:
```python
async def _on_stop(self) -> None:
    pass
```

**`_handle_event` (line 109):** Keep as `@abstractmethod` with `...` body (correct ABC pattern).

**`publish` (line 124):**
```python
async def publish(self, event: Event) -> None:
    if self._bus is not None:
        await self._bus.publish(event)
```

**`_dispatch_event` (line 132):**
```python
async def _dispatch_event(self, event: Event) -> None:
    try:
        await self._handle_event(event)
    except Exception as exc:
        logger.exception("Engine %s failed handling event %s", self.engine_name, event.event_type)
        await self._publish_error(exc, source_event=event)
```
Add `import logging` and `logger = logging.getLogger(__name__)` at top.

**`_publish_error` (line 143):**
```python
async def _publish_error(self, error: Exception, source_event: Event | None = None) -> None:
    error_event = EngineLifecycleEvent(
        event_type="engine.error",
        timestamp=Timestamp(
            world_time=datetime.now(timezone.utc),
            wall_time=datetime.now(timezone.utc),
            tick=0,
        ),
        engine_name=self.engine_name,
        status="error",
        metadata={
            "error": str(error),
            "error_type": type(error).__name__,
            "source_event_id": str(source_event.event_id) if source_event else None,
        },
    )
    if self._bus is not None:
        try:
            await self._bus.publish(error_event)
        except Exception:
            logger.error("Failed to publish error event for engine %s", self.engine_name)
```

Add imports: `from datetime import datetime, timezone`, `from terrarium.core.events import EngineLifecycleEvent`, `from terrarium.core.types import Timestamp`.

### Step 3: `terrarium/registry/registry.py` — EngineRegistry (8 methods)

```python
"""Engine registry — the central DI container for the Terrarium framework."""

from __future__ import annotations

import logging
from typing import Any, ClassVar

from terrarium.core.engine import BaseEngine
from terrarium.core.errors import EngineDependencyError
from terrarium.core.protocols import PipelineStep

logger = logging.getLogger(__name__)


class EngineRegistry:
    """Central registry holding all engine instances by name.

    Supports topological initialization ordering, protocol-based lookup,
    and pipeline step collection.
    """

    def __init__(self) -> None:
        self._engines: dict[str, BaseEngine] = {}

    def register(self, engine: BaseEngine) -> None:
        """Register an engine instance by its engine_name."""
        if not engine.engine_name:
            raise ValueError("Engine must have a non-empty engine_name")
        self._engines[engine.engine_name] = engine

    def get(self, engine_name: str) -> BaseEngine:
        """Retrieve a registered engine by name. Raises KeyError if not found."""
        if engine_name not in self._engines:
            available = sorted(self._engines.keys())
            raise KeyError(
                f"Engine '{engine_name}' not registered. "
                f"Available: {available}"
            )
        return self._engines[engine_name]

    def get_step(self, step_name: str) -> PipelineStep | None:
        """Find a registered engine that implements PipelineStep with the given name."""
        for engine in self._engines.values():
            if isinstance(engine, PipelineStep) and engine.step_name == step_name:
                return engine
        return None

    def get_protocol(self, engine_name: str, protocol_type: type) -> Any:
        """Get engine and verify it satisfies a protocol. Raises TypeError if not."""
        engine = self.get(engine_name)
        if not isinstance(engine, protocol_type):
            raise TypeError(
                f"Engine '{engine_name}' ({type(engine).__name__}) does not "
                f"satisfy protocol {protocol_type.__name__}"
            )
        return engine

    def get_pipeline_steps(self) -> dict[str, PipelineStep]:
        """Collect all engines implementing PipelineStep into a dict for the pipeline builder."""
        steps: dict[str, PipelineStep] = {}
        for engine in self._engines.values():
            if isinstance(engine, PipelineStep):
                steps[engine.step_name] = engine
        return steps

    def resolve_initialization_order(self) -> list[str]:
        """Topological sort via Kahn's algorithm. Detects cycles and missing deps."""
        # Build in-degree map
        in_degree: dict[str, int] = {name: 0 for name in self._engines}
        dependents: dict[str, list[str]] = {name: [] for name in self._engines}

        for name, engine in self._engines.items():
            for dep in engine.dependencies:
                if dep not in self._engines:
                    raise EngineDependencyError(
                        message=f"Engine '{name}' depends on '{dep}', which is not registered. "
                                f"Available: {sorted(self._engines.keys())}",
                        engine_name=name,
                    )
                dependents[dep].append(name)
                in_degree[name] += 1

        # Kahn's algorithm with sorted queues for determinism
        queue = sorted(n for n, d in in_degree.items() if d == 0)
        order: list[str] = []

        while queue:
            node = queue.pop(0)
            order.append(node)
            for dependent in sorted(dependents[node]):
                in_degree[dependent] -= 1
                if in_degree[dependent] == 0:
                    queue.append(dependent)
            queue.sort()

        if len(order) != len(self._engines):
            remaining = sorted(n for n in self._engines if n not in order)
            raise EngineDependencyError(
                message=f"Circular dependency detected among engines: {remaining}",
                engine_name=remaining[0] if remaining else "",
            )

        return order

    def list_engines(self) -> list[str]:
        """Return names of all registered engines."""
        return list(self._engines.keys())
```

### Step 4: `terrarium/registry/health.py` — HealthAggregator

```python
"""Health check aggregation across all registered engines."""

from __future__ import annotations

import logging
from typing import Any

from terrarium.registry.registry import EngineRegistry

logger = logging.getLogger(__name__)


class HealthAggregator:
    """Aggregates health checks from all engines in the registry."""

    def __init__(self, registry: EngineRegistry) -> None:
        self._registry = registry
        self._last_results: dict[str, dict[str, Any]] = {}

    async def check_all(self) -> dict[str, dict[str, Any]]:
        """Run health checks on all registered engines."""
        results: dict[str, dict[str, Any]] = {}
        for name in self._registry.list_engines():
            engine = self._registry.get(name)
            try:
                results[name] = await engine.health_check()
            except Exception as exc:
                logger.warning("Health check failed for engine %s: %s", name, exc)
                results[name] = {"engine": name, "started": False, "healthy": False, "error": str(exc)}
        self._last_results = results
        return results

    async def check_engine(self, engine_name: str) -> dict[str, Any]:
        """Run health check on a single engine."""
        engine = self._registry.get(engine_name)  # KeyError if missing
        try:
            result = await engine.health_check()
        except Exception as exc:
            result = {"engine": engine_name, "started": False, "healthy": False, "error": str(exc)}
        self._last_results[engine_name] = result
        return result

    def is_healthy(self) -> bool:
        """Return True if all engines' last health checks passed. Sync — reads cache."""
        if not self._last_results:
            return False
        return all(r.get("healthy", False) for r in self._last_results.values())
```

### Step 5: `terrarium/registry/wiring.py` — Wire + Shutdown

```python
"""Engine wiring — initialize, inject, start, and stop engines in order."""

from __future__ import annotations

import logging
from typing import Any

from terrarium.config.schema import TerrariumConfig
from terrarium.core.engine import BaseEngine
from terrarium.registry.registry import EngineRegistry

logger = logging.getLogger(__name__)


async def wire_engines(
    registry: EngineRegistry,
    bus: Any,
    config: TerrariumConfig,
) -> None:
    """Initialize and start all engines in dependency order.

    For each engine (in topological order):
    1. Extract engine-specific config from TerrariumConfig
    2. Call engine.initialize(config_dict, bus)
    3. Inject inter-engine dependencies
    4. Call engine.start()
    """
    order = registry.resolve_initialization_order()
    logger.info("Engine initialization order: %s", order)

    for engine_name in order:
        engine = registry.get(engine_name)

        # Extract config: getattr(config, "state") → StateConfig → .model_dump()
        config_obj = getattr(config, engine_name, None)
        engine_config = config_obj.model_dump() if config_obj is not None else {}

        await engine.initialize(engine_config, bus)
        await inject_dependencies(engine, registry)
        await engine.start()
        logger.info("Engine '%s' started", engine_name)


async def shutdown_engines(registry: EngineRegistry) -> None:
    """Stop all engines in reverse initialization order.

    Calls engine.stop() on each, in reverse topological order
    so dependents stop before their dependencies.
    """
    try:
        order = registry.resolve_initialization_order()
    except Exception:
        # If topo sort fails during shutdown, stop in arbitrary order
        order = registry.list_engines()

    for engine_name in reversed(order):
        engine = registry.get(engine_name)
        try:
            await engine.stop()
            logger.info("Engine '%s' stopped", engine_name)
        except Exception as exc:
            logger.error("Error stopping engine '%s': %s", engine_name, exc)


async def inject_dependencies(
    engine: BaseEngine,
    registry: EngineRegistry,
) -> None:
    """Resolve each dependency name from registry and store on engine."""
    resolved: dict[str, BaseEngine] = {}
    for dep_name in engine.dependencies:
        resolved[dep_name] = registry.get(dep_name)
    engine._dependencies = resolved
```

### Step 6: `terrarium/registry/composition.py` — Composition root

```python
"""Composition root — THE ONLY FILE that imports concrete engine classes.

Every other module in Terrarium accesses engines via protocols, engine_name
strings, or the EngineRegistry. This file is the single assembly point.
"""

from __future__ import annotations

from terrarium.registry.registry import EngineRegistry


def create_default_registry() -> EngineRegistry:
    """Create an EngineRegistry with all 10 default engines."""
    # Lazy imports — only executed when this function is called.
    # This is the composition root: the ONLY place concrete engines are imported.
    from terrarium.engines.adapter.engine import AgentAdapterEngine
    from terrarium.engines.animator.engine import WorldAnimatorEngine
    from terrarium.engines.budget.engine import BudgetEngine
    from terrarium.engines.feedback.engine import FeedbackEngine
    from terrarium.engines.permission.engine import PermissionEngine
    from terrarium.engines.policy.engine import PolicyEngine
    from terrarium.engines.reporter.engine import ReportGeneratorEngine
    from terrarium.engines.responder.engine import WorldResponderEngine
    from terrarium.engines.state.engine import StateEngine
    from terrarium.engines.world_compiler.engine import WorldCompilerEngine

    registry = EngineRegistry()
    registry.register(StateEngine())
    registry.register(PolicyEngine())
    registry.register(PermissionEngine())
    registry.register(BudgetEngine())
    registry.register(WorldResponderEngine())
    registry.register(AgentAdapterEngine())
    registry.register(WorldAnimatorEngine())
    registry.register(ReportGeneratorEngine())
    registry.register(FeedbackEngine())
    registry.register(WorldCompilerEngine())
    return registry
```

Update `registry/__init__.py` to export `shutdown_engines`:
```python
from terrarium.registry.wiring import wire_engines, inject_dependencies, shutdown_engines
```

---

## Test Harness — Detailed Implementation

### Shared Test Utility: Mock Engine Factory

Place in `tests/registry/conftest.py`:
```python
"""Shared fixtures and helpers for registry tests."""
from __future__ import annotations
from typing import Any, ClassVar
from unittest.mock import AsyncMock

from terrarium.core.engine import BaseEngine
from terrarium.core.context import ActionContext, StepResult
from terrarium.core.types import StepVerdict


def make_mock_engine(
    name: str,
    deps: list[str] | None = None,
    subs: list[str] | None = None,
    step_name_val: str | None = None,
) -> BaseEngine:
    """Create a unique mock engine subclass with given parameters.

    Creates a new class each time to avoid ClassVar mutation between tests.
    If step_name_val is provided, the engine also satisfies PipelineStep protocol.
    """
    class_attrs: dict[str, Any] = {
        "engine_name": name,
        "dependencies": deps or [],
        "subscriptions": subs or [],
    }

    async def _handle_event(self, event):
        pass

    class_attrs["_handle_event"] = _handle_event

    if step_name_val is not None:
        class_attrs["step_name"] = property(lambda self, v=step_name_val: v)

        async def execute(self, ctx: ActionContext) -> StepResult:
            return StepResult(step_name=step_name_val, verdict=StepVerdict.ALLOW)

        class_attrs["execute"] = execute

    klass = type(f"MockEngine_{name}", (BaseEngine,), class_attrs)
    return klass()


def make_mock_bus() -> AsyncMock:
    """Create a mock bus with subscribe/unsubscribe/publish."""
    bus = AsyncMock()
    bus.subscribe = AsyncMock()
    bus.unsubscribe = AsyncMock()
    bus.publish = AsyncMock()
    return bus
```

### test_registry.py (~15 tests)

```
test_register_engine — register, verify in list_engines
test_register_overwrites — same name, second wins
test_register_empty_name_raises — ValueError for empty engine_name
test_get_engine_found — register then get
test_get_engine_missing — KeyError with helpful message
test_get_step_found — engine with step_name, verify get_step returns it
test_get_step_not_found — returns None
test_get_pipeline_steps — 6 step engines + 4 non-step, verify dict has 6
test_get_protocol_match — PipelineStep on step engine, succeeds
test_get_protocol_mismatch — PipelineStep on non-step engine, TypeError
test_list_engines_empty — new registry, returns []
test_topo_sort_full_graph — all 10 engines with real deps, state first, adapter last
test_topo_sort_single — one engine, no deps
test_topo_sort_diamond — D→{B,C}→A pattern
test_circular_dependency_raises — A→B→A, EngineDependencyError
test_missing_dependency_raises — dep on unregistered, EngineDependencyError
test_topo_sort_deterministic — run 10x, same result each time
```

### test_wiring.py (~8 tests)

```
test_wire_engines — 3 engines, verify all started with config+bus
test_wire_respects_order — track init order via side effect, verify state before policy
test_wire_config_extraction — verify StateEngine._config contains state config fields
test_wire_bus_subscriptions — verify bus.subscribe called for each engine's topics
test_wire_missing_config_graceful — engine without config section gets {}
test_inject_dependencies — policy engine gets state in _dependencies
test_inject_empty_deps — engine with no deps, _dependencies is {}
test_shutdown_engines — all engines stopped in reverse order
```

### test_composition.py (~5 tests)

```
test_create_default_registry — returns EngineRegistry with 10 engines
test_all_engine_names — exact set of 10 names
test_topo_sort_no_cycles — resolve_initialization_order succeeds, state first
test_pipeline_steps_complete — 6 steps: commit, policy, permission, budget, responder, capability
test_protocol_resolution — get_protocol("state", StateEngineProtocol) succeeds
```

### test_health.py (~7 tests)

```
test_check_all_healthy — all engines healthy, verify dict results
test_check_all_one_unhealthy — one engine._healthy=False, verify result
test_check_single — single engine health check
test_is_healthy_all_pass — True after check_all with all healthy
test_is_healthy_one_fail — False when one unhealthy
test_is_healthy_before_check — False (no cache yet)
test_health_check_error — engine.health_check raises, graceful degradation
```

### test_engine.py (~10 tests)

```
test_init_defaults — _bus=None, _config={}, _started=False, _healthy=False, _dependencies={}
test_initialize — sets _config, _bus, _healthy=True
test_start_subscribes — bus.subscribe called for each subscription topic
test_start_sets_started — _started=True after start
test_stop_unsubscribes — bus.unsubscribe called, _started=False
test_health_check_format — returns dict with engine/started/healthy keys
test_publish_delegates — calls bus.publish
test_publish_no_bus — no crash when bus is None
test_dispatch_calls_handle — _handle_event called with event
test_dispatch_error_publishes — exception in _handle_event → error event published
```

### test_errors.py (~6 tests)

```
test_terrarium_error_message — str(error) == message
test_terrarium_error_context — .context attribute accessible
test_engine_error_engine_name — .engine_name attribute set
test_pipeline_error_step_name — .step_name attribute set
test_validation_error_type — .validation_type attribute set
test_error_inheritance — isinstance chain: EngineDependencyError → EngineError → TerrariumError
```

### test_context.py (~5 tests)

```
test_action_context_mutable — can set fields after creation
test_step_result_frozen — cannot mutate frozen StepResult
test_step_result_is_terminal — DENY/HOLD/ESCALATE/ERROR are terminal, ALLOW is not
test_response_proposal_frozen — cannot mutate
test_action_context_defaults — unset fields are None/empty
```

### test_events.py (~10 tests)

```
test_event_id_unique — two events get different IDs
test_event_base_fields — Event has event_id, event_type, timestamp, caused_by, metadata
test_world_event_fields — WorldEvent has actor_id, service_id, action, etc
test_policy_block_event — PolicyBlockEvent has reason field
test_policy_hold_event — PolicyHoldEvent has approver_role, timeout_seconds, hold_id
test_budget_deduction_event — has amount, remaining
test_capability_gap_event — has requested_tool
test_engine_lifecycle_event — has engine_name, status
test_event_frozen — cannot mutate
test_event_serialization — model_dump() → model_validate() round-trip
```

### test_protocols.py (~4 tests)

```
test_pipeline_step_runtime_checkable — isinstance works
test_state_engine_protocol — has expected methods
test_all_protocols_runtime_checkable — all 14 protocols pass @runtime_checkable check
test_protocol_not_satisfied — class missing method fails isinstance
```

### test_types.py (~7 new tests to fill existing stubs)

```
test_entity_id_is_str — NewType wraps str
test_fidelity_tier_ordering — VERIFIED < PROFILED
test_step_verdict_values — all 5 values exist
test_enforcement_mode_values — all 4 values exist
test_fidelity_metadata_frozen — cannot mutate
test_action_cost_defaults — default values correct
test_state_delta_frozen — cannot mutate
```

---

## Verification

1. **All registry tests pass:**
   ```bash
   .venv/bin/python -m pytest tests/registry/ -v
   ```

2. **All core tests pass:**
   ```bash
   .venv/bin/python -m pytest tests/core/ -v
   ```

3. **Zero stubs in registry/ and core/:**
   ```bash
   grep -rn "^\s*\.\.\.$" terrarium/registry/*.py terrarium/core/engine.py terrarium/core/errors.py | grep -v "abstractmethod" | grep -v "Protocol"
   ```
   Should return 0 results (only abstract methods and Protocol method signatures use `...`).

4. **Composition root isolation:**
   ```bash
   grep -rn "from terrarium.engines" terrarium/ --include="*.py" | grep -v "registry/composition.py" | grep -v "tests/" | grep -v "__pycache__"
   ```
   Should return 0 (only composition.py imports concrete engines).

5. **Integration smoke test:**
   ```python
   from terrarium.registry import create_default_registry, wire_engines, shutdown_engines, HealthAggregator
   from terrarium.config.schema import TerrariumConfig
   from terrarium.bus import EventBus

   config = TerrariumConfig()
   bus = EventBus(config.bus)
   await bus.initialize()
   registry = create_default_registry()
   await wire_engines(registry, bus, config)

   # Verify all started
   health = HealthAggregator(registry)
   results = await health.check_all()
   assert all(r["started"] for r in results.values())
   assert health.is_healthy()

   # Verify pipeline steps available
   steps = registry.get_pipeline_steps()
   assert len(steps) == 6

   # Graceful shutdown
   await shutdown_engines(registry)
   await bus.shutdown()
   ```

6. **Full test suite (regression):**
   ```bash
   .venv/bin/python -m pytest tests/ -q
   ```
   Expected: 673 + ~80 = ~753 passed

---

## IMPLEMENTATION_STATUS.md Updates

### Current Focus
```
**Phase:** B — Core Infrastructure
**Item:** B4 registry/ ✅ COMPLETE → Next: C1 state engine
**Status:** Engine DI, topological init, bus wiring, health aggregation. Phase B complete.
```

### Module Status Flips
| Module | From | To |
|--------|------|-----|
| Core types | 📋 stub | ✅ done (was already implemented, status doc outdated) |
| Core events | 📋 stub | ✅ done (was already implemented) |
| Core context | 📋 stub | ✅ done (was already implemented) |
| Core protocols | 📋 stub | ✅ done (was already implemented) |
| Core engine | 📋 stub | ✅ done |
| Core errors | 📋 stub | ✅ done |
| Registry — registry | 📋 stub | ✅ done |
| Registry — wiring | 📋 stub | ✅ done |
| Registry — composition | 📋 stub | ✅ done |
| Registry — health | 📋 stub | ✅ done |

### Session Log Entry
```
### Session 2026-03-21 — B4: Registry Module
- **Implemented:** EngineRegistry (8 methods incl. Kahn's topo sort), HealthAggregator (4 methods),
  wire_engines + shutdown_engines + inject_dependencies, create_default_registry (composition root),
  BaseEngine lifecycle (12 methods), error constructors (4 classes)
- **Also implemented:** All core/ test stubs (types, events, context, protocols, engine, errors)
- **Key decisions:**
  - Kahn's algorithm with sorted queues for deterministic topo ordering
  - shutdown_engines stops in reverse topo order (dependents first)
  - Composition root uses lazy imports inside function body
  - _dependencies dict set on engine by inject_dependencies (not constructor injection)
  - HealthAggregator.is_healthy() is sync (reads cache from last check_all)
- **Tests:** ~80 new tests across 10 test files
- **Phase B COMPLETE.** All 4 foundation + 4 infrastructure modules done.
- **Next:** C1 (state engine — first vertical slice)
```
