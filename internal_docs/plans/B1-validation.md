# Phase B1: Validation Framework Implementation

## Context

**Phase:** B1 (first Phase B item — core infrastructure)
**Module:** `terrarium/validation/`
**Depends on:** Core types only (StateDelta, ResponseProposal). ConsistencyValidator uses StateEngineProtocol but via mock in tests.
**Goal:** 5 independent validators + 1 orchestrating pipeline. Validates everything the responder produces before it reaches the state engine.

**Bigger picture:** Validation is **step 6 of the 7-step pipeline** — the last gate before state mutations are committed. Per the spec (Section 17): "The safe fallback ensures the world never enters an inconsistent state, even when LLM generation fails." Every Tier 2 response passes through validation. If it fails, the world stays consistent — the agent gets a coherent error, not corrupted data.

**Who consumes this:**
- **B2 (pipeline)** — the validation step calls `ValidationPipeline.validate_response_proposal()`
- **C2 (email pack)** — pack state machines are validated by `StateMachineValidator`
- **C3 (wire)** — first E2E action includes validation step
- **F3 (reporter)** — reads `ValidationEntry` from ledger to report validation failures

**After B1:** We have all foundation (A1-A4) + validation. Pipeline (B2) can wire validation as step 6.

---

## Architecture

```
ValidationPipeline (orchestrator)
    │
    ├── 1. SchemaValidator
    │      Validates response_body against service response schema
    │      Validates entity fields against entity schemas
    │
    ├── 2. StateMachineValidator
    │      Validates state transitions (current → new) against state machine
    │      Returns valid transitions from any state
    │
    ├── 3. ConsistencyValidator (async — needs StateEngineProtocol)
    │      Validates cross-entity references (ref:entity_type → exists?)
    │      Validates entity existence
    │
    ├── 4. TemporalValidator
    │      Validates timestamps aren't in the future
    │      Validates ordering (before < after)
    │
    └── 5. AmountValidator
           Validates refund ≤ charge
           Validates budget deduction ≤ remaining
           Validates non-negative values

ValidationPipeline.validate_with_retry():
    run all validators → if fail → call LLM callback → retry once → if still fail → safe fallback
```

**Key property:** Each validator is independently testable with plain data. No real database, no real engine. ConsistencyValidator takes `StateEngineProtocol` which can be mocked.

---

## Design Principle Compliance

| Principle | How B1 follows it |
|-----------|------------------|
| **No hardcoded values** | Validators receive schemas, state machines, thresholds as data — not embedded in code. Schemas come from packs/profiles. |
| **Config-driven** | Validation config (strict_mode, max_retries) via `ValidationConfig` Pydantic model. Created in this phase. |
| **Use enums, not magic strings** | `ValidationType` enum for validation categories. Used in ValidationResult and ValidationEntry. |
| **Protocol-based DI** | ConsistencyValidator uses `StateEngineProtocol` (not concrete engine). Fully mockable. |
| **Ledger recording** | ValidationPipeline will produce `ValidationEntry` ledger records (plumbing in B2, entry type from A4). |
| **Frozen models** | `ValidationResult` is frozen Pydantic. Merge returns NEW instance. |
| **Phase A integration** | Uses core types (StateDelta, ResponseProposal), core protocols (StateEngineProtocol). No standalone connections. |

---

## Reuse from A1-A4

| What | From | Used by |
|------|------|---------|
| `ValidationResult` | validation/schema.py | All validators return this |
| `StateDelta` | core/types.py | ConsistencyValidator checks deltas |
| `ResponseProposal` | core/context.py | ValidationPipeline validates this |
| `StateEngineProtocol` | core/protocols.py | ConsistencyValidator queries state (mocked in tests) |
| `ValidationEntry` | ledger/entries.py | Pipeline records failures to ledger (integration in B2) |

---

## Implementation Order

### Step 0: Add `ValidationType` enum to `core/types.py` and `ValidationConfig`

Add to `terrarium/core/types.py`:
```python
class ValidationType(enum.StrEnum):
    """Categories of validation checks."""
    SCHEMA = "schema"
    STATE_MACHINE = "state_machine"
    CONSISTENCY = "consistency"
    TEMPORAL = "temporal"
    AMOUNT = "amount"
```

Create `terrarium/validation/config.py` (NEW):
```python
class ValidationConfig(BaseModel):
    """Configuration for the validation framework."""
    strict_mode: bool = True       # reject all invalid, no partial accept
    max_retries: int = 1           # retries for Tier 2 LLM validation failures
    max_reference_depth: int = 5   # max depth for reference chain validation
```

Update `terrarium/config/schema.py` to import and add to TerrariumConfig:
```python
from terrarium.validation.config import ValidationConfig
# In TerrariumConfig:
validation: ValidationConfig = Field(default_factory=ValidationConfig)
```

Update `terrarium/core/__init__.py` to export `ValidationType`.

### Step 1: `validation/schema.py` — ValidationResult + SchemaValidator

ValidationResult is the shared return type. Includes `validation_type` for structured reporting.

```python
class ValidationResult(BaseModel):
    valid: bool = True
    errors: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    validation_type: ValidationType | None = None  # set by each validator

    def merge(self, other: ValidationResult) -> ValidationResult:
        """Combine two results (AND logic — valid only if both valid). Returns NEW instance."""
        return ValidationResult(
            valid=self.valid and other.valid,
            errors=self.errors + other.errors,
            warnings=self.warnings + other.warnings,
        )

class SchemaValidator:
    def validate_response(self, response: dict, schema: dict) -> ValidationResult:
        """Validate response against schema.

        Schema format (simplified JSON Schema):
        {
            "required": ["id", "status"],
            "properties": {
                "id": {"type": "string"},
                "status": {"type": "string", "enum": ["pending", "succeeded"]},
                "amount": {"type": "integer", "minimum": 0},
            }
        }
        """
        errors = []
        props = schema.get("properties", {})
        required = schema.get("required", [])

        # Check required fields
        for field in required:
            if field not in response:
                errors.append(f"Missing required field: '{field}'")

        # Check field types and constraints
        for field, value in response.items():
            if field in props:
                field_schema = props[field]
                # Type check
                expected_type = field_schema.get("type")
                if expected_type and not _check_type(value, expected_type):
                    errors.append(f"Field '{field}': expected {expected_type}, got {type(value).__name__}")
                # Enum check
                enum_values = field_schema.get("enum")
                if enum_values and value not in enum_values:
                    errors.append(f"Field '{field}': value '{value}' not in {enum_values}")
                # Minimum check
                minimum = field_schema.get("minimum")
                if minimum is not None and isinstance(value, (int, float)) and value < minimum:
                    errors.append(f"Field '{field}': {value} < minimum {minimum}")
                # Maximum check
                maximum = field_schema.get("maximum")
                if maximum is not None and isinstance(value, (int, float)) and value > maximum:
                    errors.append(f"Field '{field}': {value} > maximum {maximum}")

        return ValidationResult(valid=len(errors) == 0, errors=errors)

    def validate_entity(self, entity: dict, entity_schema: dict) -> ValidationResult:
        """Validate entity dict against entity schema. Same logic as validate_response."""
        return self.validate_response(entity, entity_schema)

def _check_type(value, expected: str) -> bool:
    type_map = {"string": str, "integer": int, "number": (int, float), "boolean": bool, "array": list, "object": dict}
    expected_type = type_map.get(expected)
    if expected_type is None:
        return True  # unknown type, skip
    return isinstance(value, expected_type)
```

### Step 2: `validation/state_machine.py` — StateMachineValidator

```python
class StateMachineValidator:
    def validate_transition(self, current_state: str, new_state: str, state_machine: dict) -> ValidationResult:
        """Check if current_state → new_state is allowed.

        state_machine format:
        {
            "states": ["open", "in_progress", "closed"],
            "transitions": {
                "open": ["in_progress", "closed"],
                "in_progress": ["closed"],
                "closed": ["open"],  # reopen
            }
        }
        """
        transitions = state_machine.get("transitions", {})
        valid_next = transitions.get(current_state, [])
        if new_state not in valid_next:
            return ValidationResult(
                valid=False,
                errors=[f"Invalid transition: '{current_state}' → '{new_state}'. Valid: {valid_next}"]
            )
        return ValidationResult(valid=True)

    def get_valid_transitions(self, current_state: str, state_machine: dict) -> list[str]:
        return state_machine.get("transitions", {}).get(current_state, [])
```

### Step 3: `validation/consistency.py` — ConsistencyValidator (async)

**Key fix:** References are defined in the entity SCHEMA (which fields are refs), not as magic strings in field values. The delta's fields contain raw entity_ids.

```python
class ConsistencyValidator:
    async def validate_references(
        self, delta: StateDelta, entity_schema: dict, state: StateEngineProtocol
    ) -> ValidationResult:
        """Check that all reference fields in a delta point to existing entities.

        entity_schema defines which fields are references:
        {"fields": {"charge": "ref:charge", "customer": "ref:customer", "amount": "integer"}}

        For each field with type "ref:X", look up the value in delta.fields
        and verify entity of type X with that ID exists in state.
        """
        errors = []
        schema_fields = entity_schema.get("fields", {})
        for field_name, field_type in schema_fields.items():
            if isinstance(field_type, str) and field_type.startswith("ref:"):
                ref_entity_type = field_type.split(":", 1)[1]
                ref_id = delta.fields.get(field_name)
                if ref_id is not None:
                    entity = await state.get_entity(ref_entity_type, EntityId(str(ref_id)))
                    if entity is None:
                        errors.append(
                            f"Field '{field_name}': references non-existent "
                            f"{ref_entity_type}:{ref_id}"
                        )
        return ValidationResult(
            valid=len(errors) == 0, errors=errors,
            validation_type=ValidationType.CONSISTENCY,
        )

    async def validate_entity_exists(
        self, entity_type: str, entity_id: EntityId, state: StateEngineProtocol
    ) -> ValidationResult:
        entity = await state.get_entity(entity_type, entity_id)
        if entity is None:
            return ValidationResult(
                valid=False,
                errors=[f"Entity {entity_type}:{entity_id} not found"],
                validation_type=ValidationType.CONSISTENCY,
            )
        return ValidationResult(valid=True, validation_type=ValidationType.CONSISTENCY)
```

This is data-driven — the schema comes from the service pack/profile, not hardcoded in the validator.

### Step 4: `validation/temporal.py` — TemporalValidator

```python
class TemporalValidator:
    def validate_timestamp(self, event_time: datetime, world_time: datetime) -> ValidationResult:
        """Event time should not be significantly in the future relative to world time."""
        if event_time > world_time:
            return ValidationResult(
                valid=False,
                errors=[f"Event time {event_time.isoformat()} is after world time {world_time.isoformat()}"]
            )
        return ValidationResult(valid=True)

    def validate_ordering(self, before: datetime, after: datetime, context: str) -> ValidationResult:
        """'before' must precede 'after'."""
        if before > after:
            return ValidationResult(
                valid=False,
                errors=[f"{context}: {before.isoformat()} is after {after.isoformat()}"]
            )
        return ValidationResult(valid=True)
```

### Step 5: `validation/amounts.py` — AmountValidator

```python
class AmountValidator:
    def validate_refund_amount(self, refund_amount: int, charge_amount: int) -> ValidationResult:
        if refund_amount > charge_amount:
            return ValidationResult(
                valid=False,
                errors=[f"Refund amount {refund_amount} exceeds charge amount {charge_amount}"]
            )
        return ValidationResult(valid=True)

    def validate_budget_deduction(self, deduction: float, remaining: float) -> ValidationResult:
        if deduction > remaining:
            return ValidationResult(
                valid=False,
                errors=[f"Budget deduction {deduction} exceeds remaining {remaining}"]
            )
        return ValidationResult(valid=True)

    def validate_non_negative(self, value: float, field_name: str) -> ValidationResult:
        if value < 0:
            return ValidationResult(
                valid=False,
                errors=[f"Field '{field_name}': value {value} is negative"]
            )
        return ValidationResult(valid=True)
```

### Step 6: `validation/pipeline.py` — ValidationPipeline (orchestrator)

All schemas, state machines, and entity schemas come from service packs/profiles — passed as data, never hardcoded.

```python
class ValidationPipeline:
    def __init__(self, config: ValidationConfig | None = None):
        self._config = config or ValidationConfig()
        self._schema = SchemaValidator()
        self._state_machine = StateMachineValidator()
        self._consistency = ConsistencyValidator()
        self._temporal = TemporalValidator()
        self._amounts = AmountValidator()

    async def validate_response_proposal(
        self, proposal: ResponseProposal, state: StateEngineProtocol,
        response_schema: dict | None = None,     # from service pack/profile
        state_machines: dict | None = None,       # from service pack/profile
        entity_schemas: dict | None = None,       # from service pack/profile
    ) -> ValidationResult:
        """Run all validators on a response proposal.

        All schemas/rules come from service packs or profiles — nothing is
        hardcoded in the validator. This makes validation work for ANY
        service, not just known ones.

        Args:
            proposal: The response proposal to validate.
            state: State engine for entity lookups (DI, protocol-based).
            response_schema: JSON-like schema for response_body (from pack/profile).
            state_machines: State machine definitions per entity type (from pack/profile).
            entity_schemas: Entity field definitions including ref types (from pack/profile).
        """
        result = ValidationResult()

        # 1. Schema validation on response_body
        if response_schema:
            r = self._schema.validate_response(proposal.response_body, response_schema)
            result = result.merge(r)

        # 2-5. Validate each state delta
        for delta in proposal.proposed_state_deltas:
            # State machine transition
            if state_machines and delta.entity_type in state_machines:
                if "status" in delta.fields and delta.previous_fields and "status" in delta.previous_fields:
                    r = self._state_machine.validate_transition(
                        delta.previous_fields["status"], delta.fields["status"],
                        state_machines[delta.entity_type]
                    )
                    result = result.merge(r)

            # Cross-entity references (uses entity schema to know which fields are refs)
            if entity_schemas and delta.entity_type in entity_schemas:
                r = await self._consistency.validate_references(
                    delta, entity_schemas[delta.entity_type], state
                )
                result = result.merge(r)

            # Amounts (check for negative values in numeric fields)
            for field_name, value in delta.fields.items():
                if isinstance(value, (int, float)):
                    r = self._amounts.validate_non_negative(
                        value, f"{delta.entity_type}.{field_name}"
                    )
                    result = result.merge(r)

        return result

    async def validate_with_retry(
        self, proposal: ResponseProposal, state: StateEngineProtocol,
        llm_callback, max_retries: int | None = None,
        response_schema: dict | None = None,
        state_machines: dict | None = None,
        entity_schemas: dict | None = None,
    ) -> tuple[ResponseProposal, ValidationResult]:
        """Validate with LLM retry on failure.

        max_retries defaults to config.max_retries if not specified.
        """
        retries = max_retries if max_retries is not None else self._config.max_retries
        current = proposal
        result = ValidationResult()
        for attempt in range(1 + retries):
            result = await self.validate_response_proposal(
                current, state, response_schema, state_machines, entity_schemas
            )
            if result.valid:
                return current, result
            if attempt < retries:
                current = await llm_callback(current, result.errors)
        return current, result
```

---

## Files to Modify / Create

| File | Action | Notes |
|------|--------|-------|
| `terrarium/core/types.py` | **UPDATE** | Add ValidationType enum |
| `terrarium/core/__init__.py` | **UPDATE** | Export ValidationType |
| `terrarium/validation/config.py` | **CREATE** | ValidationConfig (strict_mode, max_retries, max_reference_depth) |
| `terrarium/config/schema.py` | **UPDATE** | Import ValidationConfig, add to TerrariumConfig |
| `terrarium/validation/schema.py` | **IMPLEMENT** | ValidationResult (with merge + validation_type) + SchemaValidator |
| `terrarium/validation/state_machine.py` | **IMPLEMENT** | StateMachineValidator |
| `terrarium/validation/consistency.py` | **IMPLEMENT** | ConsistencyValidator (async) |
| `terrarium/validation/temporal.py` | **IMPLEMENT** | TemporalValidator |
| `terrarium/validation/amounts.py` | **IMPLEMENT** | AmountValidator |
| `terrarium/validation/pipeline.py` | **IMPLEMENT** | ValidationPipeline orchestrator |
| `terrarium/validation/__init__.py` | **VERIFY** | Re-exports correct |
| `tests/validation/test_schema.py` | **IMPLEMENT** | ~10 tests |
| `tests/validation/test_state_machine.py` | **IMPLEMENT** | ~8 tests |
| `tests/validation/test_consistency.py` | **IMPLEMENT** | ~8 tests |
| `tests/validation/test_temporal.py` | **IMPLEMENT** | ~6 tests |
| `tests/validation/test_amounts.py` | **IMPLEMENT** | ~8 tests |
| `tests/validation/test_pipeline.py` | **CREATE** | ~10 tests (missing from skeleton) |
| `IMPLEMENTATION_STATUS.md` | **UPDATE** | Flip validation to done, session log |
| `plans/B1-validation.md` | **CREATE** | Save plan to project |

---

## Tests

### test_schema.py (~10 tests)
- test_validation_result_defaults — valid=True, empty errors/warnings
- test_validation_result_merge_both_valid — merged is valid
- test_validation_result_merge_one_invalid — merged is invalid, errors combined
- test_validate_response_valid — all required fields present, types correct
- test_validate_response_missing_required — missing field → error
- test_validate_response_wrong_type — string where int expected → error
- test_validate_response_invalid_enum — value not in enum → error
- test_validate_response_below_minimum — value < minimum → error
- test_validate_response_above_maximum — value > maximum → error
- test_validate_entity_same_logic — validate_entity delegates to validate_response

### test_state_machine.py (~8 tests)
- test_valid_transition — open→in_progress allowed
- test_invalid_transition — open→closed not in transitions → error
- test_get_valid_transitions — returns correct list
- test_get_valid_transitions_unknown_state — returns empty list
- test_transition_from_terminal — closed→open (reopen) if configured
- test_empty_state_machine — empty transitions dict → all transitions invalid
- test_self_transition — state→same_state if allowed
- test_transition_error_message — error includes current, new, and valid states

### test_consistency.py (~8 tests)
- test_validate_references_all_exist — schema says field is ref:charge, delta has charge_id, charge exists → valid
- test_validate_references_missing — schema says ref:charge, but referenced charge doesn't exist → error
- test_validate_references_no_ref_fields — entity schema has no ref fields → valid (nothing to check)
- test_validate_references_field_not_in_delta — schema has ref field but delta doesn't set it → skip (no error)
- test_validate_entity_exists_found — entity exists → valid
- test_validate_entity_exists_missing — entity not found → error
- test_validate_references_multiple_refs — two ref fields, one exists one doesn't → 1 error
- test_consistency_returns_validation_type — result.validation_type == ValidationType.CONSISTENCY

### test_temporal.py (~6 tests)
- test_valid_timestamp_past — event before world time → valid
- test_valid_timestamp_equal — event equals world time → valid
- test_future_timestamp_rejected — event after world time → error
- test_ordering_correct — before < after → valid
- test_ordering_wrong — before > after → error
- test_ordering_equal — before == after → valid (not strictly before)

### test_amounts.py (~8 tests)
- test_refund_within_charge — refund ≤ charge → valid
- test_refund_equal_charge — refund == charge → valid (full refund)
- test_refund_exceeds_charge — refund > charge → error
- test_budget_deduction_within — deduction ≤ remaining → valid
- test_budget_deduction_exceeds — deduction > remaining → error
- test_non_negative_positive — positive value → valid
- test_non_negative_zero — zero → valid
- test_non_negative_negative — negative → error

### test_pipeline.py (~10 tests, NEW file)
- test_pipeline_all_valid — valid proposal passes all validators
- test_pipeline_schema_failure — bad response_body caught
- test_pipeline_state_machine_failure — invalid transition caught
- test_pipeline_consistency_failure — missing reference caught
- test_pipeline_amount_failure — negative value caught
- test_pipeline_multiple_failures — errors accumulate from all validators
- test_pipeline_retry_success — first attempt fails, LLM callback fixes, second passes
- test_pipeline_retry_exhausted — both attempts fail, returns final errors
- test_pipeline_no_schema — works without response_schema (skips schema validation)
- test_pipeline_no_state_machines — works without state_machines (skips transition validation)

---

## Completion Criteria (Zero Stubs)

| File | Methods | All Implemented? | All Tested? |
|------|---------|-----------------|-------------|
| `schema.py` | ValidationResult (with merge), SchemaValidator (2), _check_type | ✅ | ✅ 10 tests |
| `state_machine.py` | StateMachineValidator (2) | ✅ | ✅ 8 tests |
| `consistency.py` | ConsistencyValidator (2 async) | ✅ | ✅ 8 tests |
| `temporal.py` | TemporalValidator (2) | ✅ | ✅ 6 tests |
| `amounts.py` | AmountValidator (3) | ✅ | ✅ 8 tests |
| `pipeline.py` | ValidationPipeline (2) | ✅ | ✅ 10 tests |
| `__init__.py` | re-exports | ✅ | ✅ import test |

**0 stubs remaining in validation/. ~50 tests across 6 test files.**

---

## Post-Implementation Tasks

### 1. Save plan
Copy to `plans/B1-validation.md` in the project repo.

### 2. Update IMPLEMENTATION_STATUS.md

**Current Focus:**
```
**Phase:** B — Core Infrastructure
**Item:** B1 validation/ ✅ COMPLETE → Next: B2 pipeline/
**Status:** Validation framework implemented. 5 validators + pipeline orchestrator.
```

**Flip these rows to ✅ done:**
- Validation — schema
- Validation — state_machine
- Validation — consistency
- Validation — temporal
- Validation — amounts
- Validation — pipeline

**Session log entry.**

---

## Verification

1. `.venv/bin/python -m pytest tests/validation/ -v` — ALL pass
2. `.venv/bin/python -m pytest tests/validation/ --cov=terrarium/validation --cov-report=term-missing` — >90%
3. `grep -rn "^\s*\.\.\.$" terrarium/validation/*.py` — 0 results
4. Smoke test:
   ```python
   from terrarium.validation import SchemaValidator, ValidationResult, StateMachineValidator, AmountValidator

   sv = SchemaValidator()
   result = sv.validate_response({"id": "123", "status": "pending"}, {
       "required": ["id", "status"],
       "properties": {"id": {"type": "string"}, "status": {"type": "string", "enum": ["pending", "succeeded"]}}
   })
   assert result.valid

   sm = StateMachineValidator()
   result = sm.validate_transition("open", "in_progress", {
       "transitions": {"open": ["in_progress", "closed"]}
   })
   assert result.valid
   ```
5. ALL previous tests: `.venv/bin/python -m pytest tests/ -q` — 519+ passed, 0 failed
6. `plans/B1-validation.md` exists
7. `IMPLEMENTATION_STATUS.md` updated
