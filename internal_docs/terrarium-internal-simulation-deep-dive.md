# Terrarium Internal Simulation — What It Is, Why It's Different, What It Unlocks

---

## Part 1: The Fundamental Difference from Multi-Agent Frameworks

### What multi-agent frameworks actually do

In CrewAI, AutoGen, LangGraph — you define agents with roles, give them tools, and orchestrate how they talk to each other. The framework manages conversation flow: Agent A produces output, passed to Agent B, processed, passed to Agent C. The framework IS the communication layer. Information transfer is perfect, instant, and guaranteed.

```python
# CrewAI — the framework IS the communication layer
crew = Crew(
    agents=[researcher, writer, editor],
    tasks=[research_task, write_task, edit_task],
    process=Process.sequential  # framework decides the flow
)
result = crew.kickoff()
```

### What Terrarium does differently

Terrarium doesn't orchestrate agents. It creates the environment and lets agents exist inside it. Agents don't talk through Terrarium — they talk through the world's channels. Terrarium is not the orchestrator. It's the physics.

```
CrewAI:     Agent A  →  [framework passes message]  →  Agent B
Terrarium:  Agent A  →  [posts in #channel]  →  [world delivers based on visibility]  →  Agent B (maybe)
```

That "maybe" is the entire difference. In the real world, information doesn't flow perfectly. Messages get missed. People aren't in the channel. Emails go to spam. Someone reads it but doesn't act. Someone acts on partial information because they didn't see the follow-up. The delay between "sent" and "received" and "understood" and "acted on" is where most real-world failures happen.

### Five mechanical properties Terrarium has that no framework can replicate

**1. Information asymmetry is a first-class property.**
Every actor has a visibility scope — what channels they see, what emails they receive, what feeds they subscribe to. Information doesn't magically reach everyone. It propagates through channels at different speeds, in different formats, with different completeness. You can study how communication structure affects decision quality, what happens when Agent A has information Agent B needs but they don't share a channel.

**2. The world has its own timeline — things happen independently of agents.**
In CrewAI, nothing happens unless an agent acts. In Terrarium, the World Animator generates events on its own schedule: a customer emails at 2 PM, a price drops at 2:15, news publishes at 2:30, a service goes down at 3:15. These events happen whether agents are ready or not. Agents have to notice, prioritize, and respond — or miss them entirely.

**3. Actions have consequences that cascade through the world.**
An agent refunds a customer → Stripe charge status changes → customer gets confirmation email → #finance Slack gets notification → team refund budget decreases → customer sentiment shifts → customer posts positive tweet 2 hours later → other actors see it → brand sentiment ticks up. One action, eight consequences, four services, multiple actors, over a 2-hour span. The agent that issued the refund doesn't see most of these. Multi-agent frameworks don't have persistent world state where actions produce cascading consequences.

**4. Actors have persistent internal state — goals, opinions, relationships.**
A simulated customer has satisfaction levels that change, patience thresholds that decrease, communication preferences, memory of past interactions, and social connections. Their response depends on all of this accumulated state, not just the current message. Multi-agent frameworks define behavior through system prompts — stateless per invocation.

**5. You can change one variable and observe the systemic effect.**
Same seed = same starting state = same world. Change one variable (communication structure, a policy, an actor's personality, a timeline event) and run again. Observable causal effect. This is controlled experimentation on social and organizational systems. Multi-agent frameworks can't do this because there's no environment to vary — only agent prompts and tools.

### The differentiator in one sentence

Multi-agent frameworks let you orchestrate agents. Terrarium lets you see what emerges when agents live in a world they don't control.

CrewAI answers: "Can these agents complete this task together?"
Terrarium answers: "What happens when these agents exist in this reality?"

The first is a test. The second is a simulation. The first has pass/fail. The second has discoveries — things you didn't know to look for, failure modes you didn't anticipate, emergent behaviors you couldn't predict.

---

## Part 2: The Living World Concept

The world is alive — actors are doing things (trading, posting, buying, complaining, moving). They're not part of any research team. They're just living. They're the phenomenon.

Researcher agents are also inside the world. They have access to the world's services — they can query market data, read social feeds, pull news, analyze patterns in the data actors generate. They collaborate with each other through the world's communication channels (Slack, email, shared docs). They're trying to figure something out, solve something, produce a finding.

The researchers don't control the actors. They can only observe and analyze. The actors don't know researchers exist. Two independent layers occupying the same world.

```
┌─────────────────────────────────────────────┐
│  THE WORLD                                   │
│                                              │
│  Actors (living, generating data):           │
│    200 traders buying/selling                │
│    50 social media users posting             │
│    10 companies reporting earnings           │
│    News events firing on a timeline          │
│                                              │
│  ─────────────────────────────────────────   │
│                                              │
│  Researchers (agents, solving a problem):    │
│    Analyst agent — reads market data + news  │
│    Social agent — reads Twitter/Reddit feed  │
│    Quant agent — runs statistical analysis   │
│    Lead agent — synthesizes, writes report   │
│                                              │
│  They share: #research Slack, shared doc,    │
│  email thread. They argue, disagree,         │
│  challenge each other's hypotheses.          │
│                                              │
│  OUTPUT: a research finding, a prediction,   │
│  a recommendation, a paper                   │
└─────────────────────────────────────────────┘
```

---

## Part 3: Five Categories of What Internal Simulation Unlocks

### Category 1 — Behavioral Research (studying how groups behave under conditions)

Actors have personalities, goals, biases, social connections. They communicate through real channels. World Animator drives events. You observe what emerges.

**Opinion formation and polarization research.** 200 actors, Reddit-like forum, Twitter-like feed. Distribute initial opinions on a policy issue. Introduce misinformation on day 3, correction on day 5. Observe: how fast does misinfo spread? Which actor types amplify it? Does the correction reach people who saw the original? How does network structure affect polarization? Run 50 variations with different network topologies, same seed. Produce a dataset showing causal relationship between network structure and polarization rate.

**Market microstructure research.** 100 trading actors (momentum traders, value investors, noise traders, 3 institutional actors). Market data + news wire. When institutional actor starts selling slowly, how long until others detect it? Do momentum traders amplify? Does noise floor mask the signal? Change market transparency, run again. Study the effect on price efficiency.

**Organizational decision-making research.** 15 actors across 3 teams, each with different information (marketing sees feedback, engineering sees metrics, finance sees revenue). A crisis requires all three perspectives. Does information reach the decision-maker in time? What communication structure leads to faster, more accurate diagnosis? Run 100 variations.

**Why this is different from existing simulation tools (Concordia, Mesa, NetLogo):** Those simulate abstract agents with simple rules. Terrarium's actors communicate through realistic service APIs (email, Slack, Twitter) with real communication properties — message length, channel visibility, threading, notifications. When Actor A emails Actor B, that email has a subject line, body, delivery time, and sits in an inbox that Actor B might or might not check.

### Category 2 — Outcome Prediction (running scenarios forward)

The world is a model of a situation. Populate with actors, set initial conditions, run forward.

**Product-market fit testing before building.** 100 developer actors with varying needs, a launch platform, a Reddit community, a GitHub repo. Define your product's value proposition. Do actors discover it? Try it? Come back? Run with three positioning strategies, see which generates most organic adoption. Dynamic simulation where behavior is emergent, not scripted.

**Negotiation outcome prediction.** Complex deal with 4 stakeholders (CFO: price, CTO: integration, VP Eng: migration effort, Legal: compliance). Each has priorities, objections, communication patterns. Simulate: what happens leading with technical demo vs. addressing CFO pricing first? Each variation produces different trajectory. Go into real meeting having mapped the decision tree.

**Policy impact modeling.** Zoning change with actors representing residents, business owners, developers, environmentalists, politicians. Services: email, town hall forum, local news, social media. Simulate 60 days from announcement to vote. What coalition forms? What if public engagement happens day 10 vs day 30?

**Why different from traditional scenario planning:** Traditional planning is static (manually defined scenarios). Monte Carlo varies numerical parameters. Terrarium varies social dynamics — how actors communicate, react, form opinions, make decisions. Outcomes emerge from behavior, not equations.

### Category 3 — Training and Preparation (practice environment)

**Negotiation practice.** Manager actor with personality profile (data-driven, conflict-averse, budget-constrained). Practice raise conversation through email and Slack. Manager pushes back realistically. Try different approaches. Go into real conversation having rehearsed.

**Sales call preparation.** Prospect company with CTO (skeptical), VP Product (enthusiastic), IT Security (blocker). Practice pitch. CTO asks hard questions, Security raises compliance concerns. Practice handling objections through realistic channels.

**Crisis communication practice.** Journalists, customers, influencers, employees. Simulate product recall. Practice response across channels — press release, customer email, social media, internal all-hands. Run 5 times with different strategies.

**Why different from role-playing with ChatGPT:** Actors have persistent memory, personality consistency, and interact with each other — not just with you. The journalist DMs the customer for a quote. The employee leaks on social media. Multi-party and reactive.

### Category 4 — Synthetic Data and Content Generation

**Realistic training data.** 50 customer actors (different products, issues, styles, frustration levels) + 5 support agents. Run 100 simulated days. Output: thousands of realistic multi-turn conversations with natural variation. More realistic than single-LLM synthetic data because conversations emerge from interaction dynamics.

**Content strategy testing.** 500 actors across Twitter and Reddit. Publish 20 different content pieces over 30 simulated days. Discover which formats/topics/channels generate most engagement per audience segment. Find patterns like "technical deep-dives on Tuesday mornings get 3x engagement among senior developers."

**Game world prototyping.** 30 NPC actors in a medieval village, each with role, personality, routine, relationships. Run 30 days. Observe emergent social dynamics — rivalries, alliances, conflicts. These become quest lines grounded in natural dynamics.

### Category 5 — System Design Validation

**Governance model testing.** 50 DAO token-holders with different voting power, interests, activity levels. Run 6 months of governance. Does it function? Do whales dominate? Change voting mechanism from token-weighted to quadratic. Diff outcomes.

**Marketplace design testing.** 100 buyers + 50 sellers. Listings, reviews, messaging, payments. Simulate 3 months. Do buyers find what they need? Does review system prevent fraud? Introduce new fee structure — does it drive sellers away or improve quality?

**Moderation system testing.** 200 users (mostly good-faith, some boundary-pushing, 5 bad-faith). Implement moderation rules as policies. Do rules catch bad actors without over-moderating? What's the false positive rate? What happens when bad actors adapt?

---

## Part 4: Researchers Inside a Living World — Concrete Examples

### Example 1 — "What's driving this market move?"

World: 200 trading actors, market data, news wire, Twitter, Reddit. NVDA is down 7% mid-session.

Reality (known to Terrarium, not to agents): hedge fund selling started at 10 AM, fake SEC rumor on Twitter at 10:15, real supply chain issue on Reuters at 9:45. Three causes, different sources, mixed with noise.

**Market Analyst agent** — accesses order flow. Detects institutional selling pattern. Posts in #research: "15 blocks of 10k+ shares starting 10:02. This isn't retail panic."

**Social Sentiment agent** — monitors Twitter/Reddit. Finds SEC rumor (400 retweets). Notices poster's low credibility. Posts: "SEC rumor spreading. Source credibility unclear."

**News Intelligence agent** — reads Reuters wire. Finds supply chain story from 9:45. Searches for SEC filings — nothing. Posts: "No SEC filing found. But there IS a supply chain story from Reuters."

**Lead Researcher agent** — synthesizes all inputs:

```
NVDA -7% Root Cause Analysis

1. SUPPLY CHAIN (real, primary) — Reuters 9:45, preceded selloff
2. INSTITUTIONAL SELLING (real, amplifying) — orderly blocks, not panic
3. SEC RUMOR (false, noise amplifier) — no filing, low-cred source,
   amplified retail panic, turned -3% into -7%

CONFIDENCE: 72%
DISSENT: Market Analyst believes institutional flow suggests 
something beyond supply chain. Recommends waiting.
```

Because it's Terrarium, you know ground truth. Report accuracy can be scored against reality. Was the 72% confidence justified? Was the dissent right?

### Example 2 — "Predict community reaction to our feature change"

World: 300 user actors on Twitter, Reddit, GitHub. Free-to-freemium pricing change.

**Community Analyst** — tracks sentiment: "Initial reaction 60% negative, but concentrated in 30 accounts. Quiet majority hasn't spoken."

**Segment Analyst** — cross-references with engagement data: "Loudest critics are bottom 20% by usage. Top 20% power users are silent or cautiously positive."

**Strategy Synthesizer** — produces recommendation:

```
Day 1-3: Vocal minority drives negative narrative
Day 4-7: Power user analyses shift discourse  
Day 14: Stabilizes ~40% negative, 35% positive, 25% neutral

RISK: Influencer @devtools_sarah (18k followers) hasn't posted.
Profile suggests she cares about transparency. Direct pre-brief 
from founder could preempt negative take.

RECOMMENDATION: Pre-brief top 10 users, publish "why" post 
before announcement, don't over-respond to loud minority.
```

Run again with pre-briefing strategy. Do power users shape narrative earlier?

### Example 3 — "Discover patterns in misinformation correction"

World: 500 actors on Reddit + Twitter. Misinformation enters day 3, correction published day 5 by credible source.

**Data Collection agent** — logs every post, share, reaction. Tracks who saw misinfo, who saw correction, who saw both.

**Network Analysis agent** — maps propagation: "Misinfo reached 340 actors via 4 paths. Correction reached 180 via 2 paths. 160 actors saw misinfo but never saw correction — concentrated in the most insular cluster."

**Pattern Discovery agent** — finds unexpected patterns:

```
1. CORRECTION ASYMMETRY
   Misinfo reached 68% of actors. Correction reached 36%.

2. BRIDGE ACTOR BEHAVIOR
   Of 15 bridge actors: 11 shared misinfo, 4 shared correction, 
   0 shared both. Bridges don't self-correct publicly.

3. UNEXPECTED: "SILENT CORRECTION"
   23 actors who saw both quietly stopped sharing misinfo 
   but never publicly corrected. Invisible in engagement 
   metrics, visible only in activity timeline.

4. TEMPORAL FINDING
   Corrections within 2hrs reached 52% of affected actors.
   After 24hrs: only 19%. Inflection point around hour 6.

FOLLOW-UP: Run with correction at hour 1, 3, 6, 12, 24 
to map the decay curve.
```

Finding #3 ("silent correction") — nobody would have hypothesized this. It emerged from agents analyzing emergent actor behavior. The data was rich enough (full activity timelines) and the world realistic enough that the Pattern Discovery agent noticed something the researchers didn't ask about.

---

## Part 5: The Six Presets — Cognitive Operations

The presets define six fundamental cognitive operations that multi-specialist teams perform. Each produces a concrete deliverable.

| Preset | Operation | Specialists | Output |
|--------|-----------|-------------|--------|
| `synthesis` | Integrate diverse knowledge | lead-researcher, atmospheric-physicist, oceanographer, statistician | Unified research finding with multi-perspective analysis |
| `decision` | Weigh trade-offs | product-lead, engineer, designer | Decision with explicit rationale and preserved dissent |
| `prediction` | Forecast under uncertainty | macro-economist, technical-analyst, risk-analyst | Prediction with confidence intervals, risk factors, disagreement |
| `brainstorm` | Generate and refine ideas | creative-director, copywriter, social-media-specialist | Ranked creative concepts refined through collaborative tension |
| `recommendation` | Prioritize and route | support-lead, senior-agent, junior-agent + Zendesk service | Prioritized action plan grounded in real service data |
| `assessment` | Evaluate systematically | security-lead, network-engineer, compliance-officer | Findings with severity ratings, ownership, remediation |

### What this means for end users

The user doesn't think about "building agents." They think: "I have a question / problem / situation, what kind of team would I send to figure it out?"

**Individual use cases:**

- Indie dev choosing a tech stack → `decision` preset with backend-engineer, frontend-specialist, devops-engineer
- Investor evaluating a company → `assessment` with financial-analyst, market-researcher, technical-dd
- Writer developing a story → `brainstorm` with plot-architect, character-developer, dialogue-specialist
- Student studying for exam → `synthesis` with subject-expert, pedagogy-specialist, exam-strategy-coach
- OSS maintainer reviewing a major PR → `assessment` with architecture-reviewer, security-reviewer, api-design-reviewer

**Research use cases:**

- Market behavior study → `prediction` with specialists analyzing a world full of trading actors
- Social dynamics study → `synthesis` with specialists analyzing a world full of social actors
- Policy impact study → `prediction` with specialists analyzing a world full of citizen actors

**Business use cases:**

- New market exploration → `prediction` with market-analyst, customer-researcher, competitive-intelligence
- Content strategy → `brainstorm` with creative-director, copywriter, growth-hacker analyzing a social world
- Security audit → `assessment` with security-lead, network-engineer, compliance-officer examining a system world

### Why this is different from asking a single LLM

When you ask Claude "evaluate this market opportunity," you get one voice pretending to consider multiple perspectives. A monologue styled as analysis.

When Terrarium runs a `prediction` preset, each agent independently analyzes different data streams, forms their own view, posts to shared channels, reads each other's findings, challenges assumptions, and the lead synthesizes — preserving disagreements.

The output has genuine intellectual structure: "The macro-economist sees X because of data A. The technical-analyst sees Y because of data B. These contradict on Z. Prediction weights X at 60%, Y at 40% because of W. Risk-analyst flags: if assumption Q is wrong, both are invalidated."

That structure comes from the process — multiple agents with different data access, different analytical frameworks, and genuine disagreement — not from prompting one model to "consider multiple perspectives."

### The CLI experience

```bash
# Market prediction with a living world
terrarium run --preset prediction \
  --world "Tech sector, Q4 earnings, NVDA AAPL TSLA, 
           flash crash Wednesday, false rumor Thursday" \
  --actors macro-economist technical-analyst risk-analyst

# Security assessment
terrarium run --preset assessment \
  --world "Microservices, 12 services, public API gateway, 
           3 databases, AWS deployment" \
  --actors security-lead network-engineer compliance-officer

# Creative brainstorm grounded in a social world
terrarium run --preset brainstorm \
  --world "Dev tool launch, backend engineers, competitors X Y, 
           budget $500, Twitter Reddit HN" \
  --actors creative-director copywriter growth-hacker
```

The output isn't a report card. It's the deliverable itself — produced by specialists who collaborated inside a world grounded in the data and context provided.

---

## Part 6: Two Modes of Terrarium

| | Mode 1: Agent Testing | Mode 2: Collaborative Intelligence |
|---|---|---|
| **What enters the world** | Your external agent | Internal specialist agents |
| **What the world provides** | The environment to test against | The data/phenomena to analyze |
| **Who are the actors** | Simulated people your agent interacts with | The phenomenon being studied |
| **What's produced** | A report card (governance score, behavioral analysis) | A deliverable (synthesis, decision, prediction, etc.) |
| **The question answered** | "Is my agent production-ready?" | "What does this team of specialists conclude about this situation?" |
| **User mindset** | "Test my thing" | "Solve my problem" |

Mode 1 is a testing tool. Mode 2 is a thinking machine.

Both use the same world engine, same service packs, same actor system, same World Animator. The difference is what you put inside and what you expect to get out.

---

## Summary

**Terrarium is not an agent framework.** It's a causal simulation engine for systems that involve communication, decisions, and consequences.

The primitive isn't "agent." The primitive is **world** — a reality with services, actors, events, policies, and information physics.

What you do with that world is up to you:

- Put your AI agent in it → **agent testing**
- Fill it with actors and observe → **behavioral research**
- Run it forward from conditions → **outcome prediction**
- Interact with it yourself → **training and practice**
- Harvest its output → **synthetic data generation**
- Model a system inside it → **design validation**
- Staff it with specialist agents → **collaborative intelligence**

Multi-agent frameworks give you orchestration. Terrarium gives you a world. Orchestration has known outcomes (task completed or not). A world has emergent outcomes (things happen that nobody designed or predicted).

The real value: simulate your reality, and discover what you don't know you don't know.
