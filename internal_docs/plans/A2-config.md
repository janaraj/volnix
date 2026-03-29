# Phase A2: Config Module Implementation

## Context

**Phase:** A2 (second implementation phase)
**Module:** `terrarium/config/`
**Depends on:** Nothing (reads TOML files, pure Python)
**Goal:** A working config system that loads layered TOML, validates against Pydantic schemas, resolves env vars and secure refs, and provides typed access for every module in the system.

**Bigger picture:** Config is consumed by EVERY module. A3 (bus) needs BusConfig. A4 (ledger) needs LedgerConfig. B2 (pipeline) needs PipelineConfig with the 7-step list. B3 (llm) needs LLMConfig with provider registry and routing. B4 (registry/wiring) passes typed config sections to each engine. If config is wrong, nothing downstream works.

**Key design decision:** Each module owns its config definition (SRP). `config/schema.py` IMPORTS from subsystem config files and assembles them into `TerrariumConfig`. No duplicate definitions.

---

## Issues Found During Exploration

| Issue | Severity | Fix |
|-------|----------|-----|
| **Dual config definitions** — schema.py has stub copies of configs that also exist in subsystem files | HIGH | schema.py imports FROM subsystem files, no duplicates |
| **Engine receives `dict[str, Any]`** — but subsystems need typed Pydantic models | HIGH | Config loader returns TerrariumConfig; wiring extracts typed sections |
| **Missing root config sections** — ActorConfig, TemplateConfig not in TerrariumConfig | MEDIUM | Add all missing sections |
| **LLM config naming mismatch** — LLMProviderEntry vs LLMProviderConfig | MEDIUM | Standardize: subsystem file is authoritative |
| **Engine configs lack defaults** — StateConfig, PolicyConfig etc. will fail if TOML section missing | MEDIUM | Add defaults to ALL config models |
| **terrarium.development.toml has `mode = "interactive"`** | LOW | Fix to "governed" |
| **Some schema.py configs are empty stubs** | HIGH | Fill all with real fields matching terrarium.toml |

---

## Implementation Plan

### Step 1: Fix subsystem config files (add defaults everywhere)

Every module's config file needs sensible defaults so the system works with a minimal TOML. Read each file, add defaults where missing:

- `persistence/config.py` — ✅ already done (has defaults)
- `bus/config.py` — has defaults ✅
- `ledger/config.py` — has defaults ✅
- `pipeline/config.py` — needs default steps list: `["permission", "policy", "budget", "capability", "responder", "validation", "commit"]`
- `llm/config.py` — has defaults ✅ (standardize field names)
- `gateway/config.py` — has defaults ✅
- `reality/config.py` — has defaults ✅
- `runs/config.py` — has defaults ✅
- `actors/config.py` — has defaults ✅
- `templates/config.py` — has defaults ✅

Engine configs (need defaults added):
- `engines/state/config.py` — add: `db_path: str = "data/state.db"`, `snapshot_dir: str = "snapshots"`
- `engines/policy/config.py` — add: `condition_timeout_ms: int = 500`, `max_policies_per_action: int = 50`
- `engines/permission/config.py` — add: `cache_ttl_seconds: int = 300`
- `engines/budget/config.py` — add: `warning_threshold_pct: float = 80.0`, `critical_threshold_pct: float = 95.0`
- `engines/responder/config.py` — add: `max_retries: int = 2`, `fallback_enabled: bool = True`
- `engines/animator/config.py` — add: `creativity_budget: int = 5`, `intensity: str = "moderate"`, `enabled: bool = True`
- `engines/adapter/config.py` — add: `protocols: list[str] = ["mcp", "http"]`, `host: str = "0.0.0.0"`, `port: int = 8100`
- `engines/reporter/config.py` — add: `output_formats: list[str] = ["json", "markdown"]`, `output_dir: str = "reports"`
- `engines/feedback/config.py` — add: `annotations_db_path: str = "data/annotations.db"`, `external_sync_enabled: bool = False`
- `engines/world_compiler/config.py` — add: `default_seed: int = 42`, `max_entities_per_type: int = 1000`

### Step 2: Rewrite `config/schema.py` — single source of truth

`schema.py` imports ALL config models from their owning modules and assembles `TerrariumConfig`:

```python
"""Root configuration schema — imports from subsystem config files."""

from terrarium.persistence.config import PersistenceConfig
from terrarium.bus.config import BusConfig
from terrarium.ledger.config import LedgerConfig
from terrarium.pipeline.config import PipelineConfig
from terrarium.llm.config import LLMConfig
from terrarium.gateway.config import GatewayConfig
from terrarium.reality.config import RealityConfig, SeedConfig
from terrarium.runs.config import RunConfig
from terrarium.actors.config import ActorConfig
from terrarium.templates.config import TemplateConfig
from terrarium.engines.state.config import StateConfig
from terrarium.engines.policy.config import PolicyConfig
from terrarium.engines.permission.config import PermissionConfig
from terrarium.engines.budget.config import BudgetConfig
from terrarium.engines.responder.config import ResponderConfig
from terrarium.engines.animator.config import AnimatorConfig
from terrarium.engines.adapter.config import AdapterConfig
from terrarium.engines.reporter.config import ReporterConfig
from terrarium.engines.feedback.config import FeedbackConfig
from terrarium.engines.world_compiler.config import WorldCompilerConfig

class SimulationConfig(BaseModel):
    seed: int = 42
    time_speed: float = 1.0
    mode: str = "governed"
    reality: RealityConfig = Field(default_factory=RealityConfig)
    fidelity: FidelityConfig = Field(default_factory=FidelityConfig)
    seeds: list[SeedConfig] = Field(default_factory=list)

class FidelityConfig(BaseModel):
    mode: str = "auto"

class TerrariumConfig(BaseModel):
    simulation: SimulationConfig = Field(default_factory=SimulationConfig)
    pipeline: PipelineConfig = Field(default_factory=PipelineConfig)
    bus: BusConfig = Field(default_factory=BusConfig)
    ledger: LedgerConfig = Field(default_factory=LedgerConfig)
    persistence: PersistenceConfig = Field(default_factory=PersistenceConfig)
    state: StateConfig = Field(default_factory=StateConfig)
    policy: PolicyConfig = Field(default_factory=PolicyConfig)
    permission: PermissionConfig = Field(default_factory=PermissionConfig)
    budget: BudgetConfig = Field(default_factory=BudgetConfig)
    responder: ResponderConfig = Field(default_factory=ResponderConfig)
    animator: AnimatorConfig = Field(default_factory=AnimatorConfig)
    adapter: AdapterConfig = Field(default_factory=AdapterConfig)
    reporter: ReporterConfig = Field(default_factory=ReporterConfig)
    feedback: FeedbackConfig = Field(default_factory=FeedbackConfig)
    dashboard: DashboardConfig = Field(default_factory=DashboardConfig)
    gateway: GatewayConfig = Field(default_factory=GatewayConfig)
    run: RunConfig = Field(default_factory=RunConfig)
    llm: LLMConfig = Field(default_factory=LLMConfig)
    actors: ActorConfig = Field(default_factory=ActorConfig)
    templates: TemplateConfig = Field(default_factory=TemplateConfig)
    world_compiler: WorldCompilerConfig = Field(default_factory=WorldCompilerConfig)
```

SimulationConfig and FidelityConfig stay in schema.py since they're top-level orchestration, not owned by any subsystem. DashboardConfig also stays here (dashboard is simple enough).

### Step 3: Implement `config/loader.py`

The core of A2. Load layered TOML, merge, resolve, validate:

```python
import tomllib  # Python 3.11+ stdlib
import os
from pathlib import Path

class ConfigLoader:
    ENV_PREFIX = "TERRARIUM"
    ENV_SEP = "__"

    def __init__(self, base_dir: Path | None = None, env: str = "development"):
        self._base_dir = base_dir or Path.cwd()
        self._env = env

    def load(self) -> TerrariumConfig:
        merged: dict = {}

        # Layer 1: base
        base = self._base_dir / "terrarium.toml"
        if base.exists():
            merged = self._deep_merge(merged, self._load_toml(base))

        # Layer 2: environment
        env_file = self._base_dir / f"terrarium.{self._env}.toml"
        if env_file.exists():
            merged = self._deep_merge(merged, self._load_toml(env_file))

        # Layer 3: local (gitignored)
        local = self._base_dir / "terrarium.local.toml"
        if local.exists():
            merged = self._deep_merge(merged, self._load_toml(local))

        # Layer 4: env vars
        merged = self._apply_env_overrides(merged)

        # Layer 5: resolve secure refs (*_ref → env var lookup)
        merged = self._resolve_refs(merged)

        # Validate and return typed config
        return TerrariumConfig.model_validate(merged)

    @staticmethod
    def _load_toml(path: Path) -> dict:
        with open(path, "rb") as f:
            return tomllib.load(f)

    @staticmethod
    def _deep_merge(base: dict, override: dict) -> dict:
        result = base.copy()
        for key, value in override.items():
            if key in result and isinstance(result[key], dict) and isinstance(value, dict):
                result[key] = ConfigLoader._deep_merge(result[key], value)
            else:
                result[key] = value
        return result

    def _apply_env_overrides(self, config: dict) -> dict:
        prefix = f"{self.ENV_PREFIX}{self.ENV_SEP}"
        for key, value in os.environ.items():
            if key.startswith(prefix):
                parts = key[len(prefix):].lower().split(self.ENV_SEP)
                self._set_nested(config, parts, self._coerce(value))
        return config

    @staticmethod
    def _set_nested(config: dict, keys: list[str], value) -> None:
        current = config
        for k in keys[:-1]:
            current = current.setdefault(k, {})
        current[keys[-1]] = value

    @staticmethod
    def _coerce(value: str):
        if value.lower() in ("true", "false"):
            return value.lower() == "true"
        try:
            return int(value)
        except ValueError:
            pass
        try:
            return float(value)
        except ValueError:
            pass
        return value

    def _resolve_refs(self, config: dict) -> dict:
        for key, value in list(config.items()):
            if isinstance(value, dict):
                config[key] = self._resolve_refs(value)
            elif isinstance(key, str) and key.endswith("_ref") and isinstance(value, str) and value:
                env_val = os.environ.get(value)
                if env_val is not None:
                    actual_key = key[:-4]  # strip _ref
                    config[actual_key] = env_val
        return config
```

### Step 4: Implement `config/registry.py`

Runtime typed access + change subscriptions:

```python
class ConfigRegistry:
    def __init__(self, config: TerrariumConfig):
        self._config = config
        self._listeners: dict[str, list[Callable]] = {}

    def get(self, section: str, key: str) -> Any:
        section_model = getattr(self._config, section, None)
        if section_model is None:
            raise KeyError(f"Config section '{section}' not found")
        value = getattr(section_model, key, None)
        if value is None:
            raise KeyError(f"Config key '{section}.{key}' not found")
        return value

    def get_section(self, section: str) -> BaseModel:
        section_model = getattr(self._config, section, None)
        if section_model is None:
            raise KeyError(f"Config section '{section}' not found")
        return section_model

    def subscribe(self, section: str, key: str, callback: Callable) -> None:
        sub_key = f"{section}.{key}"
        self._listeners.setdefault(sub_key, []).append(callback)

    def update_tunable(self, section: str, key: str, value: Any) -> None:
        section_model = getattr(self._config, section, None)
        if section_model is None:
            raise KeyError(f"Config section '{section}' not found")
        # Pydantic models are usually frozen — need to use model_copy
        updated = section_model.model_copy(update={key: value})
        setattr(self._config, section, updated)
        # Notify listeners
        sub_key = f"{section}.{key}"
        for cb in self._listeners.get(sub_key, []):
            cb(value)
```

### Step 5: Implement `config/tunable.py`

Tunable field registry for dashboard/CLI control:

```python
@dataclass
class TunableField:
    section: str
    key: str
    current_value: Any
    default_value: Any
    validators: list[Callable[[Any], bool]] = field(default_factory=list)

class TunableRegistry:
    def __init__(self):
        self._fields: dict[str, TunableField] = {}
        self._listeners: dict[str, list[Callable]] = {}

    def register(self, field: TunableField) -> None:
        self._fields[f"{field.section}.{field.key}"] = field

    def update(self, section: str, key: str, value: Any) -> None:
        fk = f"{section}.{key}"
        field = self._fields.get(fk)
        if field is None:
            raise KeyError(f"Tunable field '{fk}' not registered")
        for validator in field.validators:
            if not validator(value):
                raise ValueError(f"Validation failed for '{fk}' with value {value}")
        field.current_value = value
        for cb in self._listeners.get(fk, []):
            cb(value)

    def get(self, section: str, key: str) -> Any:
        fk = f"{section}.{key}"
        field = self._fields.get(fk)
        if field is None:
            raise KeyError(f"Tunable field '{fk}' not registered")
        return field.current_value

    def list_tunable(self) -> list[TunableField]:
        return list(self._fields.values())

    def add_listener(self, section: str, key: str, callback: Callable) -> None:
        fk = f"{section}.{key}"
        self._listeners.setdefault(fk, []).append(callback)
```

### Step 6: Implement `config/validation.py`

Cross-field validation that runs after loading:

```python
class ConfigValidator:
    def validate_pipeline_steps(self, config: TerrariumConfig, available_engines: list[str]) -> list[str]:
        errors = []
        for step in config.pipeline.steps:
            if step not in available_engines:
                errors.append(f"Pipeline step '{step}' not in available engines: {available_engines}")
        return errors

    def validate_llm_routing(self, config: TerrariumConfig) -> list[str]:
        errors = []
        provider_names = set(config.llm.providers.keys())
        for route_name, route in config.llm.routing.items():
            if route.provider and route.provider not in provider_names:
                errors.append(f"LLM route '{route_name}' references unknown provider '{route.provider}'")
        return errors

    def validate_cross_references(self, config: TerrariumConfig) -> list[str]:
        errors = []
        # Validate reality preset is valid
        if config.simulation.reality.preset not in ("pristine", "realistic", "harsh"):
            errors.append(f"Invalid reality preset: '{config.simulation.reality.preset}'")
        # Validate fidelity mode
        if config.simulation.fidelity.mode not in ("auto", "strict", "exploratory"):
            errors.append(f"Invalid fidelity mode: '{config.simulation.fidelity.mode}'")
        # Validate simulation mode
        if config.simulation.mode not in ("governed", "ungoverned"):
            errors.append(f"Invalid simulation mode: '{config.simulation.mode}'")
        return errors

    def validate_all(self, config: TerrariumConfig, available_engines: list[str] | None = None) -> list[str]:
        errors = []
        if available_engines:
            errors.extend(self.validate_pipeline_steps(config, available_engines))
        errors.extend(self.validate_llm_routing(config))
        errors.extend(self.validate_cross_references(config))
        return errors
```

### Step 7: Fix `terrarium.development.toml`

Change `mode = "interactive"` to `mode = "governed"`.

---

## Files to Modify / Create

| File | Action | Notes |
|------|--------|-------|
| `terrarium/config/schema.py` | **REWRITE** | Import from subsystem configs, assemble TerrariumConfig |
| `terrarium/config/loader.py` | **IMPLEMENT** | TOML loading, layering, env vars, secure refs |
| `terrarium/config/registry.py` | **IMPLEMENT** | Typed access, subscriptions, tunable updates |
| `terrarium/config/tunable.py` | **IMPLEMENT** | Tunable field registry with validators |
| `terrarium/config/validation.py` | **IMPLEMENT** | Pipeline steps, LLM routing, cross-references |
| `terrarium/config/__init__.py` | **VERIFY** | Re-exports correct |
| 10+ engine config files | **UPDATE** | Add defaults to all fields |
| `terrarium/pipeline/config.py` | **UPDATE** | Add default steps list |
| `terrarium.development.toml` | **FIX** | mode = "governed" |
| `tests/config/test_loader.py` | **IMPLEMENT** | 8+ tests |
| `tests/config/test_schema.py` | **IMPLEMENT** | 6+ tests |
| `tests/config/test_registry.py` | **IMPLEMENT** | 5+ tests |
| `tests/config/test_tunable.py` | **IMPLEMENT** | 5+ tests |
| `tests/config/test_validation.py` | **CREATE** | 5+ tests |
| `IMPLEMENTATION_STATUS.md` | **UPDATE** | Flip config to done, session log |
| `plans/A2-config.md` | **CREATE** | Save plan to project |

---

## Tests

### test_loader.py (~8 tests)
- test_load_base_config — loads terrarium.toml, returns TerrariumConfig with correct values
- test_load_with_env_override — dev config merges on top of base
- test_load_with_local_override — local.toml wins over env
- test_env_var_override — TERRARIUM__SIMULATION__SEED=99 overrides seed
- test_resolve_secure_refs — api_key_ref resolves from os.environ
- test_deep_merge_nested — deeply nested dicts merge correctly
- test_deep_merge_override — scalar values in override win
- test_missing_toml_returns_defaults — if no toml file exists, returns default TerrariumConfig
- test_coerce_types — "true"→True, "42"→42, "3.14"→3.14, "hello"→"hello"

### test_schema.py (~6 tests)
- test_terrarium_config_defaults — TerrariumConfig() produces valid config with all defaults
- test_simulation_config_has_reality — simulation.reality.preset == "realistic"
- test_pipeline_config_default_steps — steps list has 7 correct step names
- test_llm_config_structure — providers dict, routing dict, defaults model
- test_all_sections_present — every section in TerrariumConfig is populated
- test_config_from_dict — TerrariumConfig.model_validate({...}) works with partial input

### test_registry.py (~5 tests)
- test_get_section — registry.get_section("persistence") returns PersistenceConfig
- test_get_value — registry.get("simulation", "seed") returns 42
- test_get_missing_section — raises KeyError
- test_update_tunable — update value and verify it changed
- test_subscribe_and_notify — callback fires on tunable update

### test_tunable.py (~5 tests)
- test_register_and_get — register field, get value back
- test_update_with_validation — validator passes, value updates
- test_update_fails_validation — validator rejects, ValueError raised
- test_listener_called — listener fires on update
- test_list_tunable — all registered fields returned

### test_validation.py (~5 tests, NEW file)
- test_validate_pipeline_steps_valid — all steps in available engines
- test_validate_pipeline_steps_invalid — unknown step returns error
- test_validate_llm_routing_valid — all providers exist
- test_validate_llm_routing_invalid — unknown provider returns error
- test_validate_cross_references — invalid preset/mode caught
- test_validate_all — aggregates all errors

---

## Completion Criteria (Zero Stubs)

After this phase:

| File | All Implemented? | All Tested? |
|------|-----------------|-------------|
| `config/loader.py` | ✅ load, _deep_merge, _apply_env_overrides, _resolve_refs, _coerce, _set_nested, _load_toml | ✅ 8+ tests |
| `config/schema.py` | ✅ TerrariumConfig with all sections imported from subsystems | ✅ 6+ tests |
| `config/registry.py` | ✅ get, get_section, subscribe, update_tunable | ✅ 5+ tests |
| `config/tunable.py` | ✅ register, update, get, list_tunable, add_listener | ✅ 5+ tests |
| `config/validation.py` | ✅ validate_pipeline_steps, validate_llm_routing, validate_cross_references, validate_all | ✅ 5+ tests |
| All engine configs | ✅ All fields have defaults | ✅ via schema tests |
| `__init__.py` | ✅ re-exports | ✅ via import test |

**0 stubs remaining in config/. All engine config files have defaults. ~30 tests total.**

---

## Additional Tests for Solid Harness

### test_loader.py — Error & edge cases
- test_malformed_toml — invalid TOML file raises clear error
- test_nonexistent_base_dir — loader handles missing directory gracefully
- test_env_var_nested_override — `TERRARIUM__LLM__DEFAULTS__TEMPERATURE=0.9` overrides nested value
- test_secure_ref_missing_env_var — `api_key_ref = "MISSING_VAR"` doesn't crash (ref stays unresolved)
- test_load_real_terrarium_toml — loads the actual `terrarium.toml` from repo root and validates

### test_schema.py — Subsystem integration
- test_all_subsystem_configs_have_defaults — every imported config model instantiates with no args
- test_config_serialization_roundtrip — model_dump() → model_validate() preserves all values
- test_simulation_config_nested — reality, fidelity, seeds all accessible

### test_registry.py — Error paths
- test_get_missing_key — raises KeyError with clear message
- test_update_tunable_notifies_multiple — multiple subscribers all called
- test_get_section_returns_typed — returns actual Pydantic model, not dict

### test_validation.py — Completeness
- test_validate_reality_preset_invalid — "chaos" preset caught
- test_validate_simulation_mode_invalid — "interactive" caught
- test_validate_all_returns_empty_when_valid — no false positives

---

## Post-Implementation Tasks

### 1. Save plan to project
Copy this plan to `plans/A2-config.md` in the project repo.

### 2. Update IMPLEMENTATION_STATUS.md

**Current Focus section — update to:**
```
**Phase:** A — Foundation Modules
**Item:** A2 config/ ✅ COMPLETE → Next: A3 bus/
**Status:** Config module fully implemented. Loads layered TOML, validates, typed access.
```

**Module Status table — flip these rows to ✅ done:**
- Config — loader
- Config — schema
- Config — registry
- Config — tunable
- Config — validation

**Session log — append entry:**
```
### Session YYYY-MM-DD — A2: Config Module
- **Implemented:** ConfigLoader (7 methods), TerrariumConfig (imports from all subsystems),
  ConfigRegistry (4 methods), TunableRegistry (5 methods), ConfigValidator (4 methods)
- **Also fixed:** Added defaults to all 10+ engine config files, fixed terrarium.development.toml
- **Tests:** N tests across 5 test files — ALL PASSING
- **Coverage:** X%
- **Decisions:** [any decisions made]
- **Zero stubs:** All config/ methods implemented
- **Next:** A3 (bus module)
```

---

## Verification

1. `.venv/bin/python -m pytest tests/config/ -v` — ALL pass (0 failures)
2. `.venv/bin/python -m pytest tests/config/ --cov=terrarium/config --cov-report=term-missing` — >90% coverage
3. `grep -rn "^\s*\.\.\.$" terrarium/config/*.py` — 0 results (no stubs)
4. Smoke test with REAL terrarium.toml:
   ```python
   from terrarium.config import ConfigLoader, TerrariumConfig, ConfigRegistry
   config = ConfigLoader(base_dir=Path(".")).load()
   assert config.simulation.mode == "governed"
   assert config.pipeline.steps[0] == "permission"
   assert config.persistence.base_dir == "data"
   registry = ConfigRegistry(config)
   assert registry.get("simulation", "seed") == 42
   ```
5. `TerrariumConfig()` with no args produces valid config (all defaults work)
6. ALL subsystem configs instantiate with no args (no missing defaults)
7. `plans/A2-config.md` exists in project repo
8. `IMPLEMENTATION_STATUS.md` updated with config → done + session log
9. Full test suite still collects: `.venv/bin/python -m pytest tests/ --collect-only` — 0 errors
