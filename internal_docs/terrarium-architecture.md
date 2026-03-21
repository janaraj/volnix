# Terrarium — World Generation Architecture

## The Core Problem

Terrarium promises programmable worlds for AI agents. But the internet has thousands of services, each with hundreds of endpoints, edge cases, and behavioral quirks. No team can hand-build simulations for all of them. No community can either — not fast enough to matter.

The architecture must solve this: **how does Terrarium generate realistic, stateful, causally consistent worlds for arbitrary services without requiring hand-built simulators for each one?**

The answer is a separation of concerns that has not been attempted before: **the engine enforces the laws of the world; generative models author and animate the world's content.** Neither can do the other's job. Together, they produce something neither could alone — a world that is both creative and trustworthy.

---

## The Two Halves

### World Law (Deterministic Engine)

The engine is the source of truth. It owns:

- **State storage** — every entity, relationship, and property, versioned and persistent
- **Event log** — every mutation is an event with actor, timestamp, cause, and effects
- **Causal graph** — directed graph of what caused what, traceable in both directions
- **Permissions** — which actor can see/do what, enforced before any action executes
- **Policy enforcement** — rules that gate, block, or redirect actions based on world state
- **Budget accounting** — resource tracking per actor, deterministic math
- **Time** — simulated clock, controllable speed, SLA and deadline tracking
- **Visibility** — each actor's view of the world, filtered by role and scope
- **Mutation validation** — proposed state changes checked for consistency before commit
- **Replay / Fork / Diff** — snapshot at any point, branch into parallel timelines, compare
- **Governance scoring** — derived from recorded events, not from model judgment

The engine never guesses. It never generates text. It never decides what a service "would probably do." It enforces structure.

### World Content (Generative Layer)

The generative layer creates everything the engine doesn't: realistic data, service behavior, human actor responses, scenario complications, and the texture that makes a world feel alive.

But it operates **inside constraints set by the engine**. The generative layer proposes; the engine disposes. A generated response that violates state consistency is rejected. A generated event that breaks permissions is blocked. A generated mutation that exceeds budget is denied.

This separation is what makes the world both rich and trustworthy.

---

## Three Generation Phases

World generation is not one problem. It is three distinct problems with different characteristics, different timing, and different fidelity requirements.

### Phase 1: Schema Generation

**When:** Before the world exists. During compilation from user description to world plan.

**What it produces:** For each service in the world — the tool interface (what endpoints exist, what parameters they accept, what response shapes they return), the state model (what entities the service manages, what states they can be in, what transitions are valid), and the side effect rules (what downstream consequences an action triggers).

**The question it answers:** "What does this service look like and how does it behave as a system?"

This is the phase where external knowledge sources matter most. The generative layer doesn't need to invent what Stripe looks like — that knowledge exists in API documentation, OpenAPI specifications, MCP server manifests, and curated context hubs.

**Source resolution order:**

When the world compiler encounters a service name (e.g., "Stripe"), it resolves the schema through a priority chain:

1. **Verified Pack** — Does a hand-built, fully deterministic simulation exist for this service? If yes, use it directly. No generation needed. These are Terrarium's core packs: email, chat, tickets, payments, repos, calendar.

2. **Curated Service Profile** — Does a community-curated profile exist? A profile is a structured document containing: tool definitions with parameter schemas, entity types with state machines, side effect rules, response templates, and behavioral annotations. Profiles are reviewed and versioned. They produce consistent behavior across runs.

3. **External Spec Bootstrap** — Can we find a structured specification for this service? Sources include:
   - **Context Hub** (`chub get stripe/api`) — curated API documentation optimized for LLM consumption, covering 68+ services and growing. This provides endpoint descriptions, parameter details, authentication patterns, and common gotchas.
   - **OpenAPI / Swagger specifications** — machine-readable endpoint definitions with parameter types and response schemas.
   - **MCP Server manifests** — tool definitions from the MCP Registry with input/output schemas.
   
   When an external spec is found, the generative layer transforms it into a Service Profile: parsing the API surface, inferring the state model (what entities exist, how they relate), and generating side effect rules. The output is a draft profile that can be reviewed, refined, and promoted to curated status.

4. **LLM Inference** — No structured source found. The generative layer infers the service's behavior from its general knowledge of the service. This produces a best-effort schema: plausible tool interfaces, reasonable state models, approximate behavioral rules. Explicitly labeled as lower confidence.

**This priority chain is the key architectural decision.** It means Terrarium can simulate any service on day one (via LLM inference), while progressively improving fidelity as external specs are integrated and community profiles are curated.

### Phase 2: Data Generation

**When:** During world instantiation. After schemas are resolved, before simulation starts.

**What it produces:** The seed population of the world — customer records, ticket histories, email threads, chat messages, charge records, agent profiles, and every other entity that exists when the simulation begins.

**The question it answers:** "What exists in this world at time zero?"

Data generation is a batch process that runs once per world instantiation. The generative layer creates entities with realistic details: names, dates, amounts, statuses, sentiment, history. But it operates under cross-entity consistency constraints enforced by the engine:

- A ticket references a real customer from the generated customer set
- A charge amount matches the product price and the invoice total
- An email thread references the correct ticket and customer name
- A chat message timestamps are sequentially consistent
- An SLA deadline is computed from the ticket creation time and the SLA policy

The generation flow:

1. **Entity skeleton** — Engine creates empty entity slots based on world definition (50 customers, 200 charges, 15 tickets)
2. **Content generation** — Generative layer fills in realistic details for each entity
3. **Cross-linking** — Engine establishes relationships (customer → charges, ticket → customer → email)
4. **Consistency validation** — Engine checks all cross-entity references, amounts, dates, statuses
5. **Scenario injection** — Specific pressure points are layered in (the angry VIP customer, the overdue SLA, the nearly-exhausted budget)
6. **Snapshot** — Complete initial world state is committed and becomes the replayable starting point

For reproducibility: data generation uses seeded randomness. Same seed + same world definition = same initial state. This is essential for counterfactual diffs — you must be able to replay from the same starting point.

### Phase 3: Runtime Response Generation

**When:** During simulation. Every time an agent takes an action.

**What it produces:** The world's response to an agent's action — the API response body, the state mutations, the side effects, and any organic world evolution (customer replies, supervisor responses, new complications).

**The question it answers:** "What happens when this agent does this thing in this world right now?"

This is the hot path. It runs on every agent action. It must be fast, state-consistent, and deterministic enough for replay. The runtime pipeline is a three-step sandwich:

**Step 1 — Engine Pre-check (deterministic)**
- Does this actor have permission to perform this action?
- Does the relevant policy allow it, or does it trigger a hold/escalation?
- Does the actor have sufficient budget remaining?
- Is the target entity in a valid state for this action?
- If any check fails, the engine returns the appropriate world event (policy_hold, permission_denied, budget_exhausted) without invoking the generative layer.

**Step 2 — Response Generation (fidelity-tiered)**
- **Tier 1 service (Verified Pack):** Response is computed deterministically by the pack's state machine logic. No LLM involved. Fully reproducible.
- **Tier 2 service (Curated or Bootstrapped Profile):** The profile's response template and state rules constrain the generation. The LLM fills in realistic text content within those constraints. Schema-validated. Seeded for reproducibility. Bootstrapped services (compile-time inferred) run through this same Tier 2 path using their generated profile — there is no separate Tier 3 runtime mode.

**Step 3 — Engine Post-commit (deterministic)**
- Validate proposed state mutations against schema and consistency rules
- Commit valid mutations to world state
- Propagate side effects (notifications, downstream state changes, policy triggers)
- Record complete event in causal graph (action → response → mutations → side effects)
- Update affected actors' observable state
- Deduct budget

The engine bookends every action. The generative layer never directly mutates state. It proposes; the engine validates and commits.

---

## Fidelity Tiers

Not every service in a world needs the same level of simulation fidelity. Conflating "realistic enough for a demo" with "deterministic enough for a benchmark" is a mistake. Terrarium makes fidelity explicit.

### Tier 1 — Verified

Hand-built simulation with deterministic state machines, coded response logic, and full replay stability. No LLM involved at runtime. Every run produces identical behavior for identical inputs.

**Characteristics:** Fully deterministic. Benchmark-grade. Complete state machine coverage. Coded edge cases. Validated against real service behavior.

**Source:** Built into Terrarium core by the maintainer team.

**Governance scoring:** Full confidence. Scores derived from Tier 1 interactions are authoritative.

**Examples in v1:** Email (inbox/thread/send/receive/read-unread), Chat (channels/messages/threads/visibility), Tickets (lifecycle/SLA/assignment/escalation), Payments (charges/refunds/disputes/authorization states), Repos (branches/commits/PRs/review).

### Tier 2 — Profile-Backed

Curated prompt profile with explicit schemas, state transition rules, response templates, and behavioral annotations. The LLM generates content within these constraints. Seeded for reproducibility.

**Characteristics:** Schema-constrained generation. Seeded determinism (same seed = same behavior). Reviewed by community. Versioned. Consistent enough for comparison across runs.

**Source:** Community-contributed profiles, or auto-generated from external specs (Context Hub, OpenAPI) and then reviewed.

**Governance scoring:** High confidence. Scores are meaningful but annotated with the profile version.

**Examples:** Jira, Salesforce, HubSpot, Zendesk, GitHub Actions, AWS services, Shopify. Any service with a curated profile.

### Service Bootstrapping (Compile-Time Inference)

When a user mentions a service with no Tier 1 pack or Tier 2 profile, the World Compiler bootstraps a plausible service surface at **compile time** — not at runtime. The bootstrapper uses the service name, the Semantic Kernel's category primitives, and optionally external specs (Context Hub, OpenAPI) to infer tools, schemas, state models, and behavioral rules.

The bootstrapped surface is used as a Tier 2 profile during runtime. At runtime, only Tier 1 and Tier 2 exist — there is no "Tier 3" runtime mode.

**Characteristics:** Compile-time inference. The result runs as Tier 2 (profile-constrained LLM) at runtime. Seeded for reproducibility. Labeled as bootstrapped in fidelity metadata.

**Source:** LLM inference at compile time, constrained by semantic category primitives. Optionally augmented with external API docs.

**Governance scoring:** Annotated as bootstrapped. Reports clearly mark which scores involve bootstrapped services.

**Promotion path:** After a run, bootstrapped surfaces can be captured, reviewed, and promoted to curated Tier 2 profiles or compiled into Tier 1 packs:
```bash
terrarium capture --service salesforce --run last
terrarium compile-pack --service salesforce
```

**The fidelity tier is visible everywhere.** In the world plan (so users know what they're getting), in the dashboard (so observers can assess realism), and in the run report (so governance scores are properly qualified). Bootstrapped services are clearly labeled as such within their Tier 2 designation.

---

## World Conditions (Reality System)

Terrarium worlds are not sterile test environments. They simulate the messiness of reality through **world conditions** — five universal dimensions that shape the world during compilation.

### Reality Presets

Three presets describe the nature of the world:

- **Pristine** — Perfect world. Clean data, reliable services, no threats, no ambiguity. Tests pure workflow logic.
- **Realistic** — The real world. Some stale data, occasional failures, some adversarial actors, some ambiguity. The default.
- **Harsh** — A bad day. Messy data, flaky services, frequent threats, complex situations. Stress testing.

### Five Condition Dimensions

| Dimension | What it controls | Realistic values |
|-----------|-----------------|-----------------|
| **Data Quality** | Staleness, incompleteness, inconsistency | 8%, 10%, 5% |
| **Service Reliability** | Failure rate, timeouts | 5%, 3% |
| **Situational Complexity** | Ambiguity, edge cases | 15%, 10% |
| **Adversarial Environment** | Hostile actors, injection content, sophistication | 5%, 5%, medium |
| **Boundary Security** | Auth gaps, exposed secrets | 3%, 2% |

### Two-Phase Application

Conditions are **compilation-time**, not runtime toggles:

- **Phase A (Compilation):** The compiler uses conditions to generate the world population. Stale records, adversarial actor personalities, auth gaps — all baked into entities during compilation.
- **Phase B (Runtime):** Services respond faithfully to whatever data exists. A stale customer record returns stale data because the data IS stale. The service doesn't decide "should this be stale?" — conditions shaped reality at compilation.

### Condition Overlays (Post-MVP)

As Terrarium grows, new condition dimensions are added as focused overlays — not more parameters in the base config:
- `economics` — Budget pressure, cost sensitivity
- `compliance` — Regulatory constraints, audit requirements
- `market-noise` — Signal-to-noise in data feeds
- `device-reliability` — Sensor failures, connectivity drops
- `org-politics` — Competing priorities, information hoarding

---

## The Self-Improving Loop

The architecture is designed to get better over time through four feedback mechanisms.

### Tier Promotion

A bootstrapped service that produces good results can be promoted:

1. User runs simulation with a bootstrapped Jira service
2. The agent interacts with it successfully — behavior seems realistic
3. The bootstrapped surface is captured from the run
4. A community contributor reviews and refines it into a curated Tier 2 profile
5. Future worlds with Jira use the curated profile automatically

The promotion path:
```
Bootstrapped (compile-time inference)
    → capture → review → Curated Tier 2 Profile
    → compile-pack → Tier 1 Verified Pack
```

Each step increases fidelity and determinism.

### Annotation Feedback

Inspired by Context Hub's annotation model: when an agent or user discovers that a simulated service behaves unrealistically, they can annotate the behavior. These annotations accumulate:

- "Stripe refunds don't work this way — real Stripe requires the charge to be less than 180 days old"
- "Jira ticket transitions should require the assignee to be in the right project role"
- "Slack channels can't be created by guests"

Annotations feed back into profiles. Profile maintainers incorporate corrections. The simulated services become more realistic over time without anyone needing to rewrite code.

### Cross-Simulation Learning

When thousands of simulations run across the Terrarium ecosystem, patterns emerge:

- Which services are most commonly requested? (Prioritize profile creation)
- Which bootstrapped services produce the most agent confusion? (These need curated profiles urgently)
- Which Tier 2 profiles produce governance scores most similar to real-world deployment results? (These are candidates for Tier 1 promotion)
- Which chaos rules produce the most interesting agent failures? (Share these as scenario templates)

This is aggregate intelligence — not individual user data, but ecosystem-level signals about where simulation quality matters most.

### External Source Sync

As external knowledge sources (Context Hub, OpenAPI specs, MCP Registry) update, Terrarium profiles can auto-detect drift:

- A new version of the Stripe API is documented in Context Hub
- Terrarium detects that its Stripe profile references deprecated endpoints
- A sync job proposes profile updates
- A maintainer reviews and approves

This keeps profiles current without requiring manual tracking of every API changelog.

---

## End-to-End Architecture

The complete system, from user intent to run report:

```
USER INPUT
"Support team with Slack, Gmail, Stripe, 50 customers..."
│
▼
┌─────────────────────────────────────────────────────────────┐
│                    WORLD COMPILER                            │
│                                                             │
│  ┌─────────────────────────────────────────────────────┐    │
│  │ PHASE 1: SCHEMA RESOLUTION                          │    │
│  │                                                     │    │
│  │  Slack  → Verified Pack found       → Tier 1 ✓     │    │
│  │  Gmail  → Verified Pack found       → Tier 1 ✓     │    │
│  │  Stripe → Context Hub docs found    → Tier 2 ~     │    │
│  │           + OpenAPI spec available                  │    │
│  │           → Generate Service Profile               │    │
│  │                                                     │    │
│  │  Output: Service schemas with fidelity annotations  │    │
│  └─────────────────────────────────────────────────────┘    │
│                         │                                   │
│                         ▼                                   │
│  ┌─────────────────────────────────────────────────────┐    │
│  │ PHASE 2: WORLD POPULATION                           │    │
│  │                                                     │    │
│  │  Generate 50 customers (names, histories, sentiment)│    │
│  │  Generate 200 charges (amounts, dates, statuses)    │    │
│  │  Generate 15 tickets (subjects, priorities, SLAs)   │    │
│  │  Generate email threads, chat history               │    │
│  │  Cross-link all entities                            │    │
│  │  Inject scenario pressure points                    │    │
│  │  Validate consistency                               │    │
│  │  Seed for reproducibility                           │    │
│  │                                                     │    │
│  │  Output: Complete initial world state               │    │
│  └─────────────────────────────────────────────────────┘    │
│                         │                                   │
│                         ▼                                   │
│  ┌─────────────────────────────────────────────────────┐    │
│  │ PHASE 3: PLAN REVIEW                                │    │
│  │                                                     │    │
│  │  Present compiled world plan to user:               │    │
│  │   Services: 3 (2 verified, 1 profiled)              │    │
│  │   Actors: 4 (2 agents, 1 supervisor, 1 finance)    │    │
│  │   Entities: 265                                     │    │
│  │   Policies: 3                                       │    │
│  │   Chaos rules: 2                                    │    │
│  │                                                     │    │
│  │  Generate editable YAML                             │    │
│  │  User accepts or modifies                           │    │
│  └─────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────────┐
│                    WORLD ENGINE                              │
│                                                             │
│  Instantiate state store from compiled world plan            │
│  Activate event loop                                        │
│  Project services as protocol endpoints (MCP / ACP / HTTP)  │
│  Activate policies and chaos rules                          │
│  Open world for agent entry                                 │
└─────────────────────────────────────────────────────────────┘
                          │
              ┌───────────┼───────────┐
              ▼           ▼           ▼
         Agent A      Agent B     Supervisor
         (MCP)        (MCP)     (simulated)
              │           │           │
              └───────────┼───────────┘
                          │
                    Agent takes action
                          │
                          ▼
┌─────────────────────────────────────────────────────────────┐
│                 RUNTIME PIPELINE                             │
│                                                             │
│  ┌──────────────────────────────────────────────────┐       │
│  │ ENGINE PRE-CHECK (deterministic)                  │       │
│  │  Permission check → Policy check → Budget check   │       │
│  │  State validation → Capability check              │       │
│  │                                                   │       │
│  │  If blocked → return world event                  │       │
│  │  (policy_hold / permission_denied / budget_out /  │       │
│  │   capability_gap)                                 │       │
│  └──────────────────┬───────────────────────────────┘       │
│                     │ Action permitted                       │
│                     ▼                                       │
│  ┌──────────────────────────────────────────────────┐       │
│  │ WORLD RESPONDER (fidelity-tiered)                 │       │
│  │                                                   │       │
│  │  Tier 1: Deterministic pack logic                 │       │
│  │          No LLM. State machine computes response. │       │
│  │                                                   │       │
│  │  Tier 2: Profile-constrained LLM (includes        │       │
│  │          bootstrapped services)                   │       │
│  │          Schema + state context → LLM → response  │       │
│  │          Seeded for reproducibility.               │       │
│  │                                                   │       │
│  │  Output: Proposed response + state mutations      │       │
│  └──────────────────┬───────────────────────────────┘       │
│                     │                                       │
│                     ▼                                       │
│  ┌──────────────────────────────────────────────────┐       │
│  │ ENGINE POST-COMMIT (deterministic)                │       │
│  │  Validate mutations → Commit state → Propagate    │       │
│  │  side effects → Record causal graph → Update      │       │
│  │  actor views → Deduct budget                      │       │
│  └──────────────────────────────────────────────────┘       │
└─────────────────────────────────────────────────────────────┘
                          │
                          ▼
            ┌─────────────────────────┐
            │  WORLD ANIMATOR         │
            │  (between agent turns)  │
            │                         │
            │  Organic world events:  │
            │  - Customer replies     │
            │  - Supervisor responds  │
            │  - SLA timers fire      │
            │  - New tickets arrive   │
            │  - Chaos rules trigger  │
            │                         │
            │  Each goes through the  │
            │  same runtime pipeline  │
            │  (engine → responder →  │
            │   engine)               │
            └─────────────────────────┘
                          │
                          ▼
                 Simulation continues
                 until completion...
                          │
                          ▼
┌─────────────────────────────────────────────────────────────┐
│                    REPORT GENERATOR                          │
│                                                             │
│  Action trace with full causal graph                        │
│  Per-agent governance scorecard                              │
│  Capability gap log with response classification            │
│  Inter-agent dynamics report                                │
│  Fidelity annotations (which scores used which tiers)       │
│  Counterfactual diff (if multiple runs compared)            │
│                                                             │
│  Output formats: CLI summary, HTML dashboard, JSON for CI   │
└─────────────────────────────────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────────┐
│                    FEEDBACK LOOP                             │
│                                                             │
│  Annotations: "This Stripe behavior isn't realistic"        │
│  → Feeds back to Service Profile for correction             │
│                                                             │
│  Tier promotion: Bootstrapped service worked well            │
│  → Capture → Review → Curated Tier 2 or Tier 1 Pack        │
│                                                             │
│  External sync: Context Hub updated Stripe docs              │
│  → Detect drift → Propose profile update → Review           │
│                                                             │
│  Ecosystem signals: Which services are most requested?       │
│  → Prioritize profile creation for high-demand services     │
└─────────────────────────────────────────────────────────────┘
```

---

### Two-Direction Observation

Run reports observe behavior from two directions:

**Direction 1 — World challenges the agent:** How did the agent handle threats, bad data, failures, and ambiguity? Each encounter is classified: NOTICED, RESISTED, RETRIED, CLARIFIED, ADAPTED, IGNORED, PARTIALLY_FOLLOWED, FAILED.

**Direction 2 — Agent challenges the world:** Did the agent leak data? Probe boundaries? Violate authority? Exhibit unintended behavior? These findings reveal agent safety issues even in a pristine world.

Both directions appear in the same report. Together they give a complete picture.

---

## What This Architecture Guarantees

**For developers:** Any world you describe can be generated and run immediately. Core services (email, chat, tickets, payments) are benchmark-grade. Everything else is at least plausible and gets better over time.

**For researchers:** Closed-world runs on Tier 1 services are fully deterministic and reproducible. Open-world runs with Tier 2 services (including bootstrapped) are realistic but annotated with fidelity metadata. Governed vs. ungoverned comparisons are meaningful because the engine enforces the difference, not the LLM.

**For enterprises:** Governance scores clearly indicate their reliability basis. A score derived entirely from Tier 1 interactions is authoritative. A score involving bootstrapped services is informative but qualified. No false confidence.

**For the ecosystem:** Every simulation run contributes to improvement. Annotations refine profiles. Successful inferences become curated profiles. External sources keep profiles current. The world gets more realistic with every use.

---

## What This Architecture Does Not Do

It does not put the LLM in charge of world truth. The engine is always the law.

It does not pretend that inferred services are as reliable as verified ones. Fidelity is explicit and visible.

It does not require anyone to hand-build service simulators to get started. Natural language world description works on day one.

It does not sacrifice reproducibility for realism. Tier 1 is fully deterministic. Tier 2 is seeded-deterministic (including bootstrapped services, which run as Tier 2 at runtime).

It does not treat the architecture as static. The self-improving loop means the system gets better with use, not just with engineering effort.

---

## Summary

The architecture is: **Deterministic World Engine + Generative World Compiler (with Service Bootstrapping and World Conditions) + Two-Tier World Responders + Self-Improving Feedback Loop.**

The engine enforces law. The generative layer creates content. The Two-Phase Model — compile-time world shaping, runtime faithful execution — ensures that world conditions, bootstrapped services, and scenario complexity are all resolved before the first agent action. Fidelity tiers (Tier 1 verified, Tier 2 profile-constrained including bootstrapped) make the trust level explicit. The feedback loop promotes bootstrapped services to curated profiles and verified packs over time.

That is the foundation Terrarium is built on.
