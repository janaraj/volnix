# Terrarium Dashboard — Implementation Status

> Single source of truth for frontend implementation progress.
> Updated after every implementation session.

## Current Focus

**Phase:** F3 — Run List Page (next)
**Status:** F0 scaffolding done, F1 design system done, F2 data layer done. 180 tests pass.

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
| **Run List** | `src/pages/run-list/` | 📋 stub | F3 | 5 files |
| **Live Console** | `src/pages/live-console/` | 📋 stub | F5 | 7 files |
| **Run Report** | `src/pages/run-report/` | 📋 stub | F4 | 8 files (6 tabs) |
| **Compare** | `src/pages/compare/` | 📋 stub | F6 | 6 files |

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
| **F3** | Run List Page | F2, `GET /api/runs` | 🔲 Next |
| **F4** | Run Report Page | F2, 8 REST endpoints | 🔲 |
| **F5** | Live Console Page | F2, `WS /ws/runs/:id/live` | 🔲 |
| **F6** | Compare Page | F2, `GET /api/compare` | 🔲 |
| **F7** | Polish + Integration | F3-F6, full backend | 🔲 |

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
