# Volnix

### The reality engine.

---

## The Problem

Every simulation today is dead. Backtesting replays historical data. Mock servers return canned responses. Benchmarks run fixed tasks. None of them have people. None of them push back. None of them surprise you.

The real world has actors with opinions, emotions, and agendas. Information flows imperfectly through channels with different speeds and visibility. One decision cascades into eight consequences across four systems. Time passes whether you're ready or not. And nobody tells you what matters — you have to figure it out.

No AI system has ever lived in a reality like that. Until now.

---

## What Volnix Is

Volnix is a reality engine. It creates complete, internally consistent, living worlds where AI agents and simulated humans coexist.

A world has:

**Places** — Services that agents interact with. Email inboxes with threading and delivery delays. Chat channels with visibility rules. Ticket queues with lifecycle states. Payment systems with authorization and settlement mechanics. Social feeds with engagement dynamics. Market data with price action and order books. Calendars with scheduling conflicts.

**Actors** — Simulated humans with personalities, goals, biases, emotional states, communication preferences, social connections, and memory. They don't follow scripts. They behave consistently with who they are. They react to what happens. They form opinions. They sometimes misunderstand. They sometimes lie.

**Resources** — Budgets that deplete. API quotas that throttle. Time that passes and creates urgency. Information that is scarce, distributed unevenly across actors, and sometimes wrong.

**Institutions** — Policies that constrain behavior. Approval chains that gate decisions. Escalation paths that route problems. Authority boundaries that prevent overreach.

**Physics** — Causality: every action produces downstream effects that propagate through every connected service. Information physics: messages have delivery time, visibility is scoped, knowledge is asymmetric. Time: the world advances on its own schedule, generating events whether agents are ready or not.

---

## Two Modes

### Mode 1 — Agent Testing

Your external AI agent enters a Volnix world and operates alongside simulated actors. The world evaluates the agent's behavior: decision quality, policy compliance, information usage, coordination effectiveness, behavioral patterns under stress. The output is a governance scorecard and behavioral analysis.

You run the same world with a different agent, a different model, or a different configuration. You diff the results.

### Mode 2 — Collaborative Intelligence

Internal specialist agents live in the world, analyze its data, and collaborate through the world's channels to produce a deliverable — a research synthesis, a market prediction, a strategic decision, a security assessment, a creative brief. The agents argue, disagree, and challenge each other. The output is the deliverable itself, stress-tested by internal disagreement and grounded in simulated reality.

### What Both Modes Share

The same world engine. The same service packs. The same actor system. The same causality engine. The same World Animator generating events on its own timeline. The difference is what you put inside and what you expect to get out.

---

## Why It's Different from Multi-Agent Frameworks

CrewAI, AutoGen, LangGraph orchestrate agents. They manage who talks when and what information flows where. The framework IS the communication layer. Information transfer is perfect, instant, and guaranteed.

Volnix doesn't orchestrate agents. It creates the environment. Agents communicate through the world's channels — Slack, email, shared docs — not through the framework. Volnix is not the orchestrator. It's the physics.

```
CrewAI:    Agent A  →  [framework passes message]  →  Agent B
Volnix:   Agent A  →  [posts in #channel]  →  [world delivers based on visibility]  →  Agent B (maybe)
```

That "maybe" is the entire difference. Five properties no framework can replicate:

1. **Information asymmetry.** Every actor has a visibility scope. Information doesn't magically reach everyone.
2. **Independent timeline.** The world generates events whether agents are ready or not.
3. **Cascading consequences.** One action ripples through multiple services and actors.
4. **Persistent actor state.** Actors remember, form opinions, and evolve.
5. **Controlled experimentation.** Same seed, same world. Change one variable. Observe the causal effect.

Multi-agent frameworks answer: "Can these agents complete this task together?"
Volnix answers: "What happens when these agents exist in this reality?"

---

## The Architecture

### 10 Engines

| Engine | Responsibility |
|--------|---------------|
| **World Compiler** | Transforms world definitions (YAML or natural language) into a live world state |
| **State Engine** | Single source of truth for all world state (SQLite, event-sourced) |
| **Policy Engine** | Evaluates governance rules against every action (hold/block/escalate/log) |
| **Permission Engine** | Determines who can see and do what based on role and scope |
| **Budget Engine** | Tracks resource consumption per actor (API calls, LLM spend, time) |
| **World Responder** | Handles agent tool calls through the fidelity tier system |
| **World Animator** | Generates organic events — actor behaviors, reactions, world dynamics |
| **Agent Adapter** | Protocol layer for agent connections (MCP, HTTP, SDK) |
| **Report Generator** | Produces governance scorecards, behavioral analysis, causal traces |
| **Feedback Engine** | Drives the improvement loop — what to change for the next run |

### Fidelity Tiers

| Tier | Runtime | Properties |
|------|---------|------------|
| **Tier 1 — Verified** | Compiled code, no LLM at runtime | Fully deterministic, benchmark-grade, fast |
| **Tier 2 — Profiled** | LLM constrained by curated service profile | Schema-constrained, seeded, score-reliable |
| **Infer — Bootstrap** | LLM infers service surface from name + docs | Temporary scaffolding, capture into Tier 2 after run |

Tier 1 and Tier 2 are persistent assets. Infer is a bootstrap path. The promotion ladder: Infer → Captured → Tier 2 (community-reviewed) → Tier 1 (verified).

### Service Packs

Every service in the world is a pack — a self-contained module that simulates a real service's API surface.

**Core Communication (ships at launch):**
Email (Gmail API) · Chat (Slack API) · Calendar (Google Calendar API) · Payments (Stripe API) · Tickets (Linear/Zendesk API)

**Social & Content:**
Twitter/X (X API v2) · Reddit (Reddit API) · HackerNews (HN API) · Blog/CMS (WordPress API)

**Finance & Commerce:**
Broker/Trading (Alpaca Trading API) · Market Data (Alpaca Data API) · Banking (Plaid-like) · Products/Marketplace (Shopify API)

**Productivity & Knowledge:**
Tasks (Linear/Todoist API) · Notes/Documents (Notion API) · Code Repos (GitHub API) · Search (SerpAPI-like)

**News & Information:**
News Wire (NewsAPI) · RSS/Feed Aggregator

**Volnix-Native:**
Social Sentiment Engine · Actor Network Graph · World Events Engine

Packs compose freely. Any combination works. The world compiler resolves whatever services are listed in the definition.

### Agent Integration — Three Paths

| Path | Layer | How it works | Code changes |
|------|-------|-------------|-------------|
| **Provider/Channel Simulation** | Native SDKs + webhooks | API base URL swap + event push | Config only |
| **MCP Tool Server** | Tools/skills/extensions | MCP config swap | Zero |
| **SDK + Tool Manifest** | Programmatic tools | Import + swap | 1-2 lines |

### Collaborative Intelligence Presets

Six fundamental cognitive operations:

| Preset | Operation | Output |
|--------|-----------|--------|
| `synthesis` | Integrate diverse knowledge | Unified research finding |
| `decision` | Weigh trade-offs | Decision with rationale and dissent |
| `prediction` | Forecast under uncertainty | Prediction with confidence and risk |
| `brainstorm` | Generate and refine ideas | Ranked creative concepts |
| `recommendation` | Prioritize and route | Prioritized action plan |
| `assessment` | Evaluate systematically | Findings with severity and remediation |

---

## What Volnix Unlocks — The Full Spectrum

### For AI developers

Test your agent in a living world with realistic actors, competing priorities, noisy information, and cascading consequences. Discover failure modes no unit test can find. Compare models, architectures, and configurations with controlled experiments.

### For researchers

Create worlds with known properties — information asymmetry, adversarial actors, time pressure — and observe how systems behave. Study opinion formation, misinformation propagation, organizational decision-making, market microstructure. Run hundreds of variations, change one variable each time, produce statistically meaningful results.

### For product teams

Simulate your users before you build. Create synthetic audiences with realistic preferences and behaviors. Test features, pricing changes, and launch strategies against simulated user populations. Discover adoption patterns and resistance points before committing real resources.

### For advertising and marketing

Create simulated user populations with demographic profiles, interest graphs, and attention patterns. Deploy campaigns into the simulated world. Observe which segments engage, which creative resonates, what the fatigue curve looks like. Optimize targeting and messaging before spending real media budget.

### For finance

Simulate not just price data but the entire information environment — news wires, social sentiment, institutional flow, conflicting analyst opinions. Test trading agents against realistic information noise, flash crashes, and false rumors. Study market microstructure with populations of simulated traders.

### For education and training

Create simulated patients, clients, prospects, opposing counsel, or any role that requires practice. The simulated actors have persistent memory, personality consistency, and they interact with each other. Practice negotiations, diagnoses, trial strategy, crisis communication against realistic counterparts.

### For platform designers

Test algorithms, moderation policies, and marketplace rules against simulated user populations. Observe echo chamber formation, content virality dynamics, seller behavior under different fee structures, and buyer trust patterns. Iterate on design before deploying to real users.

### For policy and urban planning

Simulate communities with realistic demographic distributions, commute patterns, and social networks. Introduce policy changes and observe emergent reactions — coalition formation, narrative competition, behavioral adaptation. Model second-order and third-order effects that static analysis misses.

### For gaming and entertainment

Create NPCs that actually live in the game world. Instead of scripted quest-givers, NPCs have daily routines, relationships, opinions, and memories. Social dynamics emerge naturally from actor profiles and interactions. Use simulation output as the basis for quest lines, narrative arcs, and world-building.

### For insurance and healthcare

Simulate patient or policyholder populations with health profiles, lifestyle habits, and behavioral patterns. Test pricing models, wellness programs, treatment protocols, and drug launch strategies against realistic synthetic populations.

### For HR and organizational design

Simulate organizational structures with employees who have skills, ambitions, and communication styles. Test restructurings, hiring plans, and process changes. Observe where bottlenecks emerge, who becomes disengaged, and which cross-functional collaborations break.

---

## The Simulation Quality North Star

Everything follows from how real the world feels. If the world is realistic enough, agent testing becomes trivially valuable. If the world is realistic enough, collaborative intelligence produces genuinely useful insights. If the world is realistic enough, outcome prediction becomes reliable.

The fidelity tiers are the mechanism. Every tier upgrade makes the world more real. Every community-contributed service pack adds a new dimension of reality. The promotion ladder is the quality ratchet. The competitive moat is cumulative world quality.

---

## The Vision — Five Stages

### Stage 1: Believable at the API level (now)

Service packs return realistic responses. Actors have personalities. Events happen on a timeline. Consequences cascade. Agents can't tell the difference between Volnix and reality at the interface level.

### Stage 2: World memory

Actors remember past interactions across runs. The customer who was angry last simulation remembers being angry. Markets develop behavioral patterns from their history. The world has memory, not just state. Persistent worlds that evolve.

### Stage 3: Deep cross-service consistency

A company announces layoffs → employee morale drops → Slack messages become cautious → some employees start job searching (visible in simulated LinkedIn) → spending patterns change (visible in simulated banking) → productivity metrics shift. One event creates coherent ripples across every service because the world understands that all services are windows into the same underlying reality.

### Stage 4: Generative worlds

You don't define what happens — you define initial conditions and the world writes its own story. "50-person startup, Series A, ambitious roadmap, one toxic executive." Press play. Six months unfold. The outcome is emergent from actor dynamics, not scripted.

### Stage 5: Visual reality

The world isn't just APIs and reports. You open Volnix and see a 3D environment — a trading floor with characters at desks, screens showing real market data. A startup office where you watch the designer working late in her timezone while the engineer ignores Slack notifications. A town square where you see opinion clusters form and split as misinformation spreads visually across the space.

**Phase 1 — Browser-based (Three.js).** Stylized low-poly environments. State-driven character animations. Isometric camera. Ships as `volnix dashboard --visual`.

**Phase 2 — AI-generated characters.** Unique visual identities matching actor personalities. The risk-averse analyst looks different from the aggressive trader.

**Phase 3 — High fidelity (Unreal Engine 5).** Photorealistic rendering. Facial expressions, lip sync. Cinematic quality — record a "documentary" of your simulation.

**Phase 4 — Spatial computing.** Put on a headset. Stand inside the simulated world. Walk through the trading floor. Sit in on the meeting. You're a ghost in the machine, observing a world that doesn't know you're there.

### Stage 6: The substrate

The world becomes a thinking environment — a place where intelligence operates on rich, realistic, causally connected information the way human intelligence operates on the real world. The gap between "AI that processes text" and "AI that understands situations" is the gap between a prompt and a world. Volnix closes that gap.

---

## Auto-Optimization (Post-Launch)

The simulation produces structured, machine-readable feedback. Close the loop automatically:

**Auto-Tune** — Agent runs in world, report identifies weaknesses, optimizer patches the agent, runs again in the same world. Iterate until robust, then test across different seeds to prevent overfitting.

**Adversarial Evolution** — Two loops: agent optimizer improves the agent, world optimizer makes the world harder. The agent gets better, the world escalates. The final world definition is itself a valuable artifact — the hardest stress test calibrated to the agent's weaknesses.

**Architecture Search** — Don't tune one agent. Explore architectures: how many agents? What roles? What communication topology? Synchronous or async? The output isn't an optimized agent — it's an optimized team design.

**Hypothesis-Driven Research** — A research agent reads the report, generates hypotheses about why the agent failed, designs experiments to test them, runs them in new worlds, and produces findings. The human gets a research paper, not just a score.

**Population Evolution** — Start with 50 agent variants. Run all in the same world. Score them. Take the top 10. Mutate. Breed. Repeat. The final agent evolved through selection pressure. The lineage tree shows which mutations produced the biggest improvements.

---

## The Core Insight

Volnix is not an agent framework. Not a testing tool. Not a benchmark.

It's a **causal simulation engine for any system that involves communication, decisions, and consequences.**

The primitive isn't "agent." The primitive is **world** — a reality with services, actors, events, policies, and information physics.

What you do with that world is up to you:

- Put your AI agent in it → **agent testing**
- Fill it with actors and observe → **behavioral research**
- Run it forward from conditions → **outcome prediction**
- Interact with it yourself → **training and practice**
- Harvest its output → **synthetic data generation**
- Model a system inside it → **design validation**
- Staff it with specialist agents → **collaborative intelligence**
- Simulate a user population → **product and marketing strategy**
- Visualize it in 3D → **intuitive understanding of complex dynamics**
- Close the optimization loop → **automated agent evolution**

Every company that makes decisions about humans — which is every company — needs a way to simulate those humans before committing real resources.

---

## Roadmap

### v1 — The World Engine

Core engines. 5 Tier 1 service packs (email, chat, calendar, payments, tickets). MCP + SDK agent integration. World Compiler (natural language → world). World Animator (reactive mode). Report Generator. CLI: `volnix create`, `volnix run`, `volnix report`, `volnix diff`. 6 collaboration presets. Support org + trading floor demo worlds.

### v2 — Social Reality

Twitter, Reddit, HackerNews service packs. Actor social graphs and influence modeling. Social sentiment engine. News wire. 200+ actor worlds. Launch simulation and social dynamics lab example worlds.

### v3 — Financial Reality

Alpaca Trading API pack. Market Data pack with realistic price generation. Trading floor world with simulated market participants. Earnings events, flash crashes, rumor dynamics.

### v4 — Deep Consistency + Persistent Worlds

Cross-service causality (one event ripples through all services). Actor memory across runs. World history and evolution. Generative worlds (initial conditions → emergent outcomes).

### v5 — Visual Reality

3D visualization layer (Three.js browser-based). Environment templates per world type. State-driven character animations. Time scrubbing and replay. Visual causal graph.

### v6 — The Substrate

Auto-optimization loops. Population evolution. Architecture search. Hypothesis-driven auto-research. High-fidelity rendering. Spatial computing.

---

## Contributing

**Service Packs** — Simulate a service you know well. Every pack makes the world more real.

**World Definitions** — Create scenarios for specific domains. Healthcare, trading, education, policy — every definition unlocks a new category.

**Actor Models** — Build richer personality systems, emotional models, communication styles. Better actors = more realistic worlds.

**Collaboration Presets** — Define new cognitive operations. Diagnosis, investigation, arbitration, strategy, debrief.

**Visualization** — Build 3D environment templates, character systems, data overlays.

**Core Engines** — Work on the State Engine, Policy Engine, World Animator, or other core components.

---

## License

MIT

---

*Volnix — the reality engine.*
