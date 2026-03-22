# Terrarium — Master Issues List (E2E Review 2026-03-21)

> Generated from 5 parallel review streams. Every unique finding is numbered.
> Status: OPEN | FIXED | DEFERRED (with phase) | WONTFIX (with reason)

## Summary

| Severity | Count | Fixed | Deferred | Remaining |
|----------|-------|-------|----------|-----------|
| CRITICAL | 6 | 6 | 0 | 0 |
| HIGH | 20 | 20 | 0 | 0 |
| MEDIUM | 37 | 35 | 2 | 0 |
| LOW | 14 | 14 | 0 | 0 |
| **TOTAL** | **77** | **75** | **2** | **0** |

---

## CRITICAL (6)

### ISS-001 — SQL Injection in AppendOnlyLog [FIXED]
- **Source:** Foundation Bug 1
- **File:** `terrarium/persistence/append_log.py:30-36,47-53,80,115,134`
- **Description:** Table names, column names, and filter keys are f-string interpolated into SQL. Caller-controlled strings can inject arbitrary SQL.
- **Fix:** Validate names against `^[a-zA-Z_][a-zA-Z0-9_]*$`. Validate filter keys are subset of declared columns.

### ISS-002 — ACP Command Injection in _spawn [FIXED]
- **Source:** LLM Bug 2
- **File:** `terrarium/llm/providers/acp_client.py:287-295`
- **Description:** Command+args joined into string passed to `bash -lc`. Shell metacharacters interpreted.
- **Fix:** Use `create_subprocess_exec(*cmd_parts)` directly, no shell.

### ISS-003 — ACP Command Injection in Terminal Requests [FIXED]
- **Source:** LLM Bug 3
- **File:** `terrarium/llm/providers/acp_client.py:706-716`
- **Description:** Agent-supplied command+args concatenated and passed to `bash -lc`.
- **Fix:** Use `create_subprocess_exec(command, *args)`, no shell.

### ISS-004 — ACP Unrestricted File Read/Write [FIXED]
- **Source:** LLM Bug 4
- **File:** `terrarium/llm/providers/acp_client.py:641-695`
- **Description:** `_handle_fs_read`/`_handle_fs_write` accept any path with no sandboxing. Agent can read/write anywhere on filesystem.
- **Fix:** Restrict to `self._cwd` using `Path.resolve()` + `is_relative_to()`.

### ISS-005 — FileResolver Path Traversal [FIXED]
- **Source:** LLM Bug 1
- **File:** `terrarium/llm/secrets.py:66`
- **Description:** `FileResolver.resolve()` doesn't sanitize `ref`. Path traversal via `../../etc/passwd`.
- **Fix:** Validate resolved path is within `self._dir` using `is_relative_to()`.

### ISS-006 — TOML-Config Field Mismatch: LLM Defaults [FIXED]
- **Source:** Cross-Module 1
- **File:** `terrarium.toml:135-141` vs `terrarium/llm/config.py`
- **Description:** TOML `[llm.defaults]` uses `provider`/`model`/`max_retries` but Pydantic model has `type`/`default_model`/(none). Fields silently dropped → empty-string provider/model → KeyError at runtime.
- **Fix:** Align TOML keys to match Python field names.

---

## HIGH (20)

### ISS-007 — Silent Exception Swallowing in bus._consumer [FIXED]
- **Source:** Design V03, Foundation Bug 5
- **File:** `terrarium/bus/bus.py:207-209`
- **Description:** Catches `Exception: pass`. Any subscriber error vanishes silently.
- **Fix:** Add `logging.exception()`.

### ISS-008 — Silent Exception Swallowing in middleware.process_after [FIXED]
- **Source:** Design V04, Foundation Bug 6
- **File:** `terrarium/bus/middleware.py:99-101`
- **Description:** Catches `Exception: pass` for each middleware after_publish.
- **Fix:** Add `logging.warning()` with middleware identity.

### ISS-009 — Bus.publish Swallows Persistence Errors Silently [FIXED]
- **Source:** Foundation Bug 7
- **File:** `terrarium/bus/bus.py:126-129`
- **Description:** Persistence failures caught, counter incremented, but no logging. Audit log has silent gaps.
- **Fix:** Add `logging.error()` with event context.

### ISS-010 — Unfrozen Config Models (~12 models) [FIXED]
- **Source:** Design V10-V18
- **Files:** `persistence/config.py`, `bus/config.py`, `ledger/config.py`, `pipeline/config.py`, `validation/config.py`, `llm/config.py` (3 models), `llm/types.py` (LLMRequest), `config/schema.py` (FidelityConfig, DashboardConfig, SimulationConfig, TerrariumConfig)
- **Description:** All config/value-object models lack `frozen=True`. Design principles require immutability.
- **Fix:** Add `model_config = ConfigDict(frozen=True)` to all. Refactor `update_tunable` to use `model_copy()`.

### ISS-011 — Sync I/O in Async Methods: snapshot.py [FIXED]
- **Source:** Design V05/V06
- **File:** `terrarium/persistence/snapshot.py:43-132`
- **Description:** `Path.write_text()`, `read_text()`, `stat()`, `mkdir()`, `glob()` — all sync in async methods.
- **Fix:** Wrap in `asyncio.to_thread()`.

### ISS-012 — Sync I/O in Async Methods: ledger/export.py [FIXED]
- **Source:** Design V08
- **File:** `terrarium/ledger/export.py:43-85`
- **Description:** `Path.write_text()`, `open()`, CSV writes — sync in async methods.
- **Fix:** Wrap in `asyncio.to_thread()`.

### ISS-013 — Sync I/O in FileResolver.resolve [FIXED]
- **Source:** Design V09
- **File:** `terrarium/llm/secrets.py:67`
- **Description:** `path.read_text()` blocks event loop.
- **Fix:** Wrap in `asyncio.to_thread()` at call sites, or provide `async_resolve()`.

### ISS-014 — Sync mkdir in ConnectionManager.initialize [FIXED]
- **Source:** Design V29
- **File:** `terrarium/persistence/manager.py:32`
- **Description:** `Path.mkdir()` is sync inside `async def initialize()`.
- **Fix:** `await asyncio.to_thread(Path(...).mkdir, parents=True, exist_ok=True)`.

### ISS-015 — ACP Zombie Process on Timeout/Error [FIXED]
- **Source:** LLM Bug 7
- **File:** `terrarium/llm/providers/acp_client.py:128-165`
- **Description:** Timeout/exception in `generate()` returns error but never kills subprocess. Repeated failures leak processes.
- **Fix:** Call `await self.close()` in exception handlers.

### ISS-016 — CLI Process Not Killed on Timeout [FIXED]
- **Source:** LLM Bug 8
- **File:** `terrarium/llm/providers/cli_subprocess.py:131-140`
- **Description:** `TimeoutError` caught but `proc.kill()` never called. Child continues running.
- **Fix:** Add `proc.kill(); await proc.wait()` in timeout handler.

### ISS-017 — Registry shutdown_all Doesn't Close Providers [FIXED]
- **Source:** LLM Bug 9
- **File:** `terrarium/llm/registry.py:145-151`
- **Description:** Just calls `self._providers.clear()`. Never calls `close()` on ACP providers → zombie processes.
- **Fix:** Iterate providers, call `close()` if exists, then clear.

### ISS-018 — Race Condition in ConnectionManager.get_connection [FIXED]
- **Source:** Foundation Bug 2
- **File:** `terrarium/persistence/manager.py:56-61`
- **Description:** TOCTOU: two concurrent calls create duplicate connections, leaking the first.
- **Fix:** Add `asyncio.Lock`.

### ISS-019 — Non-reentrant Transaction Flag [FIXED]
- **Source:** Foundation Bug 3
- **File:** `terrarium/persistence/sqlite.py:111-129`
- **Description:** Boolean `_in_transaction` breaks atomicity on nested calls. Inner exit resets flag.
- **Fix:** Use depth counter or raise on re-entry.

### ISS-020 — Broken replay_range to_sequence Logic [FIXED]
- **Source:** Foundation Bug 4
- **File:** `terrarium/bus/replay.py:52-68`
- **Description:** Assumes contiguous IDs. Wrong events replayed when filtered by type.
- **Fix:** Push `to_sequence` as SQL filter into persistence layer.

### ISS-021 — TOML-Config Field Mismatch: Pipeline [FIXED]
- **Source:** Cross-Module 2
- **File:** `terrarium.toml:32-33` vs `terrarium/pipeline/config.py`
- **Description:** TOML `max_side_effect_depth`/`step_timeout_seconds` → config has `side_effect_max_depth`/`timeout_per_step_seconds`. Silently ignored.
- **Fix:** Align field names.

### ISS-022 — Temporal Validator Naive vs Aware Datetime Crash [FIXED]
- **Source:** Pipeline Bug 8
- **File:** `terrarium/validation/temporal.py:34,64`
- **Description:** Comparing aware with naive datetime raises unhandled `TypeError`.
- **Fix:** Normalize to UTC or catch and return validation error.

### ISS-023 — Consistency Validator Bare Exception Catch [FIXED]
- **Source:** Pipeline Bug 1
- **File:** `terrarium/validation/consistency.py:55,89`
- **Description:** `(EntityNotFoundError, KeyError, Exception)` reduces to bare Exception. Infrastructure errors misreported.
- **Fix:** Catch only `(EntityNotFoundError, KeyError)`.

### ISS-024 — Fanout Back-Pressure Drops Never Counted [FIXED]
- **Source:** Foundation Bug 8
- **File:** `terrarium/bus/fanout.py:86-96`
- **Description:** Queue full → old event dropped via `get_nowait()` but `drops` counter not incremented.
- **Fix:** Add `drops += 1` after `get_nowait()`.

### ISS-025 — Validation Retry Can Loop Excessively [FIXED]
- **Source:** Pipeline Bug 2
- **File:** `terrarium/validation/pipeline.py:164-165`
- **Description:** No hard upper bound on retries. LLM callback returning same invalid proposal burns tokens.
- **Fix:** Add hard cap `min(retries, 10)` and validate callback return not None.

### ISS-026 — Side Effect Exponential Blowup [FIXED]
- **Source:** Pipeline Bug 3
- **File:** `terrarium/pipeline/side_effects.py:52-77`
- **Description:** `max_depth` bounds recursion but not total count. N^max_depth total executions possible.
- **Fix:** Add `max_total` counter.

---

## MEDIUM (37)

### ISS-027 — ConnectionManager Hardwired to SQLiteDatabase [FIXED]
- **Source:** Design V01
- **File:** `terrarium/persistence/manager.py:16,28`
- **Fix:** Accept factory callable via DI.

### ISS-028 — SnapshotStore Hardwired to SQLiteDatabase [DEFERRED B4]
- **Source:** Design V02
- **File:** `terrarium/persistence/snapshot.py:17,50,81`
- **Fix:** Use protocol-based dispatch instead of isinstance.

### ISS-029 — ConfigRegistry.update_tunable Bypasses Validation [FIXED]
- **Source:** Foundation Bug 14
- **File:** `terrarium/config/registry.py:69-87`
- **Fix:** Use `model_validate()` instead of bare `model_copy(update=...)`.

### ISS-030 — TunableRegistry and ConfigRegistry Not Synchronized [FIXED]
- **Source:** Foundation Bug 15
- **File:** `terrarium/config/tunable.py` + `terrarium/config/registry.py`
- **Fix:** Unify or have TunableRegistry delegate to ConfigRegistry.

### ISS-031 — OpenAI Silent Retry Catches All Exceptions [FIXED]
- **Source:** LLM Bug 12
- **File:** `terrarium/llm/providers/openai_compat.py:66-79`
- **Fix:** Catch only `openai.BadRequestError` or `TypeError`.

### ISS-032 — API Key Leakage via str(e) in Error Responses [FIXED]
- **Source:** LLM Bug 11
- **Files:** `anthropic.py:72`, `openai_compat.py:103`, `google.py:83`
- **Fix:** Sanitize error messages: `type(e).__name__ + ": " + str(e)[:200]`.

### ISS-033 — API Key Stored in Instance Variable After SDK Init [FIXED]
- **Source:** LLM Bug 10
- **Files:** `anthropic.py:26`, `google.py:27`
- **Fix:** Remove `self._api_key = api_key` lines.

### ISS-034 — ConversationManager Unbounded History Growth [FIXED]
- **Source:** LLM Bug 13
- **File:** `terrarium/llm/conversation.py:143-148`
- **Fix:** Add configurable max history length.

### ISS-035 — ACP _collected_text Race on Concurrent Generate [FIXED]
- **Source:** LLM Bug 15
- **File:** `terrarium/llm/providers/acp_client.py:141-143`
- **Fix:** Use per-request buffers keyed by session/request ID.

### ISS-036 — ACP JSON-RPC Protocol Violations (errors in result) [FIXED]
- **Source:** LLM Bug 16, 17
- **File:** `terrarium/llm/providers/acp_client.py:601-607,646,655,681,691`
- **Fix:** Add `_send_error_response()` using top-level `error` field per JSON-RPC spec.

### ISS-037 — ACP Empty Permission Options Sends Empty optionId [FIXED]
- **Source:** LLM Bug 6
- **File:** `terrarium/llm/providers/acp_client.py:613-639`
- **Fix:** Return JSON-RPC error when no options available.

### ISS-038 — ACP Token Usage Extraction Priority Bug [FIXED]
- **Source:** LLM Bug 5
- **File:** `terrarium/llm/providers/acp_client.py:842-848`
- **Fix:** Only recurse into nested dicts if no top-level values found.

### ISS-039 — Side Effect Context Missing Fields [FIXED]
- **Source:** Pipeline Bug 4
- **File:** `terrarium/pipeline/side_effects.py:108-121`
- **Fix:** Add `fidelity`, `computed_cost`, `policy_flags` to propagation.

### ISS-040 — Pipeline _FIELD_MAP Missing "responder" [FIXED]
- **Source:** Pipeline Bug 5, Design V28
- **File:** `terrarium/pipeline/dag.py:28-35`
- **Fix:** Add `"responder"` entry or document intentional omission.

### ISS-041 — Schema Validator: bool Passes int Check [FIXED]
- **Source:** Pipeline Bug 6
- **File:** `terrarium/validation/schema.py:64-69`
- **Fix:** Add explicit bool exclusion for integer checks.

### ISS-042 — Schema Validator: No additionalProperties Enforcement [FIXED]
- **Source:** Pipeline Bug 7
- **File:** `terrarium/validation/schema.py:75-134`
- **Fix:** Check `additionalProperties: false` and reject extra keys.

### ISS-043 — Schema Validator: No Nested Object/Array Validation [FIXED]
- **Source:** Pipeline Bug 14
- **File:** `terrarium/validation/schema.py:75-134`
- **Fix:** Implement recursive validation for nested objects and array items.

### ISS-044 — State Machine: No Initial-State Validation on Create [FIXED]
- **Source:** Pipeline Bug 16
- **File:** `terrarium/validation/pipeline.py:78-89`
- **Fix:** When `previous_fields` is None and operation is create, validate new_status is valid initial state.

### ISS-045 — Amount Validator Float Precision [FIXED]
- **Source:** Pipeline Bug 11
- **File:** `terrarium/validation/amounts.py:58,86`
- **Fix:** Use epsilon tolerance or Decimal for monetary comparisons.

### ISS-046 — Validation Pipeline: llm_callback Exception Unhandled [FIXED]
- **Source:** Pipeline Bug 12
- **File:** `terrarium/validation/pipeline.py:165`
- **Fix:** Wrap callback in try/except, break on failure, return last result.

### ISS-047 — No EventBusProtocol in core/protocols.py [FIXED]
- **Source:** Cross-Module 5
- **File:** `terrarium/core/protocols.py`, `terrarium/pipeline/dag.py:40`
- **Fix:** Add `EventBusProtocol` with `publish()` and `subscribe()`. Type bus params accordingly.

### ISS-048 — UsageTracker No Locking on Aggregates [FIXED]
- **Source:** LLM Bug 18
- **File:** `terrarium/llm/tracker.py:54-58`
- **Fix:** Add `asyncio.Lock` to protect `record()`.

### ISS-049 — CSV Export Loses Fields with Mixed Entry Types [FIXED]
- **Source:** Foundation Bug 18
- **File:** `terrarium/ledger/export.py:61`
- **Fix:** Collect union of all fieldnames across entries.

### ISS-050 — ConfigLoader _coerce: "0"→False, "1"→True [FIXED]
- **Source:** Foundation Bug 10
- **File:** `terrarium/config/loader.py:162-166`
- **Fix:** Check int/float before boolean, or only treat "true"/"false"/"yes"/"no" as booleans.

### ISS-051 — Snapshot load_snapshot Leaks DB Connection [DEFERRED B4]
- **Source:** Foundation Bug 9
- **File:** `terrarium/persistence/snapshot.py:68-83`
- **Fix:** Return as async context manager or register with ConnectionManager.

### ISS-052 — Ledger Empty entry_types_enabled List Means "All Enabled" [FIXED]
- **Source:** Foundation Bug 11
- **File:** `terrarium/ledger/ledger.py:72`
- **Fix:** Use `None` for "all enabled" and `[]` for "none enabled". Document.

### ISS-053 — SQLiteDatabase.backup Accesses Private aiosqlite Internals [FIXED]
- **Source:** Foundation Bug 16
- **File:** `terrarium/persistence/sqlite.py:169-180`
- **Fix:** Pin aiosqlite version range. Add comment. Use public API if available.

### ISS-054 — Hardcoded Engine List in config/validation.py [FIXED]
- **Source:** Design V19
- **File:** `terrarium/config/validation.py:110-124`
- **Fix:** Accept `available_engines` as parameter.

### ISS-055 — Hardcoded Model Names/Pricing in Providers [FIXED]
- **Source:** Design V20, V21, V23
- **Files:** `llm/registry.py:95-143`, `llm/providers/anthropic.py:98-138`, `llm/providers/google.py:108-128`
- **Fix:** Move model lists and pricing to config or shared tables.

### ISS-056 — Hardcoded Fallback System Prompt [FIXED]
- **Source:** Design V22
- **File:** `terrarium/llm/providers/anthropic.py:44`
- **Fix:** Move default system prompt to config.

### ISS-057 — Hardcoded Queue Size in bus.subscribe [FIXED]
- **Source:** Design V24, V25
- **Files:** `terrarium/bus/bus.py:73`, `terrarium/bus/types.py:44`
- **Fix:** Use `self._config.queue_size` as default.

### ISS-058 — Hardcoded max_depth=10 in SideEffectProcessor [FIXED]
- **Source:** Design V26
- **File:** `terrarium/pipeline/side_effects.py:25`
- **Fix:** Inject from `PipelineConfig.side_effect_max_depth`.

### ISS-059 — Hardcoded Sleep Interval in Side Effect Background Loop [FIXED]
- **Source:** Design V27
- **File:** `terrarium/pipeline/side_effects.py:130`
- **Fix:** Make configurable via PipelineConfig.

### ISS-060 — ActionContext world_mode/reality_preset Should Use Enums [FIXED]
- **Source:** Design V30
- **File:** `terrarium/core/context.py:100-161`
- **Fix:** Change `world_mode: str | None` to `WorldMode | None` etc.

### ISS-061 — Side Effect Background Loop No Exception Handling [FIXED]
- **Source:** Pipeline Bug 9
- **File:** `terrarium/pipeline/side_effects.py:123-132`
- **Fix:** Add try/except with logging around `process_all()`.

### ISS-062 — Side Effect Race Condition (deque vs asyncio.Queue) [FIXED]
- **Source:** Pipeline Bug 10
- **File:** `terrarium/pipeline/side_effects.py`
- **Fix:** Use `asyncio.Queue` instead of `deque`.

### ISS-063 — AnimatorConfig Default/Type Mismatch [FIXED]
- **Source:** Cross-Module 6
- **File:** `terrarium/engines/animator/config.py`
- **Fix:** Align defaults with TOML values. Fix `intensity` type.

---

## LOW (14)

### ISS-064 — Database as ABC Instead of Protocol [FIXED]
- **Source:** Design V31
- **File:** `terrarium/persistence/database.py:16`
- **Fix:** Convert to `typing.Protocol`.

### ISS-065 — LedgerQuery.limit Hardcoded Default 100 [FIXED]
- **Source:** Design V32
- **File:** `terrarium/ledger/query.py:40-41`
- **Fix:** Read from LedgerConfig.

### ISS-066 — Mock Provider Hardcoded Token Estimation [FIXED]
- **Source:** Design V33
- **File:** `terrarium/llm/providers/mock.py:61`
- **Fix:** Acceptable for mock. Document.

### ISS-067 — BusPersistence Accesses Private _log._db [FIXED]
- **Source:** Design V34
- **File:** `terrarium/bus/persistence.py:43-46`
- **Fix:** Add `add_index()` method to AppendOnlyLog.

### ISS-068 — LedgerQueryBuilder filter_time Uses Truthiness [FIXED]
- **Source:** Foundation Bug 12
- **File:** `terrarium/ledger/query.py:97-100`
- **Fix:** Use `if start is not None:`.

### ISS-069 — AppendOnlyLog limit=0 Treated as No Limit [FIXED]
- **Source:** Foundation Bug 13
- **File:** `terrarium/persistence/append_log.py:98`
- **Fix:** Use `if limit is not None:`.

### ISS-070 — Ledger Query offset=0 Treated as No Offset [FIXED]
- **Source:** Foundation Bug 17
- **File:** `terrarium/ledger/ledger.py:118`
- **Fix:** Use `if filters.offset is not None:`.

### ISS-071 — Unsubscribe Doesn't Cancel Pending Events [FIXED]
- **Source:** Foundation Bug 19
- **File:** `terrarium/bus/fanout.py:42-65`
- **Fix:** Drain queue after cancel. Document behavior.

### ISS-072 — State Machine No Unknown Target State Check [FIXED]
- **Source:** Pipeline Bug 13
- **File:** `terrarium/validation/state_machine.py:33-55`
- **Fix:** Add specific error for undefined target states.

### ISS-073 — Pipeline DAG Overwrites Step's duration_ms [FIXED]
- **Source:** Pipeline Bug 15
- **File:** `terrarium/pipeline/dag.py:82-90`
- **Fix:** Document that DAG always measures its own timing.

### ISS-074 — Google Provider Duplicate Model in list_models [FIXED]
- **Source:** LLM Bug 20
- **File:** `terrarium/llm/providers/google.py:108-112`
- **Fix:** Remove duplicate entry.

### ISS-075 — Registry Double Initialize Leaks Old Providers [FIXED]
- **Source:** LLM Bug 21
- **File:** `terrarium/llm/registry.py:54-72`
- **Fix:** Call `shutdown_all()` at start of `initialize_all()`.

### ISS-076 — __init__.py Export Hygiene (4 modules) [FIXED]
- **Source:** Cross-Module 8-11
- **Files:** `llm/__init__.py`, `bus/__init__.py`, `persistence/__init__.py`, `ledger/__init__.py`
- **Fix:** Remove internal classes from `__all__`. Add missing `Session`.

### ISS-077 — ACP terminal_wait Task Not Tracked [FIXED]
- **Source:** LLM Bug 19
- **File:** `terrarium/llm/providers/acp_client.py:727`
- **Fix:** Store task reference. Add done callback for error logging.

---

## Fix Progress Tracker

| Batch | Issues | Scope | Status |
|-------|--------|-------|--------|
| **Batch 1: Security** | ISS-001 to ISS-005 | SQL injection, command injection, path traversal | DONE |
| **Batch 2: Config breaks** | ISS-006, ISS-021 | TOML field mismatches | DONE |
| **Batch 3: Exception handling** | ISS-007 to ISS-009 | Silent swallowing → logging | DONE |
| **Batch 4: Process lifecycle** | ISS-015 to ISS-017 | Zombie processes, cleanup | DONE |
| **Batch 5: Frozen models** | ISS-010 | 12 config models | DONE |
| **Batch 6: Async I/O** | ISS-011 to ISS-014 | Sync→async wrapping | DONE |
| **Batch 7: Correctness** | ISS-018 to ISS-026 | Races, logic errors, validators | DONE |
| **Batch 8: LLM module** | ISS-031 to ISS-038 | Provider fixes, ACP protocol | DONE |
| **Batch 9: Pipeline+Validation** | ISS-039 to ISS-046, ISS-058/059/061/062 | Validator gaps, side effects | DONE |
| **Batch 10: Architecture** | ISS-027,029,030,047,048,049,050-060,063 | DI, protocols, config-driven | DONE |
| **Batch 11: Low priority** | ISS-064 to ISS-077 | Cleanup, docs, exports | DONE |

### Deferred to Phase B4
- **ISS-028** — SnapshotStore hardwired to SQLiteDatabase (requires deeper refactor)
- **ISS-051** — Snapshot load_snapshot connection lifecycle (requires context manager pattern)
