# Phase D2: Actors Module — Generic Actor Framework

## Context

**Phase:** D2 (second Phase D item — depends on D1)
**Module:** `terrarium/actors/`
**Depends on:** D1 (SocialFrictionDimension from reality module)
**Goal:** Generic, extensible actor framework. Actors are DATA, not code. No per-role subclasses. Plugin-ready personality generation. Multi-key registry.

**Key framework principle:** "We will have so many different actors, entities, personalities — we cannot keep creating new ones for everything."
- **No `class SupportAgent(Actor)` subclasses** — ActorDefinition is one model for ALL roles
- **Personality is trait-based** — universal core + extensible `traits: dict` for domain-specific
- **FrictionProfile replaces AdversarialProfile** — full spectrum: uncooperative → deceptive → hostile
- **Generator is a Protocol** — D2 provides heuristic impl, D4 plugs in LLM impl
- **Registry is generic** — `query(**filters)` not `get_agents()`, `get_humans()`

---

## Architecture

```
World Definition YAML:
  actors:
    - role: customer, count: 50, type: internal, personality: "Mix of patient and frustrated..."
    - role: support-agent, count: 2, type: external, permissions: {...}, budget: {...}
        ↓
SimpleActorGenerator.generate_batch(actor_specs, conditions)
    ↓
For each spec:
  1. Expand count (1 spec with count=50 → 50 ActorDefinitions)
  2. Generate personality from hint + conditions (heuristic or LLM)
  3. Distribute friction profiles based on SocialFrictionDimension:
     - uncooperative: ~30% get uncooperative FrictionProfile
     - deceptive: ~15% get deceptive FrictionProfile
     - hostile: ~8% get hostile FrictionProfile
     - rest: cooperative (no friction profile)
  4. Assign unique ActorIds
        ↓
ActorRegistry.register_batch(actors)
    ↓
registry.query(role="customer", has_friction=True) → [actors with friction]
registry.query(type=ActorType.AGENT) → [external agents]
```

---

## Implementation Steps (8 source files + 5 test files)

### Step 1: `terrarium/core/errors.py` — Add actor errors

```python
class ActorError(TerrariumError): pass
class ActorNotFoundError(ActorError): pass
class DuplicateActorError(ActorError): pass
class ActorGenerationError(ActorError): pass
```
Export from `core/__init__.py`.

### Step 2: `terrarium/actors/personality.py` — Trait-based models

**Personality** — extensible with `traits: dict[str, Any]`:
```python
class Personality(BaseModel, frozen=True):
    style: str = "balanced"           # universal
    response_time: str = "5m"         # universal
    strengths: list[str] = []         # universal
    weaknesses: list[str] = []        # universal
    availability: str | None = None   # universal
    traits: dict[str, Any] = {}       # EXTENSIBLE — domain-specific traits
    description: str = ""             # NL summary for LLM context
```

**FrictionProfile** — replaces AdversarialProfile:
```python
class FrictionProfile(BaseModel, frozen=True):
    category: str = "uncooperative"   # uncooperative | deceptive | hostile
    intensity: int = Field(30, ge=0, le=100)
    behaviors: list[str] = []         # ["vague_requests", "changes_mind", ...]
    sophistication: Literal["low", "medium", "high"] = "medium"
    goal: str = ""
    traits: dict[str, Any] = {}       # EXTENSIBLE
```

**AdversarialProfile** — kept as deprecated alias:
```python
def AdversarialProfile(**kwargs) -> FrictionProfile:
    """Deprecated. Use FrictionProfile(category='hostile', ...) instead."""
    kwargs.setdefault("category", "hostile")
    return FrictionProfile(**kwargs)
```

### Step 3: `terrarium/actors/definition.py` — Generic actor model

```python
class ActorDefinition(BaseModel, frozen=True):
    id: ActorId
    type: ActorType                    # agent | human | system
    role: str
    team: str | None = None
    count: int = 1                     # from YAML: how many instances
    permissions: dict[str, Any] = {}
    budget: dict[str, Any] | None = None
    visibility: dict[str, Any] | None = None
    personality: Personality | None = None
    friction_profile: FrictionProfile | None = None
    metadata: dict[str, Any] = {}      # EXTENSIBLE — world-specific fields
    personality_hint: str = ""          # raw YAML personality text for LLM
```

### Step 4: `terrarium/actors/config.py` — Generator config

```python
class ActorConfig(BaseModel, frozen=True):
    default_agent_budget: dict[str, Any] = {}
    default_human_response_time: str = "5m"
    generator_seed: int = 42
    style_weights: dict[str, float] = {"balanced": 0.3, "cautious": 0.2, ...}
    friction_behaviors: dict[str, list[str]] = {
        "uncooperative": ["vague_requests", "changes_mind", "slow_to_respond", ...],
        "deceptive": ["looks_legitimate", "provides_fake_evidence", ...],
        "hostile": ["explicit_threats", "system_exploitation", ...],
    }
```

### Step 5: `terrarium/actors/generator.py` — Protocol definition

```python
@runtime_checkable
class ActorPersonalityGenerator(Protocol):
    async def generate_personality(self, role, personality_hint, conditions, domain_context="") -> Personality: ...
    async def generate_friction_profile(self, category, intensity, sophistication, domain_context="") -> FrictionProfile: ...
    async def generate_batch(self, actor_specs, conditions, domain_context="") -> list[ActorDefinition]: ...
```

### Step 6: `terrarium/actors/simple_generator.py` — Heuristic implementation (NEW)

No LLM. Uses seeded RNG + configurable vocabulary.

```python
class SimpleActorGenerator:
    """Heuristic personality generation. Satisfies ActorPersonalityGenerator protocol."""

    def __init__(self, seed=42, config=None):
        self._rng = random.Random(seed)
        self._config = config or ActorConfig()

    async def generate_batch(self, actor_specs, conditions, domain_context=""):
        """
        1. Expand count (spec with count=50 → 50 actors)
        2. Generate personality for each from hint + conditions
        3. Distribute friction profiles based on conditions.friction
        4. Assign unique ActorIds
        """

    def _distribute_friction(self, total, friction_dim):
        """
        uncooperative=30 + deceptive=15 + hostile=8 → 53% get friction
        Uses intensity as approximate percentage, seeded for reproducibility.
        Returns: [(category, count), ...]
        """

    def _pick_style(self, conditions):
        """Weighted random style from config.style_weights."""

    def _generate_behaviors(self, category, sophistication):
        """Pick N behaviors from config.friction_behaviors[category]."""
```

**Friction distribution algorithm:**
```python
hostile_count = round(total * friction.hostile / 100)
deceptive_count = round(total * friction.deceptive / 100)
uncooperative_count = round(total * friction.uncooperative / 100)
# Ensure no double-counting: hostile actors aren't also counted as uncooperative
# Remaining are cooperative (no friction profile)
```

### Step 7: `terrarium/actors/registry.py` — Generic multi-key registry

```python
class ActorRegistry:
    def register(self, actor): ...           # builds indices, raises DuplicateActorError
    def register_batch(self, actors): ...    # bulk register
    def get(self, actor_id): ...             # by ID, raises ActorNotFoundError
    def get_or_none(self, actor_id): ...     # by ID, returns None
    def query(self, **filters): ...          # GENERIC: role=, type=, team=, has_friction=, friction_category=
    def list_actors(self): ...               # all actors
    def count(self): ...                     # total count
    def has_actor(self, actor_id): ...       # boolean
    def summary(self): ...                   # metadata: counts by type, role, friction
```

**query() implementation:**
```python
def query(self, **filters):
    result_ids = set(self._actors.keys())  # start with all
    if "role" in filters:
        result_ids &= set(self._role_index.get(filters["role"], []))
    if "type" in filters:
        result_ids &= set(self._type_index.get(filters["type"], []))
    if "team" in filters:
        result_ids &= set(self._team_index.get(filters["team"], []))
    results = [self._actors[aid] for aid in result_ids]
    if "has_friction" in filters:
        has = filters["has_friction"]
        results = [a for a in results if (a.friction_profile is not None) == has]
    if "friction_category" in filters:
        cat = filters["friction_category"]
        results = [a for a in results if a.friction_profile and a.friction_profile.category == cat]
    return results
```

### Step 8: `terrarium/actors/__init__.py` — Updated exports

Export: ActorDefinition, Personality, FrictionProfile, AdversarialProfile, ActorRegistry, ActorPersonalityGenerator, SimpleActorGenerator, ActorConfig

---

## Test Harness (~45 tests)

### test_personality.py (~10 tests)
| Test | Validates |
|------|-----------|
| `test_personality_defaults` | style="balanced", empty traits dict |
| `test_personality_with_domain_traits` | traits={"patience": 0.3, "escalation_threshold": "low"} |
| `test_personality_frozen` | Cannot mutate |
| `test_personality_description` | NL summary field |
| `test_friction_profile_defaults` | category="uncooperative", intensity=30 |
| `test_friction_profile_hostile` | category="hostile" with behaviors list |
| `test_friction_profile_frozen` | Cannot mutate |
| `test_friction_profile_intensity_bounds` | 0-100 range validated |
| `test_friction_profile_extensible` | traits dict accepts arbitrary keys |
| `test_adversarial_compat` | AdversarialProfile() creates FrictionProfile(category="hostile") |

### test_definition.py (~8 tests)
| Test | Validates |
|------|-----------|
| `test_required_fields` | id, type, role |
| `test_with_personality` | personality field set |
| `test_with_friction_profile` | friction_profile field set |
| `test_metadata_extensibility` | metadata dict accepts anything |
| `test_personality_hint` | raw YAML string carried |
| `test_count_field` | default=1, override works |
| `test_frozen` | Cannot mutate |
| `test_permissions_budget` | dict fields work |

### test_registry.py (~17 tests)
| Test | Validates |
|------|-----------|
| `test_register_and_get` | Register, retrieve by ID |
| `test_duplicate_raises` | DuplicateActorError |
| `test_not_found_raises` | ActorNotFoundError |
| `test_get_or_none` | Returns None for missing |
| `test_query_by_role` | query(role="customer") |
| `test_query_by_type` | query(type=ActorType.HUMAN) |
| `test_query_by_team` | query(team="support") |
| `test_query_has_friction` | query(has_friction=True) |
| `test_query_friction_category` | query(friction_category="hostile") |
| `test_query_multiple_filters` | AND logic: role + has_friction |
| `test_query_no_filters` | Returns all |
| `test_query_no_results` | Returns empty list |
| `test_register_batch` | Multiple actors at once |
| `test_list_actors` | All actors |
| `test_count` | Total count |
| `test_has_actor` | Boolean check |
| `test_summary` | Counts by type, role, friction |

### test_generator.py (~10 tests)
| Test | Validates |
|------|-----------|
| `test_protocol_check` | SimpleActorGenerator satisfies ActorPersonalityGenerator |
| `test_generate_personality` | Returns valid Personality |
| `test_generate_personality_deterministic` | Same seed = same result |
| `test_generate_friction_profile` | Returns valid FrictionProfile |
| `test_generate_batch_count_expansion` | count=50 → 50 actors |
| `test_generate_batch_friction_distribution` | Friction %s match conditions approximately |
| `test_generate_batch_cooperative_world` | everyone_helpful → no friction profiles |
| `test_generate_batch_hostile_world` | actively_hostile → many friction profiles |
| `test_generate_batch_unique_ids` | All IDs unique |
| `test_generate_batch_preserves_metadata` | Extra YAML fields in metadata |

---

## Files to Modify / Create

| File | Action |
|------|--------|
| `terrarium/core/errors.py` | Add ActorError family (4 classes) |
| `terrarium/core/__init__.py` | Export new errors |
| `terrarium/actors/personality.py` | REWRITE — Personality + FrictionProfile + compat alias |
| `terrarium/actors/definition.py` | REWRITE — extensible with metadata, friction_profile, personality_hint |
| `terrarium/actors/config.py` | REWRITE — generator config with friction vocabulary |
| `terrarium/actors/generator.py` | REWRITE — Protocol definition only |
| `terrarium/actors/simple_generator.py` | CREATE — heuristic implementation |
| `terrarium/actors/registry.py` | REWRITE — generic multi-key with query() |
| `terrarium/actors/__init__.py` | UPDATE — exports |
| `tests/actors/test_personality.py` | IMPLEMENT — 10 tests |
| `tests/actors/test_definition.py` | IMPLEMENT — 8 tests |
| `tests/actors/test_registry.py` | IMPLEMENT — 17 tests |
| `tests/actors/test_generator.py` | IMPLEMENT — 10 tests |

---

## Design Compliance

| Principle | How D2 follows it |
|-----------|------------------|
| **No hardcoding** | Actors are data (YAML-driven). No per-role subclasses. |
| **Extensible** | `traits: dict`, `metadata: dict`, `behaviors: list[str]` — all open-ended |
| **Plugin architecture** | ActorPersonalityGenerator Protocol. D2=heuristic, D4=LLM. |
| **Generic registry** | `query(**filters)` not `get_agents()`. Zero role-specific logic. |
| **Frozen models** | All Pydantic models frozen |
| **Config-driven** | Friction vocabulary, style weights from ActorConfig |
| **Seeded reproducibility** | `random.Random(seed)` instance, not global |
| **Module isolation** | actors/ imports only core/ and reality/ (for WorldConditions) |

---

## Verification

1. `pytest tests/actors/ -v` — ALL ~45 pass
2. `pytest tests/ -q` — 850 + ~45 = ~895 passed
3. `grep -rn "get_adversarial\|get_agents\|get_humans" terrarium/actors/registry.py` — ZERO (replaced by generic query)
4. Manual:
```python
from terrarium.actors import SimpleActorGenerator, ActorRegistry
from terrarium.reality import load_preset
conditions = load_preset("messy")
gen = SimpleActorGenerator(seed=42)
actors = await gen.generate_batch(
    [{"role": "customer", "count": 10, "type": "human"}],
    conditions,
)
reg = ActorRegistry()
reg.register_batch(actors)
print(f"Total: {reg.count()}")
print(f"With friction: {len(reg.query(has_friction=True))}")
print(f"Hostile: {len(reg.query(friction_category='hostile'))}")
```

---

---

## Detailed Implementation Code for Agents

### SimpleActorGenerator.generate_batch — FULL ALGORITHM

```python
async def generate_batch(self, actor_specs, conditions, domain_context=""):
    actors = []
    friction = conditions.friction  # SocialFrictionDimension

    for spec in actor_specs:
        role = spec["role"]
        actor_type = ActorType(spec.get("type", "human"))
        count = spec.get("count", 1)
        hint = spec.get("personality", "")
        permissions = spec.get("permissions", {})
        budget = spec.get("budget")
        team = spec.get("team")
        # Anything not in known keys goes to metadata
        known_keys = {"role", "type", "count", "personality", "permissions", "budget", "team"}
        metadata = {k: v for k, v in spec.items() if k not in known_keys}

        # Determine friction distribution for internal actors
        if actor_type != ActorType.AGENT:
            friction_assignments = self._distribute_friction(count, friction)
        else:
            friction_assignments = []  # External agents don't get friction

        friction_idx = 0
        for i in range(count):
            actor_id = ActorId(f"{role}-{uuid.uuid4().hex[:8]}")

            # Generate personality
            personality = await self.generate_personality(role, hint, conditions, domain_context)

            # Assign friction profile if this actor is in the friction pool
            friction_profile = None
            if friction_idx < len(friction_assignments):
                cat, intensity = friction_assignments[friction_idx]
                friction_profile = await self.generate_friction_profile(
                    cat, intensity, friction.sophistication, domain_context
                )
                friction_idx += 1

            actors.append(ActorDefinition(
                id=actor_id, type=actor_type, role=role, team=team,
                permissions=permissions, budget=budget,
                personality=personality, friction_profile=friction_profile,
                metadata=metadata, personality_hint=hint,
            ))
    return actors
```

### _distribute_friction — EXACT LOGIC

```python
def _distribute_friction(self, total, friction_dim):
    """Returns list of (category, intensity) tuples for actors that get friction.

    Uses friction dimension intensity values as approximate percentages.
    Seeded RNG ensures reproducibility.
    """
    assignments = []
    # Hostile first (subset of hostile), then deceptive, then uncooperative
    hostile_n = round(total * friction_dim.hostile / 100)
    deceptive_n = round(total * friction_dim.deceptive / 100)
    uncoop_n = round(total * friction_dim.uncooperative / 100)

    # Avoid double-counting: hostile actors count toward the deceptive/uncooperative pools
    deceptive_n = max(0, deceptive_n - hostile_n)
    uncoop_n = max(0, uncoop_n - hostile_n - deceptive_n)

    for _ in range(hostile_n):
        assignments.append(("hostile", self._rng.randint(60, 100)))
    for _ in range(deceptive_n):
        assignments.append(("deceptive", self._rng.randint(30, 70)))
    for _ in range(uncoop_n):
        assignments.append(("uncooperative", self._rng.randint(15, 50)))

    self._rng.shuffle(assignments)
    return assignments
```

### ActorRegistry.query — EXACT IMPLEMENTATION

```python
def query(self, **filters):
    if not filters:
        return list(self._actors.values())

    # Start with all actor IDs
    result_ids: set[ActorId] | None = None

    # Index-based filters (fast set intersection)
    if "role" in filters:
        ids = set(self._role_index.get(filters["role"], []))
        result_ids = ids if result_ids is None else result_ids & ids
    if "type" in filters:
        ids = set(self._type_index.get(filters["type"], []))
        result_ids = ids if result_ids is None else result_ids & ids
    if "team" in filters:
        ids = set(self._team_index.get(filters["team"], []))
        result_ids = ids if result_ids is None else result_ids & ids

    # Get actor objects
    if result_ids is None:
        results = list(self._actors.values())
    else:
        results = [self._actors[aid] for aid in result_ids if aid in self._actors]

    # Object-level filters (linear scan on filtered set)
    if "has_friction" in filters:
        want = filters["has_friction"]
        results = [a for a in results if (a.friction_profile is not None) == want]
    if "friction_category" in filters:
        cat = filters["friction_category"]
        results = [a for a in results if a.friction_profile and a.friction_profile.category == cat]

    return results
```

### Spec Alignment Note

The spec says: "Friction: some_difficult_people means the LLM generates some actors who are naturally difficult." In D2's **SimpleActorGenerator**, the intensity numbers are used as approximate percentages for heuristic distribution. In D4's **CompilerPersonalityGenerator** (LLM-based), the friction dimension is passed as creative direction — the LLM decides which actors are difficult and how, producing richer personalities. Both generators satisfy the same Protocol, making them interchangeable.

---

## What D2 Does NOT Leave as Stubs

Everything in D2 scope is FULLY implemented:
- ✅ Personality model with extensible traits
- ✅ FrictionProfile replacing AdversarialProfile (backward-compat alias)
- ✅ ActorDefinition with metadata, friction_profile, personality_hint
- ✅ ActorPersonalityGenerator Protocol
- ✅ SimpleActorGenerator with seeded heuristic generation
- ✅ ActorRegistry with generic query()
- ✅ ActorConfig with friction vocabulary
- ✅ All error types
- ✅ All tests

The ONLY stubs remaining after D2 are methods that genuinely require LLM (D4):
- `CompilerPersonalityGenerator` in `engines/world_compiler/personality_generator.py` — D4 scope

---

## Post-Implementation

1. Save plan to `plans/D2-actors.md`
2. Update `IMPLEMENTATION_STATUS.md` — flip actor rows to done
3. Next: D3 (kernel — static service→category registry)
