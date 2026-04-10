# Games

A **game** in Volnix is a run mode where agents take **turns**, are **scored**, and a **winner** is declared. Games sit on top of the same world engine, the same 7-step pipeline, the same internal-agent infrastructure — but add round structure, structured move tools, win conditions, and a per-game-type evaluator that interprets each round.

Use a game when you want to evaluate agent behavior under structured competition (negotiation, auction, debate, trading) — anywhere outcomes can be scored and compared turn-by-turn.

> **Player scope (today): internal agents only.** The game runner activates each player synchronously by calling `agency.activate_for_game_turn()` per turn. External (gateway) agents connect via MCP/REST and push actions asynchronously, so they don't have a turn-activation entry point yet. The structured tools, evaluator, scoring, and full governance pipeline are caller-agnostic — adding external players is a future enhancement (turn coordination + a per-turn endpoint with timeout fallback), not an architectural rework.

---

## Overview

```
World (compiled from YAML)
  |
  +-- game.enabled: true            <-- this is what makes it a game
  +-- game.mode: negotiation        <-- which game type
  +-- game.rounds.count: 8          <-- bounded duration
  |
Internal agents (the players)
  |
  +-- buyer-794aad24                <-- per-agent LLM provider/model + thinking
  +-- supplier-99b0e8da
  |
  v
GameRunner
  |
  +-- For each round:
  |     +-- Activate each player in turn
  |     +-- Player calls structured tools (negotiate_propose, ...)
  |     +-- Round evaluator processes events, updates state, scores
  |     +-- Check win conditions (early termination)
  |
  v
GameResult (winner, standings, deals/bids/etc.)
  |
  v
Deliverable (standings table + game-type-specific summary)
```

A game's tools are **first-class structured tool calls** the LLM makes natively (e.g. `negotiate_propose(deal_id, price, delivery_weeks, ...)`). The LLM provider validates the tool's JSON Schema before the call ever reaches Volnix — there is no regex parsing of chat messages.

---

## Game vs. Internal Agents

Games **are** internal agents — same `agents:` YAML, same agency engine, same governance pipeline. The differences are:

| Concern | Internal agents (no game) | Internal agents (game) |
|---|---|---|
| Activation | Event-driven (something happens, an agent reacts) | Turn-based (round runner activates each player) |
| Lead agent | Coordinates a 4-phase lifecycle | None — players are peers |
| Output | Deliverable (synthesis, prediction, ...) | Deliverable + standings + winner |
| Scoring | Governance scorecard (policy compliance, budget, ...) | Governance scorecard + game-type scoring (deal score, BATNA, ...) |
| Tools | Service-pack tools (Slack, Stripe, ...) | Service-pack tools **plus** game-type tools (`negotiate_propose`, ...) |
| Termination | Run to completion | Win condition can terminate early (e.g. deal accepted) |

You can mix the two — a game can still use Slack to chat in-character alongside its structured moves. The chat is decorative; the game moves are what get scored.

---

## Defining a Game

Add a `game:` block to your world YAML:

```yaml
world:
  name: "Supply Chain Negotiation"
  description: >
    A procurement negotiation between a buyer and supplier.

  services:
    slack: verified/slack

  # ... seeds, policies, behavior, reality ...

  game:
    enabled: true
    mode: negotiation               # which game type (plug-in lookup)
    turn_protocol: independent      # how players are activated within a round
    rounds:
      count: 8                      # max rounds before forced end
      actions_per_turn: 3           # action budget per player per round
      simultaneous: false           # players act sequentially

    resource_reset_per_round:
      api_calls: 3                  # refresh action budget each round

    scoring:
      metrics:
        - name: total_points
          source: state             # read from state entity
          entity_type: negotiation_scorecard
          field: total_points
          weight: 1.0
      ranking: descending           # higher wins

    win_conditions:
      - type: score_threshold       # first player past threshold wins
        metric: total_points
        threshold: 0.01
      - type: rounds_complete       # fallback: highest after all rounds

    between_rounds:
      animator_tick: false          # no organic events between rounds
      announce_scores: true         # publish standings to team channel
      evaluator: negotiation        # which round evaluator to use
```

The game runs once per simulation. When the win condition fires (or all rounds complete), the runner emits a `game.completed` event with the winner, standings, and reason.

---

## Per-agent LLM config

Games are the place where per-agent LLM configuration matters most. Different players can run on different providers, different models, or with different reasoning settings — and you can compare them apples-to-apples in the same round-based contest.

```yaml
agents:
  - role: buyer
    llm:
      model: claude-sonnet-4-6
      provider: anthropic
      thinking:
        enabled: true                 # Claude extended thinking
        budget_tokens: 4096           # min 1024; provider clamps if lower
    permissions: { read: [slack], write: [slack, game] }
    budget: { api_calls: 30, spend_usd: 3 }

  - role: supplier
    llm:
      model: gemini-3-flash-preview
      provider: gemini
    permissions: { read: [slack], write: [slack, game] }
    budget: { api_calls: 30, spend_usd: 3 }
```

A few things to note:

- **Both players need `write: [game]`** in their permissions — game tools live in the `game` service namespace, scoped by the same permission engine that handles every other action.
- **Claude extended thinking is opt-in** via `llm.thinking.enabled: true`. The Anthropic provider handles all the API constraints automatically: thinking blocks are round-tripped across multi-turn tool loops, `temperature` is forced to `1.0`, and `max_tokens` is bumped above the thinking budget. Default `budget_tokens: 4096` is a sensible starting point.
- **Different providers in the same game work fine.** The framework validates each provider's tool schemas independently (Gemini gets a strict subset, Anthropic gets `additionalProperties: false`), and each provider builds its own message format from the same internal representation.

See [docs/llm-providers.md](llm-providers.md) for the full list of supported providers.

---

## Structured game-move tools

Each game type registers its own tools at game start. The agents see them in their tool list alongside normal service tools and call them natively.

For negotiation, the tools are:

| Tool | Args | Purpose |
|---|---|---|
| `negotiate_propose` | `deal_id`, `price`, `delivery_weeks`, `payment_days`, `warranty_months`, `message?` | Make an opening offer |
| `negotiate_counter` | (same as propose) | Counter the other party's offer |
| `negotiate_accept` | `deal_id`, `message?` | Accept the deal at current terms (closes it) |
| `negotiate_reject` | `deal_id`, `message?` | Reject and walk away (BATNA fallback) |

Because these are typed tool calls, the LLM provider enforces the schema before Volnix sees the args. There is no regex parsing, no chance of malformed JSON, no silent drops. The round evaluator reads the committed action events directly with already-typed `input_data`.

Agents can still post chat messages alongside their moves for in-character framing — but the chat is decorative. The structured tool call is what gets scored.

---

## Win conditions

Built-in win condition handlers:

| Type | What it does |
|---|---|
| `score_threshold` | First player whose metric crosses `threshold` wins. When multiple cross simultaneously, the highest scorer wins. |
| `rounds_complete` | After `rounds.count` rounds, the highest scorer wins. Use as a fallback. |
| `elimination` | Remove players whose metric falls below `threshold`. Last standing wins. |
| `time_limit` | (Reserved for future use.) |

You can stack multiple win conditions. They're evaluated in order — the first that fires terminates the game.

---

## Built-in game blueprints

| Blueprint | Game type | Players | Description |
|---|---|---|---|
| `negotiation_competition` | negotiation | buyer, supplier | Two-party contract negotiation: price, delivery, payment terms, warranty |
| `trading_competition` | (rounds-based scoring on portfolio value) | 4 traders | Day-trading on Alpaca with elimination at $50k floor |

```bash
volnix serve negotiation_competition --internal agents_negotiation --port 8080
```

The game progresses round-by-round in the dashboard event feed. You'll see structured `world.negotiate_propose` / `world.negotiate_counter` / `world.negotiate_accept` events alongside the `game.round_started` / `game.round_ended` / `game.completed` lifecycle.

---

## Building a new game type

Adding a new game type is a **single-file change**. Create `volnix/game/evaluators/my_game.py`:

```python
from volnix.game.evaluators.base import BaseRoundEvaluator
from volnix.llm.types import ToolDefinition

# 1. Define your structured tools
MY_GAME_TOOLS: list[ToolDefinition] = [
    ToolDefinition(
        name="my_action",
        service="game",
        description="Take an action in the game.",
        parameters={
            "type": "object",
            "required": ["target"],
            "properties": {
                "target": {"type": "string"},
                "value": {"type": "number"},
            },
            "additionalProperties": False,
        },
    ),
]


class MyGameEvaluator(BaseRoundEvaluator):
    def game_tools(self) -> list[ToolDefinition]:
        return MY_GAME_TOOLS

    async def evaluate(
        self,
        state_engine,
        round_events,
        round_state,
        player_scores,
    ) -> None:
        """Process this round's committed events and update state/scores."""
        for event in round_events:
            if event.event_type == "world.my_action":
                # event.input_data is the typed payload
                target = event.input_data.get("target")
                value = event.input_data.get("value", 0)
                # ... your game logic ...

    async def build_deliverable_extras(self, state_engine) -> dict:
        """Return game-type-specific summary for the run deliverable."""
        return {"results": [...]}
```

Register it in the lazy-load block at `volnix/game/runner.py`:

```python
ROUND_EVALUATOR_REGISTRY["my_game"] = MyGameEvaluator
```

Then point a world's `game.between_rounds.evaluator` at `my_game`. **Zero changes to the game framework, the agency engine, or any pipeline step** — the registries handle the rest.

---

## What you get out of a game run

Every game produces:

- **`game.started` / `game.round_started` / `game.round_ended` / `game.completed`** events in the run event log
- **`game.score_updated`** events as players gain or lose points
- **Standings** — sorted players with rank, total score, and per-metric breakdown
- **Deliverable** — standings table + game-type extras (for negotiation: the deals reached, accepted by whom, in which round, with the final terms)
- **Causal graph** — every game move flows through the full 7-step governance pipeline, so you can trace why each move was committed (or blocked, or escalated)
- **Per-actor governance scorecard** — policy compliance, budget discipline, action effectiveness, just like any other run

You can replay a game's state.db, build a counterfactual snapshot, or compare runs across different LLM providers head-to-head.

---

## See also

- [Internal Agents](internal-agents.md) — the underlying agent framework games are built on
- [LLM Providers](llm-providers.md) — picking models for different players
- [Architecture](architecture.md) — the engines that make games work
- [Blueprints Reference](blueprints-reference.md) — full catalog of game and non-game blueprints
