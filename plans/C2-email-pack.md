# Phase C2: Extensible Pack Framework + Email Pack

## Context

**Phase:** C2 (second Phase C item — service pack system)
**Module:** `terrarium/packs/` (framework) + `terrarium/packs/verified/email/` (first proof)
**Depends on:** B1 (validation), C1 (state engine)
**Goal:** Generic, extensible pack framework. Email is first test case. Zero hardcoding.

**The user's principles:**
- "Take a pack, apply; take the data, apply and run"
- No local implementation — everything abstract
- Community-driven — drop-in directory packs
- Framework enforcement — bypassing the framework must fail validation
- Persistence owns SQL — packs NEVER touch SQL

---

## Ownership Boundaries (ENFORCED)

| Layer | Owns | Does NOT Own |
|-------|------|-------------|
| `persistence/` | SQL, tables, migrations, connections | Business logic, validation |
| `packs/base.py` | ABC contract (4 abstract methods) | Implementation details |
| `packs/{pack}/` | Tool definitions, schemas, state machines, handler logic | SQL, table creation, validation |
| `packs/registry.py` | Pack indexing, tool lookup, discovery | Execution, validation |
| `packs/runtime.py` | Validation orchestration, fidelity tagging | Pack-specific logic |
| `validation/` | Schema + state machine validation | Pack knowledge |
| `engines/state/` | Entity persistence via StateDelta | Pack dispatch |

**Enforcement:** Packs produce `StateDelta` objects → `StateEngine` persists them. Packs NEVER import from `persistence/`, `engines/`, or `bus/`. They only import from `core/` (types, context).

---

## Implementation: Detailed Code

### Step 1: `terrarium/core/errors.py` — Add pack errors

After the existing `StateError` section (~line 191), add:

```python
# ---------------------------------------------------------------------------
# Pack errors
# ---------------------------------------------------------------------------

class PackError(TerrariumError):
    """Base error for service pack operations."""
    pass

class PackNotFoundError(PackError):
    """No pack registered for the requested name or tool."""
    pass

class PackLoadError(PackError):
    """A pack module could not be loaded from disk."""
    pass

class DuplicatePackError(PackError):
    """A pack with the same pack_name is already registered."""
    pass
```

Update `terrarium/core/__init__.py` to add these to imports and `__all__`.

---

### Step 2: `terrarium/packs/base.py` — Add dispatch helper

**Reference:** Current file at `terrarium/packs/base.py:17-78`

Add BEFORE the `ServiceProfile` class (after `ServicePack`):

```python
from typing import Any, Awaitable, Callable, ClassVar

# Type alias for pack action handlers
ActionHandler = Callable[[dict[str, Any], dict[str, Any]], Awaitable[ResponseProposal]]
```

Add to `ServicePack` class (after the abstract methods, as a CONCRETE method):

```python
    # ---- Concrete dispatch helper ----
    _handlers: ClassVar[dict[str, ActionHandler]] = {}

    async def dispatch_action(
        self,
        action: ToolName,
        input_data: dict[str, Any],
        state: dict[str, Any],
    ) -> ResponseProposal:
        """Data-driven dispatch to registered _handlers.

        Packs that populate _handlers as a ClassVar can delegate
        handle_action to this method in a single line:
            async def handle_action(self, action, input_data, state):
                return await self.dispatch_action(action, input_data, state)

        Raises:
            ValueError: If no handler is registered for the action.
        """
        handler = self._handlers.get(str(action))
        if handler is None:
            known = sorted(self._handlers.keys())
            raise ValueError(
                f"Pack '{self.pack_name}' has no handler for action '{action}'. "
                f"Available: {known}"
            )
        return await handler(input_data, state)

    def get_tool_names(self) -> list[str]:
        """Return just the tool name strings (convenience)."""
        return [t["name"] for t in self.get_tools()]
```

---

### Step 3: `terrarium/packs/loader.py` — NEW file

```python
"""Dynamic pack and profile loader.

Discovers ServicePack/ServiceProfile subclasses by scanning directory trees
and importing pack.py / profile.py modules via importlib.

This is the ONLY module that performs dynamic imports of packs.
"""
from __future__ import annotations

import importlib
import inspect
import logging
from pathlib import Path

from terrarium.packs.base import ServicePack, ServiceProfile

logger = logging.getLogger(__name__)


def discover_packs(base_dir: str | Path) -> list[ServicePack]:
    """Scan subdirectories of base_dir for pack.py files.

    For each subdirectory containing pack.py:
    1. Compute dotted module path: terrarium.packs.verified.{subdir}.pack
    2. Import via importlib.import_module
    3. Find all ServicePack subclasses (not the ABC itself)
    4. Instantiate each (zero-arg constructor)

    Bad directories are logged as warnings and skipped.
    """
    results: list[ServicePack] = []
    base = Path(base_dir)
    if not base.is_dir():
        return results

    for subdir in sorted(base.iterdir()):
        if not subdir.is_dir() or subdir.name.startswith("_"):
            continue
        pack_file = subdir / "pack.py"
        if not pack_file.exists():
            continue
        module_path = _module_path_from_filepath(pack_file)
        if module_path is None:
            logger.warning("Could not determine module path for %s", pack_file)
            continue
        try:
            mod = importlib.import_module(module_path)
            classes = _find_subclasses(mod, ServicePack)
            for cls in classes:
                instance = cls()
                if instance.pack_name:  # skip malformed packs
                    results.append(instance)
                    logger.info("Discovered pack: %s (%s)", instance.pack_name, module_path)
        except Exception as exc:
            logger.warning("Failed to load pack from %s: %s", subdir.name, exc)
    return results


def discover_profiles(base_dir: str | Path) -> list[ServiceProfile]:
    """Same pattern as discover_packs but for profile.py / ServiceProfile."""
    results: list[ServiceProfile] = []
    base = Path(base_dir)
    if not base.is_dir():
        return results

    for subdir in sorted(base.iterdir()):
        if not subdir.is_dir() or subdir.name.startswith("_"):
            continue
        profile_file = subdir / "profile.py"
        if not profile_file.exists():
            continue
        module_path = _module_path_from_filepath(profile_file)
        if module_path is None:
            continue
        try:
            mod = importlib.import_module(module_path)
            classes = _find_subclasses(mod, ServiceProfile)
            for cls in classes:
                instance = cls()
                if instance.profile_name:
                    results.append(instance)
                    logger.info("Discovered profile: %s (%s)", instance.profile_name, module_path)
        except Exception as exc:
            logger.warning("Failed to load profile from %s: %s", subdir.name, exc)
    return results


def _find_subclasses(module: object, base_class: type) -> list[type]:
    """Find all classes in module that are concrete subclasses of base_class."""
    found: list[type] = []
    for _, obj in inspect.getmembers(module, inspect.isclass):
        if (
            issubclass(obj, base_class)
            and obj is not base_class
            and not inspect.isabstract(obj)
        ):
            found.append(obj)
    return found


def _module_path_from_filepath(filepath: Path) -> str | None:
    """Convert filesystem path to dotted module path.

    Walks up from filepath to find 'terrarium' package root.
    Example: /Users/.../terrarium/packs/verified/email/pack.py
           → terrarium.packs.verified.email.pack
    """
    parts = filepath.resolve().parts
    try:
        idx = parts.index("terrarium")
    except ValueError:
        return None
    # Strip .py extension from last part
    module_parts = list(parts[idx:])
    module_parts[-1] = module_parts[-1].replace(".py", "")
    return ".".join(module_parts)
```

---

### Step 4: `terrarium/packs/registry.py` — NEW file

```python
"""Pack registry — central index for all registered service packs and profiles.

Maintains three indices built from pack ABC methods:
- by pack_name: direct pack lookup
- by tool_name: reverse lookup (any tool → its owning pack)
- by category: category → [packs]

Contains ZERO pack-specific logic. All indexing derived from ServicePack ABC.
"""
from __future__ import annotations

import logging
from typing import Any

from terrarium.core.errors import DuplicatePackError, PackNotFoundError
from terrarium.packs.base import ServicePack, ServiceProfile
from terrarium.packs.loader import discover_packs, discover_profiles

logger = logging.getLogger(__name__)


class PackRegistry:
    """Central registry for packs and profiles with multi-key lookup."""

    def __init__(self) -> None:
        self._packs: dict[str, ServicePack] = {}
        self._tool_index: dict[str, str] = {}          # tool_name → pack_name
        self._category_index: dict[str, list[str]] = {} # category → [pack_name]
        self._profiles: dict[str, ServiceProfile] = {}
        self._profile_pack_index: dict[str, list[str]] = {}  # pack_name → [profile_name]

    def register(self, pack: ServicePack) -> None:
        """Register a pack. Builds all indices from pack's ABC methods.

        Raises:
            ValueError: If pack_name is empty.
            DuplicatePackError: If pack_name already registered.
        """
        if not pack.pack_name:
            raise ValueError("ServicePack must have a non-empty pack_name")
        if pack.pack_name in self._packs:
            raise DuplicatePackError(f"Pack '{pack.pack_name}' is already registered")

        # Store pack
        self._packs[pack.pack_name] = pack

        # Build tool index from pack.get_tools()
        for tool_def in pack.get_tools():
            tool_name = tool_def.get("name", "")
            if tool_name:
                if tool_name in self._tool_index:
                    logger.warning(
                        "Tool '%s' already registered by pack '%s', overwriting with '%s'",
                        tool_name, self._tool_index[tool_name], pack.pack_name,
                    )
                self._tool_index[tool_name] = pack.pack_name

        # Build category index
        self._category_index.setdefault(pack.category, []).append(pack.pack_name)
        logger.info("Registered pack '%s' (category=%s, tools=%d)",
                     pack.pack_name, pack.category, len(pack.get_tools()))

    def register_profile(self, profile: ServiceProfile) -> None:
        """Register a service profile. Validates extends_pack is registered."""
        if not profile.profile_name:
            raise ValueError("ServiceProfile must have a non-empty profile_name")
        if profile.extends_pack not in self._packs:
            raise PackNotFoundError(
                f"Profile '{profile.profile_name}' extends pack '{profile.extends_pack}' "
                f"which is not registered"
            )
        self._profiles[profile.profile_name] = profile
        self._profile_pack_index.setdefault(profile.extends_pack, []).append(profile.profile_name)

    def discover(self, verified_path: str, profiled_path: str | None = None) -> None:
        """Scan filesystem directories and register all discovered packs/profiles."""
        for pack in discover_packs(verified_path):
            if pack.pack_name not in self._packs:
                self.register(pack)
        if profiled_path:
            for profile in discover_profiles(profiled_path):
                if profile.profile_name not in self._profiles:
                    try:
                        self.register_profile(profile)
                    except PackNotFoundError:
                        logger.warning("Profile '%s' extends unregistered pack '%s'",
                                       profile.profile_name, profile.extends_pack)

    def get_pack(self, pack_name: str) -> ServicePack:
        """Retrieve pack by name. Raises PackNotFoundError."""
        if pack_name not in self._packs:
            raise PackNotFoundError(
                f"Pack '{pack_name}' not registered. Available: {sorted(self._packs.keys())}"
            )
        return self._packs[pack_name]

    def get_pack_for_tool(self, tool_name: str) -> ServicePack:
        """Reverse lookup: tool → owning pack. Raises PackNotFoundError."""
        pack_name = self._tool_index.get(tool_name)
        if pack_name is None:
            raise PackNotFoundError(
                f"No pack provides tool '{tool_name}'. Available tools: {sorted(self._tool_index.keys())}"
            )
        return self._packs[pack_name]

    def get_packs_for_category(self, category: str) -> list[ServicePack]:
        """Return all packs in a category. Returns [] if unknown category."""
        names = self._category_index.get(category, [])
        return [self._packs[n] for n in names]

    def get_profiles_for_pack(self, pack_name: str) -> list[ServiceProfile]:
        """Return all profiles extending a pack."""
        names = self._profile_pack_index.get(pack_name, [])
        return [self._profiles[n] for n in names]

    def list_packs(self) -> list[dict[str, Any]]:
        """Return metadata for all packs."""
        return [
            {
                "pack_name": p.pack_name,
                "category": p.category,
                "fidelity_tier": p.fidelity_tier,
                "tools": [t["name"] for t in p.get_tools()],
            }
            for p in self._packs.values()
        ]

    def list_tools(self) -> list[dict[str, Any]]:
        """Return all tools across all packs."""
        tools: list[dict[str, Any]] = []
        for pack in self._packs.values():
            for tool_def in pack.get_tools():
                tools.append({**tool_def, "pack_name": pack.pack_name, "category": pack.category})
        return tools

    def has_pack(self, pack_name: str) -> bool:
        return pack_name in self._packs

    def has_tool(self, tool_name: str) -> bool:
        return tool_name in self._tool_index
```

---

### Step 5: `terrarium/packs/runtime.py` — NEW file

This is the execution engine. **ZERO pack-specific logic.** Uses existing validators.

```python
"""Pack runtime — generic execution engine for service pack actions.

Contains ZERO pack-specific logic. Dispatches to ANY ServicePack through
the ABC contract, validates input/output against the pack's own schemas
and state machines using existing validators.

Enforcement: This is the ONLY sanctioned execution path. Calling
pack.handle_action() directly bypasses validation and fidelity tagging.
"""
from __future__ import annotations

import logging
from typing import Any

from terrarium.core.context import ResponseProposal
from terrarium.core.errors import PackNotFoundError, ValidationError
from terrarium.core.types import (
    FidelityMetadata,
    FidelitySource,
    FidelityTier,
    ToolName,
)
from terrarium.packs.base import ServicePack
from terrarium.packs.registry import PackRegistry
from terrarium.validation.schema import SchemaValidator, ValidationResult
from terrarium.validation.state_machine import StateMachineValidator

logger = logging.getLogger(__name__)


class PackRuntime:
    """Generic runtime for executing pack actions with validation.

    Execute pipeline (pack-agnostic):
    1. Resolve pack from tool name via registry
    2. Validate input against pack.get_entity_schemas()
    3. Call pack.handle_action(action, input_data, state)
    4. Validate output: entity deltas against schemas
    5. Validate output: state transitions against state machines
    6. Tag response with FidelityMetadata
    7. Return validated ResponseProposal
    """

    def __init__(
        self,
        pack_registry: PackRegistry,
        schema_validator: SchemaValidator | None = None,
        state_machine_validator: StateMachineValidator | None = None,
    ) -> None:
        self._registry = pack_registry
        self._schema_validator = schema_validator or SchemaValidator()
        self._sm_validator = state_machine_validator or StateMachineValidator()

    async def execute(
        self,
        action: str,
        input_data: dict[str, Any],
        state: dict[str, Any] | None = None,
    ) -> ResponseProposal:
        """Execute an action through its pack with full validation.

        Args:
            action: Tool name (e.g., "email_send").
            input_data: Input payload for the tool.
            state: Current entity state (dict of entity lists keyed by type).

        Returns:
            Validated ResponseProposal with FidelityMetadata.

        Raises:
            PackNotFoundError: No pack provides this tool.
            ValidationError: Input or output fails validation.
        """
        state = state or {}

        # 1. Resolve pack (generic lookup — no pack-specific logic)
        pack = self._registry.get_pack_for_tool(action)
        entity_schemas = pack.get_entity_schemas()
        state_machines = pack.get_state_machines()

        # 2. Validate input against tool parameter schema
        tool_def = self._find_tool_def(pack, action)
        if tool_def and "parameters" in tool_def:
            input_result = self._schema_validator.validate_entity(input_data, tool_def["parameters"])
            if not input_result.valid:
                raise ValidationError(
                    message=f"Input validation failed for '{action}': {input_result.errors}",
                    validation_type="schema",
                )

        # 3. Dispatch to pack (the ABC contract — handle_action)
        proposal = await pack.handle_action(ToolName(action), input_data, state)

        # 4. Validate output: entity deltas against schemas
        for delta in (proposal.proposed_state_deltas or []):
            schema = entity_schemas.get(delta.entity_type)
            if schema and delta.operation in ("create", "update"):
                entity_result = self._schema_validator.validate_entity(delta.fields, schema)
                if not entity_result.valid:
                    raise ValidationError(
                        message=f"Entity schema validation failed for {delta.entity_type}: {entity_result.errors}",
                        validation_type="schema",
                    )

        # 5. Validate output: state transitions
        for delta in (proposal.proposed_state_deltas or []):
            sm = state_machines.get(delta.entity_type)
            if sm and "status" in delta.fields:
                new_status = delta.fields["status"]
                old_status = (delta.previous_fields or {}).get("status")
                if old_status is not None:
                    # Update: validate transition
                    sm_result = self._sm_validator.validate_transition(old_status, new_status, sm)
                    if not sm_result.valid:
                        raise ValidationError(
                            message=f"State transition invalid for {delta.entity_type}: {sm_result.errors}",
                            validation_type="state_machine",
                        )
                else:
                    # Create: validate initial state is a known state
                    all_states = set(sm.get("transitions", {}).keys())
                    for targets in sm.get("transitions", {}).values():
                        all_states.update(targets)
                    if all_states and new_status not in all_states:
                        raise ValidationError(
                            message=f"Invalid initial state '{new_status}' for {delta.entity_type}",
                            validation_type="state_machine",
                        )

        # 6. Tag with FidelityMetadata (if not already tagged by pack)
        if proposal.fidelity is None:
            proposal = ResponseProposal(
                response_body=proposal.response_body,
                proposed_events=proposal.proposed_events,
                proposed_state_deltas=proposal.proposed_state_deltas,
                proposed_side_effects=proposal.proposed_side_effects,
                fidelity=FidelityMetadata(
                    tier=FidelityTier(pack.fidelity_tier),
                    source=FidelitySource.VERIFIED_PACK,
                    deterministic=True,
                    replay_stable=True,
                    benchmark_grade=True,
                ),
                fidelity_warning=proposal.fidelity_warning,
            )

        return proposal

    def _find_tool_def(self, pack: ServicePack, action: str) -> dict | None:
        """Find the tool definition for an action from the pack's tool list."""
        for tool in pack.get_tools():
            if tool.get("name") == action:
                return tool
        return None
```

**Key framework enforcement:** Calling `pack.handle_action()` directly works (it must — it's a method), but the response will NOT have:
- Input validation against tool parameter schemas
- Output validation against entity schemas
- State machine transition validation
- FidelityMetadata tagging

This means any code path that bypasses PackRuntime produces unvalidated, untagged responses — which the pipeline's validation step (B1) will catch downstream.

---

### Step 6: Email Pack (proof case)

**6a: `terrarium/packs/verified/email/schemas.py` (NEW)** — Pure data, zero logic.

Contains: `EMAIL_ENTITY_SCHEMA`, `MAILBOX_ENTITY_SCHEMA`, `THREAD_ENTITY_SCHEMA`, `EMAIL_TOOL_DEFINITIONS` — all as plain dicts/lists. (See plan agent output for exact content.)

**6b: `terrarium/packs/verified/email/handlers.py` (REPLACE stubs)** — 6 pure async functions.

Each handler: `async def handle_X(input_data: dict, state: dict) -> ResponseProposal`
- Returns ResponseProposal with response_body + proposed_state_deltas
- NEVER imports from persistence/, engines/, bus/
- Uses only core/ types (StateDelta, EntityId, ResponseProposal)
- Generates entity IDs via `EntityId(f"email-{uuid.uuid4().hex[:12]}")`

**6c: `terrarium/packs/verified/email/pack.py` (REPLACE stub)** — Data-driven delegation:
```python
class EmailPack(ServicePack):
    pack_name = "email"
    category = "communication"
    fidelity_tier = 1
    _handlers = {
        "email_send": handle_email_send,
        "email_list": handle_email_list,
        ... # all 6
    }
    def get_tools(self): return list(EMAIL_TOOL_DEFINITIONS)
    def get_entity_schemas(self): return {"email": EMAIL_ENTITY_SCHEMA, ...}
    def get_state_machines(self): return {"email": {"transitions": EMAIL_TRANSITIONS}}
    async def handle_action(self, action, input_data, state):
        return await self.dispatch_action(action, input_data, state)
```

---

### Step 7: Update `__init__.py` files

- `terrarium/packs/__init__.py` — export PackRegistry, PackRuntime, ActionHandler, discover_packs, discover_profiles
- `terrarium/core/__init__.py` — export PackError, PackNotFoundError, PackLoadError, DuplicatePackError

### Step 8: Wire Tier1Dispatcher

`terrarium/engines/responder/tier1.py` — Replace stub body:
```python
class Tier1Dispatcher:
    def __init__(self, pack_runtime: PackRuntime): self._runtime = pack_runtime
    async def dispatch(self, ctx): return await self._runtime.execute(ctx.action, ctx.input_data)
```

---

## Test Harness (~48 tests)

### Framework Enforcement Tests (KEY — proves packs can't bypass)

In `test_runtime.py`:
```python
async def test_bypass_direct_call_lacks_fidelity():
    """Calling pack.handle_action directly produces NO FidelityMetadata."""
    pack = MockPack()
    proposal = await pack.handle_action("mock_action", {"x": 1}, {})
    assert proposal.fidelity is None  # No tagging without runtime

async def test_runtime_always_tags_fidelity():
    """Runtime.execute always tags FidelityMetadata."""
    registry = PackRegistry(); registry.register(MockPack())
    runtime = PackRuntime(registry)
    proposal = await runtime.execute("mock_action", {"x": 1})
    assert proposal.fidelity is not None
    assert proposal.fidelity.tier == FidelityTier.VERIFIED

async def test_runtime_validates_invalid_entity():
    """Runtime rejects bad entity data that pack.handle_action would accept."""
    # MockPack returns a create delta with missing required fields
    # Direct call: succeeds (no validation)
    # Runtime: raises ValidationError
```

### test_registry.py (~11 tests — MockPack only, never EmailPack)

```
test_register_and_get — register, retrieve by name
test_register_duplicate_raises — DuplicatePackError
test_register_empty_name_raises — ValueError
test_get_pack_not_found — PackNotFoundError with available list
test_get_pack_for_tool — reverse lookup works
test_get_pack_for_unknown_tool — PackNotFoundError
test_get_packs_for_category — category → list
test_get_packs_unknown_category — returns []
test_list_packs — metadata dicts
test_list_tools — aggregated across packs
test_has_pack_and_has_tool — boolean checks
```

### test_runtime.py (~12 tests — MockPack only)

```
test_execute_valid — returns ResponseProposal
test_execute_unknown_tool — PackNotFoundError
test_execute_tags_fidelity — FidelityMetadata added
test_execute_preserves_existing_fidelity — doesn't overwrite
test_execute_validates_input_schema — bad input → ValidationError
test_execute_validates_entity_deltas — bad entity → ValidationError
test_execute_validates_transitions — invalid transition → ValidationError
test_execute_valid_create_initial_state — new entity initial state validated
test_execute_read_only_no_deltas — no deltas passes cleanly
test_bypass_direct_call_lacks_fidelity — handle_action directly has no fidelity
test_runtime_always_tags_fidelity — runtime always tags
test_runtime_rejects_what_direct_accepts — validation enforcement proof
```

### test_loader.py (~5 tests)

```
test_discover_from_verified_dir — finds email pack from filesystem
test_discover_empty_dir — returns []
test_discover_bad_dir_skipped — logs warning, doesn't crash
test_discover_profiles — finds profiles from profiled dir
test_module_path_computation — correct dotted module path
```

### test_email_pack.py (~12 tests — through framework)

```
test_metadata — pack_name, category, fidelity_tier correct
test_tools_count_and_names — 6 tools
test_entity_schemas — email, mailbox, thread present
test_state_machines — email transitions present
test_send — creates entity with status="delivered"
test_list — returns filtered emails from state
test_read — transitions delivered→read
test_reply — creates reply with thread_id + in_reply_to
test_search — filters by query/sender/subject
test_mark_read — batch transitions
test_schemas_validate — entity data passes SchemaValidator
test_state_machines_validate — transitions pass StateMachineValidator
```

### test_pack_integration.py (~8 tests — E2E)

```
test_email_registers_via_discover — filesystem discovery works
test_runtime_execute_send — full runtime → ResponseProposal
test_full_lifecycle — send → read → reply → list
test_invalid_transition_blocked — trashed→sent raises ValidationError
test_fidelity_tier1 — tier=1, deterministic=True
test_second_mock_pack_works_identically — proves extensibility (no email-specific code)
test_pack_with_no_state_machines — framework doesn't crash if pack has no SMs
test_pack_imports_only_core — verify email pack imports only from core/ (no persistence/engines/bus)
```

---

## Verification

1. `pytest tests/packs/ -v` — ALL pass
2. `grep -rn "EmailPack\|email_send" terrarium/packs/registry.py terrarium/packs/runtime.py terrarium/packs/loader.py` — 0 results (framework is generic)
3. `grep -rn "from terrarium.persistence\|from terrarium.engines\|from terrarium.bus" terrarium/packs/verified/email/` — 0 results (packs only import core/)
4. `grep -rn "^\s*\.\.\.$" terrarium/packs/**/*.py` — 0 stubs
5. `pytest tests/ -q` — 758 + ~48 = ~806 passed

---

## Files to Modify / Create

| File | Action |
|------|--------|
| `terrarium/core/errors.py` | Add 4 PackError classes |
| `terrarium/core/__init__.py` | Export new errors |
| `terrarium/packs/base.py` | Add dispatch_action + ActionHandler |
| `terrarium/packs/loader.py` | **CREATE** — dynamic discovery |
| `terrarium/packs/registry.py` | **CREATE** — central index |
| `terrarium/packs/runtime.py` | **CREATE** — execution engine |
| `terrarium/packs/verified/email/schemas.py` | **CREATE** — data definitions |
| `terrarium/packs/verified/email/handlers.py` | **IMPLEMENT** — 6 handlers |
| `terrarium/packs/verified/email/pack.py` | **IMPLEMENT** — EmailPack |
| `terrarium/packs/__init__.py` | Export framework |
| `terrarium/engines/responder/tier1.py` | Wire to PackRuntime |
| `tests/packs/test_registry.py` | **CREATE** — 11 tests |
| `tests/packs/test_runtime.py` | **CREATE** — 12 tests |
| `tests/packs/test_loader.py` | **CREATE** — 5 tests |
| `tests/packs/test_email_pack.py` | **REPLACE** — 12 tests |
| `tests/packs/test_pack_integration.py` | **CREATE** — 8 tests |

---

## Post-Implementation

1. Save plan to `plans/C2-email-pack.md`
2. Update `IMPLEMENTATION_STATUS.md`
3. Update focus: `C2 ✅ → Next: C3 WIRE (full pipeline E2E)`
