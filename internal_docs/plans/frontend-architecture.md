# Terrarium Dashboard — Frontend Architecture & Scaffolding Plan

## Context

Terrarium needs a production-grade web dashboard for observing AI agent simulations. The frontend spec (`internal_docs/terrarium-frontend-spec.md`) defines 4 pages (Run List, Live Console, Run Report, Compare), a dark industrial aesthetic, and a React 19 + TypeScript + Tailwind + shadcn/ui tech stack.

**This plan covers Phase 1 only:** architect the frontend, set up the project, establish all patterns, and create stubs/placeholders for every module. No feature implementation yet — that will be a separate plan.

The backend API endpoints do not exist yet — the user will build those separately. This plan documents the exact API contract the frontend expects.

**Monorepo layout:** `terrarium-dashboard/` lives at repo root alongside `terrarium/` (Python backend), `tests/`, `pyproject.toml`, etc. Same Git repo, separate build systems. The `terrarium dashboard` CLI command will start both backend API server and frontend dev/static server.

---

## Goal

Create `terrarium-dashboard/` at repo root with:
1. Complete project scaffolding (Vite, TS, Tailwind, shadcn/ui, ESLint, Vitest)
2. Layered architecture with enforced dependency rules
3. All type definitions mirroring backend domain models
4. Singleton services (API client, WebSocket manager) with DI via React context
5. TanStack Query setup with query key factory and all query hook stubs
6. Zustand stores (minimal — compare selection, layout prefs)
7. Router with all 4 pages as placeholder components
8. Shared component library stubs (domain, layout, feedback)
9. Page-level component stubs (one folder per page, one file per sub-component)
10. CSS variables for the dark industrial theme
11. API contract document embedded as `src/types/` TypeScript interfaces
12. Comprehensive test stubs and harness (Vitest + Testing Library + MSW)
13. Save this plan to `internal_docs/plans/`

---

## Architecture: 7-Layer Dependency Model

```
Layer 0: types/, constants/     — Pure TS. Zero runtime. Zero project imports.
Layer 1: lib/                   — Pure functions. No React, no side effects.
Layer 2: services/              — Singleton classes (ApiClient, WsManager). No React.
Layer 3: hooks/, stores/        — React hooks + Zustand. Bridge services→components.
Layer 4: providers/             — React context providers. Compose services for DI.
Layer 5: components/            — Shared UI: ui/ (shadcn), domain/, layout/, feedback/
Layer 6: pages/                 — Page components. Never import from other pages.
```

**Rule:** Layer N imports only from layers 0..N-1. Pages never import from other pages. Enforced by ESLint `import/no-restricted-paths`.

---

## Future Scalability: Multi-Agent Live View

The architecture is designed to scale to a real-time multi-agent monitoring view (agents roaming, live positions, parallel action streams) without restructuring:

- **WsManager** is a singleton with typed message dispatch via discriminated unions. Adding new message types (`agent_position`, `agent_state_change`, `agent_handoff`) is extending the `WsMessage` union in `types/ws.ts` — no changes to the manager itself.
- **Query cache bridge** (`use-live-events.ts`) pattern generalizes to any real-time data source. A future `use-agent-tracking.ts` hook would follow the same pattern: subscribe to WS, update TanStack Query cache.
- **Services layer** is extensible via DI. A future `AgentTrackingService` (managing agent position streams, heartbeats, reconnection per agent) is added to `services/`, provided via `ServicesProvider`, consumed via a new `useAgentTracking()` hook. Zero changes to existing services.
- **Pages never import from other pages.** A new `pages/agent-monitor/` folder is just a new route — no changes to Live Console, Run Report, or Compare.
- **Domain components** in `components/domain/` are the shared vocabulary. New components (`agent-avatar.tsx`, `agent-path.tsx`, `agent-heatmap.tsx`) extend the vocabulary without touching existing components.
- **Zustand stores** are scoped. A future `agent-tracking-store.ts` manages real-time agent positions independently of `compare-store.ts` or `layout-store.ts`.

The key constraint: **never put page-specific logic in shared layers.** If the multi-agent view needs a custom data structure (e.g., spatial index for agent positions), it goes in `lib/` as a pure utility, not embedded in a page component.

---

## Project Structure

```
terrarium-dashboard/
├── index.html
├── package.json
├── tsconfig.json
├── tsconfig.node.json
├── vite.config.ts
├── vitest.config.ts                    # Vitest configuration
├── tailwind.config.ts
├── postcss.config.js
├── components.json                     # shadcn/ui config
├── eslint.config.js
├── .env.example                        # VITE_API_BASE_URL=http://localhost:8200
│
├── public/
│   └── favicon.svg
│
├── src/
│   ├── main.tsx                        # Entry: mounts providers + router
│   ├── app.tsx                         # Router definition (4 routes)
│   ├── vite-env.d.ts
│   │
│   ├── types/                          # [L0] All TypeScript interfaces
│   │   ├── index.ts                    # Re-exports
│   │   ├── domain.ts                   # Run, WorldEvent, Entity, AgentSummary, Score, etc.
│   │   ├── api.ts                      # PaginatedResponse, filter params, ApiError
│   │   ├── ws.ts                       # WsMessage discriminated union
│   │   └── ui.ts                       # TabId, FilterState, OutcomeType, etc.
│   │
│   ├── constants/                      # [L0] String constants, enums
│   │   ├── index.ts
│   │   ├── routes.ts                   # Route path constants
│   │   ├── query-keys.ts              # TanStack Query key factory
│   │   └── defaults.ts                # Page sizes, stale times, debounce ms
│   │
│   ├── lib/                            # [L1] Pure utility functions
│   │   ├── index.ts
│   │   ├── formatters.ts              # Dates, durations, currency, scores
│   │   ├── classifiers.ts            # EventType→icon/color, enforcement→color, etc.
│   │   ├── score-utils.ts            # Grade computation, normalization
│   │   ├── color-utils.ts            # Score→Tailwind color class
│   │   ├── url-state.ts              # URL search param serialize/deserialize
│   │   ├── causal-graph.ts           # Flat events → tree structure
│   │   ├── comparison.ts             # Diff helpers for Compare page
│   │   └── export.ts                 # html2canvas PNG capture
│   │
│   ├── services/                       # [L2] Singletons, no React
│   │   ├── index.ts
│   │   ├── api-client.ts             # Fetch-based HTTP client, all endpoint methods
│   │   └── ws-manager.ts             # WebSocket lifecycle, reconnect, typed dispatch
│   │
│   ├── hooks/                          # [L3] React hooks
│   │   ├── index.ts
│   │   ├── queries/                   # TanStack Query hooks (one per domain)
│   │   │   ├── use-runs.ts
│   │   │   ├── use-events.ts
│   │   │   ├── use-scorecard.ts
│   │   │   ├── use-entities.ts
│   │   │   ├── use-gaps.ts
│   │   │   ├── use-actors.ts
│   │   │   └── use-compare.ts
│   │   ├── use-websocket.ts           # Hook wrapping WsManager for a run
│   │   ├── use-live-events.ts         # WS→TanStack Query cache bridge
│   │   ├── use-url-state.ts           # Generic URL-backed state
│   │   ├── use-url-filters.ts         # Event/entity filter state in URL
│   │   ├── use-url-tabs.ts            # Tab selection in URL
│   │   └── use-keyboard.ts            # Keyboard shortcuts
│   │
│   ├── stores/                         # [L3] Zustand (minimal)
│   │   ├── index.ts
│   │   ├── compare-store.ts           # Selected run IDs for comparison
│   │   └── layout-store.ts            # Sidebar collapsed, panel sizes
│   │
│   ├── providers/                      # [L4] React context
│   │   ├── index.ts
│   │   ├── app-providers.tsx          # Wraps all providers in correct order
│   │   ├── query-provider.tsx         # TanStack QueryClientProvider
│   │   └── services-provider.tsx      # ApiClient + WsManager context
│   │
│   ├── components/                     # [L5] Shared UI
│   │   ├── ui/                        # shadcn primitives (generated by CLI)
│   │   │   └── (button, badge, card, table, tabs, dialog, tooltip,
│   │   │       skeleton, scroll-area, separator, select, input, etc.)
│   │   │
│   │   ├── domain/                    # Terrarium-specific shared components
│   │   │   ├── score-bar.tsx
│   │   │   ├── score-grade.tsx
│   │   │   ├── outcome-icon.tsx
│   │   │   ├── run-status-badge.tsx
│   │   │   ├── actor-badge.tsx
│   │   │   ├── service-badge.tsx
│   │   │   ├── fidelity-indicator.tsx
│   │   │   ├── timestamp-cell.tsx
│   │   │   ├── event-type-badge.tsx
│   │   │   ├── entity-link.tsx
│   │   │   ├── enforcement-badge.tsx
│   │   │   ├── json-viewer.tsx
│   │   │   └── causal-chain.tsx
│   │   │
│   │   ├── layout/                    # Structural
│   │   │   ├── app-shell.tsx          # Sidebar + main content
│   │   │   ├── sidebar.tsx
│   │   │   ├── page-header.tsx
│   │   │   ├── panel-layout.tsx       # Resizable multi-panel
│   │   │   └── status-bar.tsx         # Connection status, active run
│   │   │
│   │   └── feedback/                  # Loading, error, empty
│   │       ├── page-loading.tsx
│   │       ├── section-loading.tsx
│   │       ├── error-boundary.tsx
│   │       ├── error-display.tsx
│   │       ├── empty-state.tsx
│   │       └── query-guard.tsx        # Wraps query: loading→error→empty→data
│   │
│   ├── pages/                          # [L6] One folder per page
│   │   ├── run-list/
│   │   │   ├── index.tsx
│   │   │   ├── run-table.tsx
│   │   │   ├── run-row.tsx
│   │   │   ├── run-filters.tsx
│   │   │   └── compare-toolbar.tsx
│   │   │
│   │   ├── live-console/
│   │   │   ├── index.tsx
│   │   │   ├── event-feed.tsx
│   │   │   ├── event-feed-item.tsx
│   │   │   ├── context-view.tsx
│   │   │   ├── inspector.tsx
│   │   │   ├── run-header-bar.tsx
│   │   │   └── transition-banner.tsx
│   │   │
│   │   ├── run-report/
│   │   │   ├── index.tsx
│   │   │   ├── report-header.tsx
│   │   │   └── tabs/
│   │   │       ├── overview-tab.tsx
│   │   │       ├── scorecard-tab.tsx
│   │   │       ├── events-tab.tsx
│   │   │       ├── entities-tab.tsx
│   │   │       ├── gaps-tab.tsx
│   │   │       └── conditions-tab.tsx
│   │   │
│   │   └── compare/
│   │       ├── index.tsx
│   │       ├── comparison-grid.tsx
│   │       ├── metric-diff-table.tsx
│   │       ├── divergence-timeline.tsx
│   │       ├── entity-diff.tsx
│   │       └── export-button.tsx
│   │
│   └── styles/
│       └── globals.css                 # Tailwind directives + CSS custom properties
│
└── tests/
    ├── setup.ts                        # Vitest global setup (jsdom, Testing Library matchers)
    ├── mocks/
    │   ├── handlers.ts                 # MSW request handlers for all API endpoints
    │   ├── server.ts                   # MSW setupServer instance
    │   ├── data/                       # Mock data factories
    │   │   ├── runs.ts                 # createMockRun(), createMockRunList()
    │   │   ├── events.ts              # createMockWorldEvent(), createMockEventList()
    │   │   ├── entities.ts            # createMockEntity()
    │   │   ├── scorecard.ts           # createMockScorecard()
    │   │   ├── gaps.ts                # createMockCapabilityGap()
    │   │   └── comparison.ts          # createMockRunComparison()
    │   └── ws-mock.ts                  # WebSocket mock for testing live features
    │
    ├── lib/                            # Unit tests for pure utility functions
    │   ├── formatters.test.ts
    │   ├── classifiers.test.ts
    │   ├── score-utils.test.ts
    │   ├── color-utils.test.ts
    │   ├── url-state.test.ts
    │   ├── causal-graph.test.ts
    │   └── comparison.test.ts
    │
    ├── services/                       # Service tests (API client + WS manager)
    │   ├── api-client.test.ts          # Tests: request construction, error handling, response parsing
    │   └── ws-manager.test.ts          # Tests: connect/disconnect, reconnect, message dispatch
    │
    ├── hooks/                          # Hook tests using renderHook + MSW
    │   ├── queries/
    │   │   ├── use-runs.test.ts
    │   │   ├── use-events.test.ts
    │   │   └── use-scorecard.test.ts
    │   ├── use-websocket.test.ts
    │   ├── use-live-events.test.ts
    │   └── use-url-state.test.ts
    │
    ├── stores/                         # Zustand store tests
    │   ├── compare-store.test.ts
    │   └── layout-store.test.ts
    │
    ├── components/                     # Component tests using Testing Library
    │   ├── domain/
    │   │   ├── score-bar.test.tsx
    │   │   ├── outcome-icon.test.tsx
    │   │   ├── run-status-badge.test.tsx
    │   │   ├── timestamp-cell.test.tsx
    │   │   └── entity-link.test.tsx
    │   └── feedback/
    │       ├── query-guard.test.tsx
    │       └── error-boundary.test.tsx
    │
    └── pages/                          # Page-level smoke tests (renders without crash)
        ├── run-list.test.tsx
        ├── live-console.test.tsx
        ├── run-report.test.tsx
        └── compare.test.tsx
```

---

## Key Patterns (implemented as stubs)

### API Client — Singleton via Context

```typescript
// services/api-client.ts — module-level singleton
class ApiClient {
  private baseUrl: string;
  constructor(baseUrl: string) { ... }
  // One method per endpoint, returns Promise<T>
  getRuns(params?: RunListParams): Promise<PaginatedResponse<Run>>
  getRun(id: string): Promise<Run>
  getRunEvents(runId: string, params?: EventFilterParams): Promise<PaginatedResponse<WorldEvent>>
  // ... (all endpoints)
}
```

Provided to React tree via `ServicesProvider` context. Consumed in hooks via `useApiClient()`.

### Query Key Factory — Single source of truth

```typescript
// constants/query-keys.ts
export const queryKeys = {
  runs: {
    all: ['runs'] as const,
    list: (params?: RunListParams) => ['runs', 'list', params] as const,
    detail: (id: string) => ['runs', id] as const,
    events: (id: string, params?: EventFilterParams) => ['runs', id, 'events', params] as const,
    // ...
  },
  compare: {
    detail: (ids: string[]) => ['compare', ...ids.sort()] as const,
  },
} as const;
```

### WebSocket → Query Cache Bridge

`use-live-events.ts` subscribes to `WsManager`, and on each message:
- `type: "event"` → appends to `queryKeys.runs.events(runId)` cache
- `type: "status"` → patches `queryKeys.runs.detail(runId)` cache
- `type: "budget_update"` → patches actor data
- `type: "run_complete"` → invalidates all run queries (triggers REST re-fetch)

This means Live Console and Run Report use the same query cache. No seam when transitioning.

### QueryGuard — Systematic loading/error/empty

```tsx
<QueryGuard query={runQuery} loadingFallback={<PageLoading />}>
  {(run) => <RunReportContent run={run} />}
</QueryGuard>
```

Every data-loading component uses this. No ad-hoc `if (isLoading)` checks.

### URL State — Filters, tabs, selections

Filters, tab selection, and selected entities are URL search params (shareable). Managed via `use-url-state.ts` / `use-url-tabs.ts` / `use-url-filters.ts` hooks that sync `React Router` search params with component state.

### Zustand — Only for cross-page + layout state

- `compare-store.ts` — run IDs selected for comparison (persists across Run List → Compare navigation)
- `layout-store.ts` — sidebar collapsed, panel sizes (persisted to localStorage)

Everything else is URL state or query cache.

---

## Test Harness

### Stack
- **Vitest** — test runner (native ESM, Vite-compatible)
- **@testing-library/react** — component rendering + queries
- **@testing-library/jest-dom** — DOM assertion matchers
- **MSW (Mock Service Worker)** — API mocking at the network level
- **@testing-library/user-event** — user interaction simulation

### Test Categories

| Category | Location | What it tests | Pattern |
|----------|----------|--------------|---------|
| **Lib unit** | `tests/lib/*.test.ts` | Pure functions (formatters, classifiers, score-utils) | Input→output assertions. No mocking. |
| **Service unit** | `tests/services/*.test.ts` | ApiClient request construction, error handling; WsManager connect/reconnect/dispatch | MSW for HTTP, mock WebSocket for WS |
| **Hook unit** | `tests/hooks/**/*.test.ts` | Query hooks return correct data; WS hook manages lifecycle; URL state syncs | `renderHook` + MSW + QueryClient wrapper |
| **Store unit** | `tests/stores/*.test.ts` | Zustand store state transitions | Direct store method calls, assert state |
| **Component render** | `tests/components/**/*.test.tsx` | Domain components render correct output for given props | `render()` + assertions on DOM |
| **Page smoke** | `tests/pages/*.test.tsx` | Pages render without crash, show expected placeholder content | `render()` wrapped in providers + router |

### Mock Data Factories

Every test file uses factory functions from `tests/mocks/data/` instead of inline mock objects. This ensures:
- Mock data matches TypeScript interfaces (type-checked)
- Changing a domain type updates one factory, not every test file
- Factories accept partial overrides: `createMockRun({ status: 'failed' })`

### MSW Handlers

`tests/mocks/handlers.ts` defines MSW handlers for every REST endpoint. Each handler returns factory-generated data. Tests that need custom responses override individual handlers per test.

### WebSocket Mock

`tests/mocks/ws-mock.ts` provides a `MockWsServer` class that simulates the backend WebSocket:
- `send(message: WsMessage)` — push a typed message to all connected clients
- `getConnections()` — inspect active connections
- Used by `use-live-events.test.ts` and `use-websocket.test.ts`

---

## Backend API Contract

The frontend needs these endpoints. **None exist yet** — the user will build them.

### REST Endpoints

| Method | Path | Query Params | Response Type |
|--------|------|-------------|--------------|
| GET | `/api/runs` | `?status=running&preset=messy&limit=50&offset=0&sort=created_at:desc` | `PaginatedResponse<Run>` |
| GET | `/api/runs/:id` | — | `Run` |
| GET | `/api/runs/:id/events` | `?actor_id=X&service_id=Y&event_type=Z&tick_from=0&tick_to=100&limit=100&offset=0` | `PaginatedResponse<WorldEvent>` |
| GET | `/api/runs/:id/events/:event_id` | — | `WorldEvent` (with causal chain populated in `causes`) |
| GET | `/api/runs/:id/scorecard` | — | `GovernanceScorecard[]` (one per actor + "collective") |
| GET | `/api/runs/:id/entities` | `?entity_type=ticket&service_id=tickets&limit=50&offset=0` | `PaginatedResponse<Entity>` |
| GET | `/api/runs/:id/entities/:entity_id` | — | `Entity` (with `state_history: StateChange[]`) |
| GET | `/api/runs/:id/gaps` | — | `CapabilityGap[]` |
| GET | `/api/runs/:id/actors/:actor_id` | — | `AgentSummary` (with `action_history: WorldEvent[]`) |
| GET | `/api/compare` | `?runs=id1,id2,id3` | `RunComparison` |

### WebSocket

| Path | Direction | Message Types |
|------|-----------|---------------|
| `WS /ws/runs/:id/live` | Server→Client | `event`, `status`, `budget_update`, `run_complete` |

**Note:** The existing backend WebSocket (`/api/v1/events/stream`) streams raw events without run scoping or typed message envelopes. The dashboard needs a **new** run-scoped endpoint with the typed `WsMessage` discriminated union defined in `src/types/ws.ts`.

### Full type definitions

All request/response TypeScript interfaces are defined in `src/types/domain.ts` and `src/types/api.ts`, mirroring:
- `terrarium/core/types.py` — EntityId, ActorId, FidelityTier, enums, value objects
- `terrarium/core/events.py` — Event hierarchy (WorldEvent, PolicyBlockEvent, BudgetEvent, etc.)
- `terrarium/core/context.py` — ResponseProposal, StepResult
- `terrarium/engines/reporter/scorecard.py` — GovernanceScorecard shape

---

## CSS Theme (Dark Industrial)

```css
/* Key tokens in globals.css */
--bg-base: hsl(220, 16%, 8%);       /* deepest background */
--bg-surface: hsl(220, 16%, 11%);    /* cards, panels */
--bg-elevated: hsl(220, 16%, 13%);   /* popovers */
--text-primary: hsl(210, 20%, 90%);  /* main content */
--text-secondary: hsl(210, 10%, 55%);/* labels */

/* Semantic: color = meaning */
--score-excellent: green (90-100)
--score-good: teal (75-89)
--score-fair: amber (60-74)
--score-poor: red (0-59)

/* Event types */
--event-success: green    --event-denied: red
--event-policy: amber     --event-world: blue
--event-system: gray

/* Fonts */
--font-ui: 'Geist Sans', system-ui
--font-mono: 'JetBrains Mono', monospace  /* ALL data uses mono */
```

---

## Implementation Steps

### Step 0: Save plan
- Copy this plan to `internal_docs/plans/frontend-architecture.md` for reference

### Step 1: Initialize project
- `npm create vite@latest terrarium-dashboard -- --template react-ts`
- Install dependencies: react 19, react-router v7, @tanstack/react-query v5, @tanstack/react-table v8, zustand v5, recharts v2, framer-motion v11, lucide-react, date-fns v4, shiki
- Install dev deps: tailwindcss v4, postcss, autoprefixer, @types/*, eslint, prettier
- Install test deps: vitest, @testing-library/react, @testing-library/jest-dom, @testing-library/user-event, msw, jsdom
- Configure `vite.config.ts` with proxy (`/api` → `localhost:8200`, `/ws` → ws proxy)
- Configure `vitest.config.ts` with jsdom environment, setup file, path aliases
- Configure `tsconfig.json` with path alias `@/` → `src/`
- Initialize Tailwind, configure `globals.css` with CSS variables
- Initialize shadcn/ui (`npx shadcn@latest init`), add core primitives (button, badge, card, table, tabs, dialog, tooltip, skeleton, scroll-area, select, input, separator)
- Configure ESLint with `import/no-restricted-paths` for layer enforcement
- Add npm scripts: `dev`, `build`, `preview`, `lint`, `typecheck`, `test`, `test:watch`, `test:coverage`

### Step 2: Create types/ and constants/
- `types/domain.ts` — all domain interfaces (Run, WorldEvent, Entity, AgentSummary, GovernanceScorecard, Score, FidelityBasis, PolicyHit, CapabilityGap, RunComparison, ComparisonMetric, DivergencePoint, WorldConditions, ServiceSummary, StateChange, FidelityMetadata)
- `types/api.ts` — PaginatedResponse<T>, RunListParams, EventFilterParams, EntityFilterParams, ApiError
- `types/ws.ts` — WsMessage discriminated union (WsEventMessage | WsStatusMessage | WsBudgetUpdateMessage | WsRunCompleteMessage)
- `types/ui.ts` — TabId, OutcomeType, EventCategory UI enums
- `constants/routes.ts` — route path constants
- `constants/query-keys.ts` — full query key factory
- `constants/defaults.ts` — STALE_TIME_*, PAGE_SIZE_*, DEBOUNCE_MS_*

### Step 3: Create lib/ utilities + their tests
- All files with exported function signatures + placeholder implementations (return sensible defaults)
- `formatters.ts` — formatRelativeTime, formatDuration, formatCurrency, formatScore, formatPercentage
- `classifiers.ts` — eventTypeToIcon, eventTypeToColor, enforcementToColor, gapResponseToIcon, runStatusToColor, outcomeToIcon
- `score-utils.ts` — computeGrade, normalizeScore, scoreToGradeLabel
- `color-utils.ts` — scoreToColorClass, interpolateScoreColor
- `url-state.ts` — serializeFilters, deserializeFilters, serializeParams
- `causal-graph.ts` — buildCausalTree from flat event list
- `comparison.ts` — computeMetricDiff, findBestValue
- `export.ts` — captureElementAsPng
- **Tests:** Create stub test files for each lib module (`tests/lib/*.test.ts`) with `describe` blocks and `it.todo()` for each function

### Step 4: Create services/ + their tests
- `api-client.ts` — ApiClient class with all endpoint methods as stubs. Internal `request<T>()` helper with fetch, error normalization, JSON parsing.
- `ws-manager.ts` — WsManager class with connect(runId), disconnect(), subscribe(handler), getStatus(). Reconnection logic with exponential backoff. Typed message parsing.
- **Tests:** `tests/services/api-client.test.ts` — stub tests for request construction, error mapping, each endpoint method
- **Tests:** `tests/services/ws-manager.test.ts` — stub tests for connect/disconnect, reconnect backoff, message dispatch, subscription cleanup

### Step 5: Create test infrastructure
- `tests/setup.ts` — Vitest setup: import `@testing-library/jest-dom`, configure MSW server start/stop
- `tests/mocks/server.ts` — MSW `setupServer()` with default handlers
- `tests/mocks/handlers.ts` — MSW handlers for all 10 REST endpoints, returning factory data
- `tests/mocks/ws-mock.ts` — MockWsServer class
- `tests/mocks/data/*.ts` — Mock data factories for all domain types (Run, WorldEvent, Entity, GovernanceScorecard, CapabilityGap, RunComparison)

### Step 6: Create hooks/ and stores/ + their tests
- `hooks/queries/*.ts` — one file per domain. Each exports hooks using the query key factory and api client context. Stub bodies with correct TanStack Query options.
- `hooks/use-websocket.ts` — wraps WsManager, manages connect/disconnect on mount/unmount
- `hooks/use-live-events.ts` — subscribes to WS, updates query cache
- `hooks/use-url-state.ts`, `use-url-filters.ts`, `use-url-tabs.ts` — URL state management
- `hooks/use-keyboard.ts` — keyboard shortcut registration
- `stores/compare-store.ts` — selectedRunIds, toggleRun, clearSelection
- `stores/layout-store.ts` — sidebarCollapsed, panelSizes (with localStorage persist)
- **Tests:** `tests/hooks/queries/use-runs.test.ts`, `use-events.test.ts`, `use-scorecard.test.ts` — stub hook tests with `renderHook`
- **Tests:** `tests/hooks/use-websocket.test.ts`, `use-live-events.test.ts`, `use-url-state.test.ts` — stub tests
- **Tests:** `tests/stores/compare-store.test.ts`, `layout-store.test.ts` — stub Zustand tests

### Step 7: Create providers/
- `query-provider.tsx` — QueryClientProvider with default options (staleTime, retry)
- `services-provider.tsx` — creates ApiClient + WsManager, provides via context, exports useApiClient() + useWsManager()
- `app-providers.tsx` — composes QueryProvider + ServicesProvider in correct order

### Step 8: Create component stubs + their tests
- **components/ui/** — installed via `npx shadcn@latest add` (not hand-written)
- **components/domain/** — each file exports a stub component that renders a placeholder `<div>` with the component name and accepts typed props
- **components/layout/** — AppShell renders sidebar + `<Outlet />`, sidebar has nav links to all 4 routes
- **components/feedback/** — QueryGuard, ErrorBoundary, PageLoading, SectionLoading, EmptyState, ErrorDisplay as functional stubs
- **Tests:** `tests/components/domain/score-bar.test.tsx`, `outcome-icon.test.tsx`, `run-status-badge.test.tsx`, `timestamp-cell.test.tsx`, `entity-link.test.tsx` — stub render tests
- **Tests:** `tests/components/feedback/query-guard.test.tsx`, `error-boundary.test.tsx` — stub tests

### Step 9: Create page stubs + smoke tests
- Each page folder gets an `index.tsx` that renders a `<PageHeader>` + placeholder content
- Sub-components in each page folder are stub files exporting empty components with correct prop types
- Router in `app.tsx` wires all 4 routes with ErrorBoundary per route
- **Tests:** `tests/pages/run-list.test.tsx`, `live-console.test.tsx`, `run-report.test.tsx`, `compare.test.tsx` — smoke tests (renders without crash, shows page title)

### Step 10: Wire main.tsx + verify
- Import AppProviders, RouterProvider
- Mount to `#root`
- Verify the app boots, renders sidebar, navigates between 4 placeholder pages

---

## Verification

After scaffolding is complete:
1. `cd terrarium-dashboard && npm install` — clean install, no errors
2. `npm run dev` — Vite starts, opens browser
3. Navigate to `/` — sees Run List placeholder with sidebar
4. Navigate to `/runs/test-1/live` — sees Live Console placeholder
5. Navigate to `/runs/test-1` — sees Run Report placeholder with tab navigation
6. Navigate to `/compare?runs=a,b` — sees Compare placeholder
7. `npm run lint` — passes (no ESLint errors, layer enforcement works)
8. `npm run typecheck` — passes (all types resolve, no `any` leaks)
9. `npm run build` — Vite production build succeeds
10. `npm run test` — all test stubs discovered, `it.todo()` tests show as pending, no failures

---

## What This Plan Does NOT Cover (future plans)

- Implementing actual component rendering (real UI, not placeholders)
- Implementing backend API endpoints
- Real data fetching (mocks or fixtures for dev mode)
- Implementing test assertions (stubs have `it.todo()` only)
- Production deployment / `terrarium dashboard` CLI integration
- Multi-agent live tracking page (architecture supports it — see Scalability section)
