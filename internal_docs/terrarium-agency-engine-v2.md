# Terrarium — AgencyEngine Implementation Spec (v2)

**Purpose:** Make internal actors alive. Modification to existing Terrarium infrastructure, not a rewrite.

**Key constraint:** Terrarium is domain-agnostic. A world can be a support org with 50 customers, a social network with 1000 users, a web browsing environment with zero human actors (where "actors" are web pages, APIs, and services), or anything else. Nothing in this spec assumes a specific domain.

---

## Current State → Target State

**Today:**
- External agents connect via MCP/HTTP, act through the 7-step pipeline
- Internal actors are static personas with no decisions, no state, no interactions
- Animator makes one LLM call per tick generating 3-5 generic events
- Single external agent assumed

**Target:**
- Multiple external agents can connect simultaneously
- Internal actors are autonomous — they observe, decide, and act
- All actors (external and internal) go through the same pipeline
- Animator handles world/environment events only, not actor behavior
- The system is explicitly multi-agent

---

## Architecture

```
Sources (produce ActionEnvelopes):
┌──────────────┐  ┌──────────────┐  ┌──────────────┐
│  External    │  │   Agency     │  │  Animator    │
│  Agent(s)    │  │   Engine     │  │              │
│              │  │              │  │  Environment │
│  MCP/HTTP    │  │  Internal    │  │  events only │
│  adapters    │  │  actors      │  │              │
└──────┬───────┘  └──────┬───────┘  └──────┬───────┘
       │                 │                 │
       │  source:        │  source:        │  source:
       │  "external"     │  "internal"     │  "environment"
       │                 │                 │
       └────────┬────────┴────────┬────────┘
                │                 │
                ▼                 ▼
        ┌─────────────────────────────┐
        │       Event Queue           │
        │    (logical time ordered)   │
        └──────────────┬──────────────┘
                       │
                       ▼
        ┌─────────────────────────────┐
        │     7-Step Pipeline         │
        │  (unchanged — one law)      │
        └──────────────┬──────────────┘
                       │
                       ▼
        ┌─────────────────────────────┐
        │     State Engine            │
        │  (unchanged — SQLite)       │
        └─────────────────────────────┘
```

---

## Multi-Agent Model

Terrarium is explicitly multi-agent. A world can contain any combination:

| Actor type | Description | Examples |
|-----------|------------|---------|
| **External agent** | User's AI agent connected via MCP/HTTP. One or more. Each occupies an actor slot defined in the world definition. | OpenClaw agent, Claude agent, custom Python agent |
| **Internal actor** | Autonomous LLM-driven actor living inside the world. Generated at compile time with persona and goals. Managed by AgencyEngine. | Customers, supervisors, social media users, competing sellers, reviewers |
| **Passive entity** | Not an actor — an entity in the State Engine that responds deterministically through service packs. No LLM involvement. | Web pages, API endpoints, databases, static content, form responses |
| **Environment** | The world itself. Produces events through the Animator. No persona. | Service outages, time-based triggers, demand spikes, external market events |

A world with "just Gmail and web browsing" has zero internal actors. The AgencyEngine does nothing. Web pages are passive entities served by the browser pack. The Animator might generate environment events (page content changes, new emails arrive). The external agent is the only decision-maker.

A world with "50 customers and 2 supervisors" has 52 internal actors. The AgencyEngine manages all of them. Multiple external agents might connect as support staff.

A world with "1000 social media users" has 1000 internal actors. The AgencyEngine manages all of them with heavy batching. External agents might connect as content moderators or influencers.

The architecture handles all cases because the AgencyEngine only activates when internal actors exist and have reasons to act.

---

## Base Interfaces

### ActionEnvelope

```python
@dataclass
class ActionEnvelope:
    """Universal action shape. Every action in the world is an ActionEnvelope,
    regardless of who initiates it."""
    
    envelope_id: str                        # unique ID
    actor_id: str                           # who is acting ("environment" for Animator)
    source: Literal[
        "external",                         # user's agent via MCP/HTTP
        "internal",                         # internal actor via AgencyEngine
        "environment",                      # world event via Animator
    ]
    action_type: str                        # service-specific action name
    target_service: str | None              # which service this targets (None for meta-actions)
    payload: dict                           # action parameters (service-specific)
    logical_time: float                     # ordering key for event queue
    parent_event_ids: list[str]             # causal parents
    metadata: dict                          # extensible (goal_id, urgency, batch_id, etc.)
```

### ActorState

```python
@dataclass
class ActorState:
    """Persistent state for any internal actor. Domain-agnostic — the persona
    and goal fields contain whatever the world compiler generated for this
    actor type in this specific world."""
    
    actor_id: str
    role: str                               # from world definition (e.g., "customer", "moderator", "seller")
    actor_type: Literal["external", "internal"]
    
    # Identity (generated at compile time, immutable during run)
    persona: dict                           # LLM-generated personality — structure varies by world
    
    # Goal (v1: single active goal)
    current_goal: str | None                # natural language goal description
    goal_strategy: str | None               # how the actor plans to achieve it
    
    # Reactive state (updated during simulation)
    waiting_for: WaitingFor | None
    frustration: float                      # 0.0 - 1.0
    urgency: float                          # 0.0 - 1.0
    
    # Memory
    pending_notifications: list[str]        # events affecting this actor since last activation
    recent_interactions: list[str]          # last N interaction summaries (compact)
    
    # Scheduling
    scheduled_action: ScheduledAction | None
    
    # Activation
    activation_tier: int                    # 0, 1, 2, or 3 — see Tiered Activation
    watched_entities: list[str]             # entity IDs this actor cares about


@dataclass
class WaitingFor:
    description: str
    since: float                            # logical_time
    patience: float                         # duration before frustration increases
    escalation_action: str | None           # what to do when patience runs out


@dataclass 
class ScheduledAction:
    logical_time: float
    action_type: str
    description: str
    payload: dict
```

### EventQueue

```python
class EventQueue:
    """Priority queue ordering all actions by logical time.
    The single entry point for all actions in the world."""
    
    def submit(self, envelope: ActionEnvelope) -> None:
        """Add an action to the queue."""
        ...
    
    def schedule(self, envelope: ActionEnvelope, delay: float) -> None:
        """Schedule an action for future logical time."""
        ...
    
    def process_next(self) -> WorldEvent | None:
        """Dequeue next envelope, run through pipeline, return committed event.
        After commit, notifies AgencyEngine and Animator."""
        ...
    
    def has_pending(self) -> bool:
        """Check if queue has actions to process."""
        ...
    
    @property
    def current_time(self) -> float:
        """Current logical time (advances as events are processed)."""
        ...
```

### AgencyEngine

```python
class AgencyEngine:
    """Manages internal actor lifecycle: activation, action generation, 
    state updates. Only active when the world has internal actors."""
    
    def __init__(self, actors: list[ActorState], compiler_settings: dict, 
                 event_queue: EventQueue, llm_client: LLMClient):
        ...
    
    def notify(self, committed_event: WorldEvent) -> None:
        """Called after every committed event. Determines which internal 
        actors should activate and generates their actions.
        
        Activation priority:
        1. Actors directly affected by the event (entity they watch was touched)
        2. Actors with scheduled actions now due
        3. Actors whose wait/frustration threshold crossed
        """
        ...
    
    def activate_actor(self, actor: ActorState, reason: str, 
                       trigger_event: WorldEvent | None) -> ActionEnvelope | None:
        """Generate an action for a single activated actor.
        Routes to appropriate tier (batch or individual LLM call).
        Returns None if actor decides to do nothing."""
        ...
    
    def process_batch(self, actors: list[tuple[ActorState, str]]) -> list[ActionEnvelope]:
        """Batch-generate actions for multiple low-stakes actors in one LLM call."""
        ...
    
    def update_actor_state(self, actor: ActorState, committed_event: WorldEvent) -> None:
        """Update actor's reactive state after their action is committed.
        Adjusts frustration, waiting_for, recent_interactions, scheduled_action.
        Deterministic — no LLM call."""
        ...
    
    def build_actor_prompt(self, actor: ActorState, reason: str, 
                           trigger_event: WorldEvent | None) -> str:
        """Build LLM prompt for action generation.
        Includes: actor persona, current state, trigger context, 
        available actions (from service packs), world brief.
        Domain-agnostic — works for any actor in any world."""
        ...


class ActorPromptBuilder:
    """Builds LLM prompts for actor action generation. 
    Domain-agnostic — assembles from actor state + world context + service capabilities.
    
    The compiler settings (reality dimensions, behavior mode, etc.) are already
    part of the world's system prompt context established during compilation.
    This builder adds actor-specific context on top."""
    
    def build_individual_prompt(self, actor: ActorState, 
                                trigger: WorldEvent | None,
                                available_actions: list[dict],
                                world_context: str) -> str:
        """Build prompt for a single actor's action generation.
        
        Structure:
        - Actor identity (persona, role — from ActorState)
        - Current state (goal, waiting_for, frustration, recent interactions)
        - Trigger (what just happened that activated this actor)
        - Available actions (what this actor CAN do — from service packs + permissions)
        - Output schema (action_type, target_service, payload, state_updates)
        """
        ...
    
    def build_batch_prompt(self, actors: list[tuple[ActorState, WorldEvent | None]],
                           available_actions: list[dict],
                           world_context: str) -> str:
        """Build prompt for batch action generation of multiple actors.
        Same structure as individual but with multiple actors in one prompt."""
        ...
```

### Animator (Refactored)

```python
class Animator:
    """Generates world/environment events. NOT per-actor behavior.
    
    Responsibilities:
    - Service reliability events (outages, degradation, timeouts)
    - Demand events (new entities appearing — new tickets, new posts, new listings)
    - Time-based events (shift changes, peak hours, deadlines)
    - External environment events (market changes, policy announcements)
    
    Guided by compiler settings (reality dimensions, behavior mode).
    Does NOT generate actions for any specific actor — that's AgencyEngine's job.
    """
    
    def __init__(self, compiler_settings: dict, event_queue: EventQueue, 
                 llm_client: LLMClient):
        ...
    
    def notify(self, committed_event: WorldEvent) -> None:
        """Called after every committed event. May generate environment events 
        in response to world state changes."""
        ...
    
    def check_scheduled_events(self, current_time: float) -> list[ActionEnvelope]:
        """Check for time-based environment events that are due."""
        ...
    
    def generate_environment_event(self, trigger: str) -> ActionEnvelope | None:
        """Generate a world-level event. Returns envelope with source='environment'.
        May use LLM for content generation, guided by compiler settings."""
        ...
```

---

## Tiered Activation Model

Not every actor needs an LLM call. The tier determines how an actor is processed when activated.

### Tier 0: Inactive

Actor has no reason to act. No computation at all. This is the default state for most actors most of the time.

**Check cost:** Zero. Actor is not evaluated.

### Tier 1: Deterministic Check (no LLM)

A fast rule-based check determines IF the actor should activate. Runs in microseconds.

**Triggers (v1 — exhaustive list):**
- **Event-affected:** A committed event touched an entity this actor watches (checked via `watched_entities`)
- **Scheduled:** Actor's `scheduled_action.logical_time` has arrived
- **Wait-threshold:** Actor's `waiting_for` patience has expired
- **Frustration-threshold:** Actor's `frustration` crossed an escalation threshold

**Check cost:** Pure Python, no LLM. O(1) per actor per trigger check.

**Output:** Actor either stays at Tier 0 (no reason to act) or escalates to Tier 2 or Tier 3.

### Tier 2: Batch LLM Generation

Multiple activated actors with similar context are batched into a single LLM call. The LLM generates actions for all of them at once.

**When to use:** Actor is activated but the situation is routine — a patient customer checking ticket status, a user scrolling their feed, a seller updating a listing.

**Classification rule (v1):**
```
If actor.frustration > 0.7       → Tier 3
If actor.role in high_stakes_roles → Tier 3  (roles from world definition)
If "adversarial" in actor.persona → Tier 3
If trigger == "threshold_crossed" → Tier 3
Else                              → Tier 2
```

`high_stakes_roles` is extracted from the world definition — any role with approval authority, escalation power, or governance responsibilities.

**LLM cost:** One call per batch (batch size configurable, default ~5 actors per call).

### Tier 3: Individual LLM Generation

Dedicated LLM call for a single actor in a critical or complex situation.

**When to use:** High frustration, authority decisions, adversarial behavior, escalation moments, any situation where response quality matters and context is nuanced.

**LLM cost:** One call per actor.

### Activation Flow

```
Committed Event arrives
        │
        ▼
┌─ Tier 1: Deterministic Check ───────────────────────┐
│                                                      │
│  For each actor in world:                            │
│    Does this event affect an entity they watch?      │
│    Is their scheduled action due?                    │
│    Has their wait patience expired?                  │
│    Has their frustration crossed threshold?           │
│                                                      │
│  Result: list of activated actors with reasons       │
│  Cost: microseconds, no LLM                          │
└──────────────────────┬───────────────────────────────┘
                       │
                       ▼
┌─ Classify: Tier 2 or Tier 3 ────────────────────────┐
│                                                      │
│  For each activated actor:                           │
│    High-stakes? → Tier 3 (individual)                │
│    Routine?     → Tier 2 (batch)                     │
│                                                      │
└──────────┬───────────────────────┬───────────────────┘
           │                       │
           ▼                       ▼
┌─ Tier 2: Batch LLM ──┐  ┌─ Tier 3: Individual LLM ─┐
│                       │  │                           │
│  Group similar actors │  │  One LLM call per actor   │
│  One LLM call per     │  │  Full context:            │
│  batch (~5 actors)    │  │    persona + state +      │
│                       │  │    trigger + available     │
│  Returns: action per  │  │    actions + world brief  │
│  actor (or do_nothing)│  │                           │
└───────────┬───────────┘  └─────────────┬─────────────┘
            │                            │
            └──────────┬─────────────────┘
                       │
                       ▼
            ActionEnvelopes submitted
            to Event Queue
```

### Scaling Math

| World size | Active per event (typical) | Tier 2 batches | Tier 3 individual | Total LLM calls |
|-----------|---------------------------|----------------|-------------------|-----------------|
| 0 actors (services only) | 0 | 0 | 0 | 0 |
| 10 actors | 1-3 | 0-1 | 0-1 | 0-2 |
| 50 actors | 3-8 | 1-2 | 1-2 | 2-4 |
| 200 actors | 5-15 | 2-3 | 2-4 | 4-7 |
| 1000 actors | 10-30 | 3-6 | 3-5 | 6-11 |

Most actors are Tier 0 (inactive) most of the time. The system only spends LLM calls on actors who have a reason to act right now.

---

## Prompt Architecture

The compiler settings (reality dimensions, behavior mode, world brief) are already established in the world's system prompt during compilation. The AgencyEngine does NOT re-inject them per actor.

**Prompt layering:**

| Layer | Set when | Contains | Changes per actor? |
|-------|----------|----------|-------------------|
| **World system prompt** | Compilation | World description, reality dimensions, behavior mode, governance rules, world brief | No — shared across all LLM calls in this world |
| **Service context** | Compilation | Available services, their schemas, available actions | No — shared |
| **Actor context** | Per activation | This actor's persona, current state, goal, frustration, recent interactions, pending notifications | Yes — unique per actor |
| **Trigger context** | Per activation | What just happened that activated this actor, the committed event details | Yes — unique per activation |
| **Output schema** | Fixed | Expected JSON response format for action generation | No — fixed |

The ActorPromptBuilder assembles layers 3-4 (actor + trigger context) and sends them as user messages against the already-established world system prompt. This means:

- The LLM already knows what kind of world this is (from system prompt)
- The LLM already knows the reality dimensions and behavior mode
- The per-actor prompt only needs to provide: who is this actor, what's their state, what just happened, what can they do
- This keeps per-actor prompts compact and reduces token cost

---

## Replay and Recording

```python
@dataclass
class ReplayEntry:
    """Records everything needed for exact replay of one action."""
    
    logical_time: float
    envelope: ActionEnvelope
    activation_reason: str              # "event_affected" | "scheduled" | "threshold" | "external"
    activation_tier: int                # 0, 1, 2, or 3
    llm_prompt: str | None              # None for external agents and Tier 0/1
    llm_output: str | None              # None for external agents and Tier 0/1
    pipeline_result: WorldEvent
    actor_state_after: dict | None      # None for external agents and environment


class ReplayLog:
    """Records all decisions for exact replay."""
    
    def record(self, entry: ReplayEntry) -> None: ...
    
    def replay_mode(self) -> bool: ...
    
    def get_recorded_output(self, logical_time: float, actor_id: str) -> str | None:
        """In replay mode, return the recorded LLM output instead of calling LLM."""
        ...
```

**Seed** gives approximate reproducibility (similar world generation). **ReplayLog** gives exact reproducibility (identical event sequence).

---

## Integration Points with Existing Infrastructure

### Unchanged

| Component | Status |
|-----------|--------|
| State Engine (SQLite + snapshot) | Unchanged |
| Service packs (Tier 1 / Tier 2) | Unchanged |
| World definition YAML | Unchanged |
| Compiler settings YAML | Unchanged |
| 7-step pipeline logic | Unchanged (new input shape, same logic) |
| Governance scorecard | Unchanged |
| Report generation | Unchanged |
| Dashboard event model | Unchanged (new `source` field on WorldEvent) |

### Modified

| Component | Change |
|-----------|--------|
| **Pipeline entry** | Accepts `ActionEnvelope` instead of raw tool calls |
| **MCP adapter** | Wraps incoming MCP tool calls as `ActionEnvelope(source="external")` |
| **HTTP adapter** | Wraps incoming HTTP requests as `ActionEnvelope(source="external")` |
| **WorldEvent** | Add `source` field: `"external"` / `"internal"` / `"environment"` |
| **World compilation** | Generate `ActorState` for each internal actor (persona + goal + waiting_for + frustration + scheduled_action) |
| **Animator** | Strip per-actor behavior. Keep environment events only. Produce `ActionEnvelope(source="environment")` |

### New

| Component | Description |
|-----------|-------------|
| `ActionEnvelope` | Universal action shape |
| `EventQueue` | Priority queue with logical time |
| `AgencyEngine` | Actor activation + action generation |
| `ActorState` | Per-actor persistent state |
| `ActorPromptBuilder` | Assembles actor-specific prompts against world system prompt |
| `ReplayLog` | Records all decisions for exact replay |

---

## The Simulation Loop

```
1. World compiled
   → State Engine initialized with all entities
   → ActorState created for each internal actor
   → Initial scheduled actions set (from compile-time generation)
   → World system prompt established (dimensions, services, governance)

2. Simulation starts → Event Queue begins processing

3. Loop:
   a. Animator checks for due environment events → submits envelopes
   b. AgencyEngine checks for due scheduled actor actions → submits envelopes
   c. External agent actions arrive via MCP/HTTP → adapter submits envelopes
   
   d. Event Queue dequeues next envelope (lowest logical_time)
      → 7-step pipeline processes it
      → State Engine commits
      → WorldEvent recorded + broadcast to dashboard
   
   e. AgencyEngine.notify(committed_event):
      → Tier 1: deterministic check — find affected actors
      → Classify activated actors into Tier 2 (batch) or Tier 3 (individual)
      → Generate actions via LLM
      → Submit new envelopes to Event Queue
   
   f. Animator.notify(committed_event):
      → Check if world should react (service degradation, demand, etc.)
      → Submit environment envelopes if needed
   
   g. Actor states updated (frustration, waiting_for, memory — deterministic)
   h. ReplayLog records everything
   
   i. Repeat from (a)

4. Simulation ends when:
   → All external agents disconnect
   → All budgets exhausted
   → Mission completed (if defined)
   → Manual stop
   → Max logical time reached
   → Event queue empty and no scheduled future events
```

---
Implementation notes:

1. Normalize actor traits outside persona 

Right now Tier 2/3 routing uses checks like “if adversarial in actor.persona,” but persona is intentionally world-specific and unstructured. That will get messy fast.
Freeze a small normalized actor-behavior block, for example:

cooperation_level
deception_risk
authority_level
stakes_level
ambient_activity_rate

Keep persona freeform for realism, but make routing depend on structured fields.

2. Define tie-breaking in the event queue

You have logical_time, but if multiple envelopes share the same time, you still need deterministic ordering.
Freeze one rule like:
(logical_time, priority, source_order, actor_id, envelope_id)

Without that, exact replay will drift.

3. Rewrite the “world system prompt established during compilation” wording

Conceptually it is right, but implementation-wise it is too fuzzy.
Freeze this instead:

Compilation produces a canonical world prompt/context bundle. Each Agency/Animator LLM call reuses that bundle, plus actor/trigger context.

That works across providers and avoids pretending the model has persistent server-side memory.

4. Add runaway-loop limits

This is the one important missing safety rail.
You need hard caps like:

max envelopes generated from one committed event
max actions per actor per logical-time window
max environment reactions per logical-time window
loop breaker if AgencyEngine and Animator keep bouncing off each other

Otherwise a lively world can spiral.

5. Freeze external-agent slot binding

The spec says multiple external agents can connect and occupy actor slots, which is good, but the binding rules need to be explicit:

how an agent claims a slot
what happens if two try to claim the same slot
what permissions/capabilities come from the slot
whether reconnect resumes the same slot

That should be nailed before backend work starts.

One smaller note: the browsing case is covered well enough for now. Passive entities can be web pages and APIs, and browsing worlds with zero human actors are explicitly supported. That’s good. Later you’ll still need richer browser/world packs, but the architecture doesn’t block that.

## v1 Scope

### Ship

- ActionEnvelope as universal action shape
- EventQueue with logical time ordering
- AgencyEngine with event-first activation (event-affected, scheduled, threshold)
- Tiered action generation (Tier 1 check → Tier 2 batch → Tier 3 individual)
- ActorState (persona, goal, waiting_for, frustration, recent_interactions, scheduled_action)
- ActorPromptBuilder (domain-agnostic prompt assembly)
- Animator refactored to environment-only
- ReplayLog for exact replay
- Multi-agent support (multiple external + multiple internal)

### Follow ups after the the V1 scope 

- Ambient random activity (no-trigger activation)
- Multi-goal planning per actor
- Actor learning across runs
- Actor coordination / alliance formation
- Population scale beyond ~100 internal actors
