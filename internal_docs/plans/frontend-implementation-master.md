# Terrarium Dashboard — Frontend Implementation Master Plan

## Context

The dashboard scaffolding (F0) is complete: 95 source files, 28 test files, 166 todo tests, clean typecheck and build. Now we need a phased implementation plan to turn stubs into a real production dashboard.

**Approach:** Same as backend — phased, each phase has Plan → Implement → Review → Next. **No mock data in the app** — real backend APIs only. Backend team builds endpoints from the API contract below.

**Tracking:** `terrarium-dashboard/IMPLEMENTATION_STATUS.md` (separate from backend).

---

## Phase Roadmap

### F0: Scaffolding — DONE

95 source files, 28 test files (166 todos), 7-layer architecture, typed stubs for everything.

### F1: Design System + Shared Components

| Scope | Files | Done = |
|-------|-------|--------|
| Implement all `lib/` utilities (formatters, classifiers, score-utils, color-utils, url-state, causal-graph, comparison, export) | `src/lib/*.ts` | All lib unit tests pass (not todo) |
| Implement all domain components with real rendering | `src/components/domain/*.tsx` (14 files) | Components render correctly with typed props, tests pass |
| Implement all feedback components (QueryGuard, ErrorBoundary, loading/error/empty states) | `src/components/feedback/*.tsx` (6 files) | QueryGuard works with real UseQueryResult shape, ErrorBoundary catches errors |
| Finalize layout components (sidebar nav, AppShell, PanelLayout, StatusBar) | `src/components/layout/*.tsx` (5 files) | App boots with dark theme, sidebar navigates, panels resize |
| Implement all lib + component tests | `tests/lib/*.test.ts`, `tests/components/**/*.test.tsx` | All tests pass (no more todos in these files) |

**Backend dependency:** None. Pure frontend work.

### F2: Data Layer (Services + Hooks)

| Scope | Files | Done = |
|-------|-------|--------|
| Implement ApiClient with real fetch, error normalization, query param building | `src/services/api-client.ts` | All endpoint methods construct correct URLs, handle errors |
| Implement WsManager with real WebSocket, reconnect, typed dispatch | `src/services/ws-manager.ts` | Connect/disconnect/reconnect works, messages dispatched to subscribers |
| Implement all query hooks with correct TanStack Query options | `src/hooks/queries/*.ts` (7 files) | Hooks call correct ApiClient methods, use correct query keys + stale times |
| Implement use-live-events.ts (WS → query cache bridge) | `src/hooks/use-live-events.ts` | WS events update TanStack Query cache correctly |
| Implement URL state hooks | `src/hooks/use-url-*.ts` (3 files) | URL params sync with component state |
| Implement all service + hook + store tests | `tests/services/*.test.ts`, `tests/hooks/**/*.test.ts`, `tests/stores/*.test.ts` | All tests pass |

**Backend dependency:** Backend team must have REST + WS endpoints available (or in progress).

### F3: Run List Page

| Scope | Files | Done = |
|-------|-------|--------|
| RunTable with TanStack Table (sortable columns, row selection) | `src/pages/run-list/run-table.tsx` | Table renders run data, sortable |
| RunRow with status badge, reality/behavior/fidelity badges, score bar, event count | `src/pages/run-list/run-row.tsx` | Each row shows all run metadata |
| RunFilters (status, preset, tag search) — filters update URL | `src/pages/run-list/run-filters.tsx` | Filters work, URL updates, page is shareable |
| CompareToolbar (selection checkboxes, "Compare N runs" button) | `src/pages/run-list/compare-toolbar.tsx` | Can select 2-3 runs, navigate to /compare |
| Page index wires data loading via useRuns + QueryGuard | `src/pages/run-list/index.tsx` | Page loads data from API, shows loading/error/empty states |
| Page-level tests | `tests/pages/run-list.test.tsx` | Tests pass |

**Backend dependency:** `GET /api/runs` must be working.

### F4: Run Report Page

| Scope | Files | Done = |
|-------|-------|--------|
| Tab router (URL-driven tab selection) | `src/pages/run-report/index.tsx` | 6 tabs, URL ?tab= param, correct tab loads |
| **Overview tab:** MetricCards (score, tickets, budget, events), MissionResult, KeyEvents, AgentSummaryCards | `tabs/overview-tab.tsx` | Overview renders summary with data from API |
| **Scorecard tab:** ScorecardGrid matrix, score cells with color gradient, FidelityBasis card | `tabs/scorecard-tab.tsx` | Scorecard renders per-agent scores, click-to-detail |
| **Events tab:** EventTable (TanStack Table), EventFilters, EventDetail panel, CausalChain links | `tabs/events-tab.tsx` | Events paginated, filterable, causal links navigate |
| **Entities tab:** EntityList, EntityCard, EntityDetail with state history timeline | `tabs/entities-tab.tsx` | Entities browsable by type, state history visible |
| **Gaps tab:** GapTable, GapSummary (response distribution chart) | `tabs/gaps-tab.tsx` | Gaps listed with response classification |
| **Conditions tab:** Per-dimension cards with encounter details | `tabs/conditions-tab.tsx` | 5 dimensions shown with agent responses |
| ReportHeader (run metadata, export button) | `report-header.tsx` | Header shows run config |
| Page-level tests | `tests/pages/run-report.test.tsx` | Tests pass |

**Backend dependency:** `GET /api/runs/:id`, `/events`, `/scorecard`, `/entities`, `/gaps`, `/actors/:id` must be working.

### F5: Live Console Page

| Scope | Files | Done = |
|-------|-------|--------|
| 3-panel layout (event feed | context view | inspector) | `src/pages/live-console/index.tsx` | Panels render, resizable |
| EventFeed (scrolling list, auto-scroll, filters) | `event-feed.tsx`, `event-feed-item.tsx` | Events stream in real-time via WebSocket |
| ContextView (changes based on selection: run status / event detail / entity / agent) | `context-view.tsx` | Clicking event shows detail, clicking entity shows entity |
| Inspector (agent profile, budget, permissions) | `inspector.tsx` | Right panel shows selected agent info |
| RunHeaderBar (tick counter, budget bars, status) | `run-header-bar.tsx` | Live metrics update from WS |
| TransitionBanner (run complete → link to report) | `transition-banner.tsx` | Banner appears on run_complete WS message |
| useLiveEvents integration (WS → feed + cache) | hook wiring | New events appear in feed, run status updates |
| Page-level tests | `tests/pages/live-console.test.tsx` | Tests pass |

**Backend dependency:** `WS /ws/runs/:id/live` must be working.

### F6: Compare Page

| Scope | Files | Done = |
|-------|-------|--------|
| ComparisonGrid (2-way or 3-way layout, adapts to run count) | `comparison-grid.tsx` | Grid renders N columns |
| MetricDiffTable (scorecard diff with winner highlighting) | `metric-diff-table.tsx` | Metrics compared, best highlighted |
| DivergenceTimeline (key divergence points) | `divergence-timeline.tsx` | Divergence points expandable |
| EntityDiff (entity state comparison) | `entity-diff.tsx` | Entity diffs shown |
| ExportButton (PNG export via html2canvas) | `export-button.tsx` | Click generates downloadable PNG |
| Page index (reads run IDs from URL, fetches comparison) | `index.tsx` | Page works with ?runs=id1,id2 |
| Page-level tests | `tests/pages/compare.test.tsx` | Tests pass |

**Backend dependency:** `GET /api/compare?runs=id1,id2,id3` must be working.

### F7: Polish + Integration

| Scope | Done = |
|-------|--------|
| Loading skeletons that match final layout shape (not spinners) | Every loading state looks like the content it replaces |
| Keyboard shortcuts (Escape to deselect, arrows in event feed, Cmd+K search) | Shortcuts work |
| Responsive (works on laptop screens, not just ultrawide) | Usable at 1280px width |
| Performance: virtualized lists for event feed (1000+ events) | Event feed smooth at 1000 events |
| Error states: API errors, WS disconnection, timeout | All error cases handled gracefully |
| Real backend integration testing | All pages work against live backend |
| `terrarium dashboard` CLI command starts both frontend + backend | Single command launches both |

---

## Backend API Contract (for backend team)

### REST Endpoints (request-response, for completed/historical data + backfill)

**Priority 1 — Required for F3 (Run List):**

```
GET /api/runs
  Purpose: List all runs (snapshot, not real-time)
  Query: ?status=running&preset=messy&limit=50&offset=0&sort=created_at:desc&tag=exp-1
  Response: PaginatedResponse<Run>
```

**Priority 2 — Required for F4 (Run Report) + F5 backfill:**

```
GET /api/runs/:id
  Purpose: Run metadata (also used as backfill on Live Console mount)
  Response: Run

GET /api/runs/:id/events
  Purpose: Event history (primary for Report, backfill for Live Console)
  Query: ?actor_id=X&service_id=Y&event_type=Z&outcome=success&tick_from=0&tick_to=100&limit=100&offset=0
  Response: PaginatedResponse<WorldEvent>

GET /api/runs/:id/events/:event_id
  Purpose: Single event with causal chain (on-demand detail view)
  Response: WorldEvent (with causal_parent_ids and causal_child_ids populated)

GET /api/runs/:id/scorecard
  Purpose: Governance scorecard (completed runs only)
  Response: GovernanceScorecard[] (one per actor + one with actor_id="collective")

GET /api/runs/:id/entities
  Purpose: Entity browser (primary for Report, backfill for Live Console)
  Query: ?entity_type=ticket&service_id=tickets&limit=50&offset=0
  Response: PaginatedResponse<Entity>

GET /api/runs/:id/entities/:entity_id
  Purpose: Entity detail with state history (on-demand)
  Response: Entity (with state_history: StateChange[])

GET /api/runs/:id/gaps
  Purpose: Capability gap log (completed runs only)
  Response: CapabilityGap[]

GET /api/runs/:id/actors/:actor_id
  Purpose: Actor profile with action history (on-demand)
  Response: AgentSummary (with action_history: WorldEvent[])
```

**Priority 3 — Required for F6 (Compare):**

```
GET /api/compare
  Purpose: Side-by-side comparison of completed runs
  Query: ?runs=id1,id2,id3  (comma-separated, 2-3 IDs)
  Response: RunComparison
```

### WebSocket Endpoint (push, for live/running data)

**Priority 2 — Required for F5 (Live Console):**

```
WS /ws/runs/:id/live
  Purpose: Real-time stream of all state changes during an active run
  Direction: Server → Client only (no client messages needed in v1)

  Message types (JSON, discriminated by "type" field):

  { type: "event", data: WorldEvent }
    — Sent when a new event occurs (agent action, animator event, side effect)

  { type: "status", data: { status: "running"|"paused", tick: number, world_time: string } }
    — Sent on every tick or status change

  { type: "budget_update", data: { actor_id: string, remaining: number, total: number, budget_type: string } }
    — Sent when any actor's budget changes

  { type: "entity_update", data: EntityUpdate }
    — Sent when entity state changes due to a committed action
    — EntityUpdate: { entity_id, entity_type, service_id, fields, changed_fields, caused_by_event }

  { type: "run_complete", data: Run }
    — Sent once when the run finishes (final Run object with completed status)
```

**NOTE:** The existing `/api/v1/events/stream` WebSocket is NOT sufficient — it streams all events globally without run scoping or typed message envelopes. The dashboard needs the new `/ws/runs/:id/live` endpoint with the discriminated union above.

### Full TypeScript Type Definitions

All types are defined in `terrarium-dashboard/src/types/domain.ts`. The backend team should use this as the response contract. Key types:

- **Run** — 20 fields including status, world_name, reality_preset, behavior, fidelity, mode, seed, conditions (5 dimensions), services[]
- **WorldEvent** — 18 fields including event_type (14 possible values), outcome (7 values), policy_hit, budget_delta, causal links, fidelity tier
- **Entity** — entity_id, entity_type, service_id, fields (dynamic), state_history[]
- **GovernanceScorecard** — actor_id, overall_score, scores[] (name, value 0-1, formula, violations), fidelity_basis, policy_hits
- **CapabilityGap** — requested_tool, response (hallucinated/adapted/escalated/skipped), next_actions
- **RunComparison** — metrics[] (name → per-run values), divergence_points (tick + per-run decisions/consequences)

---

## Data Flow Architecture: WebSocket vs REST

### Principle

**Live (running run):** WebSocket pushes all state changes. REST only for initial backfill.
**Historical (completed run):** REST only. Data is immutable.

### Data Flow by Page

| Page | Primary Source | Backfill | Notes |
|------|---------------|----------|-------|
| **Run List** | REST (`GET /api/runs`) | — | Poll every 10s for active run status updates (v1). WS optional for v2. |
| **Live Console** | WebSocket (`/ws/runs/:id/live`) | REST (`GET /api/runs/:id/events` on mount) | WS pushes events, status, budget, entity updates, run complete. REST fetches events that happened before WS connected. |
| **Run Report** | REST only | — | Completed run data is immutable. All endpoints are GET. |
| **Compare** | REST only | — | Static comparison of completed runs. |

### WebSocket Message Types (updated)

```typescript
// src/types/ws.ts — needs entity_update added
type WsMessage =
  | { type: 'event';         data: WorldEvent }        // New event occurred
  | { type: 'status';        data: RunStatusUpdate }    // Tick/status change
  | { type: 'budget_update'; data: BudgetUpdate }       // Actor budget changed
  | { type: 'entity_update'; data: EntityUpdate }       // Entity state changed (NEW)
  | { type: 'run_complete';  data: Run }                // Run finished

interface EntityUpdate {
  entity_id: string;
  entity_type: string;
  service_id: string;
  fields: Record<string, unknown>;     // Current state after update
  changed_fields: string[];             // Which fields changed
  caused_by_event: string;              // Event that triggered this update
}
```

### Live Console Dual-Source Pattern

```
Page Mount:
  1. REST: GET /api/runs/:id → run metadata
  2. REST: GET /api/runs/:id/events?limit=100 → backfill existing events
  3. WS: connect /ws/runs/:id/live → start receiving new events
  4. Merge: WS events append to the backfill list (dedup by event_id)

During Run:
  - WS pushes events → appended to event feed + query cache
  - WS pushes status → updates run detail cache
  - WS pushes budget → updates actor budget displays
  - WS pushes entity_update → updates entity cache (for inspector panel)

Run Complete:
  - WS pushes run_complete → banner appears, WS disconnects
  - User clicks "View Report" → navigates to Run Report (REST-only page)
```

---

## Stub Cleanup Before F1

The following stub changes are needed to align the architecture before implementation begins. These are part of the F1 deliverables.

### 1. Add `entity_update` to WsMessage types

**File:** `src/types/ws.ts`
**Change:** Add `WsEntityUpdateMessage` interface and include it in the `WsMessage` union.

### 2. Update use-live-events.ts stub

**File:** `src/hooks/use-live-events.ts`
**Change:** Add `entity_update` case to the switch statement (stub comment for now). Add backfill logic comment showing the dual-source merge pattern.

### 3. Add EntityUpdate type to domain.ts

**File:** `src/types/domain.ts`
**Change:** Add `EntityUpdate` interface (entity_id, entity_type, service_id, fields, changed_fields, caused_by_event).

### 4. Update WS mock for tests

**File:** `tests/mocks/ws-mock.ts`
**Change:** Ensure MockWsServer supports the new message type.

### 5. Update MSW handlers comment

**File:** `tests/mocks/handlers.ts`
**Change:** Add comment clarifying which endpoints are for backfill (Live Console) vs. primary source (Run Report).

---

## Deliverables for This Session

1. **This plan file** — phasing, API contract, data flow architecture, done criteria
2. **`terrarium-dashboard/IMPLEMENTATION_STATUS.md`** — tracking file modeled after backend
3. **`internal_docs/plans/frontend-implementation-master.md`** — saved copy of this plan

Next step: Plan F1 specifically (Design System + Shared Components + stub cleanup).
