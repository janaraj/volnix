# F2: Data Layer (Services + Hooks) — Implementation Plan

## Context

F1 complete (124 tests pass, 0 todos, audit clean). F2 implements the data layer — the bridge between backend APIs/WebSocket and the React UI. Most F2 source files were already implemented in F0 scaffolding (ApiClient, WsManager, query hooks, stores, providers). F2 focuses on:

1. Fixing the WsManager status notification pattern (polling → event-driven)
2. Implementing the 4 stub cache update handlers in `use-live-events.ts`
3. Implementing all 53 `it.todo()` test stubs across 10 test files
4. Updating IMPLEMENTATION_STATUS.md (F1 → done, F2 → done)
5. Saving plan to internal_docs/plans/

**Spec source of truth:** `internal_docs/terrarium-frontend-spec.md` (Data Contract section, lines 95-303)

---

## What's Already Done (No Changes Needed)

These files are production-ready from F0/F1:
- `src/services/api-client.ts` — 11 methods, all complete
- `src/services/ws-manager.ts` — complete except missing status listener pattern (Step 1 fix)
- All 7 query hooks (`use-runs`, `use-events`, `use-scorecard`, `use-entities`, `use-gaps`, `use-actors`, `use-compare`)
- URL state hooks (`use-url-state`, `use-url-filters`, `use-url-tabs`) — complete from F1
- Both stores (`compare-store`, `layout-store`) — complete
- Both providers (`services-provider`, `query-provider`) — complete
- Test infrastructure (`tests/mocks/handlers.ts`, `server.ts`, `ws-mock.ts`, all mock data factories)
- All types and constants

## What F2 Must Implement

| Item | File | Current State | Target |
|------|------|--------------|--------|
| WsManager status listeners | `src/services/ws-manager.ts` | Direct `this.status =` assignments | `setStatus()` emitter + `subscribeStatus()` method |
| useWebSocket event-driven | `src/hooks/use-websocket.ts` | 500ms setInterval polling | `subscribeStatus()` subscription |
| useLiveEvents handlers | `src/hooks/use-live-events.ts` | 4 stub comments ("Implementation in F2") | Real `setQueryData` / `setQueriesData` calls |
| MockWebSocket helper | `tests/helpers/mock-websocket.ts` | Doesn't exist | Shared mock for 3 test files |
| 10 test files | `tests/services/`, `tests/hooks/`, `tests/stores/` | 53 `it.todo()` stubs | 55+ real tests (53 + 2 new for subscribeStatus) |
| IMPLEMENTATION_STATUS.md | `IMPLEMENTATION_STATUS.md` | F1="Not started" | F1=done, F2=done |
| Save plan | `internal_docs/plans/` | — | Copy plan |

---

## Steps (7 total, dependency-ordered)

### Step 1: Add Status Listener Pattern to WsManager

**File:** `src/services/ws-manager.ts`

**Why:** useWebSocket polls `getStatus()` every 500ms via setInterval. This is wasteful and introduces up to 500ms lag. WsManager must emit status changes so hooks react instantly.

**Changes:**
1. Add field: `private statusListeners: Set<(status: ConnectionStatus) => void> = new Set();`
2. Add private helper that sets status AND notifies:
```typescript
private setStatus(newStatus: ConnectionStatus): void {
  if (this.status !== newStatus) {
    this.status = newStatus;
    this.statusListeners.forEach((listener) => listener(newStatus));
  }
}
```
3. Replace ALL 4 direct `this.status = '...'` assignments with `this.setStatus('...')`:
   - Line 39: `this.status = 'connecting'` → `this.setStatus('connecting')`
   - Line 46: `this.status = 'connected'` → `this.setStatus('connected')`
   - Line 72: `this.status = 'disconnected'` → `this.setStatus('disconnected')`
   - Line 92: `this.status = 'reconnecting'` → `this.setStatus('reconnecting')`
4. Add public method:
```typescript
subscribeStatus(handler: (status: ConnectionStatus) => void): () => void {
  this.statusListeners.add(handler);
  return () => { this.statusListeners.delete(handler); };
}
```

**No breaking changes.** `getStatus()` still works. `subscribe()` for messages still works. New `subscribeStatus()` is additive.

**Done:** TypeScript compiles. Existing tests still pass.

---

### Step 2: Replace Polling in useWebSocket

**File:** `src/hooks/use-websocket.ts`

**Why:** Eliminate 500ms setInterval. Use event-driven `subscribeStatus` from Step 1.

**Full replacement:**
```typescript
import { useEffect, useState } from 'react';
import { useWsManager } from '@/providers/services-provider';
import type { ConnectionStatus } from '@/types/ui';

export function useWebSocket(runId: string | null) {
  const ws = useWsManager();
  const [status, setStatus] = useState<ConnectionStatus>('disconnected');

  useEffect(() => {
    if (!runId) return;

    ws.connect(runId);
    setStatus(ws.getStatus()); // sync initial status

    const unsubStatus = ws.subscribeStatus(setStatus);

    return () => {
      unsubStatus();
      ws.disconnect();
    };
  }, [runId, ws]);

  return { status, manager: ws };
}
```

**Done:** No setInterval. Status updates are instant via listener.

---

### Step 3: Implement Cache Update Handlers in useLiveEvents

**File:** `src/hooks/use-live-events.ts`

**Why:** 4 of 5 message type handlers are stubs. Must implement real TanStack Query cache mutations.

**Full replacement** (adds useState for status, subscribeStatus, and all 4 handlers):

**Handler specifications:**

**`event`** — Append to ALL event caches for this run (filtered + unfiltered) with dedup:
```typescript
queryClient.setQueriesData<PaginatedResponse<WorldEvent>>(
  { queryKey: ['runs', runId, 'events'] },  // prefix match
  (old) => {
    if (!old) return old;
    if (old.items.some((e) => e.event_id === newEvent.event_id)) return old;
    return { ...old, items: [...old.items, newEvent], total: old.total + 1 };
  },
);
```

**`status`** — Patch run detail cache (tick + status only):
```typescript
queryClient.setQueryData(queryKeys.runs.detail(runId), (old: Run | undefined) => {
  if (!old) return old;
  return { ...old, status: message.data.status, current_tick: message.data.tick };
});
```

**`budget_update`** — Patch specific actor's budget in actor cache:
```typescript
queryClient.setQueryData(queryKeys.runs.actor(runId, actor_id), (old: AgentSummary | undefined) => {
  if (!old) return old;
  return {
    ...old,
    budget_remaining: { ...old.budget_remaining, [budget_type]: remaining },
    budget_total: { ...old.budget_total, [budget_type]: total },
  };
});
```

**`entity_update`** — Patch specific entity detail + entity list caches:
```typescript
// Single entity cache
queryClient.setQueryData(queryKeys.runs.entity(runId, update.entity_id), (old: Entity | undefined) => {
  if (!old) return old;
  return { ...old, fields: { ...old.fields, ...update.fields }, updated_at: new Date().toISOString() };
});
// Entity list caches (prefix match)
queryClient.setQueriesData<PaginatedResponse<Entity>>(
  { queryKey: ['runs', runId, 'entities'] },
  (old) => {
    if (!old) return old;
    return {
      ...old,
      items: old.items.map((e) =>
        e.entity_id === update.entity_id
          ? { ...e, fields: { ...e.fields, ...update.fields }, updated_at: new Date().toISOString() }
          : e,
      ),
    };
  },
);
```

**`run_complete`** — Already implemented (invalidates queries). No changes.

**Additional changes:**
- Add `useState` import, track status via `subscribeStatus`
- Add imports for `PaginatedResponse`, `WorldEvent`, `Run`, `Entity`, `AgentSummary` from types
- Return `status` state variable instead of `ws.getStatus()` snapshot

**Done:** All 5 handlers implemented. Cache updates are precise (no full refetches). Dedup prevents duplicates from REST backfill + WS overlap.

---

### Step 4: Create Shared MockWebSocket Test Helper

**File:** CREATE `tests/helpers/mock-websocket.ts`

**Why:** 3 test files need the same WebSocket mock. Extract once, share everywhere.

```typescript
export class MockWebSocket {
  static instances: MockWebSocket[] = [];
  url: string;
  onopen: (() => void) | null = null;
  onmessage: ((event: { data: string }) => void) | null = null;
  onclose: (() => void) | null = null;
  onerror: (() => void) | null = null;
  readyState = 0;

  constructor(url: string) {
    this.url = url;
    MockWebSocket.instances.push(this);
  }
  close() { this.readyState = 3; }
  simulateOpen() { this.readyState = 1; this.onopen?.(); }
  simulateMessage(data: string) { this.onmessage?.({ data }); }
  simulateClose() { this.onclose?.(); }
  static reset() { MockWebSocket.instances = []; }
}
```

Used by: `ws-manager.test.ts`, `use-websocket.test.ts`, `use-live-events.test.ts`

**Done:** Shared helper exists. No duplication across test files.

---

### Step 5: Implement Service Tests (api-client + ws-manager)

**Files:**
- `tests/services/api-client.test.ts` — 10 todos → real tests using MSW server
- `tests/services/ws-manager.test.ts` — 10 todos → real tests using MockWebSocket + vi.useFakeTimers

**api-client tests use:** MSW `server` from `tests/mocks/server.ts` (beforeAll/afterAll/resetHandlers pattern). Test each endpoint method + error handling (404, 500, network error via `HttpResponse.error()`).

**ws-manager tests use:** MockWebSocket from Step 4 + `vi.useFakeTimers()` for reconnect timing. Test: connect (correct URL), status transitions (connecting→connected), disconnect (clears state), reconnect backoff (1s, 2s, 4s capped at 30s), subscribe (message dispatch), unsubscribe (no dispatch), malformed message handling, **subscribeStatus** (listener callbacks + unsubscribe).

**Done:** `vitest run tests/services/` — all pass, 0 todo.

---

### Step 6: Implement Hook + Store Tests

**Files:**
- `tests/hooks/use-websocket.test.ts` — 4 todos → real tests
- `tests/hooks/use-live-events.test.ts` — 5 todos → real tests
- `tests/hooks/queries/use-runs.test.ts` — 5 todos → real tests
- `tests/hooks/queries/use-events.test.ts` — 4 todos → real tests
- `tests/hooks/queries/use-scorecard.test.ts` — 2 todos → real tests
- `tests/hooks/use-url-state.test.ts` — 4 todos → real tests
- `tests/stores/compare-store.test.ts` — 5 todos → real tests
- `tests/stores/layout-store.test.ts` — 4 todos → real tests

**Hook test pattern:** All use `renderHook` from `@testing-library/react`. Mock `@/providers/services-provider` via `vi.mock()`. Query hooks wrap in `QueryClientProvider`. URL state hooks wrap in `MemoryRouter`.

**use-live-events tests verify:**
- Events append to cache with dedup (seed cache, send WS event, check cache length)
- Status patches run detail (seed cache, send status msg, check tick/status)
- run_complete invalidates queries (spy on `queryClient.invalidateQueries`)
- Cleanup disconnects on unmount

**Store tests:** Direct Zustand state manipulation (no React needed). `useCompareStore.getState().toggleRun()`, assert state. `useLayoutStore.getState().toggleSidebar()`, check localStorage.

**Done:** `vitest run tests/hooks/ tests/stores/` — all pass, 0 todo.

---

### Step 7: Update IMPLEMENTATION_STATUS.md + Save Plan + Verify

**Files:**
- MODIFY: `terrarium-dashboard/IMPLEMENTATION_STATUS.md`
- CREATE: `internal_docs/plans/F2-data-layer.md` (copy of this plan)

**IMPLEMENTATION_STATUS.md changes:**
- Current Focus: `F2 → done, F3 next`
- Layer 1 (lib): all 📋 stub → ✅ done (completed in F1)
- Layer 2 (services): all → ✅ done
- Layer 3 (hooks): all → ✅ done (use-keyboard remains 📋 stub for F7)
- Layer 3 (stores): all → ✅ done
- Layer 5 (components): all domain/feedback/layout → ✅ done (completed in F1)
- Add F1 session log entry
- Add F2 session log entry
- Phase roadmap: F1=done, F2=done

**Verification:**
1. `npm run typecheck` — 0 errors
2. `npm run lint` — 0 errors
3. `npm run test` — F1 tests (124) + F2 tests (~55) = ~179 tests pass, remaining ~6 page todos
4. `npm run build` — succeeds

---

## File Manifest

**Create (2):**
- `tests/helpers/mock-websocket.ts`
- `internal_docs/plans/F2-data-layer.md`

**Modify — Source (3):**
- `src/services/ws-manager.ts` — add statusListeners, setStatus, subscribeStatus
- `src/hooks/use-websocket.ts` — replace polling with subscribeStatus
- `src/hooks/use-live-events.ts` — implement 4 cache handlers + status subscription

**Modify — Tests (10):**
- `tests/services/api-client.test.ts` (10 todos → ~10 real tests)
- `tests/services/ws-manager.test.ts` (10 todos → ~12 real tests including subscribeStatus)
- `tests/hooks/use-websocket.test.ts` (4 todos → 4 real tests)
- `tests/hooks/use-live-events.test.ts` (5 todos → 5 real tests)
- `tests/hooks/queries/use-runs.test.ts` (5 todos → 5 real tests)
- `tests/hooks/queries/use-events.test.ts` (4 todos → 4 real tests)
- `tests/hooks/queries/use-scorecard.test.ts` (2 todos → 2 real tests)
- `tests/hooks/use-url-state.test.ts` (4 todos → 4 real tests)
- `tests/stores/compare-store.test.ts` (5 todos → 5 real tests)
- `tests/stores/layout-store.test.ts` (4 todos → 4 real tests)

**Modify — Docs (1):**
- `terrarium-dashboard/IMPLEMENTATION_STATUS.md` — F1 done, F2 done, session logs

**Total: 2 new + 14 modified = 16 files touched.**
**Total new tests: ~55 (53 todos converted + 2 new for subscribeStatus)**
