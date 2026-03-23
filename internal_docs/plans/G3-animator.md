# Phase G3: World Animator + Shared Scheduler

## Context

The world compiles, generates entities, agents connect, governance enforces — but the world is DEAD between agent turns. The Animator makes it alive. This plan also addresses the scheduler as a separate reusable module.

## Answering All Questions First

### Q1: How are compiler presets (ideal/messy/hostile) used by the Animator?

The compiler presets set `WorldConditions` at compilation (D4b). At RUNTIME, those same conditions are **ongoing creative direction** to the Animator's LLM (spec line 235):

> *"The dimensions are ongoing creative direction to the Animator's LLM. 'This world has somewhat_neglected information quality' is an instruction that stays active throughout the simulation."*

Concrete effect per dimension:
- `information: somewhat_neglected` → Animator generates events where data conflicts, records are outdated
- `reliability: occasionally_flaky` → Animator triggers service degradation, timeouts
- `friction: some_difficult_people` → Animator makes NPCs send uncooperative messages, ghost, stall
- `complexity: moderately_challenging` → Animator introduces ambiguous situations, contradicting info
- `boundaries: a_few_gaps` → Animator creates access control incidents

The Animator reads `WorldConditions` from the compiled `WorldPlan.conditions` — the SAME object D4b uses.

### Level 2 Per-Attribute Numbers at Runtime

The spec says (line 125): *"Numbers are intensity values (0-100) that the LLM interprets when generating **and animating** the world."*

These numbers are already resolved in `WorldConditions` via `to_dict()`:
```
information: {staleness: 30, incompleteness: 35, inconsistency: 20, noise: 30}
reliability: {failures: 20, timeouts: 15, degradation: 10}
friction:    {uncooperative: 30, deceptive: 15, hostile: 8, sophistication: "medium"}
complexity:  {ambiguity: 35, edge_cases: 25, contradictions: 15, urgency: 20, volatility: 15}
boundaries:  {access_limits: 25, rule_clarity: 30, boundary_gaps: 12}
```

**How the Animator uses them:**
- `reliability.failures: 20` → ~20% chance of service failure per tick in dynamic mode
- `reliability.degradation: 10` → ~10% chance of service degrading over time
- `friction.deceptive: 15` → ~15% of NPC-generated content contains subtle deception
- `complexity.volatility: 15` → ~15% chance of situation changing while agent acts
- `boundaries.boundary_gaps: 12` → ~12% chance of access control incident

The Animator passes BOTH `reality_summary` (narrative for LLM) AND `reality_dimensions` (numbers for probabilistic decisions in the scheduler) to its components. The scheduler layer can use numbers for deterministic probability checks; the generator layer passes them to the LLM as context.

`ConditionExpander.build_prompt_context()` already returns both — we REUSE it, no duplication.

### Q2: Framework reuse — are we duplicating?

**NO duplication.** The Animator REUSES existing frameworks:

| Framework | Used by D4b (compilation) | Used by Animator (runtime) |
|-----------|--------------------------|---------------------------|
| `ConditionExpander.build_prompt_context()` | Entity generation context | Organic event generation context |
| `PromptTemplate` framework | ENTITY_GENERATION, PERSONALITY_BATCH templates | New ANIMATOR_EVENT template |
| `app.handle_action()` | Not used | Every animator event goes through pipeline |
| `ActorRegistry` | Actor generation | Actor personality lookups for NPC behavior |
| `StateEngine.query_entities()` | Population | World state reads for context |
| `SchemaValidator` | Entity validation | Event validation through pipeline |

The Animator does NOT rebuild context assembly. It uses `ConditionExpander.build_prompt_context()` directly — same function, same output format.

### Q3: Scheduler — why inside Animator? Shouldn't it be separate?

**You're right — separate module.** The scheduler is needed by:
- **Animator** — SLA timers, queue aging, scheduled NPC checks
- **Policy Engine** — hold approval timeouts
- **World Responder** — delivery delays (`schedule_event()` in spec)
- **Budget Engine** — periodic budget reports
- **Future engines** — shift handoffs, end-of-day summaries

A `terrarium/scheduling/` module with a `WorldScheduler` that any engine can register events with. The Animator owns the TICK LOOP but the scheduler is independent.

---

## Architecture

```
┌──────────────────────────────────────────┐
│  terrarium/scheduling/                    │  ← NEW shared module
│  WorldScheduler                          │
│    register_event(time, event_def)       │
│    register_recurring(interval, event)   │
│    register_trigger(condition, event)    │
│    get_due_events(world_time)            │
│    advance_time(world_time)              │
│                                          │
│  Used by: Animator, Policy, Responder    │
└──────────────┬───────────────────────────┘
               │
┌──────────────┴───────────────────────────┐
│  engines/animator/                        │
│  WorldAnimatorEngine                     │
│    configure(plan)                        │
│    tick(world_time) ──┬── scheduler.get_due_events()     (Layer 1: deterministic)
│                       └── generator.generate()            (Layer 2: LLM organic)
│    Each event → app.handle_action() → 7-step pipeline    │
│                                          │
│  Behavior modes:                         │
│    static  → tick() returns [] (OFF)     │
│    dynamic → scheduled + organic events  │
│    reactive → events only in response    │
│                                          │
│  Reality dimensions:                     │
│    Uses ConditionExpander (D1 framework) │
│    NOT duplicated                        │
│                                          │
│  Compiler presets flow:                  │
│    ideal.yaml → WorldConditions          │
│    → build_prompt_context()              │
│    → Animator LLM prompt                 │
│    → Events shaped by world personality  │
└──────────────────────────────────────────┘
```

## Implementation

### 1. Shared Scheduler Module (`terrarium/scheduling/`)

```python
# terrarium/scheduling/scheduler.py

class WorldScheduler:
    """Shared time-based event scheduling framework.

    Any engine can register events. The Animator tick loop calls
    get_due_events() each tick to fire them.

    Event types:
    - One-shot: fire at a specific world_time
    - Recurring: fire every N seconds
    - Trigger: fire when a condition on world state is met
    """

    def __init__(self) -> None:
        self._one_shot: list[ScheduledEvent] = []    # sorted by fire_time
        self._recurring: list[RecurringEvent] = []
        self._triggers: list[TriggerEvent] = []

    def register_event(self, fire_time: datetime, event_def: dict,
                       source: str = "unknown") -> str:
        """Register a one-shot event to fire at a specific time."""
        event_id = f"sched_{uuid4().hex[:8]}"
        self._one_shot.append(ScheduledEvent(
            id=event_id, fire_time=fire_time, event_def=event_def, source=source,
        ))
        self._one_shot.sort(key=lambda e: e.fire_time)
        return event_id

    def register_recurring(self, interval_seconds: float, event_def: dict,
                           source: str = "unknown") -> str:
        """Register a recurring event that fires every N seconds."""
        ...

    def register_trigger(self, condition: str, event_def: dict,
                         source: str = "unknown") -> str:
        """Register a trigger-based event (fires when condition met)."""
        ...

    async def get_due_events(self, world_time: datetime,
                             state_engine: Any = None) -> list[dict]:
        """Return all events due at or before world_time.

        One-shot events are removed after firing.
        Recurring events are rescheduled.
        Trigger events check condition against state_engine.
        """
        due = []

        # One-shot
        while self._one_shot and self._one_shot[0].fire_time <= world_time:
            event = self._one_shot.pop(0)
            due.append(event.event_def)

        # Recurring
        for recurring in self._recurring:
            if recurring.next_fire <= world_time:
                due.append(recurring.event_def)
                recurring.next_fire += timedelta(seconds=recurring.interval_seconds)

        # Trigger-based (evaluate conditions)
        if state_engine:
            for trigger in self._triggers:
                # Use ConditionEvaluator from policy engine (REUSE)
                ...

        return due

    def cancel(self, event_id: str) -> bool:
        """Cancel a scheduled event by ID."""
        ...


@dataclass
class ScheduledEvent:
    id: str
    fire_time: datetime
    event_def: dict
    source: str

@dataclass
class RecurringEvent:
    id: str
    interval_seconds: float
    next_fire: datetime
    event_def: dict
    source: str

@dataclass
class TriggerEvent:
    id: str
    condition: str
    event_def: dict
    source: str
```

### 2. AnimatorConfig — Full YAML Support

```python
class AnimatorConfig(BaseModel):
    model_config = ConfigDict(frozen=True)

    enabled: bool = True
    creativity: str = "medium"              # low | medium | high
    event_frequency: str = "moderate"       # rare | moderate | frequent
    contextual_targeting: bool = True
    escalation_on_inaction: bool = True
    creativity_budget_per_tick: int = 3     # max organic events per tick
    tick_interval_seconds: float = 60.0
    scheduled_events: list[dict[str, Any]] = Field(default_factory=list)
```

### 3. WorldAnimatorEngine — Uses Scheduler + Generator

```python
class WorldAnimatorEngine(BaseEngine):
    """Generates autonomous world events between agent turns.

    Uses: WorldScheduler (scheduling/) for deterministic events
    Uses: OrganicGenerator (LLM) for creative events
    Uses: ConditionExpander.build_prompt_context() (D1) for reality context
    Uses: app.handle_action() for pipeline execution

    Controlled by behavior mode from WorldPlan:
    - static: OFF (tick returns [])
    - dynamic: scheduled + organic
    - reactive: events only in response to recent agent actions
    """

    async def _on_initialize(self) -> None:
        self._scheduler = None  # Set during configure()
        self._generator = None
        self._behavior = "static"
        self._conditions = None
        self._recent_actions: list[dict] = []
        self._creativity_used_this_tick = 0

    async def configure(self, plan: WorldPlan, scheduler: WorldScheduler) -> None:
        """Configure from compiled world plan. Called after generate_world()."""
        self._behavior = plan.behavior
        self._conditions = plan.conditions
        self._scheduler = scheduler

        # Register scheduled events from YAML animator settings
        for event_config in plan.animator_settings.get("scheduled_events", []):
            if "interval" in event_config:
                scheduler.register_recurring(
                    interval_seconds=_parse_duration(event_config["interval"]),
                    event_def=event_config,
                    source="animator",
                )
            elif "trigger" in event_config:
                scheduler.register_trigger(
                    condition=event_config["trigger"],
                    event_def=event_config,
                    source="animator",
                )

        # Create organic generator if LLM available and not static
        llm_router = self._config.get("_llm_router")
        if llm_router and self._behavior != "static":
            self._generator = OrganicGenerator(
                llm_router=llm_router,
                conditions=self._conditions,
                config=self._typed_config,
            )

    async def tick(self, world_time: datetime) -> list[dict]:
        """Advance one tick. Returns results of generated events."""
        if self._behavior == "static":
            return []

        results = []
        self._creativity_used_this_tick = 0

        # Layer 1: Scheduled events (deterministic, no LLM)
        state_engine = self._dependencies.get("state")
        scheduled = await self._scheduler.get_due_events(world_time, state_engine)
        for event_def in scheduled:
            result = await self._execute_event(event_def, world_time)
            results.append(result)

        # Layer 2: Organic events (LLM, within budget)
        if self._generator and self._behavior in ("dynamic", "reactive"):
            budget = self._typed_config.creativity_budget_per_tick - self._creativity_used_this_tick
            recent = self._recent_actions if self._behavior == "reactive" else None
            organic = await self._generator.generate(world_time, budget, recent)
            for event_def in organic:
                result = await self._execute_event(event_def, world_time)
                results.append(result)
                self._creativity_used_this_tick += 1

        self._recent_actions = []
        return results

    async def _execute_event(self, event_def: dict, world_time: datetime) -> dict:
        """Execute event through the 7-step pipeline via app.handle_action()."""
        app = self._config.get("_app")
        result = await app.handle_action(
            actor_id=event_def.get("actor_id", "system"),
            service_id=event_def.get("service_id", "world"),
            action=event_def.get("action", "animator_event"),
            input_data=event_def.get("input_data", {}),
            world_time=world_time,
        )

        # Publish AnimatorEvent
        await self.publish(AnimatorEvent(
            event_type=f"animator.{event_def.get('action', 'event')}",
            timestamp=Timestamp(world_time=world_time, wall_time=datetime.now(tz=timezone.utc), tick=0),
            sub_type=event_def.get("sub_type", "organic"),
            actor_id=ActorId(event_def.get("actor_id", "system")),
            content=event_def,
        ))
        return result

    async def _handle_event(self, event: Event) -> None:
        """Track recent agent actions for reactive mode."""
        if self._behavior == "reactive" and hasattr(event, "action"):
            self._recent_actions.append({
                "action": event.action,
                "actor_id": str(getattr(event, "actor_id", "")),
                "event_type": event.event_type,
            })
```

### 4. AnimatorContext — Runtime Equivalent of WorldGenerationContext

The Animator REUSES `WorldGenerationContext` pattern — NOT a new context assembly:

```python
# terrarium/engines/animator/context.py

class AnimatorContext:
    """Runtime context for the Animator — mirrors WorldGenerationContext pattern.

    REUSES: ConditionExpander.build_prompt_context() (same as D4b)
    REUSES: WorldPlan fields (same as D4b)
    Adds: runtime state snapshot, recent actions, tick info

    Built ONCE when animator is configured, updated each tick.
    """

    def __init__(self, plan: WorldPlan) -> None:
        # REUSE the SAME context builder as D4b
        from terrarium.engines.world_compiler.generation_context import (
            WorldGenerationContext, BEHAVIOR_DESCRIPTIONS,
        )

        # Build base context using the SAME framework as D4b
        self._base = WorldGenerationContext(plan)

        # Extract per-attribute numbers (Level 2) for probabilistic decisions
        self.dimension_values: dict[str, dict] = {}
        for dim_name in ["information", "reliability", "friction", "complexity", "boundaries"]:
            dim = getattr(plan.conditions, dim_name)
            self.dimension_values[dim_name] = dim.to_dict()

        # Expose base context fields
        self.reality_summary = self._base.reality_summary
        self.dimensions = self._base.dimensions
        self.behavior = self._base.behavior
        self.behavior_description = self._base.behavior_description
        self.domain = self._base.domain

    def for_organic_generation(self, recent_actions: list[dict] | None = None) -> dict[str, str]:
        """Variables for ANIMATOR_EVENT template — includes per-attribute numbers."""
        return {
            "reality_summary": self.reality_summary,
            "reality_dimensions": json.dumps(self.dimensions, indent=2),
            "behavior_mode": self.behavior,
            "behavior_description": self.behavior_description,
            "domain_description": self.domain,
        }

    def get_probability(self, dimension: str, attribute: str) -> float:
        """Get a per-attribute intensity as a probability (0.0-1.0).

        Used by the scheduler for probabilistic decisions:
        - reliability.failures=20 → 0.20 (20% chance per tick)
        - friction.deceptive=15 → 0.15
        """
        dim_vals = self.dimension_values.get(dimension, {})
        raw = dim_vals.get(attribute, 0)
        if isinstance(raw, (int, float)):
            return raw / 100.0
        return 0.0
```

### 5. OrganicGenerator — Uses AnimatorContext

```python
class OrganicGenerator:
    """LLM-driven organic event generation.

    REUSES: AnimatorContext (which reuses WorldGenerationContext pattern)
    REUSES: PromptTemplate framework — ANIMATOR_EVENT template
    NO DUPLICATION of context assembly.
    """

    def __init__(self, llm_router, context: AnimatorContext, config: AnimatorConfig) -> None:
        self._router = llm_router
        self._context = context  # AnimatorContext — NOT rebuilt each call
        self._config = config

    async def generate(self, world_time: datetime, budget: int,
                       recent_actions: list[dict] | None = None) -> list[dict]:
        if budget <= 0:
            return []

        # Get template variables from AnimatorContext (NOT rebuilding)
        base_vars = self._context.for_organic_generation(recent_actions)

        response = await ANIMATOR_EVENT.execute(
            self._router,
            **base_vars,
            creativity=self._config.creativity,
            event_frequency=self._config.event_frequency,
            escalation_on_inaction=str(self._config.escalation_on_inaction),
            recent_actions=json.dumps(recent_actions or [], default=str)[:1000],
            budget=str(budget),
        )

        parsed = ANIMATOR_EVENT.parse_json_response(response)
        events = parsed if isinstance(parsed, list) else [parsed]
        return events[:budget]
```

### 6. Scheduler Uses Per-Attribute Numbers for Probabilistic Events

```python
# In WorldScheduler or within the Animator's tick():

async def _generate_probabilistic_events(self, context: AnimatorContext,
                                          world_time: datetime) -> list[dict]:
    """Generate deterministic probabilistic events based on Level 2 numbers.

    These are NOT LLM-generated — they're probability checks against
    the per-attribute intensity values from the compiler YAML.
    """
    events = []
    rng = random.Random(hash(world_time.isoformat()))  # Seeded for reproducibility

    # Reliability: service failures
    failure_prob = context.get_probability("reliability", "failures")
    if rng.random() < failure_prob:
        events.append({
            "actor_id": "system",
            "service_id": "world",
            "action": "service_degradation",
            "input_data": {"type": "failure", "probability": failure_prob},
            "sub_type": "scheduled",
        })

    # Reliability: service degradation over time
    degradation_prob = context.get_probability("reliability", "degradation")
    if rng.random() < degradation_prob:
        events.append({
            "actor_id": "system",
            "service_id": "world",
            "action": "service_degradation",
            "input_data": {"type": "degradation", "probability": degradation_prob},
            "sub_type": "scheduled",
        })

    # Complexity: volatility (situation changes)
    volatility_prob = context.get_probability("complexity", "volatility")
    if rng.random() < volatility_prob:
        events.append({
            "actor_id": "system",
            "service_id": "world",
            "action": "situation_change",
            "input_data": {"type": "volatility", "probability": volatility_prob},
            "sub_type": "scheduled",
        })

    # Boundaries: access control incidents
    gaps_prob = context.get_probability("boundaries", "boundary_gaps")
    if rng.random() < gaps_prob:
        events.append({
            "actor_id": "system",
            "service_id": "world",
            "action": "access_incident",
            "input_data": {"type": "boundary_gap", "probability": gaps_prob},
            "sub_type": "scheduled",
        })

    return events
```

### 7. Updated WorldAnimatorEngine.tick() — Uses AnimatorContext + Numbers

```python
async def tick(self, world_time: datetime) -> list[dict]:
    if self._behavior == "static":
        return []

    results = []
    self._creativity_used_this_tick = 0

    # Layer 1a: Time-based scheduled events (from YAML scheduled_events)
    state_engine = self._dependencies.get("state")
    scheduled = await self._scheduler.get_due_events(world_time, state_engine)
    for event_def in scheduled:
        result = await self._execute_event(event_def, world_time)
        results.append(result)

    # Layer 1b: Probabilistic events from per-attribute numbers
    # Uses Level 2 compiler YAML numbers: reliability.failures=20 → 20% chance
    probabilistic = await self._generate_probabilistic_events(self._context, world_time)
    for event_def in probabilistic:
        result = await self._execute_event(event_def, world_time)
        results.append(result)

    # Layer 2: Organic events (LLM, within creativity budget)
    if self._generator and self._behavior in ("dynamic", "reactive"):
        budget = self._typed_config.creativity_budget_per_tick - self._creativity_used_this_tick
        recent = self._recent_actions if self._behavior == "reactive" else None
        organic = await self._generator.generate(world_time, budget, recent)
        for event_def in organic:
            result = await self._execute_event(event_def, world_time)
            results.append(result)
            self._creativity_used_this_tick += 1

    self._recent_actions = []
    return results
```

### 5. ANIMATOR_EVENT PromptTemplate

Added to `prompt_templates.py` — uses the SAME template framework as D4b:

```python
ANIMATOR_EVENT = PromptTemplate(
    system="""You are the World Animator for a Terrarium simulation.
Generate organic world events that happen between agent turns.

## World Reality (ongoing creative direction)
{reality_summary}

## Recent Agent Actions
{recent_actions}

## Animator Settings
Creativity: {creativity}, Frequency: {event_frequency}
Escalation on inaction: {escalation_on_inaction}

## Rules
- Generate up to {budget} events as a JSON array
- Each event: {{"actor_id": "npc_id", "service_id": "service", "action": "tool_name", "input_data": {{...}}, "sub_type": "organic"}}
- Events must use actors and services that exist in the world
- Reality dimensions shape what happens (messy = things go wrong, hostile = active opposition)
- Events go through the governance pipeline — they CAN be blocked by policies

Output ONLY valid JSON array.""",

    user="Generate up to {budget} world events.",
    engine_name="animator",
    use_case="default",
)
```

### 6. Wiring

In `app.py`:
```python
# Create shared scheduler
from terrarium.scheduling.scheduler import WorldScheduler
self._scheduler = WorldScheduler()

# Wire animator
animator = self._registry.get("animator")
animator._config["_app"] = self
animator._config["_actor_registry"] = actor_registry
```

In `configure_governance()` or after `generate_world()`:
```python
animator = self._registry.get("animator")
await animator.configure(plan, self._scheduler)
```

## Files to Create/Modify

| File | Action |
|------|--------|
| `terrarium/scheduling/__init__.py` | **CREATE** — module |
| `terrarium/scheduling/scheduler.py` | **CREATE** — WorldScheduler framework |
| `terrarium/scheduling/config.py` | **CREATE** — SchedulerConfig if needed |
| `engines/animator/config.py` | **REWRITE** — full YAML settings |
| `engines/animator/engine.py` | **REWRITE** — real tick(), configure(), modes, probabilistic events |
| `engines/animator/context.py` | **CREATE** — AnimatorContext (reuses WorldGenerationContext pattern) |
| `engines/animator/scheduler.py` | **DELETE** — replaced by scheduling/ module |
| `engines/animator/generator.py` | **REWRITE** — LLM organic generation using AnimatorContext |
| `engines/world_compiler/prompt_templates.py` | **UPDATE** — add ANIMATOR_EVENT |
| `app.py` | **UPDATE** — create scheduler, wire animator |
| `tests/scheduling/test_scheduler.py` | **CREATE** |
| `tests/engines/animator/test_engine.py` | **REWRITE** |
| `tests/engines/animator/test_generator.py` | **CREATE** |
| `tests/integration/test_simulation_loop.py` | **CREATE** |

## Verification

1. `pytest tests/ -q` — all pass
2. Static mode: `animator.tick()` returns []
3. Dynamic mode: scheduled + organic events generated
4. Reactive mode: events only when recent_actions exist
5. Reality dimensions shape organic events (visible in output)
6. Events go through pipeline (visible in ledger as PipelineStepEntries)
7. Scheduler usable by other engines (register_event from Policy Engine)
8. Creativity budget enforced
9. `grep -rn "..." terrarium/engines/animator/` — ZERO stubs

## Post-Implementation
1. Save plan to `internal_docs/plans/G3-animator.md`
2. Update IMPLEMENTATION_STATUS.md
3. Principal engineer review
