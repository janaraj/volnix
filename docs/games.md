# Games

A **game** in Volnix is a run mode where agents compete through structured tool calls, are **scored**, and a **winner** is declared (or a behavioral report is produced). Games sit on top of the same world engine, the same 7-step governance pipeline, and the same internal-agent framework — they just add a structured tool surface, a scoring strategy, and an event-driven orchestrator that declares termination.

Use a game when you want to evaluate agent behavior under structured competition (negotiation, auction, debate, trading) — anywhere outcomes can be scored and compared move-by-move.

> **Player scope:** game players are **internal agents** declared in an `agents_*.yaml` profile. The `GameOrchestrator` activates them via the `AgencyActivationProtocol` — no external gateway or MCP agent plug-in yet. That's a future enhancement.

> **Event-driven, not round-based.** Cycle B rewrote the game engine from the old round-based `GameRunner`/`TurnManager` design to a pure event-driven model. There are no rounds, no turns, no between-round hooks. The orchestrator subscribes to committed game-tool events on the bus, scores each event, checks win conditions, and re-activates the next player — immediately, whenever an event commits.

---

## Overview

```
World (compiled from YAML)
  |
  +-- game.enabled: true            <-- this is what makes it a game
  +-- game.mode: negotiation        <-- which game type
  +-- game.scoring_mode: behavioral | competitive
  +-- game.flow.max_events: 40      <-- bounded duration (event count)
  +-- game.negotiation_fields: [...] <-- typed tool parameters (NF1)
  |
Internal agents (the players)
  |
  +-- buyer-794aad24                <-- per-agent LLM provider/model + thinking
  +-- supplier-99b0e8da
  |
  v
GameOrchestrator (event-driven)
  |
  +-- _on_start kickstart: publishes GameKickstartEvent, flips gate,
  |     schedules failsafe timers, activates the first mover
  |
  +-- Bus subscription to world.negotiate_* events:
  |     +-- score the event via the configured scorer
  |     +-- publish GameScoreUpdatedEvent per player
  |     +-- check win conditions via WinConditionEvaluator
  |     +-- if natural win → _terminate_natural (Path A)
  |     +-- else re-activate the next player via agency
  |
  +-- Failsafe timers (wall_clock, stalemate, max_events, all_budgets)
        all converge on _handle_timeout (Path B) which settles open
        deals and terminates
  |
  v
GameTerminatedEvent (winner, reason, standings, behavior_scores)
  |
  v
Deliverable (standings or behavior report) + event log + causal graph
```

Game-move tools are **first-class structured tool calls** the LLM makes natively (e.g. `negotiate_propose(deal_id, price, delivery_weeks, ...)`). The LLM provider validates each call's JSON Schema before the call ever reaches Volnix — there is no regex parsing of chat messages.

---

## Game vs. regular internal agents

Games **are** internal agents — same `agents_*.yaml`, same agency engine, same governance pipeline. The differences:

| Concern | Internal agents (no game) | Internal agents (game) |
|---|---|---|
| Activation | Event-driven (world happens, agent reacts) | Event-driven (game move commits, orchestrator activates the next player) |
| Lead agent | Coordinates a multi-phase lifecycle | None — players are peers |
| Output | Deliverable (synthesis, prediction, ...) | Deliverable + standings (competitive) or behavior report (behavioral) |
| Scoring | Governance scorecard (policy compliance, budget discipline, ...) | Governance scorecard + game-specific scoring (deal scoring + BATNA, or behavior metrics) |
| Tools | Service-pack tools (Slack, Stripe, ...) | Service-pack tools **plus** typed game-move tools (`negotiate_propose`, ...) |
| Termination | Run to completion | Natural win (e.g. `deal_closed`) or failsafe timeout |

Players can still post chat messages alongside their game moves for in-character framing. The chat is decorative — the structured tool call is what gets scored.

---

## Defining a game

Add a `game:` block to your world YAML. The shape below is the full event-driven schema that Cycle B and its cleanup (B-cleanup.1) stabilized.

```yaml
world:
  name: "Q3 Steel Supply Contract"
  description: >
    Buyer and supplier negotiate price, delivery, payment terms, warranty.

  services:
    slack: verified/slack

  # ... seeds, policies, behavior, reality ...

  game:
    enabled: true
    mode: negotiation                 # which game type
    scoring_mode: competitive         # or "behavioral"

    # Dynamic tool schema (NF1). Each field becomes a typed, REQUIRED
    # parameter on negotiate_propose / negotiate_counter.
    negotiation_fields:
      - name: price
        type: number                  # number | integer | string | boolean
        description: "USD per ton"
      - name: delivery_weeks
        type: integer
        description: "Weeks from order confirmation"
      - name: payment_days
        type: integer
      - name: warranty_months
        type: integer
      # string type can also carry an enum:
      # - name: freight_mode
      #   type: string
      #   enum: [sea, air, rail]

    flow:
      type: event_driven
      max_wall_clock_seconds: 900     # hard wall-clock budget for the game
      max_events: 40                  # hard cap on committed game-tool events
      stalemate_timeout_seconds: 240  # silence timeout (no game events)
      activation_mode: serial         # or "parallel"
      first_mover: buyer              # role or actor_id — required for serial
      bonus_per_event: 0.35           # competitive efficiency bonus per event saved
      reactivity_window_events: 5     # behavioral reactivity window
      state_summary_entity_types:
        - negotiation_deal

    entities:
      deals:
        - id: deal-q3-steel
          title: "Q3 Steel Supply"
          parties: [buyer, supplier]
          status: open
          consent_rule: unanimous     # or "majority"
      player_briefs:
        - actor_role: buyer
          deal_id: deal-q3-steel
          brief_content: "You are the procurement lead for Atlas..."
          mission: "Close the best deal for Atlas."
        - actor_role: supplier
          deal_id: deal-q3-steel
          brief_content: "You are the sales director at Vulcan..."
          mission: "Maximize revenue for Vulcan."
      # target_terms is only used in scoring_mode=competitive
      target_terms:
        - actor_role: buyer
          deal_id: deal-q3-steel
          ideal_terms: {price: 85, delivery_weeks: 3}
          term_weights: {price: 0.6, delivery_weeks: 0.4}
          term_ranges: {price: [80, 120], delivery_weeks: [2, 8]}
          batna_score: 25

    win_conditions:
      - type: deal_closed             # natural win (Path A)
      - type: deal_rejected           # natural win (Path A)
      - type: stalemate_timeout       # timeout (Path B)
      - type: wall_clock_elapsed      # timeout (Path B)
      - type: max_events_exceeded     # timeout (Path B)
      - type: all_budgets_exhausted   # timeout (Path B)
      - type: score_threshold         # competitive only
        metric: total_points
        threshold: 90
```

### Legacy round-based keys are rejected

Blueprints that still declare `rounds`, `turn_protocol`, `between_rounds`, or `resource_reset_per_round` raise `YAMLParseError` at compile time. Migrate to `flow.type: event_driven` + `game.entities` + `game.negotiation_fields`.

---

## Scoring modes

`scoring_mode` is a top-level routing switch with exactly two values. Pick at game configure time.

| Mode | Scorer | Output | Use case |
|---|---|---|---|
| `behavioral` | `BehavioralScorer` | Per-player behavior metrics (query quality, reactivity to animator events, policy compliance, final-terms match to state). No leaderboard. | Evaluating agent behavior in messy/hostile worlds where the "right" deal depends on facts only discoverable at runtime. |
| `competitive` | `CompetitiveScorer` | Ranked leaderboard with `deal_score` + efficiency bonus + BATNA on timeout. Requires `entities.target_terms`. | Head-to-head zero-sum negotiation where each player has ideal terms + BATNA. |

**Competitive efficiency bonus** is event-count based:
```
efficiency_bonus = max(0, (flow.max_events - event_number) * flow.bonus_per_event)
```
Closing early earns a meaningful premium; closing at event 40/40 earns zero.

**Behavioral mode never reads** `target_terms`, `ideal_terms`, `term_weights`, `term_ranges`, or `batna_score`. Those fields are silently dropped at materialization if declared in behavioral mode.

---

## Per-agent LLM config

Games are the place where per-agent LLM configuration matters most. Different players can run on different providers and different models and be compared apples-to-apples in the same event-driven contest.

```yaml
agents:
  - role: buyer
    llm:
      provider: anthropic
      model: claude-sonnet-4-6
      thinking:
        enabled: true
        budget_tokens: 4096
    permissions: { read: [slack, notion, game], write: [slack, game] }
    budget: { api_calls: 30, spend_usd: 3 }

  - role: supplier
    llm:
      provider: gemini
      model: gemini-3-flash-preview
    permissions: { read: [slack, notion, game], write: [slack, game] }
    budget: { api_calls: 30, spend_usd: 3 }
```

A few things to note:

- **Both players need `write: [game]`** in their permissions — game tools live in the `game` service namespace, scoped by the same permission engine that handles every other action.
- **Claude extended thinking is opt-in** via `llm.thinking.enabled: true`. The Anthropic provider handles the API constraints automatically.
- **Different providers in the same game work fine.** Each provider builds its own function-calling payload from the same internal `ToolDefinition`, with the same typed `negotiation_fields` shape.

See [docs/llm-providers.md](llm-providers.md) for the full list of supported providers.

---

## Structured game-move tools (NF1)

At game configure time, `VolnixApp.configure_game` calls `volnix.packs.verified.game.tool_schema.build_negotiation_tools(game_def.negotiation_fields)` and registers the resulting tool dicts on the agency via `AgencyEngine.register_game_tools(actions)`. The agency layers the standard meta-params (`reasoning`, `intended_for`, `state_updates`) onto each tool's parameters and wraps them in `ToolDefinition` instances.

When `negotiation_fields` is empty, the builder returns the static fallback (`deal_id` + `message` only, with `additionalProperties: True`) — pre-NF1 shape, preserved for backward compat.

For a blueprint that declares 4 negotiation fields (`price`, `delivery_weeks`, `payment_days`, `warranty_months`):

| Tool | Typed parameters (required) | Terminal? |
|---|---|---|
| `negotiate_propose` | `deal_id`, `price`, `delivery_weeks`, `payment_days`, `warranty_months`, `reasoning` | No |
| `negotiate_counter` | (same as propose; same field set required) | No |
| `negotiate_accept` | `deal_id`, `reasoning` | Yes — closes the deal |
| `negotiate_reject` | `deal_id`, `reasoning` | Yes — walks away |

Optional params across all four tools: `message` (one-sentence in-character framing), `intended_for`, `state_updates`.

Because these are typed tool calls, the LLM provider enforces the schema before Volnix sees the args. There is no regex parsing, no chance of malformed JSON, and no silent drops. The game pack's handlers in `volnix/packs/verified/game/handlers.py` write `negotiation_deal` and `negotiation_proposal` state deltas through the pipeline commit step (MF1).

---

## Win conditions

Win conditions come in two families.

**Path A — natural win (no settlement):**

| Type | Trigger | Outcome |
|---|---|---|
| `deal_closed` | Any `negotiation_deal.status == "accepted"` | Game terminates, reason=`deal_closed`, competitive winner = highest total_score |
| `deal_rejected` | Any `negotiation_deal.status == "rejected"` | Game terminates, reason=`deal_rejected`, winner=None |
| `score_threshold` (competitive only) | A player's `total_points` crosses `threshold` | Game terminates, top scorer wins |
| `elimination` | Remove players below `threshold`; last standing wins | Game terminates when one player remains |

**Path B — failsafe timeout (with settlement):**

| Type | Trigger | Outcome |
|---|---|---|
| `wall_clock_elapsed` | `flow.max_wall_clock_seconds` elapsed | Scorer `settle()` runs (BATNA in competitive mode) → terminates |
| `stalemate_timeout` | No game events for `flow.stalemate_timeout_seconds` | Same settle + terminate |
| `max_events_exceeded` | `event_counter >= flow.max_events` | Same settle + terminate |
| `all_budgets_exhausted` | Every player's `world_actions` budget exhausted | Same settle + terminate |

**M2 (B-cleanup.3): natural-win priority.** If a timeout event and a natural win race on different bus consumer tasks, `_handle_timeout` runs the win evaluator first. If a natural win condition is satisfied at the moment of timeout, the game terminates via Path A with the natural reason (e.g. `deal_closed`) rather than misreporting the racing timer's reason.

### GameActivePolicy

After termination the orchestrator flips a `GameActivePolicy` gate via two mechanisms:
1. **Direct** — calls `gate.set_active(False)` on the injected `_dependencies["game_active_gate"]` reference, synchronously.
2. **Bus** — publishes `GameActiveStateChangedEvent(active=False)` for any other subscriber.

Any late `negotiate_*` tool call from an agent that was mid-activation at termination time is rejected by the policy step with a `PolicyBlockEvent`.

---

## Built-in game blueprints

| Blueprint | Mode | Players | Description |
|---|---|---|---|
| `negotiation_competition` | negotiation (competitive) | buyer, supplier | Two-party Q3 Steel contract: price, delivery, payment terms, warranty |
| `supply_chain_disruption` | negotiation (behavioral) | nimbus_buyer, haiphong_supplier | Emergency PWR-7A purchase with typhoon + port closure + CFO cap |

Run either:

```bash
volnix serve volnix/blueprints/official/negotiation_competition.yaml \
  --internal volnix/blueprints/official/agents_negotiation.yaml \
  --port 8080
```

The game progresses through the dashboard event feed. You'll see structured `world.negotiate_propose` / `world.negotiate_counter` / `world.negotiate_accept` events alongside the game lifecycle (`game.kickstart` / `game.score_updated` / `game.active_state_changed` / `game.terminated`).

---

## Building a new game type

Adding a new game type is a small, bounded change under the event-driven model. The pieces:

1. **Structured tools.** If your game is a variant of negotiation, just declare different `negotiation_fields` in the blueprint — the builder already handles everything. For a genuinely new shape (auction bids, trading orders), extend `NegotiationField` or add a sibling builder in `volnix/packs/verified/game/`.

2. **Scorer.** If neither `BehavioralScorer` nor `CompetitiveScorer` fits, add a new class implementing the `GameScorer` protocol in `volnix/engines/game/scorers/`:
   ```python
   from volnix.engines.game.scorers.base import GameScorer, ScorerContext

   class AuctionScorer(GameScorer):
       async def score_event(self, ctx: ScorerContext) -> None:
           """Update player_scores based on this single committed event."""
           ...

       async def settle(
           self, open_deals, state_engine, player_scores, definition
       ) -> None:
           """Finalize scores when the game times out (Path B)."""
           ...
   ```
   Wire it into `GameOrchestrator.configure` routing based on a new `scoring_mode` literal.

3. **Win condition handlers.** If your game needs a new condition, add a handler in `volnix/engines/game/win_conditions.py` and register it in `WIN_CONDITION_HANDLER_REGISTRY`.

4. **Entity schemas.** Add new entity schemas to the game pack if your game writes a different entity shape. Write state deltas via `ResponseProposal.proposed_state_deltas` from pack handlers — the orchestrator NEVER writes entity state directly (MF1).

No changes to the orchestrator lifecycle, the pipeline, the agency engine, the bus, or the policy engine are needed. The event-driven architecture is general — only the scorer and the structured tools are game-specific.

---

## What you get out of a game run

Every game produces:

- **Lifecycle events**: `game.kickstart` / `game.score_updated` / `game.active_state_changed` / `game.terminated` / `game.timeout` / `game.engine_error` in the run event log.
- **Committed tool events**: `world.negotiate_propose` / `world.negotiate_counter` / `world.negotiate_accept` / `world.negotiate_reject` with typed `input_data`.
- **Standings** (competitive mode) — ordered players with total_score + per-metric breakdown + BATNA annotations.
- **Behavior scores** (behavioral mode) — per-player metrics: world_queries_total, unique_services_queried, reactions_to_animator, policy_compliance, final_terms_match_state.
- **Deliverable** — standings table or behavior report + game-type extras.
- **Causal graph** — every game move flows through the full 7-step governance pipeline, so you can trace why each move was committed (or blocked, or escalated).
- **Per-actor governance scorecard** — policy compliance, budget discipline, action effectiveness, just like any other run.

You can replay a game's state.db, build a counterfactual snapshot, or compare runs across different LLM providers head-to-head.

---

## See also

- [Internal Agents](internal-agents.md) — the underlying agent framework games are built on
- [LLM Providers](llm-providers.md) — picking models for different players
- [Architecture](architecture.md) — the engines that make games work
- [Blueprints Reference](blueprints-reference.md) — full catalog of game and non-game blueprints
