# Terrarium — Vision

### The world's first operating environment for artificial intelligence.

---

## The Problem

AI agents are being deployed into the real world — handling customer support, managing social media, processing payments, coordinating teams, searching the web, making decisions with real consequences.

But before deployment, they're tested by chatting with them a few times.

That's it. There's no environment where an agent can encounter stale data, uncooperative people, flaky services, ambiguous situations, policy constraints, budget limits, or adversarial actors — all the things that define reality — before they encounter them in YOUR reality.

Benchmarks test whether an agent can click buttons on a website. Observability tools trace what an agent did after it already did it. Evaluation platforms generate synthetic conversations with simulated personas. Mock servers return canned responses with no state, no consequences, and no surprises.

None of these are a world. A conversation is not a world. A task list is not a world. A mock API is not a world.

A world has places, people, rules, consequences, and time. A world responds to what you do. A world changes while you're acting. A world has other actors with their own goals who don't care about yours.

---

## What Terrarium Is

Terrarium creates complete, living realities for AI agents.

A Terrarium world has services — email inboxes, chat channels, ticket queues, payment systems, social feeds, websites, dashboards, knowledge bases, CRMs. It has actors — customers who get frustrated, supervisors who ask questions, competitors who undercut, trolls who provoke, collaborators who contribute. It has rules — policies that constrain, budgets that deplete, permissions that scope, approval chains that gate. It has physics — actions cause consequences, time creates urgency, information is imperfect, and the world changes while you act.

You describe a world in one sentence. Terrarium compiles it into a deep, internally consistent reality with hundreds of entities, autonomous actors, and unfolding situations. Then agents live in it.

```bash
terrarium create "Support team with Gmail, Slack, Stripe, 50 customers,
  one angry VIP waiting a week for a refund" --reality messy

terrarium run --agent your_agent.py
terrarium report
```

The agent doesn't know it's in a simulation. It sees real-looking APIs, real-looking data, real-looking people who respond, escalate, change their minds, and remember what happened last time. It makes decisions. The world responds. Consequences propagate. Everything is observed, recorded, and analyzable.

---

## What Makes Terrarium Different

### Living worlds, not simulated conversations

Evaluation platforms like Maxim AI and LangWatch generate synthetic multi-turn conversations with AI personas. Your agent talks to a simulated user. That's useful for chatbot testing. But agents in production don't just have conversations — they navigate organizations with cross-system state, coordinate with teammates, handle policy constraints, manage budgets, and deal with autonomous actors who have their own agendas.

Terrarium doesn't simulate conversations. It simulates reality. The customer who emails support also has a ticket, a payment history, a frustration level that's been building for 7 days, and the ability to escalate to your supervisor if you don't respond. That's a world, not a conversation.

### Governed environments, not attack surfaces

Virtue AI's Agent ForgingGround (launched March 2026) tests agents against 50+ simulated enterprise environments with red-teaming attacks. That's valuable for security. But most agent failures in production aren't attacks — they're governance failures. The agent exceeded its authority. It didn't escalate when it should have. It burned through its budget on low-priority tasks. It created duplicate work because it didn't coordinate with its teammate.

Terrarium's seven-step pipeline enforces governance on every action from every actor. Permissions, policies, budgets, capabilities, validation — all applied uniformly. The governance scorecard doesn't just tell you if your agent was hacked. It tells you if your agent would be a responsible employee.

### Any seat in the world

Every testing tool assumes your agent has one fixed role. Terrarium lets you test from any seat.

Connect your agent as the support agent handling tickets. Then connect it as the customer trying to get a refund. Then as the supervisor approving escalations. Same world. Different perspective. Completely different skills tested.

This is how you discover that your agent is great at following instructions but terrible at explaining what it needs. Or that it handles customer frustration well but can't make approval decisions under pressure.

### Multi-model in the same world, at the same time

Every benchmark and evaluation tool compares models sequentially — run Claude, then run GPT-4o, then run Llama against the same frozen scenario. Terrarium runs them simultaneously in the same living world.

Claude handles the VIP refund while GPT-4o processes billing tickets. When they need to coordinate on a duplicate request, you see what happens. The comparison isn't just "who scored higher" — it's "how do they work together, compete for resources, and handle shared state?"

### Worlds without external agents

Run a Terrarium world with zero external agents. All internal actors. A 50-person support organization operates autonomously. Watch how information flows. See where bottlenecks form. Study what happens when you change a policy. A 500-user social network debates a topic. Watch opinions form, shift, and polarize.

This is pure organizational and social simulation — not agent testing. It positions Terrarium as infrastructure for studying how AI systems behave in structured environments, not just a QA tool.

### Collaborative intelligence

This is the capability nobody else has, and it's the one that matters most for the future.

Define a world where the actors are researchers, analysts, or engineers — each with different expertise, different reasoning styles, different knowledge domains. They communicate through shared services — documents, chat channels, knowledge bases. They have governance — evidence standards, peer review, consensus requirements. They have a shared goal: solve a hard problem.

They work through it together. Autonomously. Each actor reads, analyzes, proposes, critiques, builds on others' ideas, revisits failed approaches, and converges toward a solution. The breakthrough emerges from interaction — not from a predefined pipeline of Agent A → Agent B → Agent C.

And you can see the complete causal graph of discovery. Click the final answer and trace backward: this conclusion came from researcher C's synthesis (tick 45), which combined researcher A's finding (tick 23) with researcher B's counterargument (tick 31), triggered by a document that researcher D surfaced (tick 18) that nobody had looked at until then.

This is fundamentally different from multi-agent frameworks like CrewAI, AutoGen, or MetaGPT. Those are orchestration pipelines — agents pass outputs to each other in predefined sequences. Terrarium is a world where agents coexist, communicate through services, build on each other's work asynchronously, and produce emergent solutions with observable intellectual provenance.

Your agent can join the research team. Connect as one of the researchers. See how it collaborates with autonomous AI researchers who have different perspectives. Does it build on others' ideas? Does it get stuck in its own reasoning? Does it change its mind when presented with counter-evidence? Does it dominate the conversation or contribute constructively?

No benchmark measures collaborative intelligence. Terrarium does.

---

## The Landscape

The AI agent ecosystem has matured rapidly, but a critical gap remains: no tool provides a governed, living environment where agents can be evaluated, compared, and studied as participants in a world.

**Social simulation** (OASIS, MiroFish, Stanford Generative Agents) creates agent populations that interact on social platforms. Valuable for studying discourse dynamics and emergent behavior. But these simulations have no governance framework, no cross-service causality, no service simulation, and no way to test YOUR agent — they generate all agents internally.

**Agent evaluation** (Maxim AI, LangWatch, Langfuse, Arize, LangSmith) provides tracing, evaluation metrics, and synthetic conversation testing. Essential for production monitoring. But these tools test conversations, not agents operating in environments with state, consequences, and other autonomous actors.

**Enterprise agent security** (Virtue AI Agent ForgingGround) simulates enterprise environments for red-teaming and attack testing. Important for security posture. But environments are attack surfaces, not living worlds. No governance evaluation, no population dynamics, no collaborative intelligence.

**Multi-agent frameworks** (CrewAI, AutoGen, MetaGPT, CAMEL, LangGraph) orchestrate agents for task completion. Powerful for building agent pipelines. But orchestration is not simulation — agents follow predefined workflows, not navigate open-ended worlds with autonomous actors and emergent situations.

**Benchmarks** (WebArena, OSWorld, AgentBench, SWE-bench) provide fixed tasks with fixed answers. Useful for capability measurement. But static benchmarks can't test judgment, governance compliance, collaboration, or adaptability — the qualities that matter in production.

Terrarium occupies the intersection that none of these cover: a programmable world compiler that creates governed, living environments where agents are evaluated not by answering questions but by surviving and thriving in reality.

---

## Where Terrarium Is Going

Testing agents is where Terrarium starts. It's not where Terrarium ends.

### Layer 1 — Agent evaluation

Developers test their agents in simulated worlds before production. Enterprises run governance audits. Models get compared side-by-side in identical or shared conditions. The governance scorecard becomes the standard for agent certification.

### Layer 2 — Agent populations and collaborative intelligence

Multiple agents in a world is a team. Hundreds of agents is an organization. Thousands is a society. Terrarium scales to autonomous populations operating in governed worlds — support teams, research groups, social networks, marketplaces, entire companies.

The collaborative intelligence use case matures here. Research teams of AI agents work through hard problems together. The causal graph of discovery becomes a new tool for understanding how solutions emerge from diverse perspectives.

### Layer 3 — Agent economies

Agents with budgets, transactions, and resources form economic systems. Marketplaces where agent-sellers compete for agent-buyers. Startup ecosystems with investor agents, founder agents, and employee agents. Trading environments where strategies compete in real time.

Run the simulation and observe: which strategies win? How do prices evolve? Do monopolies form? Do agents collude? Do they innovate?

### Layer 4 — Persistent worlds

Worlds that don't reset after a run. Agents have history, reputation, and institutional memory. Organizations evolve. New agents enter a world shaped by agents that came before. Norms emerge. Institutions form. Knowledge accumulates.

### Layer 5 — Connected worlds

Multiple Terrarium worlds connect. Agents move between worlds. Services built in one world export to another. Reputation earned in one world carries to the next. A network of governed realities — the operating substrate for artificial intelligence.

---

## The Core Insight

The insight behind Terrarium is not "agents need testing." The insight is:

**Intelligence develops in worlds, not in prompts.**

A human doesn't become competent by answering questions on a test. They become competent by living in a world — navigating institutions, cooperating with others, handling messy information, making decisions under uncertainty, dealing with consequences. The world is what develops intelligence.

AI agents today have powerful models but no world. They have reasoning ability but nowhere to exercise it. They can answer any question but can't navigate a bureaucracy, coordinate with a teammate, manage a budget, handle a frustrated customer who's been waiting a week, or resist a manipulation attempt from an actor who remembers what worked last time.

Terrarium gives them a world. What they do with it is what we observe, measure, and learn from.

And when multiple agents share a world — when they collaborate, debate, build on each other's work, and converge on solutions through governed processes — something new emerges. Not prompt chaining. Not orchestration pipelines. Collaborative intelligence in a living, observable environment.

---

## Why Now

**Agents are going to production.** 57% of organizations now have agents in production (LangChain 2026 State of AI Agents). 40% of enterprise applications will embed agents by end of 2026 (Gartner). These agents need to be tested, governed, and certified in environments that mirror reality, not on benchmarks or in conversations.

**MCP is the universal connector.** The Model Context Protocol has become the standard way agents connect to services. Terrarium integrates with ANY agent by being an MCP server. Your agent connects to Terrarium the same way it connects to Gmail. Universal compatibility on day one.

**Governance is becoming mandatory.** Singapore's Model AI Governance Framework for Agentic AI (January 2026), the EU AI Act high-risk rules (August 2026), and the World Economic Forum's agent governance foundations all require evaluation in environments that mirror deployment conditions. Terrarium provides exactly this.

**LLMs can generate worlds.** The World Compiler is possible now in a way it wasn't 18 months ago. An LLM can interpret "50-person support team with messy data and one angry VIP" and produce a coherent, internally consistent world with hundreds of entities and autonomous actors.

**The window is closing.** Virtue AI launched enterprise agent simulation in March 2026. OASIS has scaled to 1M social agents. Evaluation platforms are maturing fast. The unique position Terrarium occupies — governed living worlds with collaborative intelligence — won't stay unoccupied forever.

---

## Architecture in One Paragraph

Terrarium has a universal world compiler that creates worlds from natural language descriptions. Each world has a deterministic engine that enforces the laws of reality — state, permissions, policies, budgets, causality, time. Services are simulated at two fidelity levels: Tier 1 (compiled code, fully deterministic) and Tier 2 (LLM-constrained by profiles). Internal actors are autonomous — they observe, decide, and act through the same governed pipeline as external agents, with their own goals, memory, frustration, and evolving behavior. The AgencyEngine manages actor activation efficiently through tiered processing, scaling from zero actors (services-only worlds) to hundreds of autonomous participants. Five reality dimensions control the world's character: information quality, reliability, social friction, complexity, and boundaries. An event queue with logical time orders all actions — from external agents, internal actors, and the environment — through one pipeline. Everything is recorded. Everything is replayable. Everything is diffable.

---

## The Community Vision

Terrarium is open source. The engine is the foundation. The community builds what runs on it.

**World Definitions** — shareable scenarios anyone can create and publish. "The nightmare support queue." "The hostile marketplace." "The research collaboration." Create an interesting world, share it, let others test their agents in it. The lowest-barrier contribution.

**Service Packs** — simulations of specific services. The community builds profiles for Jira, Salesforce, HubSpot, LinkedIn, Shopify, and thousands more. Each pack starts as inference, gets captured, gets promoted through community review.

**Blueprints** — domain templates. Support org, social network, marketplace are the start. The community adds healthcare, DevOps, legal, education, trading, recruiting, research labs, and every domain where agents operate.

**World Packs** — curated collections. "The Enterprise Governance Audit Pack" — 20 worlds testing agent governance. "The Collaborative Research Pack" — 10 worlds with different team compositions and problem types. Packs become industry standards.

**Leaderboards** — public comparison tables showing agent/model performance across standardized worlds. The community maintains them. New worlds get added. New models get tested. The leaderboard grows.

The flywheel: worlds create content (papers, comparisons, benchmarks, demos). Content attracts users. Users create worlds. Each cycle makes the ecosystem richer.

---

## The North Star

Before agents live in our world, they should prove themselves in a Terrarium.

Before an enterprise deploys an agent fleet, they run it in a simulated organization with autonomous actors creating real pressure, and get a governance report.

Before a developer ships an agent, they run it in 50 different worlds and know exactly where it fails — not on benchmarks, but in reality.

Before a researcher studies agent collaboration, they create a world with diverse AI researchers, give them a hard problem, and trace the complete causal graph of how the solution emerged.

Before the industry trusts AI agents with real decisions, those agents have a track record — not from tests, not from demos, but from living in worlds.

Terrarium is not a testing tool that aspires to be a world engine.

Terrarium is a world engine that happens to solve the testing problem first.

---

## Get Involved

Terrarium is live and open source.

**Use it** — `pip install terrarium` and test your agent in 5 minutes.

**Build worlds** — Create a scenario, share it, let others run their agents in it.

**Build packs** — Simulate a service you know well. Every pack makes the ecosystem richer.

**Build blueprints** — Define a domain. Healthcare, trading, DevOps, research — every blueprint unlocks a new category of world.

**Shape the vision** — This is early. The architecture is set but the possibilities are open. If you see where this should go, come build it.

GitHub: [github.com/terrarium-ai/terrarium](https://github.com/terrarium-ai/terrarium)

---

*Terrarium — Programmable worlds for artificial intelligence.*
