# LLM Providers

Volnix routes all LLM calls through a central router that supports multiple provider types. You can mix providers freely — use Gemini for world compilation, OpenAI for agent reasoning, and a local Ollama model for the animator.

---

## Provider Types

### API Providers

Standard cloud API providers. Require an API key set as an environment variable.

| Type | Provider | Key Variable | Tested Models |
|------|----------|-------------|---------------|
| `google` | Google Gemini | `GOOGLE_API_KEY` | `gemini-3.1-flash-lite-preview`, `gemini-2.5-pro`, `gemini-3-flash-preview` |
| `anthropic` | Anthropic | `ANTHROPIC_API_KEY` | `claude-sonnet-4-6`, `claude-haiku-4-5-20251001` |
| `openai_compatible` | OpenAI | `OPENAI_API_KEY` | `gpt-5.4-nano`, `gpt-5.4-mini`, `gpt-4.1-mini`, `gpt-4.1` |

### OpenAI-Compatible Providers

Any provider that implements the OpenAI Chat Completions API can be used with `type = "openai_compatible"`. This includes:

- **OpenAI** — `https://api.openai.com/v1`
- **Google Gemini** (via OpenAI endpoint) — `https://generativelanguage.googleapis.com/v1beta/openai`
- **Ollama** (local) — `http://localhost:11434/v1`
- **vLLM** — `http://localhost:8000/v1`
- **Together AI** — `https://api.together.xyz/v1`
- **Groq** — `https://api.groq.com/openai/v1`
- **Any OpenAI SDK-compatible endpoint**

```toml
[llm.providers.my_provider]
type = "openai_compatible"
base_url = "https://my-provider.example.com/v1"
api_key_ref = "MY_PROVIDER_API_KEY"
default_model = "my-model-name"
timeout_seconds = 300
```

### CLI Providers

Use locally installed CLI tools. Authentication is managed by each tool.

```toml
[llm.providers.claude_cli]
type = "cli"
command = "claude"
args = ["-p"]                    # -p = non-interactive print mode
default_model = "claude-sonnet-4-6"

[llm.providers.codex_cli]
type = "cli"
command = "codex"
args = ["exec"]

[llm.providers.gemini_cli]
type = "cli"
command = "gemini"
args = []
```

### ACP Providers (Agent Communication Protocol)

Bidirectional JSON-RPC over stdio. These providers support multi-turn tool calling natively. Authentication is managed by each provider.

```toml
[llm.providers.codex_acp]
type = "acp"
command = "codex-acp"
args = ["-c", "model_reasoning_effort=\"low\""]
timeout_seconds = 300

[llm.providers.claude_acp]
type = "acp"
command = "claude-agent-acp"
timeout_seconds = 300

[llm.providers.gemini_acp]
type = "acp"
command = "gemini"
args = ["--experimental-acp"]
timeout_seconds = 300
```

---

## Task-Specific Routing

Different engine tasks have different requirements. World compilation needs structured output and large context. Agent reasoning needs tool calling. The animator needs creativity. Route each task to the best provider/model.

```toml
[llm.routing.<engine>_<use_case>]
provider = "gemini"          # Provider name from registry
model = "gemini-3.1-flash-lite-preview"
max_tokens = 16384
temperature = 0              # 0 = deterministic, 0.7 = creative
```

### Default Routing (bundled config)

| Task | Provider | Model | Purpose |
|------|----------|-------|---------|
| `world_compiler` | gemini | gemini-3.1-flash-lite-preview | World compilation, entity generation |
| `data_generator` | gemini | gemini-3.1-flash-lite-preview | Seed expansion, data generation |
| `responder_tier2` | gemini | gemini-3.1-flash-lite-preview | Tier 2 service responses |
| `profile_infer` | gemini | gemini-3.1-flash-lite-preview | Service profile inference |
| `animator` | gemini | gemini-3.1-flash-lite-preview | World event generation |
| `agency_individual` | openai | gpt-5.4-mini | Individual agent reasoning |
| `agency_batch` | openai | gpt-5.4-mini | Batch agent decisions |
| `world_compiler_policy_trigger_compilation` | openai | gpt-5.4-nano | NL policy trigger compilation |

### Overriding Routes

Create a `volnix.toml` in your project directory to override any route:

```toml
# Use Anthropic for agent reasoning instead of OpenAI
[llm.routing.agency_individual]
provider = "anthropic"
model = "claude-sonnet-4-6"
max_tokens = 4096
temperature = 0

# Use local Ollama for the animator
[llm.routing.animator]
provider = "ollama"
model = "llama3"
max_tokens = 2048
temperature = 0.5
```

---

## Tested Configurations

These provider/model combinations have been validated end-to-end (world compilation, agent runs, governance pipeline):

| Provider | Models | Notes |
|----------|--------|-------|
| **Google Gemini** | `gemini-3.1-flash-lite-preview` | Primary for compilation. Structured output via native schema. Fast, cost-effective. |
| **OpenAI** | `gpt-5.4-mini`, `gpt-5.4-nano` | Primary for agency. Supports structured output via `response_format`. `max_completion_tokens` used (not `max_tokens`). |
| **OpenAI** | `gpt-4.1-mini`, `gpt-4.1` | Tested for compilation and agency. |
| **Anthropic** | `claude-sonnet-4-6` | Tested via CLI and ACP providers. |
| **Codex ACP** | (default model) | Default provider for agent reasoning via ACP protocol. |

### Minimum Setup

Only one API key is required. The bundled config routes most tasks through Gemini:

```bash
export GOOGLE_API_KEY=your-key-here
volnix serve demo_support_escalation --internal agents_support_team
```

For the agency engine (internal agents), add an OpenAI key:

```bash
export OPENAI_API_KEY=sk-...
```

Or override the agency routing to use Gemini instead:

```toml
# volnix.toml (in your project directory)
[llm.routing.agency_individual]
provider = "gemini"
model = "gemini-3.1-flash-lite-preview"

[llm.routing.agency_batch]
provider = "gemini"
model = "gemini-3.1-flash-lite-preview"
```

---

## Adding a Custom Provider

Any OpenAI SDK-compatible endpoint works out of the box:

```toml
[llm.providers.my_local_llm]
type = "openai_compatible"
base_url = "http://localhost:8000/v1"
api_key_ref = ""                    # Empty string = no key required
default_model = "my-model"

# Route a task to it
[llm.routing.animator]
provider = "my_local_llm"
model = "my-model"
max_tokens = 2048
temperature = 0.5
```

Requirements for OpenAI-compatible providers:
- Must implement `/chat/completions` endpoint
- Must support `response_format` for structured output (used by compilation)
- Should support `tools` parameter for agent tool calling
- `max_completion_tokens` is preferred over `max_tokens` (Volnix handles the fallback automatically)
