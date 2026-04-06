# Configuration

Volnix uses a layered TOML configuration system. This guide covers every configuration section and how to customize Volnix for your needs.

---

## Config Layers

Configuration is loaded in order, with later layers overriding earlier ones:

| Priority | File | Purpose |
|----------|------|---------|
| 1 (lowest) | `volnix.toml` | Base defaults (shipped with the package) |
| 2 | `volnix.{env}.toml` | Environment overlay (e.g., `volnix.production.toml`) |
| 3 | `volnix.local.toml` | Machine-specific overrides (git-ignored) |
| 4 (highest) | `VOLNIX__section__key` | Environment variable overrides |

Select the environment with the `--env` flag:

```bash
volnix run world.yaml --env production    # loads volnix.production.toml
volnix serve world.yaml --env staging     # loads volnix.staging.toml
```

---

## Environment Variables

API keys and secrets are loaded from environment variables (or a `.env` file):

```bash
# LLM provider keys
ANTHROPIC_API_KEY=sk-ant-...
OPENAI_API_KEY=sk-proj-...
GOOGLE_API_KEY=AIza...

# ACP agent servers (optional)
ACP_CLAUDE_URL=http://localhost:3000
ACP_CODEX_URL=http://localhost:3001

# Testing (optional)
VOLNIX_RUN_REAL_API_TESTS=1
```

Copy `.env.example` to `.env` and fill in your keys. The `.env` file is git-ignored by default.

Any config key can be overridden via environment variables using double-underscore notation:

```bash
# Override simulation seed
VOLNIX__simulation__seed=123

# Override adapter port
VOLNIX__adapter__port=9000
```

---

## Data Directory

Volnix stores all runtime data under `~/.volnix/`:

```
~/.volnix/
  data/
    bus.db              # Event bus persistence
    ledger.db           # Audit log
    state.db            # Entity state
    runs/               # Per-run artifacts
    worlds/             # Compiled world definitions
    snapshots/          # State snapshots
    llm_debug/          # LLM request/response logs
  blueprints/           # User-created world blueprints
  presets/              # User-created reality presets
```

Override the base directory with the `VOLNIX_HOME` environment variable.

---

## Configuration Sections

### Simulation

```toml
[simulation]
time_speed = 1.0                    # 1.0 = real-time, 2.0 = double speed
mode = "governed"                   # "governed" | "ungoverned"
behavior = "dynamic"                # "static" | "reactive" | "dynamic"

[simulation.reality]
preset = "messy"                    # "ideal" | "messy" | "hostile"

[simulation.fidelity]
mode = "auto"                       # "auto" | "strict" | "exploratory"
```

### Simulation Runner

Controls end conditions and safety rails for the simulation loop:

```toml
[simulation_runner]
max_logical_time = 86400.0          # Max simulated time (seconds)
max_total_events = 50               # Hard cap on committed events
max_ticks = 30                      # Hard tick limit (internal-only worlds)
max_envelopes_per_event = 20        # Max responses per committed event
max_actions_per_actor_per_window = 100  # Runaway protection per actor
loop_breaker_threshold = 50         # Max internal events without external input
animator_tick_interval = 5          # Animator fires once per N ticks (prevents feedback loops)
```

### Pipeline

The 7-step governance pipeline:

```toml
[pipeline]
steps = [
    "permission",
    "policy",
    "budget",
    "capability",
    "responder",
    "validation",
    "commit",
]
side_effect_max_depth = 3
timeout_per_step_seconds = 30
```

### Engine-Specific Settings

#### Policy Engine
```toml
[policy]
condition_timeout_ms = 500          # Max time to evaluate a policy condition
max_policies_per_action = 50        # Safety limit
```

#### Permission Engine
```toml
[permission]
cache_ttl_seconds = 300             # Permission cache lifetime
```

#### Budget Engine
```toml
[budget]
warning_threshold_pct = 80          # Emit warning at 80% usage
critical_threshold_pct = 95         # Emit critical at 95% usage
```

#### Responder Engine
```toml
[responder]
max_retries = 2                     # Retry failed service responses
fallback_enabled = true             # Fall back to generic response on failure
```

#### Animator Engine
```toml
[animator]
creativity_budget = 0.3             # Fraction of LLM budget for environment events
intensity = 0.5                     # 0.0 = minimal, 1.0 = maximal event generation
enabled = true
```

#### Agency Engine
```toml
[agency]
frustration_threshold_tier3 = 0.7   # Promote actor to Tier 3 at this frustration
batch_size = 5                      # Max actors per batch LLM call
max_concurrent_actor_calls = 20     # Semaphore limit for parallel LLM calls
max_recent_interactions = 20        # Conversation history per actor
max_tool_calls_per_activation = 20  # Max tool calls an agent can make per activation
collaboration_mode = "tagged"       # "tagged" | "open"
collaboration_enabled = true        # Enable subscription-based activation
synthesis_buffer_pct = 0.10         # Reserve 10% of ticks for deliverable synthesis
```

### Adapter (Protocol Servers)

```toml
[adapter]
protocols = ["mcp", "http"]         # Active protocols
host = "0.0.0.0"
port = 8100
```

### Dashboard

```toml
[dashboard]
host = "127.0.0.1"
port = 8200
enabled = false
static_dir = "volnix-dashboard/dist"
```

### Gateway

```toml
[gateway]
host = "0.0.0.0"
port = 8000
middleware = ["auth", "rate_limit", "audit_log"]
```

### External Agent Slots

```toml
[agents]
max_external_agents = 10
allow_unregistered_access = true    # Auto-register unknown agents
auto_assign_enabled = true          # Auto-assign to available slots
```

### Middleware

```toml
[middleware]
auth_enabled = false                # Enable Bearer token authentication
status_codes_enabled = true         # Translate errors to HTTP status codes
prefixes_enabled = false            # Enable service-specific URL prefixes
```

### Logging

```toml
[logging]
level = "INFO"                      # DEBUG | INFO | WARNING | ERROR
format = "text"                     # text | json
llm_debug = true                    # Write LLM request/response to data/llm_debug/
```

### Persistence

```toml
[persistence]
wal_mode = true                     # SQLite WAL mode (recommended)

[bus]
queue_size = 1000
persistence_enabled = true

[ledger]
retention_days = 90
```

---

## LLM Provider Configuration

### Provider Registry

Register providers under `[llm.providers.<name>]`:

```toml
# API-based providers
[llm.providers.anthropic]
type = "anthropic"
api_key_ref = "ANTHROPIC_API_KEY"

[llm.providers.openai]
type = "openai_compatible"
base_url = "https://api.openai.com/v1"
api_key_ref = "OPENAI_API_KEY"
timeout_seconds = 300

[llm.providers.gemini]
type = "google"
api_key_ref = "GOOGLE_API_KEY"
default_model = "gemini-2.5-flash"

# Local providers (no API key)
[llm.providers.ollama]
type = "openai_compatible"
base_url = "http://localhost:11434/v1"
api_key_ref = ""

# CLI providers (use their own auth)
[llm.providers.claude_cli]
type = "cli"
command = "claude"
args = ["-p"]

[llm.providers.codex_cli]
type = "cli"
command = "codex"
args = ["exec"]

# ACP providers (stdio JSON-RPC)
[llm.providers.codex_acp]
type = "acp"
command = "codex-acp"
timeout_seconds = 300
```

### Default Provider

```toml
[llm.defaults]
type = "acp"
provider = "codex_acp"
default_model = ""
max_tokens = 4096
temperature = 0.7
timeout_seconds = 300
```

### Task-Specific Routing

Route specific engine tasks to different providers/models:

```toml
[llm.routing.world_compiler]
provider = "gemini"
model = "gemini-3.1-flash-lite-preview"
max_tokens = 16384
temperature = 0

[llm.routing.data_generator]
provider = "gemini"
model = "gemini-3.1-flash-lite-preview"
max_tokens = 16384
temperature = 0

[llm.routing.responder_tier2]
provider = "gemini"
model = "gemini-3.1-flash-lite-preview"
max_tokens = 4096
temperature = 0.7

[llm.routing.agency_individual]
provider = "openai"
model = "gpt-5.4-mini"
max_tokens = 4096
temperature = 0

[llm.routing.agency_batch]
provider = "openai"
model = "gpt-5.4-mini"
max_tokens = 8192
temperature = 0

[llm.routing.animator]
provider = "gemini"
model = "gemini-3.1-flash-lite-preview"
max_tokens = 2048
temperature = 0.5

[llm.routing.world_compiler_policy_trigger_compilation]
provider = "openai"
model = "gpt-5.4-nano"
max_tokens = 4096
temperature = 0
```

The routing key format is `{engine_name}_{use_case}`. The router resolves by checking task-specific routing first, then falling back to defaults. See [LLM Providers](llm-providers.md) for the full provider guide and tested models.

---

## Creating Override Files

### Environment-specific config

Create `volnix.production.toml` for production settings:

```toml
[logging]
level = "WARNING"
llm_debug = false

[middleware]
auth_enabled = true

[simulation_runner]
max_total_events = 200
```

### Local overrides

Create `volnix.local.toml` (git-ignored) for your machine:

```toml
[llm.defaults]
provider = "ollama"

[dashboard]
enabled = true

[logging]
level = "DEBUG"
```

---

## Tuning Guide

### Simulation Length

| Parameter | Default | Effect | When to change |
|-----------|---------|--------|---------------|
| `max_total_events` | 50 | Hard cap on committed events | Increase for longer simulations (100-200 for complex scenarios) |
| `max_ticks` | 30 | Hard tick limit | Increase if agents need more rounds to complete mission |
| `max_logical_time` | 86400 | Simulated wall clock limit (seconds) | Rarely needs changing |

**Quick rule**: For a 3-agent team with a synthesis deliverable, 50 events / 30 ticks is usually enough. For 5+ agents or complex multi-step missions, increase to 100-150 events / 50 ticks.

### Agent Behavior

| Parameter | Default | Effect | When to change |
|-----------|---------|--------|---------------|
| `max_tool_calls_per_activation` | 20 | Max actions per agent turn | Increase if agents hit the limit before completing their task |
| `max_recent_interactions` | 20 | Conversation history window | Increase for longer conversations, decrease to reduce LLM token usage |
| `synthesis_buffer_pct` | 0.10 | Reserve last 10% of ticks for deliverable | Increase if deliverables are cut short |
| `collaboration_enabled` | true | Agents respond to each other's messages | Disable for isolated agent testing |

### Animator (Dynamic Mode)

| Parameter | Default | Effect | When to change |
|-----------|---------|--------|---------------|
| `animator_tick_interval` | 5 | Animator fires once per N ticks | Decrease for more frequent NPC events, increase for calmer worlds |
| `creativity` | medium | Event creativity level | Set in blueprint YAML, not TOML |
| `event_frequency` | moderate | How often events occur | Set in blueprint YAML |
| `escalation_on_inaction` | true | NPCs escalate if agents don't respond | Disable for less pressure |

### Budget Thresholds

| Parameter | Default | Effect | When to change |
|-----------|---------|--------|---------------|
| `warning_threshold_pct` | 80 | Emit warning event at 80% budget usage | Lower for earlier visibility |
| `critical_threshold_pct` | 95 | Emit critical event at 95% | Lower to give agents more warning before exhaustion |

### LLM Cost Control

Route expensive operations to cheaper models:

```toml
# Cheap model for world compilation and data generation
[llm.routing.world_compiler]
provider = "gemini"
model = "gemini-3.1-flash-lite-preview"

# Cheap model for policy trigger compilation
[llm.routing.world_compiler_policy_trigger_compilation]
provider = "openai"
model = "gpt-5.4-nano"

# Smarter model for agent reasoning
[llm.routing.agency_individual]
provider = "openai"
model = "gpt-4.1-mini"
```

### Performance

| Parameter | Default | Effect | When to change |
|-----------|---------|--------|---------------|
| `max_concurrent_actor_calls` | 20 | Parallel LLM calls | Decrease if hitting rate limits |
| `pipeline.timeout_per_step_seconds` | 30 | Max time per pipeline step | Increase for slow LLM providers |
| `bus.queue_size` | 1000 | Event bus queue depth | Increase for very active worlds |
