# Prompt Optimization Analysis — World Compiler LLM Calls

## Current State (Post Live Test)

Live test with codex-acp (reasoning=low): 11:51 for 130 entities across 13 entity types.
Each entity type requires 1 LLM call = ~13 serial calls + 2 personality calls + 2 seed calls = ~17 LLM calls total.

## Prompt Size Breakdown (per entity generation call)

| Section | Chars | Est. Tokens | Repeated? | Note |
|---------|-------|-------------|-----------|------|
| World description | ~50 | ~12 | Yes | Short, good |
| Mission | ~30 | ~8 | Yes | Short, good |
| Reality summary (narrative) | ~500 | ~125 | Yes, identical | Good — concise narrative |
| Reality dimensions (full JSON) | ~1500 | ~375 | Yes, identical | **Huge** — all 5 dimensions, every attribute + description |
| Behavior mode description | ~300 | ~75 | Yes, identical | Full paragraph, same every call |
| Actor summary | ~30 | ~8 | Yes | Small |
| Policies summary | ~60 | ~15 | Yes | Small |
| Seeds section | ~200 | ~50 | Yes, identical | Sent even for irrelevant entity types (labels, mailboxes) |
| Entity schema (JSON) | ~800-2000 | ~200-500 | No (per type) | Necessary — varies per entity |
| Rules (8 bullet points) | ~600 | ~150 | Yes, identical | Boilerplate |
| **Total per call** | **~4000-6500** | **~1000-1600** | | |
| **Total all calls (×17)** | **~68K-110K** | **~17K-27K** | | Input tokens only |

## Optimization Opportunities

### O1: Remove detailed dimensions JSON, keep only narrative summary
- **Savings:** ~375 tokens/call × 13 entity calls = **~5K tokens**
- **Risk:** Low — the narrative summary already conveys the intent. The per-attribute numbers (staleness=30, incompleteness=35) are engineering precision that LLMs don't actually use when generating narrative data.
- **Current:** Both narrative AND full JSON are sent. Example: "Information management has been neglected..." (narrative) PLUS `{"staleness": 30, "incompleteness": 35, ...}` (JSON)
- **Proposed:** Keep only the narrative summary. Remove `Detailed dimensions:\n{reality_dimensions}`.

### O2: Only include seeds for seed-relevant entity types
- **Savings:** ~50 tokens × 8 irrelevant calls = **~400 tokens**
- **Risk:** Low — seeds about "Margaret Chen's refund" don't affect label, mailbox, group, organization, draft generation.
- **Proposed:** Only include seeds section for entity types that match seed keywords (email, message, ticket, channel, user). For others, replace with "None".

### O3: Shorten behavior mode to 1 line
- **Savings:** ~60 tokens/call × 13 = **~780 tokens**
- **Risk:** Low — "dynamic: entities have in-flight activities and pending events" is sufficient.
- **Current:** Full paragraph: "DYNAMIC MODE: Generate entities with in-flight activities, pending events, and evolving situations. Some tickets are mid-conversation, some orders are processing, some customers are waiting for responses. The world is ALIVE — it will continue generating events during simulation. Create a world with momentum and unresolved tension."
- **Proposed:** "dynamic: Generate entities with in-flight activities, pending events, and momentum."

### O4: Trim rules to 3 essential bullets
- **Savings:** ~100 tokens/call × 13 = **~1300 tokens**
- **Risk:** Low — most rules are implied by the schema itself.
- **Current:** 8 bullets (count, schema conformance, required fields, ID format, reality reflection, behavior mode shapes, seeds, output format)
- **Proposed:** 3 bullets: count + schema + output format. Remove the ones that restate what the schema/context already says.

### O5: Strip field descriptions from entity schema
- **Savings:** ~100-200 tokens/call × 13 = **~1300-2600 tokens**
- **Risk:** Medium — some descriptions help (e.g., "Unix timestamp" for `created` field). But most are obvious from field names.
- **Proposed:** Remove `"description": "..."` from schema properties before sending to LLM. Keep `x-terrarium-identity` and `x-terrarium-ref` annotations.

### O6: Reduce default entity count from 10 to 5
- **Savings:** ~50% reduction in OUTPUT tokens (LLM generates half as many entities)
- **Risk:** Medium — fewer entities means less world richness. But for testing, 5 is sufficient.
- **Proposed:** Make configurable via compiler settings YAML, default to 5 for worlds with >2 services.

### O7: Batch compatible entity types into single LLM call
- **Savings:** Reduces number of serial LLM calls from 13 to ~5-6 (batch same-service entities)
- **Risk:** Medium — larger response, more truncation risk. But reduces cold-start overhead per call.
- **Proposed:** Generate all entities for one service in a single call (e.g., channel + message + user together for chat pack).

## Summary

| Optimization | Token Savings | Latency Impact | Risk | Priority |
|-------------|--------------|----------------|------|----------|
| O1: Remove dimensions JSON | ~5K | -20% | Low | High |
| O2: Targeted seeds | ~400 | -2% | Low | Medium |
| O3: Short behavior mode | ~780 | -3% | Low | Medium |
| O4: Trim rules | ~1300 | -5% | Low | Medium |
| O5: Strip descriptions | ~1300-2600 | -5-10% | Medium | Medium |
| O6: Reduce entity count | ~50% output | -30-40% | Medium | High |
| O7: Batch entity types | N/A (fewer calls) | -40-50% | Medium | High |
| **Total (O1-O5)** | **~8K-10K** | **~35-40%** | | |
| **Total (all)** | **~60-70%** | **~60-70%** | | |

## Live Test Metrics

- Test duration: 11:51 (711 seconds)
- Entity types: 13
- Total entities: 130
- Average per entity type: ~55 seconds (includes LLM latency + validation)
- Seeds processed: 2 (added ~2 min)
- Personalities: 2 roles (added ~1 min)
- Retries: 3 sections needed 1 retry each

## Non-Blocking Issues from Live Test

1. **Permission short-circuit:** Agent actions blocked because test uses string actor IDs ("support-agent") not matching compiled actor IDs. Fix: use actual actor IDs from `result["actors"]`.
2. **43 "no response_schema" warnings:** Tool definitions don't include response schemas. Fix: add `response_schema` to tool definitions in schemas.py.
3. **`labels_list` flagged as mutation:** GET endpoint but no parameters defined. Fix: add empty parameters `{}`.
