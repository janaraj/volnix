# Terrarium Dashboard — Implementation Status

> Single source of truth for frontend implementation progress.
> Updated after every implementation session.

## Current Focus

**Phase:** F1 — Design System + Shared Components
**Status:** Not started. Scaffolding (F0) complete.

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
| **Domain types** | `src/types/domain.ts` | ✅ done | F0 | Run, WorldEvent, Entity, AgentSummary, GovernanceScorecard, CapabilityGap, RunComparison, WorldConditions (5 dimensions), 28+ interfaces |
| **API types** | `src/types/api.ts` | ✅ done | F0 | PaginatedResponse, filter params, ApiError |
| **WS types** | `src/types/ws.ts` | ✅ done | F0 | WsMessage union (5 message types including entity_update) |
| **UI types** | `src/types/ui.ts` | ✅ done | F0 | ReportTabId, OutcomeCategory, ConnectionStatus, FilterState |
| **Route constants** | `src/constants/routes.ts` | ✅ done | F0 | ROUTES + path builder functions |
| **Query keys** | `src/constants/query-keys.ts` | ✅ done | F0 | Full factory for all 11 query keys |
| **Defaults** | `src/constants/defaults.ts` | ✅ done | F0 | Stale times, page sizes, debounce, WS reconnect |

### Layer 1: Lib Utilities

| Module | Path | Status | Phase | Notes |
|--------|------|--------|-------|-------|
| **Formatters** | `src/lib/formatters.ts` | 📋 stub | F1 | formatRelativeTime, formatDuration, formatCurrency, formatScore, formatPercentage, formatTick, truncateId |
| **Classifiers** | `src/lib/classifiers.ts` | 📋 stub | F1 | eventTypeToColorClass, outcomeToColorClass, enforcementToColorClass, gapResponseToLabel, runStatusToColorClass, scoreToGradeLabel |
| **Score utils** | `src/lib/score-utils.ts` | 📋 stub | F1 | computeGrade, normalizeScore |
| **Color utils** | `src/lib/color-utils.ts` | 📋 stub | F1 | scoreToColorClass, interpolateScoreColor |
| **URL state** | `src/lib/url-state.ts` | 📋 stub | F1 | serializeParams, deserializeParams |
| **Causal graph** | `src/lib/causal-graph.ts` | 📋 stub | F1 | buildCausalTree |
| **Comparison** | `src/lib/comparison.ts` | 📋 stub | F1 | findBestValue, computeMetricDelta |
| **Export** | `src/lib/export.ts` | 📋 stub | F1 | captureElementAsPng |

### Layer 2: Services

| Module | Path | Status | Phase | Notes |
|--------|------|--------|-------|-------|
| **API client** | `src/services/api-client.ts` | 📋 stub | F2 | Fetch-based, 10 endpoint methods, error normalization |
| **WS manager** | `src/services/ws-manager.ts` | 📋 stub | F2 | WebSocket lifecycle, reconnect, typed dispatch |

### Layer 3: Hooks & Stores

| Module | Path | Status | Phase | Notes |
|--------|------|--------|-------|-------|
| **use-runs** | `src/hooks/queries/use-runs.ts` | 📋 stub | F2 | useRuns, useRun |
| **use-events** | `src/hooks/queries/use-events.ts` | 📋 stub | F2 | useRunEvents, useRunEvent |
| **use-scorecard** | `src/hooks/queries/use-scorecard.ts` | 📋 stub | F2 | useScorecard |
| **use-entities** | `src/hooks/queries/use-entities.ts` | 📋 stub | F2 | useEntities, useEntity |
| **use-gaps** | `src/hooks/queries/use-gaps.ts` | 📋 stub | F2 | useCapabilityGaps |
| **use-actors** | `src/hooks/queries/use-actors.ts` | 📋 stub | F2 | useActor |
| **use-compare** | `src/hooks/queries/use-compare.ts` | 📋 stub | F2 | useComparison |
| **use-websocket** | `src/hooks/use-websocket.ts` | 📋 stub | F2 | useWebSocket |
| **use-live-events** | `src/hooks/use-live-events.ts` | 📋 stub | F2 | WS→cache bridge + backfill merge |
| **use-url-state** | `src/hooks/use-url-state.ts` | 📋 stub | F1 | Generic URL-backed state |
| **use-url-filters** | `src/hooks/use-url-filters.ts` | 📋 stub | F1 | Event/entity filter state |
| **use-url-tabs** | `src/hooks/use-url-tabs.ts` | 📋 stub | F1 | Tab selection in URL |
| **use-keyboard** | `src/hooks/use-keyboard.ts` | 📋 stub | F7 | Keyboard shortcuts |
| **compare-store** | `src/stores/compare-store.ts` | 📋 stub | F2 | Selected run IDs |
| **layout-store** | `src/stores/layout-store.ts` | 📋 stub | F2 | Sidebar, panel sizes |

### Layer 4: Providers

| Module | Path | Status | Phase | Notes |
|--------|------|--------|-------|-------|
| **App providers** | `src/providers/app-providers.tsx` | ✅ done | F0 | Composes Query + Services |
| **Query provider** | `src/providers/query-provider.tsx` | ✅ done | F0 | TanStack QueryClientProvider |
| **Services provider** | `src/providers/services-provider.tsx` | ✅ done | F0 | ApiClient + WsManager context |

### Layer 5: Components

| Module | Path | Status | Phase | Notes |
|--------|------|--------|-------|-------|
| **ScoreBar** | `src/components/domain/score-bar.tsx` | 📋 stub | F1 | Horizontal score bar |
| **ScoreGrade** | `src/components/domain/score-grade.tsx` | 📋 stub | F1 | Letter grade badge |
| **OutcomeIcon** | `src/components/domain/outcome-icon.tsx` | 📋 stub | F1 | Event outcome icon |
| **RunStatusBadge** | `src/components/domain/run-status-badge.tsx` | 📋 stub | F1 | Run status indicator |
| **ActorBadge** | `src/components/domain/actor-badge.tsx` | 📋 stub | F1 | Actor ID display |
| **ServiceBadge** | `src/components/domain/service-badge.tsx` | 📋 stub | F1 | Service + tier indicator |
| **FidelityIndicator** | `src/components/domain/fidelity-indicator.tsx` | 📋 stub | F1 | Tier 1/2 display |
| **TimestampCell** | `src/components/domain/timestamp-cell.tsx` | 📋 stub | F1 | Relative + absolute time |
| **EventTypeBadge** | `src/components/domain/event-type-badge.tsx` | 📋 stub | F1 | Event type badge |
| **EntityLink** | `src/components/domain/entity-link.tsx` | 📋 stub | F1 | Clickable entity navigation |
| **EnforcementBadge** | `src/components/domain/enforcement-badge.tsx` | 📋 stub | F1 | Policy enforcement type |
| **JsonViewer** | `src/components/domain/json-viewer.tsx` | 📋 stub | F1 | Syntax-highlighted JSON |
| **CausalChain** | `src/components/domain/causal-chain.tsx` | 📋 stub | F1 | Causal event chain |
| **QueryGuard** | `src/components/feedback/query-guard.tsx` | 📋 stub | F1 | Loading/error/empty guard |
| **ErrorBoundary** | `src/components/feedback/error-boundary.tsx` | 📋 stub | F1 | React error boundary |
| **PageLoading** | `src/components/feedback/page-loading.tsx` | 📋 stub | F1 | Page skeleton |
| **SectionLoading** | `src/components/feedback/section-loading.tsx` | 📋 stub | F1 | Section skeleton |
| **ErrorDisplay** | `src/components/feedback/error-display.tsx` | 📋 stub | F1 | Error card + retry |
| **EmptyState** | `src/components/feedback/empty-state.tsx` | 📋 stub | F1 | No data state |
| **AppShell** | `src/components/layout/app-shell.tsx` | 📋 stub | F1 | Sidebar + content |
| **Sidebar** | `src/components/layout/sidebar.tsx` | 📋 stub | F1 | Navigation |
| **PageHeader** | `src/components/layout/page-header.tsx` | 📋 stub | F1 | Title + breadcrumb |
| **PanelLayout** | `src/components/layout/panel-layout.tsx` | 📋 stub | F1 | 3-panel resizable |
| **StatusBar** | `src/components/layout/status-bar.tsx` | 📋 stub | F1 | Connection status |

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

---

## Phase Roadmap

| Phase | Name | Depends On | Status |
|-------|------|-----------|--------|
| **F0** | Scaffolding | — | ✅ Done |
| **F1** | Design System + Shared Components | F0 | 🔲 Next |
| **F2** | Data Layer (Services + Hooks) | F1, backend APIs | 🔲 |
| **F3** | Run List Page | F2, `GET /api/runs` | 🔲 |
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
