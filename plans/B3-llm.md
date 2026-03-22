# Phase B3: LLM Module Implementation

## Context

**Phase:** B3 (third Phase B item — the biggest infrastructure module)
**Module:** `terrarium/llm/`
**Depends on:** A4 (ledger — UsageTracker writes LLMCallEntry), core types
**Goal:** Complete LLM provider system — API providers (real SDK calls), ACP client (agent protocol), CLI subprocess fallback, mock for testing, secret resolution, routing, usage tracking.

**Bigger picture:** Per DESIGN_PRINCIPLES.md: *"DO use the LLM router for all LLM calls — never call provider SDKs directly."* Every engine that needs LLM generation (responder, animator, world compiler, service bootstrapper) goes through the router. The router picks the right provider and model based on config, tracks usage, records to ledger.

**Three paths to LLMs:**
1. **API SDK** — Anthropic/OpenAI/Google Python SDKs. Terrarium manages API keys via SecretResolver.
2. **ACP Client** — Terrarium as HOST sends tasks to local coding agents (Claude Code, Codex, Gemini CLI) via Agent Client Protocol. Agent uses its own credentials.
3. **CLI Subprocess** — Fallback for tools without ACP. Simple pipe: prompt → stdin → stdout → response.

---

## Architecture

```
Engine needs LLM
    │
    ▼
LLMRouter.route(request, engine_name, use_case)
    │
    ├── 1. Lookup routing config: llm.routing.{engine_name}_{use_case}
    │      → provider name + model
    │
    ├── 2. Get provider: ProviderRegistry.get(name)
    │
    ├── 3. Call provider.generate(request) → LLMResponse
    │      │
    │      ├── AnthropicProvider   → anthropic SDK → HTTPS → Anthropic API
    │      ├── OpenAICompatProvider → openai SDK → HTTPS → OpenAI/Gemini/Groq/Ollama/vLLM
    │      ├── GoogleNativeProvider → google SDK → HTTPS → Google Gemini
    │      ├── ACPClientProvider   → acp SDK → ACP protocol → local agent (Claude Code/Codex)
    │      ├── CLISubprocessProvider → asyncio.subprocess → local CLI tool
    │      └── MockLLMProvider     → deterministic seed-based response
    │
    ├── 4. UsageTracker.record() → LLMCallEntry to Ledger
    │
    └── 5. Return LLMResponse


SecretResolver (resolves API keys)
    │
    ├── EnvVarResolver    → os.environ.get("ANTHROPIC_API_KEY")
    ├── FileResolver      → read from .secrets/ANTHROPIC_API_KEY
    └── ChainResolver     → try resolvers in order
```

---

## Design Principle Compliance

| Principle | How B3 follows it |
|-----------|------------------|
| **No hardcoded values** | Provider names, models, base_urls, keys all from TOML config |
| **Config-driven routing** | `llm.routing.{engine}` maps engine→provider+model. No routing logic in code. |
| **Ledger recording** | Every LLM call → LLMCallEntry (provider, model, tokens, cost, latency, success) |
| **Secret management** | SecretResolver protocol — env vars now, extensible to vault/keyring |
| **Protocol-based DI** | LLMProvider ABC. Router uses it, doesn't know concrete types. |
| **No direct SDK calls** | Engines call Router. Router delegates to Provider. Never SDK directly. |

---

## Implementation Order

### Step 1: `llm/types.py` — Core types

Already has LLMRequest, LLMResponse, LLMUsage, ProviderInfo as stubs. Implement with full field definitions. Add:
- `ProviderType` enum: API, ACP, CLI, MOCK

### Step 2: `llm/secrets.py` — SecretResolver (NEW file)

```python
"""Secret resolution for LLM API keys and credentials."""

class SecretResolver(Protocol):
    def resolve(self, ref: str) -> str | None:
        """Resolve a secret reference to its actual value."""
        ...

class EnvVarResolver:
    """Resolves secrets from environment variables."""
    def resolve(self, ref: str) -> str | None:
        return os.environ.get(ref)

class FileResolver:
    """Resolves secrets from files in a directory."""
    def __init__(self, secrets_dir: str = ".secrets"):
        self._dir = Path(secrets_dir)

    def resolve(self, ref: str) -> str | None:
        path = self._dir / ref
        if path.is_file():
            return path.read_text().strip()
        return None

class ChainResolver:
    """Tries multiple resolvers in order, returns first non-None."""
    def __init__(self, resolvers: list[SecretResolver]):
        self._resolvers = resolvers

    def resolve(self, ref: str) -> str | None:
        for resolver in self._resolvers:
            val = resolver.resolve(ref)
            if val is not None:
                return val
        return None
```

### Step 3: `llm/provider.py` — LLMProvider ABC

Already has stubs. Implement with:
- `provider_name: ClassVar[str]`
- `async generate(request: LLMRequest) -> LLMResponse`
- `async validate_connection() -> bool`
- `async list_models() -> list[str]`
- `get_info() -> ProviderInfo`

### Step 4: Provider Implementations

#### `llm/providers/anthropic.py` — AnthropicProvider
- Uses `anthropic` Python SDK (AsyncAnthropic)
- `__init__(api_key: str, default_model: str)`
- `generate()`: creates message, maps response to LLMResponse
- `validate_connection()`: tries a minimal API call
- `list_models()`: returns known Anthropic models
- Handles: rate limits, timeouts, error mapping
- Cost calculation based on model + token counts

#### `llm/providers/openai_compat.py` — OpenAICompatibleProvider
- Uses `openai` Python SDK (AsyncOpenAI) with configurable base_url
- `__init__(api_key: str | None, base_url: str, default_model: str)`
- Works with: OpenAI, Gemini (compat endpoint), Groq, Together, Ollama, vLLM
- `api_key=None` for local endpoints (Ollama)
- Same generate/validate/list pattern

#### `llm/providers/google.py` — GoogleNativeProvider
- Uses `google-generativeai` SDK
- `__init__(api_key: str, default_model: str)`
- Native Gemini features (if any beyond OpenAI compat)
- Same pattern

#### `llm/providers/acp_client.py` — ACPClientProvider (NEW)
- Terrarium as ACP HOST, connects to local coding agents
- Uses official `acp` Python SDK (https://agentclientprotocol.com/libraries/python)
- Agents expose themselves via ACP: claude-agent-acp, codex-acp, etc.
- `__init__(agent_url: str, agent_name: str, timeout: float)`
- `generate()`:
  1. Create ACP client session
  2. Send task to agent with prompt content
  3. Await task completion (agent does the work)
  4. Parse agent result → LLMResponse
- `validate_connection()`: check agent availability via ACP
- Config:
  ```toml
  [llm.providers.claude_acp]
  type = "acp"
  agent_url = "http://localhost:3000"   # ACP agent endpoint
  agent_name = "claude"
  ```
- No API key from Terrarium — agent (Claude Code/Codex) uses its own credentials
- Install: `pip install acp` (add to pyproject.toml dependencies)
- References:
  - ACP Python SDK: https://agentclientprotocol.com/libraries/python
  - Claude Agent ACP: https://github.com/zed-industries/claude-agent-acp
  - Codex ACP: https://github.com/zed-industries/codex-acp

#### `llm/providers/cli_subprocess.py` — CLISubprocessProvider (NEW)
- Fallback for tools without ACP
- `__init__(command: str, args: list[str], default_model: str | None)`
- `generate()`:
  1. Build command: `[command] + args + [prompt_text]`
  2. `asyncio.create_subprocess_exec()` with stdin pipe
  3. Write prompt to stdin, read stdout
  4. Parse stdout → LLMResponse
- Config:
  ```toml
  [llm.providers.claude_cli]
  type = "cli"
  command = "claude"
  args = ["--print"]
  default_model = "claude-sonnet-4-20250514"
  ```
- No API key — CLI handles its own auth

#### `llm/providers/mock.py` — MockLLMProvider
- Deterministic seed-based responses for testing
- `__init__(seed: int, responses: dict | None)`
- `generate()`: returns predictable response based on seed + request hash
- Zero network calls, zero API keys

### Step 5: `llm/config.py` — Updated config models

Add new provider type support:
```python
class LLMProviderEntry(BaseModel):
    type: str = ""                    # "anthropic" | "openai_compatible" | "google" | "acp" | "cli" | "mock"
    base_url: str | None = None       # For openai_compat
    api_key_ref: str = ""             # Env var name for API key (empty for CLI/ACP)
    default_model: str = ""
    max_tokens: int = 4096
    temperature: float = 0.7
    timeout_seconds: float = 30.0
    # CLI-specific
    command: str = ""                  # CLI binary name
    args: list[str] = Field(default_factory=list)  # CLI arguments
    # ACP-specific
    agent_url: str = ""               # ACP agent endpoint URL
    agent_name: str = ""              # ACP agent identifier
```

### Step 6: `llm/registry.py` — ProviderRegistry

- `initialize_all(config, secret_resolver)`: for each provider in config, resolve keys, create instance, register
- Factory pattern: `type` field determines which provider class to create
- `get(name)`, `list_providers()`, `shutdown_all()`

### Step 7: `llm/router.py` — LLMRouter

- `__init__(config, registry, tracker)`
- `route(request, engine_name, use_case)`:
  1. Find routing entry in config
  2. Get provider from registry
  3. Override model if routing specifies one
  4. Call provider.generate()
  5. Record to tracker
  6. Return response
- Fallback to defaults if no routing entry for engine

### Step 8: `llm/tracker.py` — UsageTracker

- `__init__(ledger)`: receives Ledger via DI
- `record(request, response, engine_name, actor_id)`: creates LLMCallEntry, appends to ledger
- In-memory aggregates: by actor, by engine, total
- `get_usage_by_actor()`, `get_usage_by_engine()`, `get_total_usage()`, `get_cost_by_actor()`

---

## Files to Modify / Create

| File | Action | Notes |
|------|--------|-------|
| `terrarium/llm/types.py` | **IMPLEMENT** | LLMRequest, LLMResponse, LLMUsage, ProviderInfo, ProviderType |
| `terrarium/llm/secrets.py` | **CREATE** | SecretResolver protocol, EnvVarResolver, FileResolver, ChainResolver |
| `terrarium/llm/provider.py` | **IMPLEMENT** | LLMProvider ABC |
| `terrarium/llm/providers/anthropic.py` | **IMPLEMENT** | Real Anthropic SDK calls |
| `terrarium/llm/providers/openai_compat.py` | **IMPLEMENT** | Real OpenAI SDK calls + base_url |
| `terrarium/llm/providers/google.py` | **IMPLEMENT** | Real Google SDK calls |
| `terrarium/llm/providers/acp_client.py` | **CREATE** | ACP client provider via httpx |
| `terrarium/llm/providers/cli_subprocess.py` | **CREATE** | Subprocess CLI provider |
| `terrarium/llm/providers/mock.py` | **IMPLEMENT** | Deterministic mock |
| `terrarium/llm/config.py` | **IMPLEMENT** | Updated with CLI/ACP fields |
| `terrarium/llm/registry.py` | **IMPLEMENT** | Factory + lifecycle |
| `terrarium/llm/router.py` | **IMPLEMENT** | Routing + fallback |
| `terrarium/llm/tracker.py` | **IMPLEMENT** | Ledger integration + aggregates |
| `terrarium/llm/__init__.py` | **UPDATE** | Export new types |
| `tests/llm/test_*.py` | **IMPLEMENT** | All test files |
| `tests/llm/test_secrets.py` | **CREATE** | SecretResolver tests |
| `tests/llm/test_acp_client.py` | **CREATE** | ACP client tests |
| `tests/llm/test_cli_subprocess.py` | **CREATE** | CLI subprocess tests |
| `tests/llm/test_integration.py` | **CREATE** | Router + registry + tracker E2E |
| `IMPLEMENTATION_STATUS.md` | **UPDATE** | Flip LLM to done, session log |
| `plans/B3-llm.md` | **CREATE** | Save plan to project |

---

## Tests

### test_types.py (~6 tests)
- test_llm_request_defaults
- test_llm_response_frozen
- test_llm_usage_frozen
- test_provider_info_frozen
- test_provider_type_enum
- test_request_with_output_schema

### test_secrets.py (NEW ~8 tests)
- test_env_var_resolver_found — env var exists → returns value
- test_env_var_resolver_missing — env var missing → returns None
- test_file_resolver_found — file exists → returns content
- test_file_resolver_missing — file missing → returns None
- test_chain_resolver_first_wins — first resolver has it → returns immediately
- test_chain_resolver_fallback — first fails, second succeeds
- test_chain_resolver_all_fail — all return None → returns None
- test_chain_resolver_empty — no resolvers → returns None

### test_provider.py (~4 tests)
- test_provider_abc_cannot_instantiate
- test_provider_has_required_methods
- test_provider_name_class_var
- test_provider_info_structure

### test_mock.py (~6 tests)
- test_mock_deterministic — same seed + same input = same output
- test_mock_different_seeds — different seeds = different output
- test_mock_custom_responses — responses dict overrides seed
- test_mock_validate_connection — always True
- test_mock_list_models — returns mock model list
- test_mock_usage_tracking — returns realistic token counts

### test_anthropic_provider.py (~5 tests)
- test_anthropic_init — requires api_key
- test_anthropic_generate — real API call (skip if no ANTHROPIC_API_KEY)
- test_anthropic_validate — connection check (skip if no key)
- test_anthropic_error_handling — invalid key → proper error
- test_anthropic_cost_calculation — token counts map to cost

### test_openai_compat.py (~5 tests)
- test_openai_compat_init — requires base_url
- test_openai_compat_generate — real API call (skip if no key)
- test_openai_compat_custom_base_url — different base_url works
- test_openai_compat_no_api_key — works for Ollama (no key needed)
- test_openai_compat_error_handling — bad base_url → proper error

### test_acp_client.py (NEW ~6 tests)
- test_acp_init — requires base_url
- test_acp_generate_success — mock ACP server → task created → completed → response
- test_acp_generate_timeout — task doesn't complete → timeout error
- test_acp_validate_connection — health check
- test_acp_task_failed — agent returns error → proper error
- test_acp_no_server — connection refused → proper error

### test_cli_subprocess.py (NEW ~6 tests)
- test_cli_generate — mock command → response
- test_cli_command_not_found — missing binary → proper error
- test_cli_timeout — command hangs → timeout
- test_cli_error_exit — non-zero exit → proper error
- test_cli_empty_output — command returns nothing → proper error
- test_cli_with_model_flag — model passed to command

### test_registry.py (~6 tests)
- test_register_and_get — register provider, retrieve by name
- test_get_missing — KeyError for unknown name
- test_list_providers — returns all ProviderInfo
- test_initialize_from_config — creates providers from TOML config
- test_factory_creates_correct_types — "anthropic" → AnthropicProvider, "cli" → CLISubprocessProvider
- test_shutdown_all — cleanup

### test_router.py (~8 tests)
- test_route_default — no routing entry → uses defaults
- test_route_by_engine — routing entry exists → correct provider + model
- test_route_model_override — request.model_override takes precedence
- test_route_records_to_tracker — UsageTracker.record() called
- test_route_fallback — provider not found → uses default provider
- test_route_temperature_override — routing overrides temperature
- test_get_provider_for — returns correct provider instance
- test_get_model_for — returns correct model string

### test_tracker.py (~6 tests)
- test_record_creates_ledger_entry — LLMCallEntry in ledger
- test_usage_by_actor — aggregates per actor
- test_usage_by_engine — aggregates per engine
- test_total_usage — grand total
- test_cost_by_actor — USD cost tracking
- test_tracker_without_ledger — works with ledger=None (no crash)

### test_integration.py (NEW ~5 tests)
- test_router_with_mock_provider — full route cycle: request → mock → response → ledger entry
- test_router_with_real_ledger — LLMCallEntry persisted to real Ledger (A4)
- test_registry_initialize_from_toml — load real terrarium.toml, create providers
- test_secret_resolver_in_registry — api_key_ref resolved via SecretResolver
- test_full_cycle — config → secret resolver → registry → router → tracker → ledger

---

## Completion Criteria (Zero Stubs)

| File | All Implemented? | All Tested? |
|------|-----------------|-------------|
| `types.py` | ✅ | ✅ 6 tests |
| `secrets.py` (NEW) | ✅ | ✅ 8 tests |
| `provider.py` | ✅ | ✅ 4 tests |
| `providers/anthropic.py` | ✅ | ✅ 5 tests (skip if no key) |
| `providers/openai_compat.py` | ✅ | ✅ 5 tests (skip if no key) |
| `providers/google.py` | ✅ | ✅ 3 tests (skip if no key) |
| `providers/acp_client.py` (NEW) | ✅ | ✅ 6 tests |
| `providers/cli_subprocess.py` (NEW) | ✅ | ✅ 6 tests |
| `providers/mock.py` | ✅ | ✅ 6 tests |
| `config.py` | ✅ | ✅ via config tests |
| `registry.py` | ✅ | ✅ 6 tests |
| `router.py` | ✅ | ✅ 8 tests |
| `tracker.py` | ✅ | ✅ 6 tests |
| `__init__.py` | ✅ | ✅ import test |

**0 stubs remaining. ~80 tests across 13 test files.**

---

## Post-Implementation Tasks

### 1. Save plan to `plans/B3-llm.md`
### 2. Update IMPLEMENTATION_STATUS.md

**Current Focus:**
```
**Phase:** B — Core Infrastructure
**Item:** B3 llm/ ✅ COMPLETE → Next: B4 registry/
**Status:** LLM provider system: API + ACP + CLI + mock. SecretResolver. Router + tracker.
```

**Flip all LLM rows to ✅ done.**
**Session log entry.**

---

## Verification

1. `.venv/bin/python -m pytest tests/llm/ -v` — ALL pass
2. `.venv/bin/python -m pytest tests/llm/ --cov=terrarium/llm --cov-report=term-missing` — >85%
3. `grep -rn "^\s*\.\.\.$" terrarium/llm/*.py terrarium/llm/providers/*.py` — 0 stubs
4. Mock provider smoke test:
   ```python
   from terrarium.llm.providers.mock import MockLLMProvider
   from terrarium.llm.types import LLMRequest
   provider = MockLLMProvider(seed=42)
   response = await provider.generate(LLMRequest(system_prompt="test", user_content="hello"))
   assert response.content  # non-empty
   ```
5. SecretResolver:
   ```python
   from terrarium.llm.secrets import EnvVarResolver
   import os
   os.environ["TEST_KEY"] = "secret123"
   assert EnvVarResolver().resolve("TEST_KEY") == "secret123"
   ```
6. Real API test (if key available):
   ```python
   from terrarium.llm.providers.anthropic import AnthropicProvider
   provider = AnthropicProvider(api_key=os.environ["ANTHROPIC_API_KEY"])
   response = await provider.generate(LLMRequest(system_prompt="Reply with 'ok'", user_content="test"))
   assert "ok" in response.content.lower()
   ```
7. ALL previous tests: `.venv/bin/python -m pytest tests/ -q` — 583+ passed
