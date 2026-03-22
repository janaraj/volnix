# Phase D1: Reality Module — World Personality System

## Context

**Phase:** D1 (first Phase D item — no dependencies, feeds D2 + D4)
**Module:** `terrarium/reality/`
**Goal:** Implement the 5-dimension reality system with two-level config (labels + numbers), preset loading from YAML, and an expander that packages conditions for LLM prompts.

**Key spec principle:** Dimensions are PERSONALITY TRAITS, not engineering parameters. The LLM interprets them holistically. "somewhat_neglected information" means the LLM generates a world where data management has been neglected — contextually coherent, not randomly distributed.

**What D1 does NOT do:** No LLM calls (that's D4). No entity mutation (the LLM does that during compilation). No concrete overlay implementations (post-MVP).

**Scope clarification — Two YAML files:**
The spec defines two separate YAML files:
1. **World Definition YAML** (domain-specific: services, actors, policies, seeds, mission) — this is **D4's job** (compiler parses it)
2. **Compiler Settings YAML** (universal: seed, behavior, fidelity, mode, reality dimensions, animator) — **D1 handles the `reality:` section** within this

D1 creates 3 small preset YAML files (ideal/messy/hostile) that define dimension labels. D1 also implements the config parsing for the `reality:` section of compiler settings. The full world definition YAML parsing and the compiler settings file structure are D4.

---

## Architecture

```
User: --reality messy --adjust "friction: many_difficult_people"
    ↓
ConditionExpander.expand("messy", overrides={"friction": "many_difficult_people"})
    ↓
1. load_preset("messy") → YAML → 5 labels (somewhat_neglected, occasionally_flaky, ...)
2. Apply overrides → friction label upgraded to "many_difficult_people"
3. Resolve labels → WorldConditions with 5 frozen dimension models
    ↓
ConditionExpander.build_prompt_context(conditions) → dict
    ↓
Structured context for LLM:
{
    "reality_summary": "This is a messy world with...",
    "dimensions": {
        "information": {"level": "somewhat_neglected", "attributes": {...}, "description": "..."},
        "reliability": {"level": "occasionally_flaky", ...},
        "friction": {"level": "many_difficult_people", ...},
        "complexity": {"level": "moderately_challenging", ...},
        "boundaries": {"level": "a_few_gaps", ...},
    }
}
    ↓
D4 (World Compiler) passes this to LLM during world generation
D4 (Animator) uses this as ongoing creative direction at runtime
```

---

## Implementation Steps (12 files)

### Step 1: Add `pyyaml` dependency
**File:** `pyproject.toml`
Add `"pyyaml>=6.0"` to dependencies list.

### Step 2: Add Reality error types
**File:** `terrarium/core/errors.py`
```python
class RealityError(TerrariumError): pass
class InvalidLabelError(RealityError): pass  # unknown label string
class InvalidPresetError(RealityError): pass  # unknown preset name
class DimensionValueError(RealityError): pass  # value out of 0-100 range
```
Export from `core/__init__.py`.

### Step 3: Rewrite `terrarium/reality/dimensions.py` — 5 dimension models + WorldConditions

All 18 attributes across 5 dimensions with correct names from spec:

| Dimension Class | Attributes (int 0-100) | Special |
|----------------|----------------------|---------|
| `InformationQualityDimension` | staleness, incompleteness, inconsistency, noise | — |
| `ReliabilityDimension` | failures, timeouts, degradation | — |
| `SocialFrictionDimension` | uncooperative, deceptive, hostile | sophistication: "low"/"medium"/"high" |
| `ComplexityDimension` | ambiguity, edge_cases, contradictions, urgency, volatility | — |
| `BoundaryDimension` | access_limits, rule_clarity, boundary_gaps | — |

All frozen Pydantic models. All numeric fields use `Field(default=0, ge=0, le=100)` for validation.

`WorldConditions` aggregate:
```python
class WorldConditions(BaseModel, frozen=True):
    information: InformationQualityDimension = Field(default_factory=InformationQualityDimension)
    reliability: ReliabilityDimension = Field(default_factory=ReliabilityDimension)
    friction: SocialFrictionDimension = Field(default_factory=SocialFrictionDimension)
    complexity: ComplexityDimension = Field(default_factory=ComplexityDimension)
    boundaries: BoundaryDimension = Field(default_factory=BoundaryDimension)
```

Shared base class `BaseDimension` with `to_dict()`, `field_names()` helpers.

### Step 4: Create `terrarium/reality/labels.py` — Label system (NEW file)

The two-level config system. Maps labels ↔ dimension values.

**5 labels per dimension, mapping to intensity ranges:**
```python
LABEL_SCALES = {
    "information": ["pristine", "mostly_clean", "somewhat_neglected", "poorly_maintained", "chaotic"],
    "reliability": ["rock_solid", "mostly_reliable", "occasionally_flaky", "frequently_broken", "barely_functional"],
    "friction": ["everyone_helpful", "mostly_cooperative", "some_difficult_people", "many_difficult_people", "actively_hostile"],
    "complexity": ["straightforward", "mostly_clear", "moderately_challenging", "frequently_confusing", "overwhelmingly_complex"],
    "boundaries": ["locked_down", "well_controlled", "a_few_gaps", "many_gaps", "wide_open"],
}
```

**Label → default attribute values (COMPLETE MAPPING TABLE):**

The numbers are intensity values (0-100) the LLM interprets. NOT percentages applied by code.

```python
# Information Quality defaults per label
INFORMATION_DEFAULTS = {
    "pristine":           {"staleness": 0, "incompleteness": 0, "inconsistency": 0, "noise": 0},
    "mostly_clean":       {"staleness": 10, "incompleteness": 12, "inconsistency": 5, "noise": 8},
    "somewhat_neglected": {"staleness": 30, "incompleteness": 35, "inconsistency": 20, "noise": 30},
    "poorly_maintained":  {"staleness": 55, "incompleteness": 60, "inconsistency": 40, "noise": 55},
    "chaotic":            {"staleness": 80, "incompleteness": 85, "inconsistency": 70, "noise": 80},
}

# Reliability defaults per label
RELIABILITY_DEFAULTS = {
    "rock_solid":          {"failures": 0, "timeouts": 0, "degradation": 0},
    "mostly_reliable":     {"failures": 8, "timeouts": 5, "degradation": 3},
    "occasionally_flaky":  {"failures": 20, "timeouts": 15, "degradation": 10},
    "frequently_broken":   {"failures": 50, "timeouts": 35, "degradation": 25},
    "barely_functional":   {"failures": 80, "timeouts": 60, "degradation": 50},
}

# Social Friction defaults per label
FRICTION_DEFAULTS = {
    "everyone_helpful":        {"uncooperative": 0, "deceptive": 0, "hostile": 0, "sophistication": "low"},
    "mostly_cooperative":      {"uncooperative": 10, "deceptive": 5, "hostile": 2, "sophistication": "low"},
    "some_difficult_people":   {"uncooperative": 30, "deceptive": 15, "hostile": 8, "sophistication": "medium"},
    "many_difficult_people":   {"uncooperative": 55, "deceptive": 30, "hostile": 20, "sophistication": "medium"},
    "actively_hostile":        {"uncooperative": 75, "deceptive": 50, "hostile": 40, "sophistication": "high"},
}

# Complexity defaults per label
COMPLEXITY_DEFAULTS = {
    "straightforward":          {"ambiguity": 0, "edge_cases": 0, "contradictions": 0, "urgency": 0, "volatility": 0},
    "mostly_clear":             {"ambiguity": 10, "edge_cases": 8, "contradictions": 3, "urgency": 5, "volatility": 3},
    "moderately_challenging":   {"ambiguity": 35, "edge_cases": 25, "contradictions": 15, "urgency": 20, "volatility": 15},
    "frequently_confusing":     {"ambiguity": 60, "edge_cases": 45, "contradictions": 30, "urgency": 40, "volatility": 30},
    "overwhelmingly_complex":   {"ambiguity": 85, "edge_cases": 70, "contradictions": 55, "urgency": 65, "volatility": 55},
}

# Boundaries defaults per label
BOUNDARIES_DEFAULTS = {
    "locked_down":     {"access_limits": 0, "rule_clarity": 0, "boundary_gaps": 0},
    "well_controlled": {"access_limits": 10, "rule_clarity": 8, "boundary_gaps": 3},
    "a_few_gaps":      {"access_limits": 25, "rule_clarity": 30, "boundary_gaps": 12},
    "many_gaps":       {"access_limits": 50, "rule_clarity": 55, "boundary_gaps": 30},
    "wide_open":       {"access_limits": 75, "rule_clarity": 80, "boundary_gaps": 55},
}
```

**Key functions:**
```python
def resolve_label(dimension_name: str, label: str) -> BaseDimension:
    """Convert a label to a dimension model with default attribute values."""

def resolve_dimension(dimension_name: str, value: str | dict) -> BaseDimension:
    """Resolve either a label string OR a per-attribute dict to a dimension model."""

def label_to_intensity(label: str, dimension_name: str) -> int:
    """Get the approximate center intensity (0-100) for a label."""

def is_valid_label(label: str, dimension_name: str) -> bool:
    """Check if a label is valid for a dimension."""
```

### Step 5: Rewrite YAML preset files

**`terrarium/reality/data/presets/ideal.yaml`:**
```yaml
information: pristine
reliability: rock_solid
friction: everyone_helpful
complexity: straightforward
boundaries: locked_down
```

**`terrarium/reality/data/presets/messy.yaml`:**
```yaml
information: somewhat_neglected
reliability: occasionally_flaky
friction: some_difficult_people
complexity: moderately_challenging
boundaries: a_few_gaps
```

**`terrarium/reality/data/presets/hostile.yaml`:**
```yaml
information: poorly_maintained
reliability: frequently_broken
friction: many_difficult_people
complexity: frequently_confusing
boundaries: many_gaps
```

Pure label format. The label system (Step 4) expands these to full attribute values.

### Step 6: Implement `terrarium/reality/presets.py`

Remove duplicate `RealityPreset` enum. Import from `core/types.py`.

```python
from terrarium.core.types import RealityPreset

def load_preset(preset: RealityPreset | str) -> WorldConditions:
    """Load a built-in preset from YAML, resolve labels, return WorldConditions."""

def load_from_yaml(path: str | Path) -> WorldConditions:
    """Load conditions from a custom YAML file."""

def _get_preset_path(preset: str) -> Path:
    """Resolve preset name to YAML file path."""
```

### Step 7: Update `terrarium/reality/config.py`

Support two-level config in `RealityConfig`:
```python
class RealityConfig(BaseModel):
    preset: str = "messy"
    # Each dimension can be a label string OR a dict of per-attribute values
    information: str | dict[str, Any] | None = None
    reliability: str | dict[str, Any] | None = None
    friction: str | dict[str, Any] | None = None
    complexity: str | dict[str, Any] | None = None
    boundaries: str | dict[str, Any] | None = None
```

`None` means "use preset default." A string means "override with this label." A dict means "override with these specific attribute values."

### Step 8: Rewrite `terrarium/reality/expander.py` — NO entity mutation

```python
class ConditionExpander:
    """Expands reality presets + overrides into WorldConditions and LLM prompt context.

    The expander does NOT mutate entities. It packages conditions as
    structured context for the LLM to interpret during world generation
    and animation. The LLM decides how personality traits manifest.
    """

    def expand(self, preset: str, overrides: dict | None = None) -> WorldConditions:
        """Load preset, apply per-dimension overrides, return resolved WorldConditions."""

    def build_prompt_context(self, conditions: WorldConditions) -> dict[str, Any]:
        """Package conditions as structured LLM prompt context.

        Returns a dict suitable for injection into LLM system prompts:
        {
            "reality_summary": "This is a messy world where...",
            "dimensions": {
                "information": {
                    "level": "somewhat_neglected",
                    "intensity": 33,
                    "attributes": {"staleness": 30, "incompleteness": 35, ...},
                    "description": "Information management has been neglected..."
                },
                ...
            }
        }
        """

    def get_summary(self, conditions: WorldConditions) -> str:
        """Return a human-readable one-paragraph summary."""

    def merge_overrides(self, base: WorldConditions, overrides: dict) -> WorldConditions:
        """Merge per-dimension overrides onto a base WorldConditions."""
```

**NO `apply_to_entities`, `apply_to_actors`, `apply_to_services`, `apply_to_boundaries`.**
Those methods are REMOVED. The LLM handles entity shaping in D4.

**`build_prompt_context` implementation detail:**
```python
def build_prompt_context(self, conditions: WorldConditions) -> dict[str, Any]:
    context = {"dimensions": {}}
    for dim_name in ["information", "reliability", "friction", "complexity", "boundaries"]:
        dim = getattr(conditions, dim_name)
        # Find which label best matches the current values
        level_label = self._find_closest_label(dim_name, dim)
        attrs = dim.to_dict()
        context["dimensions"][dim_name] = {
            "level": level_label,
            "attributes": attrs,
            "description": self._describe_dimension(dim_name, level_label, attrs),
        }
    context["reality_summary"] = self._build_summary(context["dimensions"])
    return context

def _describe_dimension(self, name: str, label: str, attrs: dict) -> str:
    """Generate a natural-language description of a dimension for LLM context."""
    # Maps each dimension+label to a descriptive sentence
    descriptions = {
        ("information", "somewhat_neglected"): "Information management has been neglected. Some records are outdated, some fields are missing, data across sources sometimes conflicts.",
        ("reliability", "occasionally_flaky"): "Infrastructure is somewhat unreliable. Services occasionally fail or timeout, especially under load.",
        # ... etc for all 25 combinations
    }
    return descriptions.get((name, label), f"{name}: {label}")
```

### Step 9: Rewrite `terrarium/reality/seeds.py` — Generic model

```python
class Seed(BaseModel, frozen=True):
    """A specific scenario guaranteed to exist in the world."""
    description: str
    entity_hints: dict[str, Any] = Field(default_factory=dict)
    actor_hints: dict[str, Any] = Field(default_factory=dict)
```

`SeedProcessor` stays as stubs (needs LLM from D4).

### Step 10: Implement `terrarium/reality/overlays.py` — Registry framework

Implement `OverlayRegistry` (register, get, list_overlays, compose). Keep the ABC. Don't implement concrete overlays (post-MVP). The pattern matches `PackRegistry`.

### Step 11: Update `terrarium/reality/__init__.py`

Export: `WorldConditions`, `ConditionExpander`, `load_preset`, all dimension classes, `OverlayRegistry`, `Seed`, label utilities.

### Step 12: Tests (~45 tests)

---

## Test Harness

### test_dimensions.py (~10 tests)
| Test | Validates |
|------|-----------|
| `test_information_defaults` | All 4 attrs default to 0 |
| `test_reliability_defaults` | All 3 attrs default to 0 |
| `test_friction_defaults` | All 3 attrs + sophistication="low" |
| `test_complexity_defaults` | All 5 attrs default to 0 |
| `test_boundary_defaults` | All 3 attrs default to 0 |
| `test_frozen_immutability` | Cannot mutate frozen models |
| `test_world_conditions_aggregate` | All 5 dimensions accessible |
| `test_validation_range` | Values outside 0-100 raise ValidationError |
| `test_field_names_helper` | field_names() returns correct list |
| `test_to_dict` | Serialization works |

### test_labels.py (~10 tests)
| Test | Validates |
|------|-----------|
| `test_all_25_labels_valid` | Every label recognized |
| `test_resolve_label_information` | "somewhat_neglected" → InformationQualityDimension with values |
| `test_resolve_label_friction` | "some_difficult_people" → SocialFrictionDimension |
| `test_resolve_dimension_with_label` | String input → resolved dimension |
| `test_resolve_dimension_with_dict` | Dict input → constructed dimension |
| `test_invalid_label_raises` | Bad label → InvalidLabelError |
| `test_label_intensity_ordering` | pristine < mostly_clean < somewhat_neglected < ... |
| `test_mixed_config` | Some labels, some dicts → all resolved |
| `test_sophistication_preserved` | Friction label preserves sophistication level |
| `test_label_scales_complete` | Every dimension has exactly 5 labels |

### test_presets.py (~8 tests)
| Test | Validates |
|------|-----------|
| `test_load_ideal` | All dimensions at lowest intensity |
| `test_load_messy` | All dimensions at moderate intensity |
| `test_load_hostile` | All dimensions at high intensity |
| `test_yaml_parseable` | All 3 YAML files load without error |
| `test_invalid_preset_raises` | "fantasy" → InvalidPresetError |
| `test_custom_yaml_path` | load_from_yaml with custom file |
| `test_preset_returns_frozen` | Result is frozen WorldConditions |
| `test_enum_values` | IDEAL/MESSY/HOSTILE match strings |

### test_expander.py (~12 tests)
| Test | Validates |
|------|-----------|
| `test_expand_messy` | Returns WorldConditions with moderate values |
| `test_expand_with_label_override` | Preset + label override merges correctly |
| `test_expand_with_dict_override` | Preset + dict override merges correctly |
| `test_expand_mixed_overrides` | Some labels, some dicts |
| `test_build_prompt_context` | Returns dict with reality_summary + dimensions |
| `test_prompt_context_has_all_5` | All 5 dimensions in context |
| `test_prompt_context_has_attributes` | Each dimension has level + attributes + description |
| `test_get_summary` | Returns readable string |
| `test_merge_overrides` | Merges correctly onto base |
| `test_invalid_dimension_name` | Unknown dimension in overrides → error |
| `test_no_apply_to_entities` | ConditionExpander has NO apply_to_entities method |
| `test_no_entity_mutation_methods` | Verify old mutation methods are GONE |

### test_overlays.py (~5 tests)
| Test | Validates |
|------|-----------|
| `test_registry_register_and_get` | Register overlay, retrieve by name |
| `test_registry_list` | List all overlays |
| `test_unknown_overlay_none` | Unknown name → None |
| `test_abc_not_instantiable` | Overlay ABC requires implementation |
| `test_registry_empty` | New registry has no overlays |

### test_seeds.py (~4 tests)
| Test | Validates |
|------|-----------|
| `test_seed_creation` | Description + optional hints |
| `test_seed_frozen` | Cannot mutate |
| `test_empty_hints` | Default empty dicts |
| `test_seed_with_hints` | entity_hints and actor_hints populated |

**Total: ~49 tests**

---

## Files to Modify / Create

| File | Action |
|------|--------|
| `pyproject.toml` | Add pyyaml dependency |
| `terrarium/core/errors.py` | Add RealityError hierarchy |
| `terrarium/core/__init__.py` | Export new errors |
| `terrarium/reality/dimensions.py` | REWRITE — 18 attrs, correct names |
| `terrarium/reality/labels.py` | CREATE — label system |
| `terrarium/reality/data/presets/*.yaml` | REWRITE — label format |
| `terrarium/reality/presets.py` | IMPLEMENT — YAML loading, remove dup enum |
| `terrarium/reality/config.py` | UPDATE — two-level config |
| `terrarium/reality/expander.py` | REWRITE — expand + prompt context (NO mutation) |
| `terrarium/reality/seeds.py` | REWRITE — generic Seed model |
| `terrarium/reality/overlays.py` | IMPLEMENT — registry framework |
| `terrarium/reality/__init__.py` | UPDATE — exports |
| `tests/reality/test_dimensions.py` | IMPLEMENT — 10 tests |
| `tests/reality/test_labels.py` | CREATE — 10 tests |
| `tests/reality/test_presets.py` | IMPLEMENT — 8 tests |
| `tests/reality/test_expander.py` | IMPLEMENT — 12 tests |
| `tests/reality/test_overlays.py` | IMPLEMENT — 5 tests |
| `tests/reality/test_seeds.py` | IMPLEMENT — 4 tests |

---

## Design Principles Compliance

| Principle | How D1 follows it |
|-----------|------------------|
| **No hardcoding** | Presets are YAML data, not code. Labels are data-driven. |
| **Config-driven** | Two-level config from TOML/YAML |
| **Frozen models** | All dimension models are frozen Pydantic |
| **No entity mutation** | Expander builds LLM prompt context, doesn't touch entities |
| **Extensible** | Overlay ABC for future domain extensions |
| **Reuses existing patterns** | Frozen models, ABC, registry, YAML loading |
| **No LLM in D1** | Pure data + logic. LLM integration is D4. |
| **Module isolation** | reality/ imports only core/ |

---

## Verification

1. `pytest tests/reality/ -v` — ALL ~49 pass
2. `grep -rn "apply_to_entities\|apply_to_actors\|apply_to_services\|apply_to_boundaries" terrarium/reality/` — ZERO results (old mutation methods gone)
3. `pytest tests/ -q` — 825 + ~49 = ~874 passed
4. Manual verification:
```python
from terrarium.reality import ConditionExpander, load_preset
conditions = load_preset("messy")
print(conditions.information.staleness)  # ~30
expander = ConditionExpander()
ctx = expander.build_prompt_context(conditions)
print(ctx["reality_summary"])  # Human-readable summary
```

---

## Post-Implementation

1. Save plan to `plans/D1-reality.md`
2. Update `IMPLEMENTATION_STATUS.md` — flip reality rows to done
3. Next: D2 (actors — uses WorldConditions from D1)
