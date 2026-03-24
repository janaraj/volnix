# Terrarium Dashboard — Implementation Status

> Single source of truth for frontend implementation progress.
> Updated after every implementation session.

## Current Focus

**Phase:** F7 — Polish + Integration (next)
**Status:** F0-F6 done. ALL 4 pages implemented. 269 tests pass. 0 todos remaining.

---

## Module Status

### Legend
- ✅ `done` — Fully implemented, tests passing
- 🔧 `in-progress` — Being implemented in current phase
- 📦 `partial` — Some functionality implemented, rest is stub
- 📋 `stub` — Skeleton only (signatures, no logic)
- 🔲 `todo` — Not yet created

### Layer 0: Types & Constants

| Module | Path | Status | Phase | Notes |
|--------|------|--------|-------|-------|
| **Domain types** | `src/types/domain.ts` | ✅ done | F0 | Run, WorldEvent, Entity, AgentSummary, GovernanceScorecard, CapabilityGap, RunComparison, WorldConditions (5 dimensions), EntityUpdate, 30+ interfaces |
| **API types** | `src/types/api.ts` | ✅ done | F0 | PaginatedResponse, filter params, ApiError |
| **WS types** | `src/types/ws.ts` | ✅ done | F0 | WsMessage union (5 message types including entity_update) |
| **UI types** | `src/types/ui.ts` | ✅ done | F0 | ReportTabId, OutcomeCategory, ConnectionStatus, FilterState |
| **Route constants** | `src/constants/routes.ts` | ✅ done | F0 | ROUTES + path builder functions |
| **Query keys** | `src/constants/query-keys.ts` | ✅ done | F0 | Full factory for all 11 query keys |
| **Defaults** | `src/constants/defaults.ts` | ✅ done | F0 | Stale times, page sizes, debounce, WS reconnect |

### Layer 1: Lib Utilities

| Module | Path | Status | Phase | Notes |
|--------|------|--------|-------|-------|
| **cn** | `src/lib/cn.ts` | ✅ done | F1 | clsx wrapper for conditional classes |
| **Formatters** | `src/lib/formatters.ts` | ✅ done | F1 | date-fns relative time, Intl currency, duration math. 22 tests |
| **Classifiers** | `src/lib/classifiers.ts` | ✅ done | F1 | 6 functions, all data-driven Record lookups. 33 tests |
| **Score utils** | `src/lib/score-utils.ts` | ✅ done | F1 | computeGrade with theme tokens, normalizeScore. 10 tests |
| **Color utils** | `src/lib/color-utils.ts` | ✅ done | F1 | Dark-theme score classes, HSL interpolation. 11 tests |
| **URL state** | `src/lib/url-state.ts` | ✅ done | F0 | serializeParams, deserializeParams. 7 tests |
| **Causal graph** | `src/lib/causal-graph.ts` | ✅ done | F1 | Recursive tree builder with cycle detection. 6 tests |
| **Comparison** | `src/lib/comparison.ts` | ✅ done | F0 | findBestValue, computeMetricDelta. 8 tests |
| **Export** | `src/lib/export.ts` | ✅ done | F0 | captureElementAsPng with dynamic html2canvas import |

### Layer 2: Services

| Module | Path | Status | Phase | Notes |
|--------|------|--------|-------|-------|
| **API client** | `src/services/api-client.ts` | ✅ done | F0+F2 | 11 fetch methods, error normalization, query param building. 10 tests |
| **WS manager** | `src/services/ws-manager.ts` | ✅ done | F0+F2 | Connect, disconnect, reconnect (exp backoff), subscribe, subscribeStatus. 12 tests |

### Layer 3: Hooks & Stores

| Module | Path | Status | Phase | Notes |
|--------|------|--------|-------|-------|
| **use-runs** | `src/hooks/queries/use-runs.ts` | ✅ done | F0 | useRuns, useRun. 5 tests |
| **use-events** | `src/hooks/queries/use-events.ts` | ✅ done | F0 | useRunEvents, useRunEvent. 4 tests |
| **use-scorecard** | `src/hooks/queries/use-scorecard.ts` | ✅ done | F0 | useScorecard. 2 tests |
| **use-entities** | `src/hooks/queries/use-entities.ts` | ✅ done | F0 | useEntities, useEntity |
| **use-gaps** | `src/hooks/queries/use-gaps.ts` | ✅ done | F0 | useCapabilityGaps |
| **use-actors** | `src/hooks/queries/use-actors.ts` | ✅ done | F0 | useActor |
| **use-compare** | `src/hooks/queries/use-compare.ts` | ✅ done | F0 | useComparison |
| **use-websocket** | `src/hooks/use-websocket.ts` | ✅ done | F2 | Event-driven status via subscribeStatus. 4 tests |
| **use-live-events** | `src/hooks/use-live-events.ts` | ✅ done | F2 | 5 WS→cache handlers (event dedup, status patch, budget, entity, run_complete). 5 tests |
| **use-url-state** | `src/hooks/use-url-state.ts` | ✅ done | F0 | Generic URL-backed state. 4 tests |
| **use-url-filters** | `src/hooks/use-url-filters.ts` | ✅ done | F0 | Event/entity filter state |
| **use-url-tabs** | `src/hooks/use-url-tabs.ts` | ✅ done | F0 | Tab selection in URL |
| **use-keyboard** | `src/hooks/use-keyboard.ts` | 📋 stub | F7 | Keyboard shortcuts |
| **use-copy-to-clipboard** | `src/hooks/use-copy-to-clipboard.ts` | ✅ done | F1 | navigator.clipboard + visual feedback |
| **compare-store** | `src/stores/compare-store.ts` | ✅ done | F0 | Selected run IDs. 5 tests |
| **layout-store** | `src/stores/layout-store.ts` | ✅ done | F0 | Sidebar, panel sizes. 4 tests |

### Layer 4: Providers

| Module | Path | Status | Phase | Notes |
|--------|------|--------|-------|-------|
| **App providers** | `src/providers/app-providers.tsx` | ✅ done | F0 | Composes Query + Services |
| **Query provider** | `src/providers/query-provider.tsx` | ✅ done | F0 | TanStack QueryClientProvider |
| **Services provider** | `src/providers/services-provider.tsx` | ✅ done | F0 | ApiClient + WsManager context |

### Layer 5: Components

| Module | Path | Status | Phase | Notes |
|--------|------|--------|-------|-------|
| **ScoreBar** | `src/components/domain/score-bar.tsx` | ✅ done | F1 | interpolateScoreColor + formatScore. 4 tests |
| **ScoreGrade** | `src/components/domain/score-grade.tsx` | ✅ done | F1 | computeGrade with theme tokens |
| **OutcomeIcon** | `src/components/domain/outcome-icon.tsx` | ✅ done | F1 | Lucide icons via Record, outcomeToColorClass. 4 tests |
| **RunStatusBadge** | `src/components/domain/run-status-badge.tsx` | ✅ done | F1 | runStatusToColorClass, pulse animation. 5 tests |
| **ActorBadge** | `src/components/domain/actor-badge.tsx` | ✅ done | F1 | Lucide User/Check, truncateId, copy-on-click |
| **ServiceBadge** | `src/components/domain/service-badge.tsx` | ✅ done | F1 | Lucide Server, tier tokens |
| **FidelityIndicator** | `src/components/domain/fidelity-indicator.tsx` | ✅ done | F1 | Lucide ShieldCheck/Shield |
| **TimestampCell** | `src/components/domain/timestamp-cell.tsx` | ✅ done | F1 | formatRelativeTime + full ISO hover. 2 tests |
| **EventTypeBadge** | `src/components/domain/event-type-badge.tsx` | ✅ done | F1 | eventTypeToColorClass |
| **EntityLink** | `src/components/domain/entity-link.tsx` | ✅ done | F1 | truncateId + copy button. 4 tests |
| **EnforcementBadge** | `src/components/domain/enforcement-badge.tsx` | ✅ done | F1 | Lucide icons via Record, enforcementToColorClass |
| **JsonViewer** | `src/components/domain/json-viewer.tsx` | ✅ done | F1 | Regex syntax highlighting, copy button |
| **CausalChain** | `src/components/domain/causal-chain.tsx` | ✅ done | F1 | Visual chain with dots/lines, Lucide GitBranch |
| **QueryGuard** | `src/components/feedback/query-guard.tsx` | ✅ done | F0 | Loading/error/empty guard. 5 tests |
| **ErrorBoundary** | `src/components/feedback/error-boundary.tsx` | ✅ done | F0 | React error boundary. 3 tests |
| **PageLoading** | `src/components/feedback/page-loading.tsx` | ✅ done | F1 | Lucide Loader2 + animate-spin |
| **SectionLoading** | `src/components/feedback/section-loading.tsx` | ✅ done | F0 | animate-pulse skeletons |
| **ErrorDisplay** | `src/components/feedback/error-display.tsx` | ✅ done | F1 | Lucide AlertTriangle, styled retry |
| **EmptyState** | `src/components/feedback/empty-state.tsx` | ✅ done | F1 | Configurable Lucide icon prop |
| **AppShell** | `src/components/layout/app-shell.tsx` | ✅ done | F1 | Sidebar + Outlet + StatusBar |
| **Sidebar** | `src/components/layout/sidebar.tsx` | ✅ done | F1 | Lucide icons, accent border active, collapsed state |
| **PageHeader** | `src/components/layout/page-header.tsx` | ✅ done | F0 | Title + breadcrumb + actions |
| **PanelLayout** | `src/components/layout/panel-layout.tsx` | ✅ done | F1 | Explicit separators, min-w-0 |
| **StatusBar** | `src/components/layout/status-bar.tsx` | ✅ done | F1 | ConnectionStatus prop, 4 states via Record |

### Layer 6: Pages

| Module | Path | Status | Phase | Notes |
|--------|------|--------|-------|-------|
| **Run List** | `src/pages/run-list/` | ✅ done | F3 | RunCard, RunFilters, RunTable, CompareToolbar, page orchestrator. 16 tests |
| **Live Console** | `src/pages/live-console/` | ✅ done | F5 | All 7 files: shell, header, feed (4 filters + auto-scroll), context (3 modes), inspector, banner. 23 tests. |
| **Run Report** | `src/pages/run-report/` | ✅ done | F4 | All 8 files: shell, header, 6 tabs. TanStack Table in Events. 34 tests. |
| **Compare** | `src/pages/compare/` | ✅ done | F6 | MetricDiffTable, DivergenceTimeline, ScoreComparisonBars, ExportButton, page orchestrator with branding. 12 tests. |

### Test Infrastructure

| Module | Path | Status | Phase | Notes |
|--------|------|--------|-------|-------|
| **Vitest setup** | `tests/setup.ts` | ✅ done | F0 | jest-dom + cleanup |
| **MSW handlers** | `tests/mocks/handlers.ts` | ✅ done | F0 | 10 REST endpoint handlers |
| **MSW server** | `tests/mocks/server.ts` | ✅ done | F0 | setupServer instance |
| **WS mock** | `tests/mocks/ws-mock.ts` | ✅ done | F0 | MockWsServer class |
| **Mock factories** | `tests/mocks/data/*.ts` | ✅ done | F0 | 6 factory files |
| **MockWebSocket** | `tests/helpers/mock-websocket.ts` | ✅ done | F2 | Shared WebSocket mock for 3 test files |

---

## Phase Roadmap

| Phase | Name | Depends On | Status |
|-------|------|-----------|--------|
| **F0** | Scaffolding | — | ✅ Done |
| **F1** | Design System + Shared Components | F0 | ✅ Done |
| **F2** | Data Layer (Services + Hooks) | F1 | ✅ Done |
| **F3** | Run List Page | F2, `GET /api/v1/runs` | ✅ Done |
| **F4a** | Run Report Shell + Summary Tabs | F3 | ✅ Done |
| **F4b** | Run Report Data Tabs (Events, Entities, Gaps) | F4a | ✅ Done |
| **F5a** | Live Console Feed + Header + Banner | F4 | ✅ Done |
| **F5b** | Live Console Context + Inspector | F5a | ✅ Done |
| **F6** | Compare Page | F2, `GET /api/v1/compare` | ✅ Done |
| **F7** | Polish + Integration | F3-F6, full backend | 🔲 Next |

---

## Session Log

### Session 2026-03-22 — F0: Scaffolding
- **Created:** 95 source files, 28 test files (166 todos), full project config
- **Stack:** React 19, TypeScript 5.9, Vite 8, Tailwind 4, TanStack Query 5, Zustand 5, Vitest 4
- **Architecture:** 7-layer dependency model (types → constants → lib → services → hooks/stores → providers → components → pages)
- **Verification:** typecheck clean, lint 0 errors, build succeeds, 166 todo tests discovered
- **Key decisions:**
  - @/ path alias for all imports
  - No mock data in app — real backend APIs only
  - WebSocket for live data, REST for historical + backfill
  - entity_update WS message type for real-time entity state changes
  - Dual-source pattern: REST backfill + WS stream for Live Console

### Session 2026-03-23 — F1: Design System + Shared Components
- **Implemented:** 8 lib utilities (formatters with date-fns, data-driven classifiers, HSL color interpolation, recursive causal graph builder), 14 domain components (all emojis→Lucide icons, all colors→classifiers), 6 feedback components (spinner, icons, QueryGuard), 5 layout components (Lucide sidebar, ConnectionStatus StatusBar, panel separators)
- **Created:** `src/lib/cn.ts` (clsx wrapper), `src/hooks/use-copy-to-clipboard.ts` (clipboard hook)
- **Tests:** 124 tests pass (97 lib + 27 component), 0 todos in F1 scope
- **Verification:** typecheck 0 errors, lint 0 errors, build succeeds
- **Key decisions:**
  - No shadcn/ui in F1 — pure Tailwind + custom components
  - Inter font (not Geist Sans — requires Vercel package)
  - All classifier mappings are Record<string, string> lookups — zero if/switch heuristics
  - Copy-on-click via useCopyToClipboard hook + Check icon feedback

### Session 2026-03-23 — F2: Data Layer (Services + Hooks)
- **Implemented:** WsManager subscribeStatus (event-driven status, replaced 500ms polling), useLiveEvents 5 cache handlers (event dedup via setQueriesData prefix match, status patch, budget patch, entity upsert, run_complete invalidation), useWebSocket event-driven
- **Created:** `tests/helpers/mock-websocket.ts` (shared mock for 3 test files)
- **Tests:** 180 tests pass (124 F1 + 56 F2), 8 remaining todos (4 page smoke tests — F3-F6)
- **Verification:** typecheck 0 errors, lint 0 errors, build succeeds
- **Key decisions:**
  - Subscribe to status listeners BEFORE calling connect (avoids React lint warning about setState in effect)
  - setQueriesData with prefix key match for event dedup across filtered + unfiltered caches
  - Removed Zustand persist middleware from layout-store (jsdom incompatibility, persistence is runtime concern to add in F7)
  - ApiClient uses string concatenation for URL building (not new URL) for jsdom compatibility

### Session 2026-03-23 — F3: Run List Page
- **Implemented:** RunCard (multi-line card with status badge, badges, score bar, stats, actions), RunFilters (status/preset dropdowns + debounced tag search), RunTable (card list wired to compare store), CompareToolbar (floating bottom bar with selection count, clear, compare navigation), Page index (orchestrator with URL filters, conditional 10s polling for running runs, QueryGuard, empty states)
- **Created:** `src/hooks/use-debounce.ts` (generic debounce hook for filter input)
- **Updated:** All ApiClient paths → `/api/v1/` prefix (aligned with backend convention), all MSW handlers updated, added `governance_score?: number | null` to Run type, enriched mock data with varied runs
- **Tests:** 198 tests pass (182 F1+F2 + 16 F3), 6 remaining todos (F4-F6 page stubs)
- **Verification:** typecheck 0 errors, lint 0 errors, build succeeds
- **Key decisions:**
  - Card layout (not data table) — matches spec's multi-line card design, TanStack Table reserved for F4 Events tab
  - Conditional polling: refetchInterval function checks for running runs → 10s when active, false when all done
  - Module-level FILTER_DEFAULTS constant prevents useUrlState re-render loops
  - RunCard exported from run-row.tsx (keeps filename, better export name)
  - Empty state distinguishes between "no runs at all" and "no runs match filters"

### Session 2026-03-23 — F4a: Run Report Shell + Summary Tabs
- **Implemented:** ReportHeader (tag name, world name, badges, governance score display), page shell (tab router with 6 tabs, URL-backed active tab via useUrlTabs, QueryGuard wrapping), OverviewTab (4 metric cards + key events filtered by type + agent summary from scorecard), ScorecardTab (HTML matrix grid with per-dimension rows/per-actor columns, scoreToColorClass cells, fidelity basis card with service list + confidence), ConditionsTab (5 dimension cards from DIMENSION_CONFIG Record, numeric bars + text badges)
- **Tests:** 17 tests (shell loading/header/tabs + tab switching + overview metrics + scorecard dimensions/confidence/hint/collective + conditions cards/header + error handling)
- **Audit fixes applied:**
  - Conditions tab: added Reality/Behavior header, full dimension titles ("Information Quality" not "Information")
  - Scorecard tab: added "Click any score" hint text
  - Mock data: scorecard returns 3 entries (agent-alpha, agent-beta, collective)
- **Deferred:** MissionResult component (backend dependency), scorecard cell click→modal (deferred to F7)
- **Verification:** 215 tests pass, typecheck 0 errors, lint 0 errors

### Session 2026-03-23 — F4b: Run Report Data Tabs
- **Implemented:** EventsTab (TanStack Table v8 with 5 columns, URL-driven filters, pagination controls, event detail panel with JsonViewer x2 + policy section + budget impact + clickable causal links + EntityLink + FidelityIndicator), EntitiesTab (card list with type filter, entity detail panel with JsonViewer + state history timeline with dot+connector format), GapsTab (distribution summary with per-response-type icons/colors, HTML table with Event/Agent/Gap/Response columns, empty state)
- **Key spec items covered:**
  - Causal chain items are CLICKABLE (update ?event= param, not just copy)
  - Entity IDs in event detail are CLICKABLE (EntityLink navigates to entities tab)
  - Budget impact displayed (budget_delta + budget_remaining)
  - "[View causal chain →]" label text
  - FidelityIndicator on event detail
  - All filter dropdowns have aria-labels for testing
- **Fixed:** index.tsx ActiveTab now passes runId to all 3 data tabs
- **Enriched mock data:** entity now includes state_history (3 StateChange entries)
- **Tests:** 17 new tests (events: 7, entities: 5, gaps: 5). Total: 232 tests pass.
- **Verification:** typecheck 0 errors, lint 0 errors, build succeeds

### Session 2026-03-24 — F5a: Live Console Feed + Header + Banner
- **Implemented:** EventFeedItem (multi-line card with timestamp/outcome/actor/action/description, actor click with stopPropagation), EventFeed (auto-scroll via useRef + useEffect with 32px threshold, outcome + event_type filters with data-driven Records, empty state), RunHeaderBar (breadcrumb "Terrarium > tag > Live", connection status dot via STATUS_CONFIG Record, tick/agents/events stats, disabled Pause/Stop buttons), TransitionBanner (green banner "Run completed" + "View report" link), Page Index (full orchestrator with useLiveEvents for WS bridge, useRun + useRunEvents for cache reads, local useState for selection, PanelLayout wiring)
- **Typed stubs for F5b:** ContextView and Inspector accept full prop interfaces but render placeholder text
- **Tests:** 14 new tests (header: 7, feed: 4, banner: 2, error: 1). Total: 246 tests pass.
- **Verification:** typecheck 0 errors, lint 0 errors, build succeeds
- **Key decisions:**
  - Multi-line event cards per spec mockup (4-5 lines each)
  - 3 context view modes (overview + event + agent) — entity mode deferred
  - Activity Timeline sparkline deferred to F7
  - Selection state is local useState (not URL — Live Console is ephemeral)
  - Auto-scroll detection: onScroll handler checks 32px from bottom threshold

### Session 2026-03-24 — F5b: Live Console Context + Inspector
- **Implemented:** ContextView (3 modes: RunOverviewView with metric grid + services + badges, EventDetailView with JsonViewer + budget + policy + clickable causal links + FidelityIndicator, AgentDetailView with budget bars + stats), Inspector (2 modes: AgentInspector with budget bars + stats, RunInspector with metadata + services)
- **Key patterns:** CausalLink buttons call onSelectEvent (clickable navigation, not copy). Budget bars use BUDGET_LABELS Record with ScoreBar per type. MetricCard local component with hover.
- **Tests:** 7 new tests (context: overview + event detail + input/output + close + inspector: run metadata + services). Total: 255 tests pass.
- **Verification:** typecheck 0 errors, lint 0 errors, build succeeds

### Session 2026-03-24 — F6: Compare Page
- **Implemented:** MetricDiffTable (headline comparison with findBestValue winner highlighting + "✓best" labels), DivergenceTimeline (tick + description + per-run decisions rendered neutrally — NO heuristic coloring), ScoreComparisonBars (ScoreBar per run per numeric metric, filters to 0-100 range), ExportButton (captureElementAsPng with ref), Page Index (breadcrumb, "Comparing:" header, branded export area with Hexagon logo + footer, CompareContent sub-component for conditional hook)
- **Milestone:** ALL 4 pages implemented (Run List, Run Report, Live Console, Compare). **0 remaining it.todo() tests.**
- **Tests:** 12 new tests. Total: 269 tests pass across 28 test files.
- **Verification:** typecheck 0 errors, lint 0 errors, build succeeds
- **Key decisions:**
  - No heuristic coloring on divergence decisions (DivergencePoint type lacks per-run boolean)
  - Export area includes branding header (Hexagon + "Terrarium") + world info + footer ("Generated by Terrarium Dashboard")
  - entity-diff.tsx repurposed as ScoreComparisonBars (entity diff not in spec)
  - comparison-grid.tsx rendered as no-op (page index handles layout directly)

---

## Deferred Features

### Backend-Dependent (blocked on new API fields/endpoints)

| Feature | Spec Reference | What Backend Needs to Provide | Current Workaround |
|---------|---------------|-------------------------------|-------------------|
| **Events: Free-text search** | Spec line 658 ("Free-text search across action names and output content") | `search` query param on `GET /api/v1/runs/:id/events` | Search input rendered (readOnly) with tooltip "Server-side search available in a future release" |
| **Overview: Tickets Resolved metric** | Spec line 514 ("13/15 resolved") | `tickets_resolved: { count: number; total: number }` field on Run type | Shows Events/Actors/Services count instead |
| **Overview: Budget Used metric** | Spec line 515 ("$6.58 of $20 used, 67%") | `budget_summary: { used_usd: number; total_usd: number }` field on Run type | Shows generic metric cards |
| **Overview: Agent action count + budget bar** | Spec line 543-544 ("Actions: 47", "Budget: 28% remaining") | `action_count: number` + `budget_remaining_pct: number` on GovernanceScorecard or AgentSummary per-actor | Shows score + policy hits only |
| **MissionResult checklist** | Spec lines 520-525 (✓/✗ per success criterion) | `mission_criteria: Array<{ name: string; target: string; actual: string; met: boolean }>` on Run type | Not rendered (clean omission) |
| **Overview: Agent denials count** | Spec line 546 ("Denials: 1 (adapted ✓)") | `denial_count: number` + `denial_responses: string[]` on GovernanceScorecard | Not rendered |

### Frontend-Only Deferrals (no backend dependency)

| Feature | Reason | Target Phase |
|---------|--------|-------------|
| Scorecard cell → event modal | Needs Dialog/Modal component + event fetching by score dimension. Scorecard data already has `violations: string[]` event IDs. | F7 (Polish) |
| Layout persistence (localStorage) | Zustand persist middleware incompatible with jsdom in tests. Works in browser. | F7 (Polish) |
| Header breadcrumb ("Terrarium › tag › Report") | UX polish, currently shows tag + subtitle | F7 (Polish) |
| Live Console: budget bars in run overview | Spec says overview shows "budget bars" but needs per-agent budget data without N+1 fetching. Need budget summary endpoint or agent list on Run type. | Future (backend dependency) |
| Live Console: entity selection mode in ContextView | Spec lists "Entity selected" as 4th context mode. EntityLink already navigates to F4 entities tab. Inline entity detail deferred. | Future |
| Activity Timeline sparkline | Complex Recharts histogram visualization in Live Console bottom bar. | F7 (Polish) |
| Hover states on report cards | Cards are read-only display; hover states needed if cards become clickable | F7 (Polish) |
| Compare: divergence expand/collapse | Spec says "Click to expand into full event detail" — v1 shows all details inline | F7 (Polish) |
| Compare: divergence success/fail coloring | DivergencePoint type has no per-run boolean field. Decisions rendered neutrally. | Backend dependency |

---

## Backend API Endpoints

### Core APIs (agent-facing, available now)
| Method | Path | What it does |
|--------|------|-------------|
| GET | `/api/v1/health` | Health check |
| GET | `/api/v1/tools` | List available tools (from PackRegistry) |
| POST | `/api/v1/actions/{tool_name}` | Execute tool call through 7-step pipeline |
| GET | `/api/v1/entities/{entity_type}` | Query entities (with permission check) |
| WS | `/api/v1/events/stream` | WebSocket — live event streaming |

### Report APIs (dashboard-facing, available now)
| Method | Path | What it does |
|--------|------|-------------|
| GET | `/api/v1/report` | Full simulation report |
| GET | `/api/v1/report/scorecard` | Governance scorecard (per-actor + collective) |
| GET | `/api/v1/report/gaps` | Capability gap log |
| GET | `/api/v1/report/causal/{event_id}` | Causal trace for a specific event |
| GET | `/api/v1/report/challenges` | Two-direction observation |

### Dashboard APIs (to be built by backend team)
| Method | Path | What it does |
|--------|------|-------------|
| GET | `/api/v1/runs` | List all runs (paginated, filterable) |
| GET | `/api/v1/runs/:id` | Single run detail |
| GET | `/api/v1/runs/:id/events` | Run events (paginated, filterable) |
| GET | `/api/v1/runs/:id/events/:eid` | Single event with causal chain |
| GET | `/api/v1/runs/:id/entities` | Run entities (paginated) |
| GET | `/api/v1/runs/:id/entities/:eid` | Single entity with history |
| GET | `/api/v1/runs/:id/actors/:aid` | Actor detail with history |
| GET | `/api/v1/compare?runs=id1,id2` | Run comparison |
| WS | `/ws/runs/:id/live` | Run-scoped live event stream |
