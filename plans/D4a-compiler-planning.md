# Phase D4a: World Compiler — Planning & Resolution Phase

## Context

**Phase:** D4a (first half of D4)
**Module:** `terrarium/engines/world_compiler/`
**Depends on:** D1 (reality), D2 (actors), D3 (kernel/resolver), B3 (LLM)
**Goal:** Parse input (YAML or NL) → resolve services → produce WorldPlan

---

## D4a vs D4b — Clear Boundary

```
D4a (THIS PLAN): Input → Parse → Resolve → WorldPlan
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  Step 1: Parse input (NL or YAML) → structured world definition
  Step 2: Classify services → SemanticRegistry categories
  Step 3: Resolve services → ServiceSurface per service
  Output: WorldPlan (frozen model — complete plan, no generated data yet)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

D4b (NEXT PLAN): WorldPlan → Generate → Validate → Populate
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  Step 4: Generate entities via LLM (shaped by reality dimensions)
  Step 5: Validate consistency (state machines, references)
  Step 6: Inject user seeds
  Step 7: Populate StateEngine + snapshot
  Output: Running world with populated state
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

**Why split:** D4a is testable WITHOUT LLM entity generation. YAML parsing, service resolution, and WorldPlan assembly can be tested with mock LLMs. D4b requires real LLM calls for entity generation and is harder to test deterministically.

---

## TWO Layers of LLM Usage

The compiler uses LLM in TWO distinct ways:

### Layer 1: NL → Structured Plan (D4a)
**When:** User types `terrarium create "Support team with Slack, Gmail, Stripe, 50 customers"`
**What LLM does:** Interprets the NL description and produces structured YAML:
- Extracts services: [email, chat, payments]
- Extracts actors: [{role: support-agent, count: 2, type: external}, {role: customer, count: 50, type: internal}]
- Infers policies: [{name: "Refund approval", enforcement: hold}]
- Suggests seeds: ["VIP customer waiting for refund"]

**This is a TRANSLATION task** — NL → structured data. The LLM is acting as a parser.
**Framework:** `NLParser` class with configurable system prompt and output schema.

### Layer 2: World Data Generation (D4b)
**When:** WorldPlan is ready, entities need to be created
**What LLM does:** Generates realistic entity content shaped by reality dimensions:
- Creates 50 customers with names, histories, frustration levels
- Creates 200 charges with amounts, statuses, dates
- Creates tickets with descriptions, SLA states
- ALL shaped by "information: somewhat_neglected" (some records outdated, some fields missing)

**This is a GENERATION task** — LLM creates content. The dimensions are creative direction.
**Framework:** `EntityGenerator` class with dimension-aware prompts. (D4b scope)

### Layer 3: Runtime Animation (Phase G3)
**When:** During simulation in dynamic/reactive modes
**What LLM does:** Generates new events based on world state + dimensions:
- Customer frustrated → LLM generates follow-up message
- Service under load → LLM generates degradation event

**This is an ANIMATION task** — ongoing creative direction. (Phase G3 scope)

---

## How Behavior Modes Affect D4a

| Behavior | D4a Impact | D4b Impact | Runtime Impact |
|----------|-----------|-----------|----------------|
| **static** | No difference — plan is the same | Generate data, then freeze | Animator OFF |
| **reactive** | No difference — plan is the same | Same generation | Animator ON but only reacts to agent |
| **dynamic** | No difference — plan is the same | Same generation + configure Animator | Animator ON, generates proactive events |

**D4a is behavior-agnostic.** The behavior mode is stored in WorldPlan.behavior and passed to the Animator config. The COMPILATION is the same regardless of behavior — only RUNTIME differs.

The `animator_settings` in WorldPlan (creativity, event_frequency, contextual_targeting, escalation_on_inaction) are carried from compiler settings YAML and stored for the Animator engine to use at runtime.

---

## LLM Interpretation Framework (NOT one-off prompts)

### PromptTemplate system

Instead of hardcoding prompts in each class, D4a introduces a `PromptTemplate` pattern:

```python
class PromptTemplate:
    """Reusable, configurable prompt template for LLM interactions.

    Templates are defined as data (not inline strings in code).
    They accept variables that are filled at runtime.
    """
    def __init__(self, system: str, user: str, output_schema: dict | None = None):
        self.system = system
        self.user = user
        self.output_schema = output_schema

    def render(self, **variables) -> tuple[str, str]:
        """Render system + user prompts with variables."""
        return (
            self.system.format(**variables),
            self.user.format(**variables),
        )

    async def execute(self, router: LLMRouter, engine_name: str, use_case: str, **variables) -> LLMResponse:
        """Render and execute via LLM router."""
        system, user = self.render(**variables)
        return await router.route(
            LLMRequest(system_prompt=system, user_content=user),
            engine_name=engine_name, use_case=use_case,
        )
```

### Templates for D4a

```python
# NL → World Definition
NL_TO_WORLD_DEF = PromptTemplate(
    system="""You are Terrarium's world definition interpreter.

Given a natural language description of a world, produce a structured
world definition in YAML format. The output must include:

1. world.name — a short descriptive name
2. world.description — expanded description
3. world.services — map of service names to pack references
   Use "verified/X" for known categories: email, chat, tickets, payments, repos, calendar
   Use bare names for services that need inference: stripe, salesforce, etc.
4. world.actors — list of actor specs with role, count, type (external/internal), personality
5. world.policies — governance rules (optional)
6. world.seeds — specific scenarios (optional)
7. world.mission — success criteria (optional)

Known service categories: {categories}
Known verified packs: {verified_packs}

Output ONLY valid YAML matching this schema.""",

    user="Create a world definition for: {description}",

    output_schema={...},  # JSON Schema for world definition
)

# NL → Compiler Settings
NL_TO_COMPILER_SETTINGS = PromptTemplate(
    system="""Generate compiler settings for a Terrarium world.
The settings control how the world is generated and run.

Reality preset: {reality} (ideal/messy/hostile)
Behavior mode: {behavior} (static/reactive/dynamic)
Fidelity: {fidelity} (auto/strict/exploratory)
Seed: {seed}

Output valid YAML compiler settings.""",

    user="Generate compiler settings for the world described as: {description}",
)
```

This framework means:
- Prompts are DATA, not inline strings
- Templates are testable independently
- New use cases add new templates, not new code
- Variables are typed and documented

---

## Implementation — Detailed Code

### File 1: `terrarium/engines/world_compiler/prompt_templates.py` (NEW)

```python
"""LLM prompt templates for the world compiler.

All LLM interactions in the compiler use PromptTemplate objects.
Templates are data — prompts are not hardcoded inline.
New compilation features add new templates, not new code.
"""
from __future__ import annotations
import json
import logging
from typing import Any

from terrarium.llm.router import LLMRouter
from terrarium.llm.types import LLMRequest, LLMResponse

logger = logging.getLogger(__name__)


class PromptTemplate:
    """Reusable prompt template for LLM interactions."""

    def __init__(
        self,
        system: str,
        user: str,
        output_schema: dict[str, Any] | None = None,
        engine_name: str = "world_compiler",
        use_case: str = "default",
    ) -> None:
        self.system = system
        self.user = user
        self.output_schema = output_schema
        self.engine_name = engine_name
        self.use_case = use_case

    def render(self, **variables: Any) -> tuple[str, str]:
        """Render system + user prompts with template variables."""
        try:
            sys_prompt = self.system.format(**variables)
            user_prompt = self.user.format(**variables)
        except KeyError as e:
            raise ValueError(f"Missing template variable: {e}")
        return sys_prompt, user_prompt

    async def execute(
        self,
        router: LLMRouter,
        **variables: Any,
    ) -> LLMResponse:
        """Render, send to LLM, return response."""
        sys_prompt, user_prompt = self.render(**variables)
        request = LLMRequest(
            system_prompt=sys_prompt,
            user_content=user_prompt,
        )
        return await router.route(request, self.engine_name, self.use_case)

    def parse_json_response(self, response: LLMResponse) -> dict[str, Any]:
        """Extract JSON from LLM response (structured output or content parsing)."""
        # Try structured output first
        if response.structured_output:
            return response.structured_output

        # Parse JSON from content
        content = response.content.strip()
        # Handle markdown code blocks
        if content.startswith("```"):
            lines = content.split("\n")
            content = "\n".join(lines[1:-1])  # Strip ``` markers

        return json.loads(content)


# ── NL → World Definition Template ──────────────────────────────

NL_TO_WORLD_DEF = PromptTemplate(
    system="""You are Terrarium's world definition interpreter.

Given a natural language description, produce a structured world definition as JSON.

The output MUST contain:
- "world": {{
    "name": "short name",
    "description": "expanded description",
    "services": {{"service_name": "pack_reference"}},
    "actors": [{{"role": "...", "count": N, "type": "external|internal", "personality": "..."}}],
    "policies": [{{"name": "...", "description": "...", "enforcement": "hold|block|escalate|log"}}],
    "seeds": ["specific scenario descriptions"],
    "mission": "what success looks like"
  }}

Known semantic categories: {categories}
Known verified packs: {verified_packs}

For services with verified packs, use "verified/pack_name".
For services with profiles, use "profiled/service_name".
For unknown services, use the bare service name (the compiler will resolve it).

Output ONLY valid JSON. No markdown, no explanation.""",

    user="""Create a world definition for this description:

{description}""",

    engine_name="world_compiler",
    use_case="nl_to_world_def",
)


# ── NL → Compiler Settings Template ─────────────────────────────

NL_TO_COMPILER_SETTINGS = PromptTemplate(
    system="""Generate Terrarium compiler settings as JSON.

The output MUST contain:
- "compiler": {{
    "seed": {seed},
    "behavior": "{behavior}",
    "fidelity": "{fidelity}",
    "mode": "governed",
    "reality": {{
      "preset": "{reality}"
    }},
    "animator": {{
      "creativity": "medium",
      "event_frequency": "moderate",
      "contextual_targeting": true,
      "escalation_on_inaction": true
    }}
  }}

Output ONLY valid JSON.""",

    user="""Generate compiler settings for a world described as: {description}

Use these overrides:
- Reality: {reality}
- Behavior: {behavior}
- Fidelity: {fidelity}
- Seed: {seed}""",

    engine_name="world_compiler",
    use_case="nl_to_compiler_settings",
)
```

### File 2: `terrarium/engines/world_compiler/plan.py` (NEW)

```python
"""WorldPlan — the contract between D4a (planning) and D4b (generation).

A WorldPlan is the COMPLETE plan for a world: resolved services,
reality conditions, actor specs, policies, seeds. It contains
everything D4b needs to generate entities and populate the StateEngine.
"""
from __future__ import annotations
from typing import Any

from pydantic import BaseModel, Field

from terrarium.kernel.surface import ServiceSurface
from terrarium.reality.dimensions import WorldConditions


class ServiceResolution(BaseModel, frozen=True):
    """Resolution metadata for a single service."""
    service_name: str
    spec_reference: str          # "verified/email", "profiled/stripe", bare "stripe"
    surface: ServiceSurface
    resolution_source: str       # "tier1_pack", "context_hub", "openapi", "llm_inference", "kernel_inference"


class WorldPlan(BaseModel, frozen=True):
    """Complete world plan — output of D4a, input to D4b.

    Contains:
    - Resolved services (each has a ServiceSurface with operations + schemas)
    - Reality conditions (dimensions + LLM prompt context)
    - Actor specs (raw YAML, D4b expands with personalities)
    - Policies, seeds, mission (raw YAML, D4b processes)
    - Behavior + animator settings (for runtime, not compilation)
    """
    # ── Metadata ──
    name: str = ""
    description: str = ""
    seed: int = 42
    behavior: str = "dynamic"       # static | reactive | dynamic
    fidelity: str = "auto"          # auto | strict | exploratory
    mode: str = "governed"          # governed | ungoverned

    # ── Resolved services (D4a fills) ──
    services: dict[str, ServiceResolution] = Field(default_factory=dict)

    # ── Actor specs (raw, D4b expands) ──
    actor_specs: list[dict[str, Any]] = Field(default_factory=list)

    # ── Reality (D1) ──
    conditions: WorldConditions = Field(default_factory=WorldConditions)
    reality_prompt_context: dict[str, Any] = Field(default_factory=dict)

    # ── Raw YAML sections (D4b processes) ──
    policies: list[dict[str, Any]] = Field(default_factory=list)
    seeds: list[str] = Field(default_factory=list)
    mission: str = ""

    # ── Runtime settings (carried to engines) ──
    animator_settings: dict[str, Any] = Field(default_factory=dict)

    # ── Blueprint (if detected) ──
    blueprint: str | None = None

    # ── Compilation metadata ──
    source: str = ""                # "yaml" or "nl"
    warnings: list[str] = Field(default_factory=list)

    def validate_plan(self) -> list[str]:
        """Validate plan completeness. Returns list of errors."""
        errors: list[str] = []
        if not self.name:
            errors.append("WorldPlan missing name")
        if not self.services:
            errors.append("WorldPlan has no resolved services")
        for svc_name, res in self.services.items():
            surface_errors = res.surface.validate_surface()
            for se in surface_errors:
                errors.append(f"Service '{svc_name}': {se}")
        if self.fidelity == "strict":
            for svc_name, res in self.services.items():
                if res.surface.confidence < 0.5:
                    errors.append(f"Service '{svc_name}' below strict fidelity (confidence={res.surface.confidence})")
        return errors

    def get_service_names(self) -> list[str]:
        """All resolved service names."""
        return list(self.services.keys())

    def get_entity_types(self) -> set[str]:
        """All entity types across all resolved services."""
        types: set[str] = set()
        for res in self.services.values():
            types.update(res.surface.entity_schemas.keys())
        return types
```

### File 3: `terrarium/engines/world_compiler/yaml_parser.py` (NEW)

```python
"""YAML parser for world definition + compiler settings files.

Handles both YAML file paths and pre-loaded dicts (from NL parser).
Integrates with D1 ConditionExpander for reality section processing.
"""
from __future__ import annotations
import logging
from pathlib import Path
from typing import Any

import yaml

from terrarium.core.errors import YAMLParseError
from terrarium.engines.world_compiler.plan import WorldPlan
from terrarium.reality.expander import ConditionExpander

logger = logging.getLogger(__name__)


class YAMLParser:
    """Parses world definition + compiler settings YAML → WorldPlan components."""

    def __init__(self, condition_expander: ConditionExpander | None = None) -> None:
        self._expander = condition_expander or ConditionExpander()

    async def parse(
        self,
        world_def_path: str | Path,
        compiler_settings_path: str | Path | None = None,
    ) -> tuple[WorldPlan, dict[str, Any]]:
        """Parse YAML files → (partial WorldPlan, service_specs).

        Returns:
            WorldPlan with empty services (caller resolves them)
            + dict mapping service_name → spec_reference string
        """
        world_def = self._load_yaml(world_def_path)
        compiler_settings = self._load_yaml(compiler_settings_path) if compiler_settings_path else {}
        return await self.parse_from_dicts(world_def, compiler_settings)

    async def parse_from_dicts(
        self,
        world_def: dict[str, Any],
        compiler_settings: dict[str, Any] | None = None,
    ) -> tuple[WorldPlan, dict[str, Any]]:
        """Parse dicts → (partial WorldPlan, service_specs)."""
        compiler_settings = compiler_settings or {}
        world = world_def.get("world", world_def)
        compiler = compiler_settings.get("compiler", compiler_settings)

        # Extract sections
        service_specs = self._extract_service_specs(world.get("services", {}))
        actor_specs = self._extract_actor_specs(world.get("actors", []))
        policies = world.get("policies", [])
        seeds = world.get("seeds", [])
        mission = world.get("mission", "")

        # Process reality via D1 ConditionExpander
        conditions, reality_ctx = self._extract_reality(compiler)

        # Compiler metadata
        meta = self._extract_compiler_metadata(compiler)

        plan = WorldPlan(
            name=world.get("name", "Unnamed World"),
            description=world.get("description", ""),
            seed=meta.get("seed", 42),
            behavior=meta.get("behavior", "dynamic"),
            fidelity=meta.get("fidelity", "auto"),
            mode=meta.get("mode", "governed"),
            services={},  # Empty — caller fills via CompilerServiceResolver
            actor_specs=actor_specs,
            conditions=conditions,
            reality_prompt_context=reality_ctx,
            policies=policies,
            seeds=seeds,
            mission=mission,
            animator_settings=compiler.get("animator", {}),
            source="yaml",
        )
        return plan, service_specs

    def _load_yaml(self, path: str | Path) -> dict[str, Any]:
        """Load a YAML file. Raises YAMLParseError on failure."""
        path = Path(path)
        try:
            with path.open("r") as f:
                data = yaml.safe_load(f)
            return data if isinstance(data, dict) else {}
        except FileNotFoundError:
            raise YAMLParseError(f"YAML file not found: {path}")
        except yaml.YAMLError as exc:
            raise YAMLParseError(f"Invalid YAML in {path}: {exc}")

    def _extract_service_specs(self, services: dict | list) -> dict[str, Any]:
        """Extract service_name → spec_reference mapping.

        Handles all formats from the spec:
        - Simple: email: verified/email
        - Complex: web: {provider: verified/browser, sites: [...]}
        - Bare: stripe (no prefix)
        """
        specs: dict[str, Any] = {}
        if isinstance(services, dict):
            for name, value in services.items():
                specs[name] = value  # str or dict
        return specs

    def _extract_actor_specs(self, actors: list) -> list[dict[str, Any]]:
        """Extract actor specs, preserving ALL YAML fields."""
        return [dict(a) for a in actors] if actors else []

    def _extract_reality(self, compiler: dict) -> tuple[Any, dict]:
        """Extract reality section → (WorldConditions, prompt_context)."""
        reality = compiler.get("reality", {})
        preset = reality.get("preset", "messy")

        # Build overrides from non-preset fields
        overrides: dict[str, Any] = {}
        for dim_name in ("information", "reliability", "friction", "complexity", "boundaries"):
            if dim_name in reality:
                overrides[dim_name] = reality[dim_name]

        # Expand via D1
        conditions = self._expander.expand(preset, overrides if overrides else None)
        prompt_ctx = self._expander.build_prompt_context(conditions)

        return conditions, prompt_ctx

    def _extract_compiler_metadata(self, compiler: dict) -> dict[str, Any]:
        """Extract seed, behavior, fidelity, mode."""
        return {
            "seed": compiler.get("seed", 42),
            "behavior": compiler.get("behavior", "dynamic"),
            "fidelity": compiler.get("fidelity", "auto"),
            "mode": compiler.get("mode", "governed"),
        }
```

### File 4: `terrarium/engines/world_compiler/nl_parser.py` (NEW)

```python
"""NL parser — converts natural language description to structured world plan.

Uses the LLM as a TRANSLATOR (Layer 1): NL → structured YAML dicts.
This is different from Layer 2 (entity generation in D4b) which uses
LLM as a CREATOR to generate content.
"""
from __future__ import annotations
import json
import logging
from typing import Any

from terrarium.core.errors import NLParseError
from terrarium.engines.world_compiler.prompt_templates import (
    NL_TO_WORLD_DEF,
    NL_TO_COMPILER_SETTINGS,
    PromptTemplate,
)
from terrarium.llm.router import LLMRouter

logger = logging.getLogger(__name__)


class NLParser:
    """Converts natural language world description to structured dicts."""

    def __init__(self, llm_router: LLMRouter) -> None:
        self._router = llm_router

    async def parse(
        self,
        description: str,
        reality: str = "messy",
        behavior: str = "dynamic",
        fidelity: str = "auto",
        seed: int = 42,
        categories: str = "",
        verified_packs: str = "",
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        """NL description → (world_def_dict, compiler_settings_dict).

        Uses two LLM calls:
        1. NL → world definition (services, actors, policies, seeds)
        2. NL → compiler settings (reality, behavior, animator)

        Args:
            description: Natural language world description
            reality: Preset hint (ideal/messy/hostile)
            behavior: Behavior mode hint (static/reactive/dynamic)
            fidelity: Fidelity mode hint (auto/strict/exploratory)
            seed: Reproducibility seed
            categories: Comma-separated category names (for LLM context)
            verified_packs: Comma-separated pack names (for LLM context)

        Returns:
            Tuple of (world_def_dict, compiler_settings_dict)

        Raises:
            NLParseError: If LLM response cannot be parsed
        """
        # Step 1: Generate world definition
        world_def = await self._generate_world_def(description, categories, verified_packs)

        # Step 2: Generate compiler settings
        compiler_settings = await self._generate_compiler_settings(
            description, reality, behavior, fidelity, seed
        )

        return world_def, compiler_settings

    async def _generate_world_def(self, description: str, categories: str, verified_packs: str) -> dict:
        """Use LLM to generate world definition from NL."""
        try:
            response = await NL_TO_WORLD_DEF.execute(
                self._router,
                description=description,
                categories=categories or "communication, work_management, money_transactions, scheduling, code_devops, identity_auth, storage_documents, authority_approvals, monitoring_observability",
                verified_packs=verified_packs or "email, chat, tickets, payments, repos, calendar",
            )
            return NL_TO_WORLD_DEF.parse_json_response(response)
        except (json.JSONDecodeError, KeyError, ValueError) as exc:
            raise NLParseError(f"Failed to parse world definition from LLM: {exc}")
        except Exception as exc:
            raise NLParseError(f"LLM call failed: {exc}")

    async def _generate_compiler_settings(
        self, description: str, reality: str, behavior: str, fidelity: str, seed: int
    ) -> dict:
        """Use LLM to generate compiler settings."""
        try:
            response = await NL_TO_COMPILER_SETTINGS.execute(
                self._router,
                description=description,
                reality=reality,
                behavior=behavior,
                fidelity=fidelity,
                seed=seed,
            )
            return NL_TO_COMPILER_SETTINGS.parse_json_response(response)
        except (json.JSONDecodeError, KeyError, ValueError) as exc:
            # Fallback: use defaults with user hints
            logger.warning("Failed to parse compiler settings from LLM, using defaults: %s", exc)
            return {
                "compiler": {
                    "seed": seed,
                    "behavior": behavior,
                    "fidelity": fidelity,
                    "mode": "governed",
                    "reality": {"preset": reality},
                }
            }
```

### File 5: `terrarium/engines/world_compiler/service_resolution.py` (NEW)

```python
"""Full service resolution chain for the world compiler.

Bridges PackRegistry (Tier 1/2) with ServiceResolver (external specs + kernel).
"""
from __future__ import annotations
import logging
from typing import Any

from terrarium.core.errors import ServiceResolutionFailedError
from terrarium.engines.world_compiler.plan import ServiceResolution
from terrarium.kernel.registry import SemanticRegistry
from terrarium.kernel.resolver import ServiceResolver
from terrarium.kernel.surface import ServiceSurface
from terrarium.packs.registry import PackRegistry

logger = logging.getLogger(__name__)


class CompilerServiceResolver:
    """Resolves ALL services in a world definition."""

    def __init__(
        self,
        pack_registry: PackRegistry | None = None,
        kernel: SemanticRegistry | None = None,
        resolver: ServiceResolver | None = None,
    ) -> None:
        self._packs = pack_registry
        self._kernel = kernel
        self._resolver = resolver

    async def resolve_all(
        self,
        service_specs: dict[str, Any],
        fidelity_mode: str = "auto",
    ) -> tuple[dict[str, ServiceResolution], list[str]]:
        """Resolve ALL services. Returns (resolutions, warnings)."""
        resolutions: dict[str, ServiceResolution] = {}
        warnings: list[str] = []

        for svc_name, spec_ref in service_specs.items():
            try:
                resolution = await self.resolve_one(svc_name, spec_ref, fidelity_mode)
                if resolution:
                    resolutions[svc_name] = resolution
                else:
                    warnings.append(f"Could not resolve service '{svc_name}'")
            except Exception as exc:
                warnings.append(f"Error resolving '{svc_name}': {exc}")

        return resolutions, warnings

    async def resolve_one(
        self,
        service_name: str,
        spec_reference: Any,
        fidelity_mode: str = "auto",
    ) -> ServiceResolution | None:
        """Resolve a single service through the full chain."""
        tier, name = self._parse_spec_reference(spec_reference)

        # Step 1: Verified pack
        if tier == "verified" and self._packs:
            try:
                pack = self._packs.get_pack(name)
                surface = ServiceSurface.from_pack(pack)
                return ServiceResolution(
                    service_name=service_name,
                    spec_reference=str(spec_reference),
                    surface=surface,
                    resolution_source="tier1_pack",
                )
            except Exception:
                logger.debug("No verified pack for '%s'", name)

        # Step 2: Profiled service
        if tier == "profiled" and self._packs:
            # Check if profile extends a pack
            try:
                profiles = self._packs.get_profiles_for_pack(name)
                if profiles:
                    # For now, use the base pack's surface
                    # D4b will overlay profile-specific behavior
                    logger.debug("Found profile for '%s'", name)
            except Exception:
                pass

        # Steps 3-6: External specs + kernel (via D3 ServiceResolver)
        if self._resolver:
            surface = await self._resolver.resolve(service_name)
            if surface:
                # Check fidelity threshold in strict mode
                if fidelity_mode == "strict" and surface.confidence < 0.5:
                    logger.warning("Skipping '%s' in strict mode (confidence=%.1f)", service_name, surface.confidence)
                    return None
                return ServiceResolution(
                    service_name=service_name,
                    spec_reference=str(spec_reference),
                    surface=surface,
                    resolution_source=surface.source,
                )

        return None

    def _parse_spec_reference(self, spec_ref: Any) -> tuple[str, str]:
        """Parse spec reference into (tier, name).

        'verified/email' → ('verified', 'email')
        'profiled/stripe' → ('profiled', 'stripe')
        'stripe' → ('auto', 'stripe')
        dict → ('complex', pack_name_from_provider_key)
        """
        if isinstance(spec_ref, dict):
            provider = spec_ref.get("provider", "")
            if "/" in provider:
                parts = provider.split("/", 1)
                return parts[0], parts[1]
            return "complex", provider
        if isinstance(spec_ref, str) and "/" in spec_ref:
            parts = spec_ref.split("/", 1)
            return parts[0], parts[1]
        return "auto", str(spec_ref)
```

### File 6: Update `terrarium/engines/world_compiler/engine.py`

Replace stub methods with D4a orchestration. Keep D4b methods as stubs with clear docstrings.

```python
class WorldCompilerEngine(BaseEngine):
    engine_name = "world_compiler"
    dependencies = ["state"]
    subscriptions = []

    async def _on_initialize(self) -> None:
        """Wire sub-components."""
        self._condition_expander = ConditionExpander()
        self._yaml_parser = YAMLParser(self._condition_expander)

        # LLM router (optional — NL parsing needs it)
        self._llm_router = self._config.get("_llm_router")
        self._nl_parser = NLParser(self._llm_router) if self._llm_router else None

        # Service resolution (optional — needs kernel + packs)
        self._compiler_resolver = None
        kernel = self._config.get("_kernel")
        pack_registry = self._config.get("_pack_registry")
        service_resolver = self._config.get("_service_resolver")
        if kernel:
            self._compiler_resolver = CompilerServiceResolver(
                pack_registry=pack_registry,
                kernel=kernel,
                resolver=service_resolver,
            )

    async def compile_from_yaml(self, world_def_path, settings_path=None) -> WorldPlan:
        """YAML files → WorldPlan (D4a)."""
        partial, specs = await self._yaml_parser.parse(world_def_path, settings_path)
        return await self._resolve_and_assemble(partial, specs)

    async def compile_from_nl(self, description, reality="messy", behavior="dynamic",
                               fidelity="auto", seed=42) -> WorldPlan:
        """NL description → WorldPlan (D4a)."""
        if not self._nl_parser:
            raise CompilerError("NL parsing requires an LLM router")

        # Provide context about available services
        categories = ""
        verified_packs = ""
        if self._compiler_resolver and self._compiler_resolver._kernel:
            categories = ", ".join(self._compiler_resolver._kernel.list_categories())
        if self._compiler_resolver and self._compiler_resolver._packs:
            verified_packs = ", ".join(
                p["pack_name"] for p in self._compiler_resolver._packs.list_packs()
            )

        world_def, settings = await self._nl_parser.parse(
            description, reality, behavior, fidelity, seed,
            categories=categories, verified_packs=verified_packs,
        )
        partial, specs = await self._yaml_parser.parse_from_dicts(world_def, settings)
        # Override source
        partial = partial.model_copy(update={"source": "nl"})
        return await self._resolve_and_assemble(partial, specs)

    async def _resolve_and_assemble(self, partial, service_specs) -> WorldPlan:
        """Resolve services and assemble final WorldPlan."""
        if not self._compiler_resolver:
            return partial.model_copy(update={
                "warnings": list(partial.warnings) + ["No service resolver available"],
            })

        resolutions, warnings = await self._compiler_resolver.resolve_all(
            service_specs, partial.fidelity,
        )

        return partial.model_copy(update={
            "services": resolutions,
            "warnings": list(partial.warnings) + warnings,
        })

    # ── D4b stubs (next phase) ──

    async def generate_world(self, plan: WorldPlan) -> dict:
        """D4b: Generate entities from WorldPlan. Stub — next phase."""
        raise NotImplementedError("D4b: entity generation not yet implemented")

    async def _handle_event(self, event) -> None:
        logger.debug("WorldCompiler received event: %s", event.event_type)
```

### File 7: `terrarium/core/errors.py` — Add compiler errors

```python
class CompilerError(TerrariumError): pass
class YAMLParseError(CompilerError): pass
class NLParseError(CompilerError): pass
class ServiceResolutionFailedError(CompilerError): pass
class WorldPlanValidationError(CompilerError): pass
```

---

## Test YAML Fixtures

### `tests/fixtures/worlds/acme_support.yaml` (world definition)
Full example from the spec — services, actors, policies, seeds, mission.

### `tests/fixtures/worlds/acme_compiler.yaml` (compiler settings)
Matching settings — seed, behavior, fidelity, reality preset.

### `tests/fixtures/worlds/minimal_world.yaml`
```yaml
world:
  name: "Minimal Test World"
  description: "A simple test world"
  services:
    email: verified/email
  actors:
    - role: agent
      type: external
      count: 1
```

---

## Test Harness (~41 tests)

*(Same as previous plan — test_plan.py 8, test_yaml_parser.py 12, test_nl_parser.py 7, test_service_resolution.py 9, test_engine.py 5)*

---

## Verification

1. `pytest tests/engines/world_compiler/ -v` — ALL ~41 pass
2. `pytest tests/ -q` — 928 + ~41 = ~969 passed
3. Manual YAML compilation
4. Manual NL compilation (mock LLM)

---

## Post-Implementation

1. Save plan to `plans/D4a-compiler-planning.md`
2. Update IMPLEMENTATION_STATUS.md
3. Next: D4b (entity generation + validation + seed injection + StateEngine population)
